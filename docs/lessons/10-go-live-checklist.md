# Lesson 10: Go-live checklist

## Goal

Check every piece once, save the workflows to the private repo, and run one real test per mailbox
type. When every line below is ticked, MailFlow is live. Design:
[SYSTEM-DESIGN.md §8-10](../SYSTEM-DESIGN.md#8-operations), picture: [rollout.png](../images/rollout.png).

## What you need

- Lessons 1-9 done.
- Your helper, for the server items (Caddy rule, `OLLAMA_KEEP_ALIVE`, exports).
- About one hour.

## Steps

Go down the table. Tick each line only when you have looked at it yourself.

| # | Check | Where | Done |
|---|---|---|---|
| 1 | Every collector (`MailFlow · From … (IMAP/Gmail/M365)`), `Work email · Telegram`, `MailFlow · Inbox page`, `MailFlow · Email page` and `MailFlow · Cleanup` are **Active** | Overview, the toggle on each | ☐ |
| 2 | Every MailFlow workflow (and `Work email · Telegram`) has **Error workflow** = `MailFlow · Errors` | Each workflow → Settings | ☐ |
| 3 | Every Gmail Trigger: **Read Status** = Unread and read emails, **Simplify** off | Gmail collectors | ☐ |
| 4 | Every Email Trigger (IMAP): **Action** = None, Download Attachments off | IMAP collectors | ☐ |
| 5 | Every Execute Sub-workflow: **Wait For Sub-Workflow Completion** off | All collectors | ☐ |
| 6 | Page password set: both page Webhooks use **Basic Auth** `MailFlow page login`, with a long password | Inbox page, Email page (both triggers) | ☐ |
| 7 | **Caddy rule decided** (D6): tailnet only → the rule blocking `/webhook/mailflow*` from the internet is in place and tested from outside the tailnet | Helper, srv1 | ☐ |
| 8 | **`OLLAMA_KEEP_ALIVE` decided**: `30m` in `/opt/automation/.env` and redeployed, or knowingly left at `2m` | Helper, server `ai` | ☐ |
| 9 | Test rows deleted from `MailFlow emails` (`mailbox` = `test@` and other tests) | Data tables | ☐ |
| 10 | No throwaway workflows left (`Practice · delete me`, `MailFlow · error test`); the `Work email · Telegram (backup)` copy kept **inactive** | Overview | ☐ |
| 11 | **Exports saved** to the private `n8n-chatbot` repo: add `"MailFlow": "mailflow"` to the project list in `tools/n8n-sync.py`, run it, check the `mailflow/` folder has every MailFlow workflow, and that the files name credentials only (no passwords) | Private repo, with your helper | ☐ |
| 12 | **One end-to-end test per mailbox type** (below) passed | — | ☐ |

### End-to-end test per mailbox type

For each type you use (POP3 work mail, IMAP, Gmail, Microsoft 365), send one email from an outside
account to one mailbox of that type, then:

1. Within about 2 minutes it is on the inbox page with the right mailbox label.
2. Its type, priority, mood, summary and next step look right; open it, the body is readable.
3. Click **Replied · waiting on customer**, then **Done**; it moves to **Waiting on customer**, then to **Done**.
4. In the mail app, the email is still there and unread.

Also send one angry test email that needs an answer today (like the billing example in lesson 2)
to any mailbox: it is sorted P1 and the "🔴 P1 email: answer today" Telegram alert arrives. Afterwards delete the test rows.

## Check it works

All 12 lines ticked; every end-to-end test passed.

## What to watch in the first week

| What | How | Act when |
|---|---|---|
| Is mail arriving? | Inbox page, **Everything** view: the newest email is at the top | Older than you expect for a working day: check **Executions** for failures |
| Failures | Telegram error messages; n8n → **Executions** (only failed runs are kept on this server) | Any repeated error: fix the node it names |
| AI speed | How long emails take to appear in busy mornings | Often more than ~10 minutes behind: raise `OLLAMA_KEEP_ALIVE`, add rules, or consider a cloud model (D3/D4) |
| Sorting quality | Skim types, priorities and moods daily | The same kind of email keeps landing wrong (e.g. a real complaint as P3): sharpen the `type` or `priority` `description` in the schema (lesson 2) |
| Rules catching too much | **Everything** view, filter Type **Marketing** / **Notification**: anything important there? | Narrow the `Obvious mail?` conditions |
| Duplicates | Same email twice in the list | Check `message_id` is filled in that collector |
| Table size | Data tables view | Growing fast: ask your helper to raise `N8N_DATA_TABLES_MAX_SIZE_BYTES` to 1 GiB |
| Secrets expiring | Calendar reminder for the Microsoft client secret; Gmail External logins expire every 7 days | Renew before they lapse |

## If something goes wrong

| Problem | What to do |
|---|---|
| A collector is active but silent | Re-run that mailbox's lesson **Check it works**; look in **Executions**. |
| The page opens from outside the tailnet | The Caddy rule is not in place (line 7). |
| Exports contain a password | Stop; do not push. Tell your helper. Exports must name credentials only. |

## What you learned

- Going live is a checklist, not a feeling: each line is something you saw yourself.
- Saved exports in the private repo let you rebuild or roll back a workflow.
- The first week is for watching speed, sorting quality and errors, then adjusting.
