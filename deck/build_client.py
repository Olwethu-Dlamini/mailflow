"""MailFlow for hackathon organisers: the client deck (MailFlow-Client.pptx).

Screenshots are the real app showing made-up emails (deck/demo_server.py); no real mail.
Build: deck/build.sh
"""

from kit import (AMBER, AMBER_SOFT, BLUE, BLUE_SOFT, CONTENT_W, GREEN, GREEN_SOFT, HERE, Inches, LINE, MARGIN,
                 MUTED, RED, RED_SOFT, TEXT, TEXT2, TOP, VIOLET, VIOLET_SOFT, Deck, bullets, card, flow, picture,
                 pill, rule, shape, table, text)
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN

d = Deck("MailFlow · one inbox for your hackathon")

# 1 ---------------------------------------------------------------------------------------------
d.title_slide(
    "For hackathon organisers",
    "One inbox for your whole hackathon",
    "Every email from every mailbox, sorted by what it is about, who sent it and how urgent it is, "
    "so your team answers the right thing first.",
    "Welcome. MailFlow takes the mail your hackathon gets in all its mailboxes and turns it into one "
    "shared, sorted inbox for your team. In the next ten minutes: the problem it solves, what it does, "
    "what your team sees, and how we get you started.",
    footnote="Screens in this deck show the real MailFlow app with made-up example emails.")

# 2 ---------------------------------------------------------------------------------------------
s = d.slide("The problem", "Hackathon mail is everywhere, and the urgent email gets buried", (
    "A hackathon gets mail in many places: a general hello address, a sponsors address, press, plus a "
    "stream of automatic notices from Devpost, Eventbrite and friends. Nobody sees all of it, and the "
    "email that matters most, a safety report or a team that cannot submit 40 minutes before the "
    "deadline, sits between a newsletter and a registration question. And when five organisers share "
    "a mailbox, nobody knows who already answered."))
for i, (head, body, fg, bg) in enumerate([
    ("Many mailboxes", "hello@, sponsors@, press@, personal inboxes of the organisers: each opened on its own.", BLUE, BLUE_SOFT),
    ("Lots of noise", "Devpost submissions, Eventbrite sign-ups, newsletters and sales pitches bury real questions.", MUTED, None),
    ("Urgent mail gets missed", "A code-of-conduct report or a submission problem can't wait until someone opens the right inbox.", RED, RED_SOFT),
    ("Who answered?", "Several organisers, one mailbox: some emails get two answers, some get none.", AMBER, AMBER_SOFT),
]):
    x = MARGIN + i * (Inches(2.86) + Inches(0.2))
    card(s, x, TOP + Inches(0.3), Inches(2.86), Inches(3.6), head, body, accent=fg, tint=bg, body_size=15)

# 3 ---------------------------------------------------------------------------------------------
s = d.slide("What MailFlow does", "Collect, sort, work the queue, reply", (
    "MailFlow does four things. It collects every new email from every mailbox you connect, without "
    "changing anything in those mailboxes. It sorts each email: the topic, who sent it, how urgent it "
    "is, whether someone must reply, a one-line summary and the next step. Your team works one shared "
    "queue: what needs a reply, most urgent first. And for Gmail mailboxes you reply right from "
    "MailFlow; the answer lands in the same Gmail conversation."))
flow(s, TOP + Inches(0.25), [
    ("Collect", "Every new email from every mailbox you connect. Your mailboxes stay as they are: nothing is moved, deleted or marked read."),
    ("Sort", "Topic, sender, priority P1-P3, needs a reply, a one-line summary and the next step, for every email."),
    ("Work the queue", "One shared inbox: what needs a reply, most urgent first. Mark replied or done so everyone knows."),
    ("Reply", "Answer from MailFlow (Gmail mailboxes today); it lands in the same conversation. Urgent mail also pings your phone."),
], h=Inches(3.5), body_size=14)

# 4 ---------------------------------------------------------------------------------------------
s = d.slide("What your team sees", "One shared inbox, sorted for the event", (
    "This is the MailFlow page. On the left: search, the views such as Needs reply, Mine and P1, "
    "answer today, and your mailboxes. In the middle: the queue, most urgent first, each email with "
    "its next step and how long it has been waiting; the waiting time turns red when it is late. Topic "
    "and sender filters sit above it. On the right: the open email, what the AI made of it, and the "
    "buttons to take it, mark it replied or done. Here the top email is a code-of-conduct report, "
    "marked P1 and shown in red."),
    subtitle="Views on the left, the queue in the middle, the open email on the right.")
picture(s, "app/queue.png", y=Inches(1.9), max_h=Inches(4.85))

# 5 ---------------------------------------------------------------------------------------------
s = d.slide("How every email is sorted", "Topic, sender and priority, chosen for a hackathon", (
    "Every email gets a topic from a list made for hackathons, from Registration and Team to "
    "Sponsorship, Logistics and Code of conduct. It gets the sender: a participant, a sponsor, a mentor "
    "or judge, a volunteer, a supplier or venue, the press, someone on your team, or an automatic "
    "system. And a priority: P1 answer today, P2 this week, P3 no answer needed. Platform notices and "
    "newsletters are recognised by simple rules in a second; everything else is read by the AI. The "
    "lists can be adjusted to your event."))
text(s, MARGIN, TOP, Inches(3), Inches(0.35), "TOPIC", 12, MUTED, True)
topics = ["Registration", "Team", "Rules & judging", "Submission", "Sponsorship", "Mentor/Judge", "Volunteer",
          "Logistics", "Prizes & payouts", "Media/press", "Withdrawal", "Code of conduct",
          "Platform notification", "Marketing", "Other"]
x, y = MARGIN, TOP + Inches(0.42)
for t in topics:
    fg, bg = (RED, RED_SOFT) if t == "Code of conduct" else (TEXT2, None)
    w = Inches(0.105 * len(t) + 0.5)
    if x + w > MARGIN + CONTENT_W:
        x, y = MARGIN, y + Inches(0.5)
    pill(s, x, y, t, fg=fg, bg=bg or LINE, size=13, w=w)
    x += w + Inches(0.12)
y += Inches(0.75)
text(s, MARGIN, y, Inches(3), Inches(0.35), "SENDER", 12, MUTED, True)
x, y = MARGIN, y + Inches(0.42)
for t in ["Participant", "Sponsor", "Mentor/Judge", "Volunteer", "Vendor/Venue", "Press", "Organiser", "Automated"]:
    w = Inches(0.105 * len(t) + 0.5)
    pill(s, x, y, t, fg=VIOLET, bg=VIOLET_SOFT, size=13, w=w)
    x += w + Inches(0.12)
y += Inches(0.75)
text(s, MARGIN, y, Inches(3), Inches(0.35), "PRIORITY", 12, MUTED, True)
for i, (p, fg, bg, body) in enumerate([
    ("P1", RED, RED_SOFT, "Answer today: safety, problems during the event, submissions near the deadline, sponsors and money"),
    ("P2", AMBER, AMBER_SOFT, "This week: questions, registrations, teams, logistics, mentors, volunteers, press"),
    ("P3", MUTED, LINE, "No answer needed: notifications, newsletters, thank-yous"),
]):
    yy = y + Inches(0.42) + i * Inches(0.44)
    pill(s, MARGIN, yy, p, fg=fg, bg=bg, size=13, w=Inches(0.55))
    text(s, MARGIN + Inches(0.75), yy + Inches(0.02), CONTENT_W - Inches(0.75), Inches(0.4), body, 15, TEXT2)

# 6 ---------------------------------------------------------------------------------------------
s = d.slide("What can't wait", "P1: answer today, and your phone knows too", (
    "The P1 view shows what must be answered today. P1 is for a code-of-conduct or safety report, a "
    "problem during the event such as a power cut at the venue, a team that cannot submit close to "
    "the deadline, and sponsor commitments or money. Every P1 email also sends an alert to the "
    "organiser's phone through Telegram, so nobody has to keep the inbox open to catch it."))
picture(s, "app/p1-list.png", x=MARGIN, y=TOP - Inches(0.15), max_w=Inches(4), max_h=Inches(4.9))
bullets(s, MARGIN + Inches(3.6), TOP + Inches(0.2), Inches(8.2), Inches(4.6), [
    ("Safety first. ", "Code-of-conduct reports are always P1 and shown in red."),
    ("During the event. ", "Venue, power, WiFi or access problems."),
    ("Deadlines. ", "A team that can't submit with minutes to go."),
    ("Sponsors and money. ", "Contracts, invoices, prize payouts."),
    ("On your phone. ", "Every P1 email sends a Telegram alert."),
], size=18, spacing=16)

# 7 ---------------------------------------------------------------------------------------------
s = d.slide("Reply and track", "Answer from MailFlow and let the team see it's handled", (
    "Open an email and you see what it says, the AI's summary and next step, and a reply box. The "
    "reply is sent from your mailbox, in the same conversation, and the email moves to Waiting on "
    "customer, so the rest of the team sees it is handled. Mark it Done when it is finished, or Reopen "
    "it. Today replies from the page work for Gmail mailboxes; for other mailboxes you reply in your "
    "mail app and mark it here."))
picture(s, "app/reply-email.png", x=MARGIN, y=TOP - Inches(0.15), max_w=Inches(6), max_h=Inches(4.9))
x0 = MARGIN + Inches(5.6)
text(s, x0, TOP + Inches(0.05), Inches(3.8), Inches(0.35), "EVERY EMAIL MOVES THROUGH", 12, MUTED, True)
for i, (label, fg, bg, body) in enumerate([
    ("Open", TEXT2, LINE, "New, needs attention"),
    ("Waiting on customer", BLUE, BLUE_SOFT, "Replied, waiting for them"),
    ("Done", GREEN, GREEN_SOFT, "Finished; Reopen any time"),
]):
    yy = TOP + Inches(0.55) + i * Inches(0.95)
    pill(s, x0, yy, label, fg=fg, bg=bg, size=13, w=Inches(2.3))
    text(s, x0, yy + Inches(0.42), Inches(3.8), Inches(0.4), body, 14, TEXT2)
text(s, x0, TOP + Inches(3.5), Inches(3.8), Inches(1.0),
     "Replies from the page: Gmail mailboxes today. Other mailboxes: reply in your mail app, mark it here.",
     13, MUTED)

# 7b --------------------------------------------------------------------------------------------
s = d.slide("Who's on it", "Everyone sees who has each email, and what was done", (
    "With more than one person on the inbox, two people must never answer the same email. Anyone can "
    "take an email: their name shows next to it in the queue and it moves to their Mine view; an "
    "admin can give an email to someone. Every email keeps a short history: who took it, who replied, "
    "who marked it done. And when the AI got the topic or priority wrong, anyone can correct it in one "
    "click; the email moves to the right place at once."))
picture(s, "app/team-email.png", x=MARGIN, y=TOP - Inches(0.15), max_w=Inches(6), max_h=Inches(4.9))
bullets(s, MARGIN + Inches(6.4), TOP + Inches(0.2), Inches(5.4), Inches(4.6), [
    ("Take it. ", "Press Take (or A): your name is on it, it's under Mine."),
    ("Hand it over. ", "An admin gives an email to anyone on the team."),
    ("See the history. ", "Who took it, replied or marked it done, and when."),
    ("Fix the AI. ", "Change the priority, topic or needs-a-reply in one click."),
], size=17, spacing=14)

# 8 ---------------------------------------------------------------------------------------------
s = d.slide("On the go", "Works on the organiser's phone", (
    "Organisers are on their feet during an event, so the page works on a phone: one column at a "
    "time, the views in a menu, and the open email with its buttons and reply box. Together "
    "with the Telegram alert for P1, the person on duty can handle urgent mail from the venue floor."))
picture(s, "app/phone-list.png", x=MARGIN + Inches(0.4), y=TOP - Inches(0.1), max_w=Inches(2.6), max_h=Inches(4.95))
picture(s, "app/phone-email.png", x=MARGIN + Inches(3.4), y=TOP - Inches(0.1), max_w=Inches(2.6), max_h=Inches(4.95))
bullets(s, MARGIN + Inches(6.6), TOP + Inches(0.2), Inches(5.2), Inches(4.5), [
    ("One column at a time: ", "the queue, then the email."),
    ("Views in a menu: ", "Needs reply, Mine, P1 and the rest."),
    ("Everything works: ", "reply, mark waiting or done."),
    ("Paired with alerts: ", "P1 email pings Telegram on your phone."),
], size=16)

# 9 ---------------------------------------------------------------------------------------------
s = d.slide("A day at the event", "What MailFlow does while you run the hackathon", (
    "Here is a day at the event. At 08:30 the venue writes that hall B has no power: P1, Logistics, "
    "and your phone buzzes. At 10:10 a participant reports harassment: P1, Code of conduct, shown in "
    "red. Through the day Devpost and Eventbrite notices are sorted aside by rules and never reach the "
    "queue. At 14:00 a sponsor confirms and needs an invoice: P1, Sponsorship. At 17:20 a team can't "
    "upload its video forty minutes before the deadline: P1, Submission. Everything else, the "
    "registration questions, team matching and visa letters, waits as P2 in order."))
rows = [
    ["Time", "Email", "MailFlow", "What happens"],
    ["08:30", "Venue: power outage in hall B", "P1 · Logistics · Vendor/Venue", "Telegram alert; top of the queue"],
    ["10:10", "Participant reports harassment", "P1 · Code of conduct · Participant", "Shown in red; Telegram alert"],
    ["all day", "Devpost / Eventbrite notices", "P3 · Platform notification", "Sorted aside by rules in seconds"],
    ["14:00", "Sponsor confirms, needs invoice", "P1 · Sponsorship · Sponsor", "Alert; reply from MailFlow"],
    ["17:20", "Team can't upload its demo video", "P1 · Submission · Participant", "Alert; answered before the deadline"],
    ["any", "Registration, teams, visa letters", "P2 · their topic", "Wait in order, oldest first"],
]
table(s, MARGIN, TOP + Inches(0.1), [Inches(1.1), Inches(3.6), Inches(3.6), Inches(3.53)], rows, size=14,
      row_h=Inches(0.56))

# 10 --------------------------------------------------------------------------------------------
s = d.slide("Privacy and security", "Your mail stays yours", (
    "Privacy matters with participant mail. The AI that reads the emails runs on our own server, so "
    "email text is not sent to an outside AI company. Your mailboxes are only read: nothing is moved, "
    "deleted or marked read, and your team keeps using its normal mail apps. Every organiser has their "
    "own login; passwords are stored scrambled, and repeated wrong passwords lock the login. The page "
    "is only reachable over an encrypted HTTPS connection, and the keys that reach your mailboxes "
    "never leave the server."))
for i, (head, body) in enumerate([
    ("AI on our own server", "Email text is not sent to an outside AI service."),
    ("Mailboxes untouched", "Read only: nothing moved, deleted or marked read."),
    ("A login per organiser", "Admins add and remove people; wrong passwords lock the login."),
    ("Encrypted connection", "HTTPS only; mailbox keys never leave the server."),
]):
    col, row = i % 2, i // 2
    card(s, MARGIN + col * Inches(5.95), TOP + Inches(0.1) + row * Inches(2.25), Inches(5.85), Inches(2.0),
         head, body, accent=GREEN, tint=GREEN_SOFT, head_size=18, body_size=15)

# 11 --------------------------------------------------------------------------------------------
s = d.slide("How well it sorts", "Tested on typical hackathon emails", (
    "We tested the sorting on sixteen typical hackathon emails, at least one per topic and sender: "
    "registrations, team matching, rules questions, a failing submission, a sponsor, a judge, a "
    "volunteer, visa and food questions, prize money, press, a withdrawal, a harassment report, a "
    "venue power cut, a sales pitch and a Devpost notice. The topic and the sender were right for all "
    "sixteen, the priority for fifteen. The AI takes about thirty seconds an email; notices caught by "
    "the rules take seconds. If the AI ever gives an unusable answer, the email is still shown, "
    "marked Not sorted, so nothing gets lost."))
for i, (big, small, fg) in enumerate([
    ("16 / 16", "topic right", GREEN), ("16 / 16", "sender right", GREEN),
    ("15 / 16", "priority right", GREEN), ("~30 s", "per email (rules: seconds)", BLUE),
]):
    x = MARGIN + i * (Inches(2.86) + Inches(0.2))
    shape(s, x, TOP + Inches(0.2), Inches(2.86), Inches(1.9), fill=None, line=LINE, kind=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    text(s, x, TOP + Inches(0.45), Inches(2.86), Inches(0.8), big, 38, fg, True, align=PP_ALIGN.CENTER)
    text(s, x, TOP + Inches(1.35), Inches(2.86), Inches(0.5), small, 15, MUTED, align=PP_ALIGN.CENTER)
bullets(s, MARGIN, TOP + Inches(2.55), CONTENT_W, Inches(2.4), [
    "16 made-up but typical emails: registration, teams, rules, submissions, sponsors, judges, volunteers, "
    "logistics, visas, prizes, press, a withdrawal, a harassment report, a venue problem, a sales pitch, a Devpost notice.",
    "If the AI's answer is ever unusable, the email still appears, marked Not sorted: nothing is lost.",
    "The topic list and the priority rules can be adjusted to your event.",
], size=15)

# 12 --------------------------------------------------------------------------------------------
s = d.slide("Getting started", "From your mailboxes to a working inbox", (
    "Getting started takes three steps. First, connect your mailboxes: Gmail and any mailbox with IMAP "
    "today; Microsoft 365 can be added. Second, we create a login for each organiser, and an admin on "
    "your side can add more. Third, we check the topics and priorities against your event, and you go "
    "live. Before the event we send test emails through it together, so your team has seen it work."))
flow(s, TOP + Inches(0.2), [
    ("Connect mailboxes", "Gmail and any IMAP mailbox today; Microsoft 365 can be added. Your mailboxes stay as they are."),
    ("Team logins", "A login for each organiser; your admin adds or removes people any time."),
    ("Tune and go live", "We check topics and priorities against your event, send test emails together, and switch it on."),
], h=Inches(3.0), body_size=15)
text(s, MARGIN, TOP + Inches(3.6), CONTENT_W, Inches(0.5),
     "What we need from you: the mailboxes to connect, the list of organisers, and your event dates.", 16, TEXT, True)

d.save(HERE / "MailFlow-Client.pptx")
