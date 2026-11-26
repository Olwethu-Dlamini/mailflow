"""The Integrations dialog as an admin uses it, against the demo's stand-ins (deck/demo_n8n.py):
connecting a mailbox, replying from it over SMTP, and switching the AI."""

import demo_n8n
from conftest import sign_in
from demo_n8n import GOOD_KEY, GOOD_PASSWORD, FakeSmtp


def open_integrations(page):
    page.click("#user-btn")
    page.click("#open-integrations")
    page.wait_for_selector("#integrations-dialog[open] table.mailboxes")


def labels(page):
    return page.locator("table.mailboxes tbody .mailbox-name b").all_text_contents()


def test_staff_have_no_integrations(page):
    sign_in(page, "thabo@mailflow.example")
    page.click("#user-btn")
    assert page.locator("#open-integrations").is_hidden()
    assert page.locator("#open-password").is_visible()


def test_connect_a_mailbox_then_reply_from_it_over_smtp(page):
    FakeSmtp.sent.clear()
    sign_in(page)
    open_integrations(page)
    assert labels(page) == ["hello@", "press@", "sponsors@"]

    form = page.locator("#integrations-body form")
    form.locator("input[name=label]").fill("support@")
    form.locator("input[name=user]").fill("support@mailflow.example")
    form.locator("input[name=password]").fill("wrong password")
    form.locator("button[type=submit]").click()
    page.wait_for_selector("#integrations-body .error:not([hidden])")
    assert "refused the sign-in" in form.locator(".error").text_content()
    assert labels(page) == ["hello@", "press@", "sponsors@"]

    form.locator("input[name=password]").fill(GOOD_PASSWORD)
    form.locator("button[type=submit]").click()
    page.wait_for_function("() => [...document.querySelectorAll('table.mailboxes .mailbox-name b')].some((b) => b.textContent === 'support@')")
    assert page.locator("#toast").text_content().startswith("support@ is connected")
    # Straight on to its replies, with the sign-in filled in from the mailbox (Gmail is preselected).
    smtp = page.locator("#integrations-body form")
    assert smtp.locator("h3").text_content() == "Replies from support@"
    assert smtp.locator("input[name=host]").input_value() == "smtp.gmail.com"
    assert smtp.locator("input[name=from_address]").input_value() == "support@mailflow.example"

    # Replies for an existing mailbox: sponsors@, then answer one of its emails from the page.
    page.locator("tr", has=page.locator("b", has_text="sponsors@")).get_by_role("button", name="Replies…").click()
    smtp = page.locator("#integrations-body form")
    smtp.locator("input[name=host]").fill("smtp.mailflow.example")
    smtp.locator("input[name=user]").fill("sponsors@mailflow.example")
    smtp.locator("input[name=password]").fill(GOOD_PASSWORD)
    smtp.locator("input[name=from_address]").fill("sponsors@mailflow.example")
    smtp.locator("input[name=from_name]").fill("Hackathon sponsors desk")
    smtp.locator("button[type=submit]").click()
    page.wait_for_function("() => document.querySelector('#toast')?.textContent.includes('now go out over SMTP')")
    row = page.locator("tr", has=page.locator("b", has_text="sponsors@"))
    assert "SMTP · sponsors@mailflow.example" in row.text_content()
    page.keyboard.press("Escape")

    page.goto("/?view=all&id=3")  # Gold sponsorship: contract and invoice, to sponsors@
    page.wait_for_selector("form.reply textarea")
    page.fill("form.reply textarea", "The contract and invoice are attached.")
    page.click("form.reply button[type=submit]")
    page.wait_for_function("() => document.querySelector('#toast')?.textContent.startsWith('Reply sent')")
    sent = FakeSmtp.sent[-1]
    assert sent["From"] == "Hackathon sponsors desk <sponsors@mailflow.example>"
    assert sent["In-Reply-To"] == "<demo-3@mailflow.example>"
    assert sent["Subject"] == "Re: Gold sponsorship: contract and invoice"


def test_switch_the_ai_to_a_cloud_provider_with_a_checked_key(page):
    sign_in(page)
    open_integrations(page)
    page.get_by_role("tab", name="AI that sorts").click()
    assert "Mistral on your own server" in page.locator(".tab-panel").text_content()
    form = page.locator("#integrations-body form")
    form.locator("select[name=provider]").select_option("openai")
    assert "go to OpenAI" in form.locator(".note").text_content()
    form.locator("input[name=api_key]").fill("not-a-key")
    form.get_by_role("button", name="Check key").click()
    page.wait_for_function("() => document.querySelector('#integrations-body .error:not([hidden])')?.textContent.includes('refused')")
    form.locator("input[name=api_key]").fill(GOOD_KEY)
    form.get_by_role("button", name="Check key").click()
    page.wait_for_function("() => document.querySelector('#integrations-body .error.ok')?.textContent.startsWith('The key works')")
    assert page.locator("#ai-models option").count() == 2
    form.locator("input[name=model]").fill("model-small")
    form.get_by_role("button", name="Use this model").click()
    page.wait_for_function("() => document.querySelector('.tab-panel b')?.textContent.startsWith('OpenAI · model-small')")
    assert demo_n8n.GOOD_KEY not in page.content()
