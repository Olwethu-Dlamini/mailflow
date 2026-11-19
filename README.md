# MailFlow

All mailboxes in one place, each email sorted for a hackathon organiser (**topic**, **sender**,
**priority**, whether it **needs a reply** and the **next step**), worked by the team on one web page,
`https://mailflow.22112002.xyz`, each with their own login. **n8n** is the engine (collects, sorts
with the AI on the company's own server, sends replies); the page is a small web app in [`app/`](app/).

![How MailFlow fits together](docs/images/architecture.png)

| Start here | What it is |
|---|---|
| [docs/AS-BUILT.md](docs/AS-BUILT.md) | What is running now: the as-built overview and a drawing of every live n8n workflow |
| [docs/SYSTEM-DESIGN.md](docs/SYSTEM-DESIGN.md) | How it works, the data, the AI (with measured speeds), security, rollout, decisions |
| [docs/WHAT-I-NEED.md](docs/WHAT-I-NEED.md) | Decisions and logins to collect before and during the build |
| [docs/lessons/](docs/lessons/) | Step-by-step lessons for building it yourself in n8n, one working piece per lesson |
| [app/](app/) | The MailFlow web app: logins, the queue, replies; how to run and deploy it |
| [deck/MailFlow.pdf](deck/MailFlow.pdf) | The presentation (also `deck/MailFlow.pptx` to edit) |

**This repo is public.** It holds the design, lessons, pictures, deck and the web app's code. Never
commit mailbox addresses, passwords, API keys, `.env` files, email content or workflow exports here;
exports go in the private `n8n-chatbot` repo, secrets only in `/opt/mailflow/app/.env` on `ai`.
