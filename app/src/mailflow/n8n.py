"""The n8n engine: the MailFlow emails data table (n8n public API) and the Reply webhook.

The API key and the reply secret stay in this process; the browser only ever talks to the app.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from .config import Settings

log = logging.getLogger(__name__)

PAGE = 250  # the n8n API's maximum page size
ROW_CAP = 3000  # most rows read for one list; ~4.5 KB each, so ~13 MB at worst
CACHE_SECONDS = 15
STATUSES = ("open", "waiting", "done")
REPLY_RESULTS = ("sent", "cannot", "not_found")


class EngineDown(Exception):
    """n8n could not be reached, refused the app's credentials, or answered something unexpected."""


def _filter(column: str, condition: str, value) -> str:
    return json.dumps({"type": "and", "filters": [{"columnName": column, "condition": condition, "value": value}]})


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

    async def recent_rows(self, days: int = 30) -> list[dict]:
        """Rows received in the last `days` days, newest first; cached for CACHE_SECONDS."""
        if self._cache and self._clock() - self._cache[0] < CACHE_SECONDS:
            return self._cache[1]
        since = (self._now() - timedelta(days=days)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {"limit": str(PAGE), "sortBy": "received_at:desc", "filter": _filter("received_at", "gte", since)}
        rows: list[dict] = []
        while True:
            body = (await self._call("GET", self._rows_url, params=params, headers=self._headers)).json()
            rows.extend(body.get("data", []))
            cursor = body.get("nextCursor")
            if not cursor or len(rows) >= ROW_CAP:
                break
            params["cursor"] = cursor
        if len(rows) >= ROW_CAP:
            log.warning("row cap %d reached: older emails in the last %d days are not listed", ROW_CAP, days)
            rows = rows[:ROW_CAP]
        self._cache = (self._clock(), rows)
        return rows

    async def get_row(self, row_id: int) -> dict | None:
        params = {"limit": "1", "filter": _filter("id", "eq", row_id)}
        body = (await self._call("GET", self._rows_url, params=params, headers=self._headers)).json()
        data = body.get("data", [])
        return data[0] if data else None

    async def set_status(self, row_id: int, to: str) -> None:
        status = to if to in STATUSES else "open"
        payload = {"filter": json.loads(_filter("id", "eq", row_id)), "data": {"status": status}}
        await self._call("PATCH", f"{self._rows_url}/update", json=payload, headers=self._headers)
        self._cache = None

    async def send_reply(self, message_id: str, text: str) -> str:
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
        if result == "sent":
            self._cache = None
        return result
