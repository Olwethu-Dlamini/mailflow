"""Browser tests: the real page in Chrome, against the app serving made-up emails (deck/demo_server.py).

Needs Chrome or Chromium: Playwright's own (`uv run playwright install chromium`) or any other,
named in MAILFLOW_CHROME. Without one these tests are skipped, and say why.
"""

import copy
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "deck"))
import demo_server

ORIGINAL_ROWS = copy.deepcopy(demo_server.ROWS)
PASSWORD = "demo-password-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# Per module: Playwright's synchronous API holds an event loop of its own while it runs, which the
# async tests that follow must not find.
@pytest.fixture(scope="module")
def chrome():
    playwright_sync = pytest.importorskip("playwright.sync_api")
    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("MAILFLOW_CHROME") or None)
        except Exception as error:  # noqa: BLE001 - any launch failure means: no usable browser here
            pytest.skip(f"no Chrome for the browser tests ({error.__class__.__name__}); set MAILFLOW_CHROME")
        yield browser
        browser.close()


@pytest.fixture
def site():
    """A fresh app with the made-up emails, on its own port; its address."""
    demo_server.ROWS[:] = copy.deepcopy(ORIGINAL_ROWS)
    reply_mailboxes = list(demo_server.web.REPLY_MAILBOXES)  # the demo changes it; other tests need it back
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(demo_server.build_app(port), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the app did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    demo_server.web.REPLY_MAILBOXES[:] = reply_mailboxes


@pytest.fixture
def page(chrome, site):
    context = chrome.new_context(base_url=site, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    context.close()
    assert errors == [], f"the page threw: {errors}"


def sign_in(page, email="demo@mailflow.example"):
    page.goto("/login")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector(".item")
