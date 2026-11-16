"""Build the MailFlow presentation (MailFlow.pptx) from the docs in this repo.

Needs: python-pptx  (pip install python-pptx)
Run:   python3 deck/build_deck.py
PDF:   soffice --headless --convert-to pdf --outdir deck deck/MailFlow.pptx
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
IMAGES = HERE.parent / "docs" / "images"
OUT = HERE / "MailFlow.pptx"

DARK = RGBColor(0x1F, 0x29, 0x37)
GREY = RGBColor(0x6B, 0x72, 0x80)
LIGHT = RGBColor(0xF3, 0xF4, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PURPLE = RGBColor(0x7C, 0x3A, 0xED)  # processing
CYAN = RGBColor(0x08, 0x91, 0xB2)    # data
GREEN = RGBColor(0x16, 0xA3, 0x4A)   # pages
SLATE = RGBColor(0x33, 0x41, 0x55)   # overview / general

W, H = Inches(13.333), Inches(7.5)
FONT = "Calibri"

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


def style(run, size, color=DARK, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold


def box(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
    s.shadow.inherit = False
    return s


def text(slide, x, y, w, h, lines, size=20, color=DARK, bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate([lines] if isinstance(lines, str) else lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        style(run, size, color, bold)
    return tb


def bullets(slide, x, y, w, h, items, size=22, accent=SLATE):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        dot = p.add_run()
        dot.text = "\u25A0  "
        style(dot, size - 6, accent)
        if isinstance(item, tuple):  # (bold lead, rest)
            r = p.add_run()
            r.text = item[0]
            style(r, size, DARK, True)
            r = p.add_run()
            r.text = item[1]
            style(r, size)
        else:
            r = p.add_run()
            r.text = item
            style(r, size)
    return tb


def slide(title, accent, notes, section=""):
    s = prs.slides.add_slide(BLANK)
    box(s, 0, 0, Inches(0.22), H, fill=accent)
    if section:
        text(s, Inches(0.6), Inches(0.25), Inches(8), Inches(0.4), section.upper(),
             size=14, color=accent, bold=True)
    text(s, Inches(0.6), Inches(0.55), Inches(12.2), Inches(0.9), title, size=34, bold=True)
    box(s, Inches(0.6), Inches(1.42), Inches(1.2), Inches(0.06), fill=accent)
    text(s, Inches(11.3), Inches(7.0), Inches(1.8), Inches(0.35),
         str(len(prs.slides._sldIdLst)), size=12, color=GREY, align=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = notes
    return s


def picture(s, name, top=Inches(1.7), max_w=Inches(12.1), max_h=Inches(5.25)):
    from PIL import Image  # python-pptx depends on Pillow
    path = IMAGES / name
    with Image.open(path) as im:
        ratio = im.width / im.height
    w = max_w
    h = int(w / ratio)
    if h > max_h:
        h = max_h
        w = int(h * ratio)
    return s.shapes.add_picture(str(path), int((W - w) / 2), top, w, h)


def table(s, x, y, w, rows, col_w, accent, size=18, row_h=Inches(0.5)):
    shp = s.shapes.add_table(len(rows), len(rows[0]), x, y, w, row_h * len(rows))
    t = shp.table
    for i, cw in enumerate(col_w):
        t.columns[i].width = cw
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = accent if r == 0 else (LIGHT if r % 2 == 0 else WHITE)
            cell.margin_left = cell.margin_right = Inches(0.12)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = val
            style(run, size, WHITE if r == 0 else DARK, bold=(r == 0 or c == 0))
    return shp


# 1 Title -------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
box(s, 0, 0, W, Inches(0.3), fill=PURPLE)
box(s, 0, Inches(0.3), W, Inches(0.12), fill=CYAN)
box(s, 0, Inches(0.42), W, Inches(0.08), fill=GREEN)
text(s, Inches(0.9), Inches(2.3), Inches(11.5), Inches(1.4),
     "MailFlow \u2014 every company mailbox in one place", size=40, bold=True)
text(s, Inches(0.9), Inches(3.8), Inches(11.5), Inches(0.7),
     "Built in n8n on our own server", size=26, color=GREY)
text(s, Inches(0.9), Inches(5.6), Inches(11.5), Inches(0.9),
     ["Collect  \u2192  Sort with AI  \u2192  Show on one page"], size=22, color=PURPLE, bold=True)
s.notes_slide.notes_text_frame.text = (
    "Welcome. This is MailFlow: one place where we can see every email that arrives in any company "
    "mailbox. It is built in n8n, the automation tool already running on our own server, and the AI "
    "that sorts the mail runs on that server too. In the next few minutes: the problem, how it works, "
    "what it costs in time, what I need from you, and how we roll it out.")

# 2 The problem -------------------------------------------------------------
s = slide("The problem", SLATE, (
    "Today our mail is spread over many mailboxes on different providers: Gmail, Microsoft 365, IMAP "
    "hosting and an old POP3 server. Each one has to be opened separately, so nobody sees everything. "
    "The real cost is the urgent or angry email that sits in a mailbox nobody opened that day. "
    "That is the gap MailFlow closes."), "Why")
bullets(s, Inches(0.6), Inches(1.8), Inches(12), Inches(5), [
    ("Many mailboxes. ", "Each team and address has its own."),
    ("Different providers. ", "Gmail, Microsoft 365, IMAP hosting, an old POP3 server."),
    ("Nobody sees everything. ", "Each mailbox must be opened on its own."),
    ("Mail gets missed. ", "Urgent or angry emails can sit unnoticed in a mailbox nobody opened that day."),
], size=24)

# 3 The goal ----------------------------------------------------------------
s = slide("The goal: what version 1 does", SLATE, (
    "Version 1 does exactly four things. It collects every new email from every connected mailbox. "
    "It gives each one a category, a mood, an urgency and a one-line summary. It shows all of them on "
    "one web page, newest first, with filters and a Done button. And it sends a Telegram alert when "
    "an email is both urgent and negative. Important: the mailboxes themselves do not change. Nothing "
    "is moved, deleted or marked as read; people keep using their normal mail apps. Replying, "
    "assigning and per-person logins come later."), "Why")
bullets(s, Inches(0.6), Inches(1.8), Inches(12.1), Inches(4.3), [
    ("Collect ", "every new email from every connected mailbox, whatever the provider."),
    ("Sort ", "each one: category, sentiment, urgency and a one-line summary."),
    ("Show ", "all of them on one web page, newest first, with filters and a Done button."),
    ("Alert ", "on Telegram when an email is urgent and negative."),
], size=24, accent=PURPLE)
text(s, Inches(0.6), Inches(5.75), Inches(12.1), Inches(1.1), [
    "Unchanged: the mailboxes. Nothing is moved, deleted or marked read.",
    "Not in v1: replying, assigning, per-person logins, attachments, a daily summary."],
    size=18, color=GREY)

# 4 Architecture ------------------------------------------------------------
s = slide("How it fits together", SLATE, (
    "Left to right: the mailboxes, where mail arrives as today. One small collector workflow per "
    "mailbox notices new mail and puts it into one common shape. A single shared workflow, Process "
    "email, skips duplicates, sorts obvious mail with simple rules and asks the AI about the rest. "
    "Each email becomes one row in an n8n Data table. Two web pages, also built in n8n, read that "
    "table. Purple is processing, cyan is data, green is the pages; the rest of the deck uses the "
    "same colours."), "Overview")
picture(s, "architecture.png")

# 5 Journey -----------------------------------------------------------------
s = slide("One email's journey", PURPLE, (
    "Follow one email. Step 1: it arrives and its collector notices it, by push, by polling, or via "
    "mail-poll for the old POP3 server. Step 2: the collector hands it to Process email in the common "
    "shape. Step 3: Process email checks the table: if this email is already saved, it stops, so a "
    "collector running twice does no harm. Step 4: newsletters and no-reply mail are tagged by rules; "
    "everything else goes to the AI, which returns category, sentiment, urgency and summary, and the "
    "row is saved. Step 5: if it is urgent and negative, a Telegram alert goes out; the inbox page "
    "reads the rows for the list."), "Processing")
steps = [
    ("New email", "The collector notices it (push, poll or mail-poll)."),
    ("Common shape", "The collector hands it to Process email."),
    ("Already saved?", "If the row exists, stop. No duplicates."),
    ("Sort and save", "Rules tag obvious mail; the AI tags the rest."),
    ("Alert and show", "Urgent + negative \u2192 Telegram. The page reads the table."),
]
cw, gap, top = Inches(2.3), Inches(0.12), Inches(2.1)
for i, (head, body) in enumerate(steps):
    x = Inches(0.6) + i * (cw + gap)
    accent = CYAN if i == 3 else (GREEN if i == 4 else PURPLE)
    box(s, x, top, cw, Inches(3.9), fill=LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE).adjustments[0] = 0.06
    c = box(s, x + Inches(0.8), top + Inches(0.3), Inches(0.7), Inches(0.7), fill=accent, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    r = tf.paragraphs[0].add_run()
    r.text = str(i + 1)
    style(r, 24, WHITE, True)
    text(s, x + Inches(0.15), top + Inches(1.2), cw - Inches(0.3), Inches(0.6), head,
         size=20, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + Inches(0.15), top + Inches(1.95), cw - Inches(0.3), Inches(1.9), body,
         size=18, color=SLATE, align=PP_ALIGN.CENTER)

# 6 What the team sees ------------------------------------------------------
s = slide("What the team sees", GREEN, (
    "This is the inbox page. Every email from every mailbox, newest first. Each line shows the "
    "mailbox, the sender, the subject, the AI's one-line summary and coloured tags for category, mood "
    "and urgency. Filters at the top narrow it by mailbox, category, mood and status. Clicking an "
    "email opens it with its tags and a Mark as done button. The page is protected by a password. "
    "The first version may look plainer than this mock-up."), "Pages")
picture(s, "inbox-mockup.png")

# 7 Workflows ---------------------------------------------------------------
s = slide("The n8n workflows", PURPLE, (
    "These are the n8n workflows, every one named starting with 'MailFlow \u00b7'. One small collector "
    "per mailbox type, all ending in the same shared Process email workflow. Two page workflows start "
    "with a Webhook and return HTML. Two side jobs: one sends error alerts to Telegram, the other "
    "deletes rows older than 90 days every night. Adding a mailbox later means duplicating a "
    "collector and choosing the new login."), "Processing")
picture(s, "workflows.png")

# 8 The AI ------------------------------------------------------------------
s = slide("The AI: four answers per email", PURPLE, (
    "For every email that the rules do not catch, the AI answers four questions in one call: the "
    "category, from a fixed list we choose; the sender's mood; the urgency, where High means it needs "
    "an answer today; and a summary of at most 15 words. Temperature is zero, so the same email always "
    "gets the same answer. The default is Mistral running locally with Ollama: nothing extra to pay "
    "and the email never leaves our server, but it takes 22 to 30 seconds per email. A cloud model is "
    "a few seconds and fractions of a cent per email, but the text goes to that provider, so it needs "
    "the company's OK. Swapping is one node."), "Processing")
bullets(s, Inches(0.6), Inches(1.75), Inches(12.1), Inches(2.4), [
    ("Category: ", "Billing, Support, Sales, Internal, Newsletter, Other"),
    ("Mood: ", "Positive, Neutral, Negative"),
    ("Urgency: ", "High (needs an answer today), Normal, Low"),
    ("Summary: ", "one short sentence, at most 15 words"),
], size=20, accent=PURPLE)
table(s, Inches(0.6), Inches(4.3), Inches(12.1), [
    ["Choice", "Speed per email", "Cost", "Email text goes"],
    ["Ollama \u00b7 Mistral 7B on our server (default)", "22-30 s warm; 99 s first email",
     "Nothing extra", "Stays on the server"],
    ["Cloud model (Groq, OpenAI, OpenRouter)", "A few seconds", "Fractions of a cent", "To that provider"],
], [Inches(4.6), Inches(3.1), Inches(2.2), Inches(2.2)], PURPLE, size=18, row_h=Inches(0.62))

# 9 Measured ----------------------------------------------------------------
s = slide("Measured on our server", PURPLE, (
    "We tested this on our own server on 16 November 2026 with four test emails, local Mistral and "
    "temperature zero. Category and mood were right on all four. The first email took 99 seconds "
    "because the model had to load; after that, 22 to 30 seconds. Warm, Mistral sorts about 120 to "
    "160 emails an hour. At 1,000 emails a day that is about 42 an hour on average, so it keeps up, "
    "though morning peaks will queue for a while. In real use the newsletter would be caught by the "
    "rules and never reach the AI."), "Processing")
table(s, Inches(0.6), Inches(1.75), Inches(12.1), [
    ["Test email", "Answer", "Time"],
    ["Charged twice for November", "Billing \u00b7 Negative \u00b7 High", "99.1 s (model loading)"],
    ["Quote for 20 office routers", "Sales \u00b7 Positive \u00b7 High", "29.8 s"],
    ["November product newsletter", "Newsletter \u00b7 Neutral \u00b7 Normal", "24.5 s"],
    ["Re: connection problem", "Support \u00b7 Positive \u00b7 Normal", "21.6 s"],
], [Inches(4.4), Inches(4.6), Inches(3.1)], PURPLE, size=20, row_h=Inches(0.6))
text(s, Inches(0.6), Inches(5.45), Inches(12.1), Inches(0.5),
     "Category and mood right on all four.", size=20, bold=True)
text(s, Inches(0.6), Inches(6.0), Inches(12.1), Inches(1.0), [
    "Warm: about 120-160 emails an hour once loaded.",
    "1,000 emails a day is about 42 an hour on average: it keeps up; morning peaks queue."],
    size=20, color=SLATE)

# 10 Security ---------------------------------------------------------------
s = slide("Security and privacy", CYAN, (
    "Because the pages show company email, both are behind a password, and we recommend blocking them "
    "from the internet so they only work on our private network. Mailbox passwords and keys live only "
    "in n8n's encrypted credentials, never in workflows or files. With the local AI, no email text "
    "leaves the server; a cloud model needs the company's OK first. MailFlow only reads mailboxes; it "
    "never marks anything as read. And old rows are deleted after 90 days."), "Data")
bullets(s, Inches(0.6), Inches(1.8), Inches(12.1), Inches(5), [
    ("Pages: ", "password protected; recommended: reachable on our private network only."),
    ("Logins: ", "only in n8n's encrypted credentials, never in workflows or files."),
    ("AI: ", "local by default, nothing leaves the server; cloud needs the company's OK."),
    ("Mailboxes: ", "read only; nothing is moved, deleted or marked read."),
    ("Old data: ", "deleted every night after 90 days."),
    ("POP3 webhook: ", "checks a secret header."),
], size=22, accent=CYAN)

# 11 What we need -----------------------------------------------------------
s = slide("What we need", SLATE, (
    "To build this I need a few things only you or the company's admins can give. First, decisions: "
    "the categories, what High urgency means, local or cloud AI, who may open the page, how long to "
    "keep email, and who gets the alerts. Second, the private mailbox list with a login for each: "
    "server and password or app password for IMAP, a Google Cloud project for Gmail, and for Microsoft "
    "365 an Entra admin who registers an app with Mail.Read permission. Third, a few small server "
    "changes that I prepare and you run. None of this goes into the public repo."), "Plan")
cols = [
    ("Decisions", PURPLE, ["Categories", "What \"High urgency\" means",
                           "Local or cloud AI", "Who opens the page",
                           "Keep mail how long (90 days)", "Who gets alerts"]),
    ("Logins per provider", CYAN, ["IMAP: server, user, (app) password",
                                   "POP3: one mail-poll each",
                                   "Gmail: a Google Cloud project",
                                   "Microsoft 365: an Entra app"]),
    ("Admin help + server", GREEN, ["Entra admin: Mail.Read, limited to MailFlow mailboxes",
                                    "Keep Mistral loaded (30 min)",
                                    "Bigger data table limit (1 GiB)",
                                    "Block pages from the internet",
                                    "HTTPS address for Google sign-in"]),
]
cw = Inches(3.9)
for i, (head, acc, items) in enumerate(cols):
    x = Inches(0.6) + i * (cw + Inches(0.2))
    box(s, x, Inches(1.8), cw, Inches(0.6), fill=acc)
    text(s, x + Inches(0.15), Inches(1.8), cw - Inches(0.3), Inches(0.6), head,
         size=20, color=WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    box(s, x, Inches(2.4), cw, Inches(4.5), fill=LIGHT)
    bullets(s, x + Inches(0.1), Inches(2.5), cw - Inches(0.2), Inches(4.3), items, size=18, accent=acc)

# 12 Rollout ----------------------------------------------------------------
s = slide("Rollout", GREEN, (
    "We roll out in steps, and each step ends with something that works. Phase 0: prepare the mailbox "
    "list, categories, AI choice and logins. Phase 1, lessons 1 to 3: the work mailbox sorted into the "
    "table. Phase 2, lesson 4: every IMAP mailbox. Phase 3, lessons 5 and 6: everyone sees all mail on "
    "one page with a Done button. Phase 4, lessons 7 and 8: Gmail and Microsoft connected. Phase 5, "
    "lessons 9 and 10: error alerts, cleanup and the go-live checklist. Replying, assigning and "
    "per-person logins come later."), "Plan")
picture(s, "rollout.png", top=Inches(1.65), max_h=Inches(3.3))
table(s, Inches(0.6), Inches(5.2), Inches(12.1), [
    ["0. Prepare", "1. First mailbox", "2. IMAP", "3. Inbox page", "4. Gmail + Microsoft", "5. Go live"],
    ["Lesson 0", "Lessons 1-3", "Lesson 4", "Lessons 5-6", "Lessons 7-8", "Lessons 9-10"],
], [Inches(1.8), Inches(2.1), Inches(1.6), Inches(2.0), Inches(2.6), Inches(2.0)], GREEN, size=18,
    row_h=Inches(0.55))

# 13 Next steps -------------------------------------------------------------
s = slide("Next steps", GREEN, (
    "Two things to start. First, prepare the private mailbox list and make the decisions on the "
    "previous slide; the suggested defaults are fine for a first version. Second, lessons 1 to 3 "
    "build the first mailbox end to end: the work mail through mail-poll, sorted by the AI and saved "
    "in the table. That takes about two to three hours, and each lesson ends with a check that proves "
    "it works. Questions?"), "Plan")
for i, (num, head, body, acc) in enumerate([
    ("1", "Prepare", "The private mailbox list and the decisions (defaults are fine for v1).", CYAN),
    ("2", "Lessons 1-3", "First mailbox end to end: work mail sorted by the AI and saved in the table. "
                         "About 2-3 hours.", PURPLE),
]):
    y = Inches(1.9) + i * Inches(2.2)
    c = box(s, Inches(0.6), y, Inches(1.0), Inches(1.0), fill=acc, shape=MSO_SHAPE.OVAL)
    r = c.text_frame.paragraphs[0].add_run()
    c.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    r.text = num
    style(r, 32, WHITE, True)
    text(s, Inches(1.9), y - Inches(0.05), Inches(10.8), Inches(0.6), head, size=28, bold=True)
    text(s, Inches(1.9), y + Inches(0.6), Inches(10.8), Inches(1.2), body, size=22, color=SLATE)
text(s, Inches(0.6), Inches(6.3), Inches(12.1), Inches(0.6),
     "Each lesson ends with a check that proves the step works.", size=20, color=GREEN, bold=True)

prs.save(OUT)
print(f"Wrote {OUT} ({len(prs.slides._sldIdLst)} slides)")
