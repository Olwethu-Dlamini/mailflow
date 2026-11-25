import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from mailflow.config import Settings
from mailflow.n8n import Engine, EngineDown

SETTINGS = Settings(
    n8n_url="http://n8n:5678",
    n8n_api_key="key-123",
    table_id="HwHXJgR6FLgD8aeS",
    reply_url="http://n8n:5678/webhook/mailflow/reply",
    reply_secret="reply-secret",
    db_path=":memory:",
    cookie_secure=True,
    trusted_proxy="",
    site_origin="https://mailflow.example",
)
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
ROWS = "/api/v1/data-tables/HwHXJgR6FLgD8aeS/rows"


def engine(handler, clock=None):
    return Engine(SETTINGS, transport=httpx.MockTransport(handler), now=lambda: NOW, clock=clock or (lambda: 0.0))


async def test_recent_rows_follows_the_cursor_and_filters_30_days():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["X-N8N-API-KEY"] == "key-123"
        if request.url.params.get("cursor") == "page2":
            return httpx.Response(200, json={"data": [{"id": 3}], "nextCursor": None})
        return httpx.Response(200, json={"data": [{"id": 1}, {"id": 2}], "nextCursor": "page2"})

    rows = await engine(handler).recent_rows()
    assert [r["id"] for r in rows] == [1, 2, 3]
    first = seen[0].url.params
    assert first["limit"] == "250"
    assert first["sortBy"] == "received_at:desc"
    assert json.loads(first["filter"]) == {
        "type": "and",
        "filters": [{"columnName": "received_at", "condition": "gte", "value": "2026-10-20T12:00:00Z"}],
    }


async def test_recent_rows_stops_at_the_cap():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": [{"id": i} for i in range(250)], "nextCursor": "more"})

    rows = await engine(handler).recent_rows()
    assert len(rows) == 3000
    assert calls == 12


def counting(rows):
    """An n8n that serves `rows` and counts list reads, single-row reads and writes."""
    calls = {"list": 0, "one": 0, "write": 0}

    def handler(request):
        if request.method != "GET":
            calls["write"] += 1
            return httpx.Response(200, json={"result": "sent"} if "webhook" in request.url.path else True)
        f = json.loads(request.url.params["filter"])["filters"][0]
        if f["columnName"] == "id":
            calls["one"] += 1
            return httpx.Response(200, json={"data": [r for r in rows if r["id"] == f["value"]], "nextCursor": None})
        calls["list"] += 1
        return httpx.Response(200, json={"data": [dict(r) for r in rows], "nextCursor": None})

    return handler, calls


async def test_a_fresh_list_is_served_as_it_is_and_an_older_one_at_once_while_it_is_read_again():
    clock = [0.0]
    handler, calls = counting([{"id": 1}])
    e = engine(handler, clock=lambda: clock[0])
    await e.recent_rows()
    clock[0] = 14.0
    await e.recent_rows()
    assert calls["list"] == 1 and not e.stale
    clock[0] = 16.0
    assert [r["id"] for r in await e.recent_rows()] == [1]  # served before n8n answered
    assert e.stale
    await e._reading
    assert calls["list"] == 2 and not e.stale


async def test_a_list_older_than_six_hours_waits_for_n8n():
    clock = [0.0]
    rows = [{"id": 1}]
    handler, calls = counting(rows)
    e = engine(handler, clock=lambda: clock[0])
    await e.recent_rows()
    rows.append({"id": 2})
    clock[0] = 6 * 3600 + 1.0
    assert not e.ready
    assert [r["id"] for r in await e.recent_rows()] == [1, 2]
    assert calls["list"] == 2


async def test_requests_that_arrive_together_share_one_read():
    handler, calls = counting([{"id": 1}])
    e = engine(handler)
    e.warm()
    await asyncio.gather(e.recent_rows(), e.recent_rows(), e.recent_rows())
    assert calls["list"] == 1


async def test_a_failed_background_read_keeps_serving_the_list():
    clock = [0.0]
    down = [False]

    def handler(request):
        if down[0]:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"data": [{"id": 1}], "nextCursor": None})

    e = engine(handler, clock=lambda: clock[0])
    await e.recent_rows()
    down[0], clock[0] = True, 30.0
    assert [r["id"] for r in await e.recent_rows()] == [1]
    with pytest.raises(EngineDown):
        await e._reading
    assert [r["id"] for r in await e.recent_rows()] == [1]


async def test_changes_made_during_a_background_read_are_not_lost():
    clock = [0.0]
    release = asyncio.Event()
    reads = 0
    patches = []

    async def handler(request):
        nonlocal reads
        if request.method == "GET":
            reads += 1
            if reads == 2:
                await release.wait()  # n8n answers with what it had when the read began
            return httpx.Response(200, json={"data": [{"id": 1, "status": "open", "priority": "P3"}], "nextCursor": None})
        patches.append(json.loads(request.content)["data"])
        return httpx.Response(200, json=True)

    e = engine(handler, clock=lambda: clock[0])
    await e.recent_rows()
    clock[0] = 20.0
    await e.recent_rows()  # starts the background read, which hangs
    await asyncio.sleep(0)
    clock[0] = 21.0
    await e.set_status(1, "done")
    await e.set_fields(1, {"priority": "P1", "sorted_by": "person"})
    release.set()
    await e._reading
    row = (await e.recent_rows())[0]
    assert (row["status"], row["priority"], row["sorted_by"]) == ("done", "P1", "person")
    assert patches == [{"status": "done"}, {"priority": "P1", "sorted_by": "person"}]


async def test_an_email_in_the_cached_list_opens_without_asking_n8n():
    clock = [0.0]
    handler, calls = counting([{"id": 1, "body": "hello"}, {"id": 2, "body": "world"}])
    e = engine(handler, clock=lambda: clock[0])
    await e.recent_rows()
    assert (await e.get_row(2))["body"] == "world"
    assert calls["one"] == 0
    assert await e.get_row(99) is None  # not in the list: n8n is asked
    assert calls["one"] == 1
    clock[0] = 6 * 3600 + 1.0  # a list older than six hours is not trusted for one email
    assert (await e.get_row(1))["body"] == "hello"
    assert calls["one"] == 2


async def test_a_status_change_or_a_sent_reply_updates_the_cached_list_in_place():
    handler, calls = counting([{"id": 1, "message_id": "<a@x>", "status": "open"}, {"id": 2, "message_id": "<b@x>", "status": "open"}])
    e = engine(handler)
    await e.recent_rows()
    await e.set_status(1, "done")
    assert await e.send_reply(2, "<b@x>", "Thanks") == "sent"
    rows = await e.recent_rows()
    assert [r["status"] for r in rows] == ["done", "waiting"]
    assert (await e.get_row(1))["status"] == "done"
    assert calls == {"list": 1, "one": 0, "write": 2}


async def test_set_status_filters_by_row_id_and_refuses_an_unknown_status():
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=True)

    with pytest.raises(ValueError):
        await engine(handler).set_status(7, "bogus")
    assert sent == []
    await engine(handler).set_status(7, "waiting")
    request = sent[0]
    assert request.method == "PATCH"
    assert request.url.path == ROWS + "/update"
    assert json.loads(request.content) == {
        "filter": {"type": "and", "filters": [{"columnName": "id", "condition": "eq", "value": 7}]},
        "data": {"status": "waiting"},
    }


async def test_get_row_returns_none_when_missing():
    def handler(request):
        assert json.loads(request.url.params["filter"])["filters"][0] == {"columnName": "id", "condition": "eq", "value": 5}
        return httpx.Response(200, json={"data": [], "nextCursor": None})

    assert await engine(handler).get_row(5) is None


async def test_connection_error_and_server_errors_raise_engine_down():
    def refused(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(EngineDown):
        await engine(refused).recent_rows()

    for status in (401, 500, 502):
        with pytest.raises(EngineDown):
            await engine(lambda request, s=status: httpx.Response(s, json={})).recent_rows()


async def test_send_reply_posts_to_the_webhook_with_the_secret():
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"result": "sent"})

    assert await engine(handler).send_reply(9, "<abc@x>", "Thanks!") == "sent"
    assert str(sent[0].url) == "http://n8n:5678/webhook/mailflow/reply"
    assert sent[0].headers["X-MailFlow-Secret"] == "reply-secret"
    assert json.loads(sent[0].content) == {"id": "<abc@x>", "text": "Thanks!"}


async def test_send_reply_refused_or_odd_answer_raises_engine_down():
    with pytest.raises(EngineDown):
        await engine(lambda request: httpx.Response(403, text="Authorization data is wrong!")).send_reply(1, "<a>", "x")
    with pytest.raises(EngineDown):
        await engine(lambda request: httpx.Response(200, json={"result": "maybe"})).send_reply(1, "<a>", "x")


async def test_a_reply_sent_while_the_first_read_is_under_way_is_not_lost():
    release = asyncio.Event()

    async def handler(request):
        if "webhook" in request.url.path:
            return httpx.Response(200, json={"result": "sent"})
        await release.wait()  # the start-up read began before the reply and answers late
        return httpx.Response(200, json={"data": [{"id": 4, "status": "open"}], "nextCursor": None})

    e = engine(handler)
    e.warm()
    await asyncio.sleep(0)
    assert await e.send_reply(4, "<d@x>", "On it") == "sent"  # nothing in memory yet
    release.set()
    assert (await e.recent_rows())[0]["status"] == "waiting"
