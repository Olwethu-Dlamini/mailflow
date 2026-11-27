"""The n8n engine: the MailFlow emails data table (n8n public API) and the Reply webhook.

The API key and the reply secret stay in this process; the browser only ever talks to the app.

Reading the 30-day list from n8n takes a second or more, so the list is kept in memory: younger
than CACHE_SECONDS it is served as it is; up to STALE_SECONDS it is still served at once while a
fresh copy is read in the background (the page shows it is updating and asks again); older, or
when there is none, the request waits for n8n. Only one read runs at a time, and the list is read
once when the app starts. Emails do not change once sorted, only their status, which the app
itself sets (or n8n's Reply workflow, which the app calls).
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from .config import Settings

log = logging.getLogger(__name__)

PAGE = 250  # the n8n API's maximum page size
DAYS = 30  # the queue shows the last 30 days, like the n8n Inbox page did
ROW_CAP = 3000  # most rows read for one list; ~4.5 KB each, so ~13 MB at worst
FUTURE_SKEW = timedelta(days=1)  # a Date header up to a day ahead is a wrong clock; beyond that it is not listed
# The longest text kept per field from n8n. Senders choose these headers, and only the body is cut by
# the collectors, so the list (and the row cap above) stays bounded in memory whatever arrives.
FIELD_LIMITS = {"subject": 500, "from_name": 200, "from_address": 320, "summary": 1000, "next_step": 500, "message_id": 998, "body": 20_000}
CACHE_SECONDS = 15
STALE_SECONDS = 6 * 3600
STATUSES = ("open", "waiting", "done")
REPLY_RESULTS = ("sent", "cannot", "not_found")


class EngineDown(Exception):
    """n8n could not be reached, refused the app's credentials, or answered something unexpected."""


def _filter(column: str, condition: str, value, *more: tuple[str, str, object]) -> str:
    filters = [{"columnName": c, "condition": op, "value": v} for c, op, v in ((column, condition, value), *more)]
    return json.dumps({"type": "and", "filters": filters})


def _trim(row: dict) -> dict:
    for field, limit in FIELD_LIMITS.items():
        value = row.get(field)
        if isinstance(value, str) and len(value) > limit:
            row[field] = value[:limit]
    return row


class Engine:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
    ):
        self._settings = settings
        self._client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(10.0, read=120.0))
        self._rows_url = f"{settings.n8n_url}/api/v1/data-tables/{settings.table_id}/rows"
        self._headers = {"X-N8N-API-KEY": settings.n8n_api_key}
        self._now = now
        self._clock = clock
        self._cache: tuple[float, list[dict]] | None = None
        self._reading: asyncio.Task | None = None
        # Fields changed by the app (status, corrected labels), for a read that began before them.
        self._edits: dict[int, tuple[dict, float]] = {}

    def _age(self) -> float | None:
        return None if self._cache is None else self._clock() - self._cache[0]

    @property
    def stale(self) -> bool:
        """The list being served is older than CACHE_SECONDS (a fresh copy is on its way)."""
        age = self._age()
        return age is None or age >= CACHE_SECONDS

    @property
    def ready(self) -> bool:
        """A list can be served without waiting for n8n."""
        age = self._age()
        return age is not None and age < STALE_SECONDS

    def _read_once(self) -> asyncio.Task:
        """The read in progress, or a new one: requests that arrive meanwhile share it."""
        if self._reading is None or self._reading.done():
            self._reading = asyncio.create_task(self._read())
            self._reading.add_done_callback(_log_failure)
        return self._reading

    def warm(self) -> None:
        """Start reading the list now (at start-up), so the first visitor does not wait for n8n."""
        self._read_once()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise EngineDown(f"n8n unreachable: {error.__class__.__name__}") from error
        if response.status_code >= 400:
            raise EngineDown(f"n8n answered {response.status_code} for {method} {httpx.URL(url).path}")
        return response

    async def recent_rows(self) -> list[dict]:
        """Rows received in the last DAYS days, newest first (see the module notes on caching)."""
        age = self._age()
        if age is not None and age < CACHE_SECONDS:
            return self._cache[1]
        reading = self._read_once()
        if age is not None and age < STALE_SECONDS:
            return self._cache[1]
        return await reading

    async def _read(self) -> list[dict]:
        started = self._clock()
        now = self._now().astimezone(UTC)
        since = (now - timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Bounded on both sides: emails dated in the future by their sender would otherwise sort
        # first, never age out, and could fill the row cap ahead of every real email.
        until = (now + FUTURE_SKEW).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {"limit": str(PAGE), "sortBy": "received_at:desc", "filter": _filter("received_at", "gte", since, ("received_at", "lte", until))}
        rows: list[dict] = []
        while True:
            body = (await self._call("GET", self._rows_url, params=params, headers=self._headers)).json()
            rows.extend(_trim(row) for row in body.get("data", []))
            cursor = body.get("nextCursor")
            if not cursor or len(rows) >= ROW_CAP:
                break
            params["cursor"] = cursor
        if len(rows) >= ROW_CAP:
            log.warning("row cap %d reached: older emails in the last %d days are not listed", ROW_CAP, DAYS)
            rows = rows[:ROW_CAP]
        # A change made while this read was under way may be missing from what n8n sent.
        for row in rows:
            edit = self._edits.get(row.get("id"))
            if edit and edit[1] >= started:
                row.update(edit[0])
        self._edits = {k: v for k, v in self._edits.items() if v[1] >= started}
        self._cache = (self._clock(), rows)
        return rows

    def cached_row(self, row_id: int) -> dict | None:
        """The row from the list in memory, if there is a usable list and the row is in it."""
        if not self.ready:
            return None
        return next((row for row in self._cache[1] if row.get("id") == row_id), None)

    def _changed(self, row_id: int, data: dict) -> None:
        # The change is already in n8n; the row in memory follows, so the list need not be read
        # again, and a read already under way gets it applied too (see _read).
        for row in self._cache[1] if self._cache else []:
            if row.get("id") == row_id:
                row.update(data)
        earlier = self._edits.get(row_id, ({}, 0.0))[0]
        self._edits[row_id] = ({**earlier, **data}, self._clock())

    async def get_row(self, row_id: int) -> dict | None:
        """One row: from the cached list when it is there (it holds the whole row), else from n8n."""
        cached = self.cached_row(row_id)
        if cached is not None:
            return cached
        params = {"limit": "1", "filter": _filter("id", "eq", row_id)}
        body = (await self._call("GET", self._rows_url, params=params, headers=self._headers)).json()
        data = body.get("data", [])
        return _trim(data[0]) if data else None

    async def set_status(self, row_id: int, to: str) -> None:
        if to not in STATUSES:
            raise ValueError(f"unknown status {to!r}")
        await self.set_fields(row_id, {"status": to})

    async def set_fields(self, row_id: int, data: dict) -> None:
        """Change columns of one row in n8n (the caller checks the values)."""
        payload = {"filter": json.loads(_filter("id", "eq", row_id)), "data": data}
        await self._call("PATCH", f"{self._rows_url}/update", json=payload, headers=self._headers)
        self._changed(row_id, data)

    async def send_reply(self, row_id: int, message_id: str, text: str) -> str:
        """Ask MailFlow · Reply to answer the email in Gmail. Returns 'sent', 'cannot' or 'not_found'."""
        response = await self._call(
            "POST",
            self._settings.reply_url,
            json={"id": message_id, "text": text},
            headers={"X-MailFlow-Secret": self._settings.reply_secret},
        )
        try:
            result = response.json().get("result")
        except (ValueError, AttributeError):
            result = None
        if result not in REPLY_RESULTS:
            raise EngineDown("the Reply workflow answered something unexpected")
        if result == "sent":  # MailFlow · Reply sets the row to waiting; also when it is not in memory yet
            self._changed(row_id, {"status": "waiting"})
        return result


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning("reading the list from n8n failed: %s", task.exception())
