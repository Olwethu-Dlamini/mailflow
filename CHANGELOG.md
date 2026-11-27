# Changelog

All notable changes to MailFlow. Dates are YYYY-MM-DD.

## Unreleased

## 1.0.0 - 2026-11-27

The first release. It covers the work from 2026-11-16 to 2026-11-27.

### Added

- **n8n workflows.** One collector per mailbox (IMAP, Gmail, Microsoft 365, or a webhook for
  POP3), and a shared Process email workflow. Process email skips duplicates, sorts obvious mail
  with rules and asks an AI about the rest. Each email gets a topic, a sender type, a priority
  (P1 to P3), needs-a-reply, a one-line summary and a next step. An email the AI cannot sort is
  saved as *Not sorted*. The labels fit a hackathon organiser.
- **Email table.** One row per email in an n8n data table, with the first 4,000 characters of the
  body.
- **Alerts and cleanup.** Telegram alerts for P1 emails and for any failed workflow. A nightly
  Cleanup workflow deletes emails older than 90 days.
- **Web app.** A FastAPI app with one account per person. It has a queue with views (Needs reply,
  Mine, P1, Waiting, Done, Everything), search, and mailbox, topic and sender filters. Statuses
  are open, waiting and done, with Undo.
- **Layout.** Sidebar, list and open email in three panes, a dark theme and a phone layout.
  Keyboard shortcuts cover moving and triage. After Done or Waiting the next email opens.
- **Replies from the page.** Gmail replies go through n8n. Any other mailbox can reply over SMTP
  from the app, in the same conversation.
- **Who has it.** Staff take an email or let it go; admins give emails to anyone. Each email has
  an activity log of who did what. People can correct the AI's priority, topic and needs-a-reply.
- **Integrations page for admins.** Connect an IMAP mailbox (Gmail, Microsoft 365 or another
  provider), pause or remove collectors, and set up SMTP replies. Choose the AI: Mistral on your
  own server (Ollama), Groq, OpenAI, Mistral cloud or Anthropic. Set the Telegram alerts.
  Process email is backed up in the app before every change.
- **Continue with Google** sign-in, optional, for accounts an admin already added.
- **Public landing page** at `/` and a short guide inside the app.
- **Speed.** The last 30 days are kept in memory and the page arrives with the list. Status
  changes apply at once and save in the background. Static files carry a content hash and are
  cached for a year. Long lists render in pages.
- **Deploy.** A Docker container and compose file, a one-command deploy script with checks, and a
  script to publish the site through a Cloudflare tunnel and Caddy. A `mailflow user` command
  manages accounts on the server.
- **Install for a new customer.** The time zone, the repository, folders, address and port are
  settings instead of values for one server; the n8n workflows and the emails table are in `n8n/`
  with import steps; a backup script for the app's database and settings
  (`app/deploy/backup.sh`); a note on personal data for buyers (`docs/DATA-PROTECTION.md`).
- **Tests.** API and unit tests, and browser tests in Chrome against made-up emails
  (`deck/demo_server.py`).
- **Docs.** System design, an as-built page, lessons 0 to 10 for building it in n8n, client and
  technical decks, Lighthouse reports.

### Security

- Passwords hashed with scrypt, at least 12 characters. At most 2 checked at a time.
- 5 failed sign-ins lock an email and 20 lock an IP address for 15 minutes. Each attempt is
  counted before the password is checked.
- Session cookie `__Host-mf_session`: HttpOnly, Secure, SameSite=Strict. Sessions end after 12
  hours idle, 7 days, sign-out, a password change or when the account is disabled.
- Every change needs the `X-MailFlow` header and the site's own origin. Strict Content Security
  Policy, no inline script. Email text is always shown as text. The queue page is never cached.
- Google sign-in uses state, nonce and PKCE, links an account only where Google owns the address,
  and then matches on Google's account id.
- SMTP passwords are sealed with `MAILFLOW_SECRET_KEY`. Mailbox passwords, AI keys and the bot
  token stay in n8n's encrypted credentials. The n8n API key never reaches the browser.
- The Reply webhook needs a secret header and a well-formed Message-ID.
- Sender headers are cut to a sane length and emails dated in the future are kept out of the list.
- The container runs read-only, as a non-root user, without Linux capabilities, in 128 MB. Its
  port is published on one LAN address only, and the public site accepts only the tunnel.
- Findings from a security audit and from code reviews were fixed before this release.
