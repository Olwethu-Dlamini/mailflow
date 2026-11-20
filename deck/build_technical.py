"""MailFlow: how it works. The technical deck for the owner (MailFlow-Technical.pptx).

Facts come from docs/SYSTEM-DESIGN.md, docs/AS-BUILT.md and app/README.md as of 20 November 2026.
Build: deck/build.sh
"""

from kit import (AMBER, AMBER_SOFT, BLUE, BLUE_SOFT, CONTENT_W, GREEN, GREEN_SOFT, HERE, Inches, MARGIN, MUTED,
                 RED, RED_SOFT, SKY, SKY_SOFT, TEXT, TEXT2, TOP, VIOLET, VIOLET_SOFT, Deck, bullets, card, flow,
                 picture, table, text)

d = Deck("MailFlow · how it works")

# 1 ---------------------------------------------------------------------------------------------
d.title_slide(
    "Technical overview",
    "MailFlow: how it works",
    "Every part, how they connect, how one email and one click travel through them, and what to do "
    "when something breaks. As built on 20 November 2026.",
    "This deck is for you, the owner. It goes from the big picture down to the commands you run, so "
    "you can explain MailFlow, change it, and fix it. The order: the picture, the parts, three journeys "
    "(an email, a page load, a reply), the AI, security, running it, and what is still open.",
    footnote="Source of truth: docs/SYSTEM-DESIGN.md, docs/AS-BUILT.md, app/README.md in the mailflow repo.")

# 2 ---------------------------------------------------------------------------------------------
s = d.slide("The big picture", "Mailboxes → n8n → data table → web app → your team", (
    "Read it left to right. Mail arrives in the mailboxes as always. In n8n, one small collector per "
    "mailbox picks up new mail and hands it to one shared workflow, Process email, which sorts it with "
    "rules and a local AI and saves one row per email in an n8n data table. The MailFlow web app reads "
    "that table and shows it to the team; when someone replies, the app asks n8n to send the reply "
    "through Gmail. n8n is the engine; the web app is only the screen."))
picture(s, "deck-architecture.png", y=Inches(1.55), max_h=Inches(5.3), border=False)

# 3 ---------------------------------------------------------------------------------------------
s = d.slide("As built", "Where every part runs", (
    "Same system, drawn by where it runs. Two VMs on Proxmox: ai at 10.0.0.31 and srv1 at 10.0.0.10. "
    "On ai, in Docker: n8n, Ollama with Mistral, and the mailflow container on port 3100. On srv1: the "
    "Cloudflare Tunnel and Caddy, which already served the other websites. The blue line is a browser "
    "request: Cloudflare, the tunnel, Caddy, then ai port 3100. The violet line is email: IMAP from "
    "Gmail, and IMAP over Tailscale from the 22112002 mail server, into n8n. Tailscale is also how you "
    "reach the n8n editor; it is not on the internet."))
picture(s, "deck-as-built.png", y=Inches(1.5), max_h=Inches(5.35), border=False)

# 4 ---------------------------------------------------------------------------------------------
s = d.slide("The parts", "What each piece is and why it is there", (
    "Each row is one piece. The mailboxes are unchanged. The collectors and Process email are n8n "
    "workflows. The data table lives inside n8n's own database, so it is covered by the server "
    "backup. The AI is Ollama running Mistral 7B on ai. The web app is a small FastAPI program in its "
    "own container; it keeps only accounts and sessions itself. srv1 and Cloudflare publish it; "
    "Telegram carries the P1 alerts."))
table(s, MARGIN, TOP - Inches(0.1), [Inches(2.4), Inches(3.3), Inches(6.13)], [
    ["Part", "What it is", "Job"],
    ["Mailboxes", "Gmail, 22112002.xyz (IMAP)", "Where mail arrives, unchanged; read only"],
    ["Collectors", "n8n workflow per mailbox", "New mail → one common shape → Process email"],
    ["Process email", "n8n workflow", "Skip duplicates, rules, AI, fallback, save, P1 alert"],
    ["AI", "Ollama · Mistral 7B on ai", "Topic, sender, priority, needs reply, summary, next step"],
    ["Data table", "n8n Data table 'MailFlow emails'", "One row per email incl. status open → waiting → done"],
    ["Reply", "n8n workflow (Gmail node)", "Sends the reply in the same Gmail thread, sets waiting"],
    ["Web app", "FastAPI + HTML/JS, Docker 'mailflow'", "The page: logins, queue, status, reply box, users"],
    ["Publishing", "srv1: Cloudflare Tunnel + Caddy", "https://mailflow.22112002.xyz → ai:3100"],
    ["Alerts", "Telegram bot", "A message for every P1 email"],
], size=14, row_h=Inches(0.48))

# 5 ---------------------------------------------------------------------------------------------
s = d.slide("Journey 1: one email", "From arriving in Gmail to a row in the queue", (
    "One email. The collector for that mailbox sees it, without marking it read, and maps its fields "
    "into the common shape: message id, mailbox, sender, subject, time and the first 4,000 "
    "characters. Process email first checks the message id: if the row exists, it stops, so running "
    "twice does no harm. Simple rules catch newsletters, no-reply senders and event platforms like "
    "Devpost in under a second. Everything else goes to Mistral, which takes about 30 seconds. The row "
    "is saved; if it is P1, Telegram pings your phone. The page shows it on its next refresh."))
flow(s, TOP + Inches(0.1), [
    ("Collector", "IMAP sees new mail, leaves it unread, maps it to the common shape."),
    ("Duplicate?", "Same message id already saved → stop. Safe to run twice."),
    ("Rules", "Newsletter, no-reply, Devpost / Eventbrite / Luma / MLH → sorted in < 1 s."),
    ("AI", "Mistral answers 6 fields, ~30 s. Unusable answer → saved as Not sorted."),
    ("Save + alert", "One row in the data table. P1 → Telegram. Page shows it within 60 s."),
], h=Inches(3.1), body_size=13)
text(s, MARGIN, TOP + Inches(3.5), CONTENT_W, Inches(1.0), [
    "Common shape: message_id · mailbox · source · from_name · from_address · subject · received_at · body (first 4,000 characters)",
], 13, MUTED)

# 6 ---------------------------------------------------------------------------------------------
s = d.slide("Process email, node by node", "The shared brain in n8n", (
    "This is the real workflow, drawn from its n8n export. Has message id stops empty test runs. "
    "Already saved checks the table by message id. Obvious mail is the rules. Sort with AI is n8n's "
    "Information Extractor with the Ollama model attached; it is set to continue on error, so a bad "
    "answer does not stop the run. Merge joins the email with the AI's answer by position, AI tags "
    "builds the row, with fallbacks when the answer is missing, Save email inserts it, and P1 sends "
    "the Telegram alert."))
picture(s, "workflows/process-email.png", y=Inches(1.7), max_h=Inches(3.6), border=False)
bullets(s, MARGIN, Inches(5.45), CONTENT_W, Inches(1.4), [
    ("Sort with AI: ", "Information Extractor + Ollama (mistral:latest, temperature 0), On Error: Continue."),
    ("AI tags: ", "if the answer is missing → Other / Other / P2, needs a reply, 'Sort this email by hand', sorted_by = unsorted."),
], size=14, spacing=6)

# 7 ---------------------------------------------------------------------------------------------
s = d.slide("The AI", "Six answers per email, from instructions you can read", (
    "The AI answers six fields: topic, sender, priority, needs reply, summary and next step. The "
    "allowed values are in a JSON schema; the rules for choosing them are in the node's system prompt, "
    "one line per topic, ending with the exact answer form. That structure matters with a 7B model: "
    "with the rules crammed into the schema it put ten of fifteen test emails under Registration; with "
    "the system prompt it got sixteen of sixteen topics right. Temperature zero means the same email "
    "always gets the same answer. To change the topics, edit the prompt and the enum, and the TOPICS "
    "list in the app."))
for i, (head, body, fg, bg) in enumerate([
    ("Where it lives", "n8n → MailFlow · Process email → Sort with AI. Options → System Prompt Template: the rules. Schema: the six fields and allowed values.", VIOLET, VIOLET_SOFT),
    ("Model", "Ollama · mistral:latest on ai, temperature 0. Local: no email text leaves the server. ~30 s an email when loaded.", SKY, SKY_SOFT),
    ("Changing topics", "Edit the system prompt line + the schema enum, then TOPICS / SENDERS in app/src/mailflow/queue.py.", AMBER, AMBER_SOFT),
]):
    card(s, MARGIN + i * Inches(3.98), TOP - Inches(0.1), Inches(3.85), Inches(2.25), head, body, accent=fg,
         tint=bg, head_size=16, body_size=13)
table(s, MARGIN, TOP + Inches(2.4), [Inches(4.4), Inches(2.6), Inches(1.7), Inches(1.7), Inches(1.43)], [
    ["Test: 16 hackathon emails", "Topic", "Sender", "Priority", "Time"],
    ["Rules inside the schema", "4 / 15", "14 / 15", "13 / 15", "~32 s"],
    ["System prompt + answer form", "16 / 16", "16 / 16", "15 / 16", "~30 s"],
], size=14, row_h=Inches(0.45))

# 8 ---------------------------------------------------------------------------------------------
s = d.slide("The web app", "A small FastAPI program in its own container", (
    "The web app is about 700 lines of Python and one page of plain JavaScript, no build step. config "
    "reads the settings, n8n.py talks to n8n's API and the Reply webhook, queue.py holds the views, "
    "filters and the late rule, auth.py and store.py are logins and sessions in SQLite, web.py is the "
    "HTTP layer. The browser only ever talks to the app; the n8n API key and the reply secret stay in "
    "the container's settings file. 51 tests cover the rules, the n8n client and every route."))
table(s, MARGIN, TOP - Inches(0.1), [Inches(2.6), Inches(9.23)], [
    ["File (app/src/mailflow/)", "Job"],
    ["config.py", "Settings from /opt/mailflow/app/.env: n8n address and API key, reply secret, site origin, trusted proxy"],
    ["n8n.py", "Reads rows (last 30 days, paged, 15 s cache), updates status, calls the Reply webhook"],
    ["queue.py", "Views, Topic/Sender filters, sorting (P1 first, oldest first), the late rule (P1 4 h, P2 24 h)"],
    ["auth.py · store.py", "scrypt passwords, sessions, lockout; SQLite in the mailflow_data volume"],
    ["web.py", "Routes, security headers, the origin check, the 64 KB body limit, the http → https redirect"],
    ["static/", "index.html, login.html, app.js, app.css: the page, text-only rendering of email content"],
    ["cli.py", "mailflow user add | reset | disable | enable | list (on the server)"],
], size=13, row_h=Inches(0.5))
text(s, MARGIN, Inches(6.35), CONTENT_W, Inches(0.4),
     "Tests: cd app && uv run pytest  (51 tests: queue rules, n8n client, auth and lockout, every route)", 13, MUTED)

# 9 ---------------------------------------------------------------------------------------------
s = d.slide("Journey 2: opening the page", "From the browser to the data and back", (
    "When someone opens the page, the browser connects to Cloudflare over HTTPS. Cloudflare sends it "
    "through the tunnel to srv1, where Caddy forwards it to ai port 3100. The app checks the session "
    "cookie; without one it sends you to the login page. With one, it asks n8n's API for the last 30 "
    "days of rows, at most 3,000, cached 15 seconds, and builds the queue: the view, the filters, the "
    "sort order and the late markers. The page refreshes every 60 seconds and whenever you come back "
    "to the tab."))
flow(s, TOP + Inches(0.1), [
    ("Browser", "https://mailflow.22112002.xyz; http is redirected to https."),
    ("Cloudflare", "HTTPS, then the tunnel to srv1. Adds Cf-Connecting-IP (the visitor)."),
    ("srv1 Caddy", "Forwards to ai 10.0.0.31:3100 on the LAN."),
    ("App", "Session cookie? No → login page. Yes → continue."),
    ("n8n API", "Rows of the last 30 days → queue: view, filters, P1 first, late."),
], h=Inches(3.0), body_size=13)
bullets(s, MARGIN, TOP + Inches(3.4), CONTENT_W, Inches(1.4), [
    "The page refreshes every 60 s and when you return to the tab; if a refresh fails it says since when the list is old.",
    "Logins are counted per visitor: the app trusts Cf-Connecting-IP only on requests from srv1 (TRUSTED_PROXY=10.0.0.10).",
], size=14, spacing=6)

# 10 --------------------------------------------------------------------------------------------
s = d.slide("Journey 3: a reply", "From the reply box to the customer's inbox", (
    "A reply starts in the reply box, which shows only for the Gmail mailbox. The app checks the email "
    "and the text, then posts to n8n's Reply webhook with the secret header. n8n looks up the email in "
    "Gmail by its Message-ID, replies with the Gmail node so it lands in the same thread and in Sent, "
    "and sets the row to waiting. The app shows 'Reply sent' and the email moves to Waiting on "
    "customer. Other mailboxes can't reply from the page yet: n8n's normal send node can't keep the "
    "thread."))
flow(s, TOP + Inches(0.1), [
    ("Reply box", "Only for the gmail mailbox; text up to 20,000 characters."),
    ("App → n8n", "POST /webhook/mailflow/reply with X-MailFlow-Secret. No secret → 403."),
    ("Find in Gmail", "Search rfc822msgid:<Message-ID>."),
    ("Send", "Gmail node 'Reply': same thread, lands in Sent."),
    ("Waiting", "Row status → waiting; the page shows 'Reply sent'."),
], h=Inches(3.0), body_size=13)
text(s, MARGIN, TOP + Inches(3.45), CONTENT_W, Inches(0.8),
     "Answers: sent · cannot (not gmail, or empty) · not_found (not in Gmail). Other mailboxes: reply in the mail app, mark it on the page.",
     14, MUTED)

# 11 --------------------------------------------------------------------------------------------
s = d.slide("Security", "Layer by layer", (
    "Security in layers. At the edge: HTTPS by Cloudflare, plain http redirected. Logins: one account "
    "per person, scrypt hashed, at least 12 characters, five failures lock an email and twenty lock a "
    "visitor for 15 minutes. Sessions: HttpOnly, Secure, SameSite Strict cookies that end after 12 "
    "hours idle or 7 days. Requests: every change needs the page's own header and origin, bodies over "
    "64 KB are refused, and a strict content policy blocks injected scripts; email text is only ever "
    "shown as text. Secrets stay on the server. The container runs read-only, without privileges, on "
    "the LAN address only. n8n's editor stays on Tailscale."))
table(s, MARGIN, TOP - Inches(0.1), [Inches(2.4), Inches(9.43)], [
    ["Layer", "Control"],
    ["Edge", "Cloudflare HTTPS; http → https (308); the app's port is bound to ai's LAN address only"],
    ["Logins", "One account per person; scrypt; 12+ characters; 5 failures / email and 20 / visitor → locked 15 min"],
    ["Sessions", "Random token, only its hash stored; HttpOnly, Secure, SameSite=Strict; 12 h idle, 7 days max"],
    ["Requests", "Changes need X-MailFlow: 1 and the site's own Origin; body ≤ 64 KB; strict CSP, no inline script"],
    ["Email content", "Always rendered as text (never HTML), so an email cannot run code in the page"],
    ["Secrets", "n8n API key and reply secret only in /opt/mailflow/app/.env (root, 600); never sent to the browser"],
    ["Container", "Non-root, read-only filesystem, no Linux capabilities, no-new-privileges, 128 MB"],
    ["n8n", "Editor and API only on Tailscale; the Reply webhook needs its secret header (403 without)"],
], size=13, row_h=Inches(0.5))

# 12 --------------------------------------------------------------------------------------------
s = d.slide("Docker and deploying", "One container, one script", (
    "The app is one Docker container, built from app/Dockerfile and started by app/docker-compose.yml. "
    "It joins the automation stack's network, so it reaches n8n as http://n8n:5678. Accounts live in "
    "the mailflow_data volume and survive updates. The deploy script does everything: it pulls the "
    "repo into /opt/mailflow, keeps the settings file, rebuilds and restarts the container, and waits "
    "until it reports healthy. srv1 was set up once with its own script."))
for i, (head, body, fg, bg) in enumerate([
    ("Container 'mailflow'", "python:3.13-slim, uvicorn on :8000 → published 10.0.0.31:3100. Network automation_default. Volume mailflow_data (/data). Healthcheck /healthz.", BLUE, BLUE_SOFT),
    ("Deploy / update", "On ai: sudo bash ~/mailflow-deploy.sh\nPulls /opt/mailflow, rebuilds, restarts, waits for healthy. The same command for every update.", GREEN, GREEN_SOFT),
    ("Publish (done once)", "On srv1: app/deploy/srv1-publish.sh. Backs up, adds the tunnel line + Caddy block, validates (restores on failure), DNS, reloads.", SKY, SKY_SOFT),
]):
    card(s, MARGIN + i * Inches(3.98), TOP - Inches(0.1), Inches(3.85), Inches(3.0), head, body, accent=fg,
         tint=bg, head_size=16, body_size=13)
text(s, MARGIN, TOP + Inches(3.15), CONTENT_W, Inches(1.4), [
    "Settings: /opt/mailflow/app/.env (root, 600): N8N_URL, N8N_API_KEY, MAILFLOW_TABLE_ID, N8N_REPLY_SECRET, SITE_ORIGIN, TRUSTED_PROXY, COOKIE_SECURE, DB_PATH",
    "Code: github.com/Olwethu-Dlamini/mailflow (public, no secrets)   ·   n8n workflow exports: the private n8n-chatbot repo",
], 13, MUTED, spacing=6)

# 13 --------------------------------------------------------------------------------------------
s = d.slide("Running it", "The commands you will actually use", (
    "Day to day you need a handful of commands, all on ai in /opt/mailflow/app. ps shows whether the "
    "container is running and healthy; logs shows what it is doing. Accounts can be managed in the "
    "page under Users, or with the mailflow command inside the container, for example to reset your "
    "own password. In n8n, executions shows failed runs of the workflows, and the data table can be "
    "opened in the editor to see the rows."))
table(s, MARGIN, TOP - Inches(0.1), [Inches(4.2), Inches(7.63)], [
    ["Task", "Command / place"],
    ["Is it up?", "sudo docker compose ps   (in /opt/mailflow/app)"],
    ["What is it doing?", "sudo docker compose logs -f --tail 100"],
    ["Update to the latest code", "sudo bash ~/mailflow-deploy.sh"],
    ["Restart", "sudo docker compose restart"],
    ["Add / reset / disable a user", "Page → Users   or   sudo docker compose exec mailflow mailflow user reset --email …"],
    ["Failed n8n runs", "n8n editor (Tailscale) → Executions, filter Error"],
    ["See the rows", "n8n editor → Overview → Data tables → MailFlow emails"],
    ["Health check from outside", "https://mailflow.22112002.xyz/healthz → {\"ok\":true}"],
], size=13, row_h=Inches(0.5))

# 14 --------------------------------------------------------------------------------------------
s = d.slide("When something breaks", "Symptom → where to look → fix", (
    "When something goes wrong, start from what you see. 'MailFlow engine unreachable' means the app "
    "is fine but cannot reach n8n: check the n8n container and the API key. A 502 or Cloudflare error "
    "page means the app or the path to it is down: check the container, then Caddy and cloudflared on "
    "srv1. If new mail stops appearing, look at n8n's executions for the collectors and Process email. "
    "A page error after an update is an old cached page: hard reload. Emails marked Not sorted were "
    "saved but the AI's answer was unusable: label them by hand."))
table(s, MARGIN, TOP - Inches(0.1), [Inches(3.6), Inches(4.2), Inches(4.03)], [
    ["You see", "Where to look", "Usual fix"],
    ["'MailFlow engine unreachable'", "n8n container; API key in .env", "Start n8n; replace the key; redeploy"],
    ["Cloudflare error / 502", "docker compose ps on ai; Caddy + cloudflared on srv1", "Restart the container / services"],
    ["No new mail in the queue", "n8n Executions: collectors, Process email", "Re-test the IMAP credential; re-activate"],
    ["Page error after an update", "Old page code cached in the browser", "Hard reload (Ctrl+Shift+R)"],
    ["Reply 'not sent'", "Gmail OAuth credential in n8n", "Sign in with Google again in the credential"],
    ["Email shows 'Not sorted'", "AI answer was unusable", "Label it by hand; nothing was lost"],
    ["Can't log in (locked)", "5 wrong passwords in 15 min", "Wait 15 min or reset via the CLI"],
], size=13, row_h=Inches(0.52))

# 15 --------------------------------------------------------------------------------------------
s = d.slide("Decisions", "Why it is built this way", (
    "The key decisions. n8n as the engine, because it has triggers for every mailbox type and the AI "
    "nodes, and you can change it without code. One shared Process email, so types, rules and AI live "
    "in one place. A data table instead of a database server: nothing extra to run, covered by the "
    "backup. Local Mistral, so mail stays on the server. A separate web app for a real login and a "
    "public address. And the hackathon labels, replacing the customer-service ones, with the rules in "
    "the system prompt."))
table(s, MARGIN, TOP - Inches(0.1), [Inches(0.8), Inches(4.4), Inches(6.63)], [
    ["#", "Decision", "Why"],
    ["M1", "Build in n8n", "Triggers for every mailbox type and AI nodes built in; changeable without code"],
    ["M2", "One shared Process email", "Topics, rules and the AI in one place; collectors stay tiny"],
    ["M3", "n8n Data table for storage", "No extra service; inside n8n's database, covered by the server backup"],
    ["M5/6", "Rules first, local Mistral", "Newsletters need no AI; email text never leaves the server"],
    ["M10", "Replies via the Gmail node", "Keeps the Gmail thread and Sent folder; n8n's send node can't"],
    ["M11", "Separate web app, a login each", "A real public site with per-person accounts; n8n stays the engine"],
    ["M12", "Hackathon labels", "Who writes and about what decides the answer; rules in the system prompt"],
], size=13, row_h=Inches(0.52))

# 16 --------------------------------------------------------------------------------------------
s = d.slide("Limits and next steps", "What is not done yet", (
    "What is not done yet, roughly in order of importance. There is no error alert: if a collector or "
    "Process email fails, nobody is told; an n8n error workflow to Telegram fixes that. Nothing deletes "
    "old rows yet; the plan is 90 days. Replies work only for the Gmail mailbox. Mistral takes about "
    "30 seconds an email, so a big burst queues; a cloud model would be faster but sends text out. "
    "The app's n8n API key can do everything in n8n, not just the table. And several emails processed "
    "at the same moment can be saved twice; collectors send one at a time, so this is rare."))
for i, (head, body, fg, bg) in enumerate([
    ("No error alerts yet", "A failing collector or Process email is silent. Next: an n8n error workflow → Telegram.", RED, RED_SOFT),
    ("No cleanup yet", "Rows are never deleted; the page shows 30 days. Next: nightly delete after 90 days.", AMBER, AMBER_SOFT),
    ("Replies: Gmail only", "Other mailboxes need a sender that keeps the thread (e.g. the DDOService bridge).", AMBER, AMBER_SOFT),
    ("AI speed", "~30 s an email on Mistral; bursts queue. A cloud model is seconds but sends text out.", SKY, SKY_SOFT),
    ("Wide API key", "n8n API keys can do everything; scope it if n8n offers scopes, keep it on the server.", SKY, SKY_SOFT),
    ("Rare duplicates", "Two runs at the same moment can save one email twice; collectors send one at a time.", SKY, SKY_SOFT),
]):
    col, row = i % 3, i // 3
    card(s, MARGIN + col * Inches(3.98), TOP - Inches(0.1) + row * Inches(2.45), Inches(3.85), Inches(2.25),
         head, body, accent=fg, tint=bg, head_size=16, body_size=13)

d.save(HERE / "MailFlow-Technical.pptx")
