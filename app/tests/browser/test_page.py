"""The page as a person uses it: signing in, the queue, the keys, triage with Undo, taking an
email, correcting the AI, and email text that must stay text. Made-up emails (deck/demo_server.py):
Needs reply holds 8, P1 first and oldest first."""

import time

import conftest
import demo_server
import pytest
from conftest import sign_in

REPLY_ORDER = [
    "Gold sponsorship: contract and invoice",
    "Report about a participant",
    "URGENT: Devpost won't accept our video",
    "Interview request",
    "Can I still register?",
    "Visa invitation letter",
    "Looking for a team",
    "Can we use code we wrote before?",
]


def subjects(page):
    return page.locator("#list .item .subject").all_text_contents()


def count(page, view):
    return page.locator(f".nav-item[title^='{view}'] .n").text_content()


def wait_for_subject(page, subject):
    page.wait_for_function("(s) => document.querySelector('.detail-subject')?.textContent === s", arg=subject)


def server_email(page, row_id):
    # A function, not a string: the page's CSP forbids eval, which string predicates need.
    return page.evaluate("async (id) => (await fetch(`/api/emails/${id}`)).json()", row_id)


def wait_for_server(page, row_id, field, value, timeout=5.0):
    deadline = time.monotonic() + timeout
    while (got := server_email(page, row_id)[field]) != value:
        assert time.monotonic() < deadline, f"email {row_id}: {field} stayed {got!r}, expected {value!r}"
        time.sleep(0.05)


def test_sign_in_shows_the_queue_in_order(page):
    sign_in(page)
    assert subjects(page) == REPLY_ORDER
    assert count(page, "Needs reply") == "8"
    assert count(page, "P1") == "4"
    assert page.locator(".list-title").text_content() == "Needs reply"


def test_a_wrong_password_is_refused_with_a_message(page):
    page.goto("/login")
    page.fill("input[name=email]", "demo@mailflow.example")
    page.fill("input[name=password]", "not the password")
    page.click("button[type=submit]")
    page.wait_for_selector("#login-error:not([hidden])")
    assert "Wrong email or password" in page.locator("#login-error").text_content()
    assert page.url.endswith("/login")


def test_click_opens_an_email_and_j_k_move_through_the_list(page):
    sign_in(page)
    page.locator("#list .item").nth(1).click()
    page.wait_for_selector(".message .body:not(.loading)")
    assert page.locator(".detail-subject").text_content() == REPLY_ORDER[1]
    assert "table 14" in page.locator(".message .body").text_content()
    page.keyboard.press("j")
    wait_for_subject(page, REPLY_ORDER[2])
    page.keyboard.press("k")
    page.keyboard.press("k")
    wait_for_subject(page, REPLY_ORDER[0])
    assert page.locator("#list .item.selected .subject").text_content() == REPLY_ORDER[0]


def test_done_moves_on_and_undo_brings_the_email_back_on_the_server_too(page):
    sign_in(page)
    page.locator("#list .item").first.click()
    page.wait_for_selector(".detail-subject")
    page.keyboard.press("e")
    wait_for_subject(page, REPLY_ORDER[1])
    assert REPLY_ORDER[0] not in subjects(page)
    assert count(page, "Needs reply") == "7"
    assert count(page, "Done") == "2"
    wait_for_server(page, 3, "status", "done")
    page.wait_for_selector("#toast .toast-action")
    page.keyboard.press("z")
    wait_for_subject(page, REPLY_ORDER[0])
    wait_for_server(page, 3, "status", "open")
    # The list redraws inside a view transition, a frame or so after the email opens.
    page.wait_for_function("(n) => document.querySelectorAll('#list .item').length === n", arg=len(REPLY_ORDER))
    assert subjects(page) == REPLY_ORDER
    assert count(page, "Needs reply") == "8"


def test_undo_on_an_email_not_in_the_list_adds_no_row(page):
    sign_in(page)
    page.keyboard.press("6")  # Everything: loaded, and kept for later
    page.wait_for_function("() => document.querySelector('.list-title')?.textContent === 'Everything'")
    everything = subjects(page)
    page.locator("#list .item", has_text=REPLY_ORDER[0]).click()
    page.wait_for_selector(".message .body:not(.loading)")
    # Switch to Waiting with the email still open (as Back/Forward can): it is not in that list.
    page.evaluate("() => go({ view: 'waiting' })")
    page.wait_for_function("() => document.querySelector('.list-title')?.textContent.startsWith('Waiting')")
    page.keyboard.press("e")
    wait_for_server(page, 3, "status", "done")
    page.wait_for_selector("#toast .toast-action")
    page.keyboard.press("z")
    wait_for_server(page, 3, "status", "open")
    # Show the kept Everything list as the page has it: no fresh copy from the server may replace it.
    page.route("**/api/inbox**", lambda route: route.abort())
    page.keyboard.press("6")
    page.wait_for_function("() => document.querySelector('.list-title')?.textContent === 'Everything'")
    assert page.locator("#list .item[data-id='undefined']").count() == 0
    assert subjects(page) == everything


def test_switching_views_with_the_number_keys(page):
    sign_in(page)
    page.keyboard.press("3")
    page.wait_for_function("() => document.querySelector('.list-title')?.textContent.startsWith('P1')")
    assert len(subjects(page)) == 4
    page.keyboard.press("1")
    page.wait_for_function("() => document.querySelector('.list-title')?.textContent === 'Needs reply'")
    assert subjects(page) == REPLY_ORDER


def test_taking_an_email_puts_it_under_mine_and_in_its_activity(page):
    sign_in(page, "thabo@mailflow.example")
    page.locator("#list .item").first.click()
    page.wait_for_selector(".detail-bar button:has-text('Take')")
    page.keyboard.press("a")
    page.wait_for_selector("#activity li")
    assert "Thabo Nkosi took it" in page.locator("#activity li").first.text_content()
    assert count(page, "Mine") == "1"
    assert page.locator("#list .item").first.locator(".holder.mine").text_content() == "TNYou"
    page.keyboard.press("2")
    page.wait_for_function("() => document.querySelector('.list-title')?.textContent === 'Mine'")
    assert subjects(page) == [REPLY_ORDER[0]]


def test_correcting_the_priority_reorders_the_list_and_reaches_n8n(page):
    sign_in(page)
    page.locator("#list .item").first.click()
    page.wait_for_selector(".detail-tags select[aria-label=Priority]")
    page.select_option(".detail-tags select[aria-label=Priority]", "P3")
    page.wait_for_function("() => document.querySelector('.ai-label')?.textContent.includes('corrected by a person')")
    assert subjects(page)[-1] == REPLY_ORDER[0]  # P3 now: last in Needs reply
    wait_for_server(page, 3, "priority", "P3")
    row = next(r for r in demo_server.ROWS if r["id"] == 3)  # what the stand-in n8n now holds
    assert (row["priority"], row["sorted_by"]) == ("P3", "person")


@pytest.fixture
def html_email(monkeypatch):
    """Email 3 with markup in its subject and text, in place before the app starts."""
    row = next(r for r in conftest.ORIGINAL_ROWS if r["id"] == 3)
    monkeypatch.setitem(row, "body", '<img src=x onerror="window.pwned=1"><b>bold?</b><script>window.pwned=2</script>')
    monkeypatch.setitem(row, "subject", "<i>tags in the subject</i>")
    return row


def test_email_text_with_html_is_shown_as_text(html_email, page):
    sign_in(page)
    assert page.locator("#list .item .subject").first.text_content() == "<i>tags in the subject</i>"
    assert page.locator("#list .item .subject i").count() == 0
    page.locator("#list .item").first.click()
    page.wait_for_selector(".message .body:not(.loading)")
    body = page.locator(".message .body")
    assert body.text_content() == html_email["body"]
    assert body.locator("img, b, script").count() == 0
    assert page.evaluate("() => window.pwned") is None
