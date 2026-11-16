# Lesson 3: First mailbox: work mail (POP3)

## Goal

Send every new work email into `MailFlow · Process email`. The old work server is read over POP3
by `mail-poll` on the server, which already posts each new email to the live workflow
`Work email · Telegram`. You add a **second branch** to that workflow; the existing Telegram alert
keeps working exactly as before. Design: [SYSTEM-DESIGN.md §2.1](../SYSTEM-DESIGN.md#21-collectors-one-per-mailbox)
("Why a separate POP3 path"), picture: [architecture.png](../images/architecture.png).

```
New work email ─┬→ Format alert → Send alert            (already there, do not change)
                └→ MailFlow shape → Process email        (new)
```

## What you need

- Lesson 2 done and its check passed.
- Access to send a test email to the work mailbox from another account.
- Do **not** touch `mail-poll` on the server. Nothing changes there.

> **Warning: this edits a live workflow.** Real work mail flows through it every minute. Make a
> backup copy first (step 1), work carefully, and save only when the branch is complete.

## Steps

1. Open **Overview**, find `Work email · Telegram`, open its **⋯** menu and choose **Duplicate**.
   Name the copy `Work email · Telegram (backup)`. Leave the copy **inactive**. If anything goes
   wrong you can restore from it.
2. Open the live `Work email · Telegram`. Its first node is the Webhook `New work email`.
3. Drag from the output dot of `New work email` to an empty spot and add **Edit Fields (Set)**.
   A node output may connect to several nodes; each gets its own copy of the item. Rename the new
   node `MailFlow shape`.
4. In `MailFlow shape`: **Mode** Manual Mapping, **Include Other Input Fields** off. Add these 8
   String fields. mail-poll puts everything under `$json.body`; keys with a hyphen need square
   brackets.

   | Name | Value (expression) |
   |---|---|
   | `message_id` | `{{ $json.body['message-id'] }}` |
   | `mailbox` | `work@` (fixed text: the short label you want on the page) |
   | `source` | `pop3` |
   | `from_name` | see below |
   | `from_address` | see below |
   | `subject` | `{{ $json.body.subject }}` |
   | `received_at` | `{{ DateTime.fromRFC2822($json.body.date).toISO() }}` |
   | `body` | `{{ $json.body.body }}` |

   The `from` value looks like `Sipho Mamba <sipho@example.com>`. Split it with these two
   expressions:

   `from_name`:

   ```
   {{ $json.body.from.includes('<') ? $json.body.from.split('<')[0].trim().replace(/^"|"$/g, '') : '' }}
   ```

   `from_address`:

   ```
   {{ ($json.body.from.match(/<([^>]+)>/) || [null, $json.body.from])[1].trim().toLowerCase() }}
   ```

   The first takes the text before `<` and removes quotes. The second takes the text between `<`
   and `>`, or the whole value if there are no brackets. mail-poll already cuts `body` to 1,500
   characters, below the 4,000 limit.
5. After `MailFlow shape` add **Execute Sub-workflow**. Rename it `Process email`.
   - **Workflow**: **From list** → `MailFlow · Process email`.
   - The 8 input fields appear. Fill each with the same name from the input panel, e.g.
     `message_id` = `{{ $json.message_id }}` (drag each one).
   - **Options** → **Wait For Sub-Workflow Completion**: **off**. The AI takes ~25 s or more; with
     this off, the work-email workflow does not wait for it, so the Telegram alert is not slowed
     down.
6. Open workflow **Settings** and add the tag `mailflow` if you like (the name stays the same).
7. **Save**. The workflow is already active, so the new branch is live from now on.

### Optional: test in the editor first (before step 7)

Pin sample data on `New work email` (output panel → **Edit Output**) and click **Execute
workflow**. Pinned data is used only in editor runs, never by real mail.

```json
[
  {
    "headers": {},
    "params": {},
    "query": {},
    "body": {
      "from": "Sipho Mamba <sipho@example.com>",
      "to": "work@example.com",
      "cc": "",
      "reply-to": "",
      "subject": "Charged twice for November",
      "date": "Mon, 16 Nov 2026 08:41:00 +0200",
      "message-id": "<test-pop3-1@mail.example.com>",
      "references": "",
      "body": "My card was debited twice for invoice INV-2291. Please refund one payment today.",
      "body_truncated": false
    }
  }
]
```

Check `MailFlow shape`'s output: `from_name` = `Sipho Mamba`, `from_address` =
`sipho@example.com`, `received_at` = `2026-11-16T08:41:00.000+02:00`. Note this test also runs
the existing `Format alert → Send alert` branch, so you will get the normal work-mail alert too.
Then **unpin** the data, delete the test row from `MailFlow emails`, and save.

## Check it works

1. From another account, send an email to the work mailbox, e.g. subject `MailFlow test 1`.
2. Within about **2 minutes** (mail-poll checks every minute, plus ~25-100 s of AI) a row with
   that subject appears in `MailFlow emails`, `mailbox` = `work@`, `source` = `pop3`.
3. The normal work-mail Telegram alert still arrives as before.
4. Delete the test row.

Successful live runs are not saved on this server, so the table is where you look, not
**Executions**.

## If something goes wrong

| Problem | What to do |
|---|---|
| The old Telegram alert stopped | Open the workflow, check `Format alert → Send alert` are still connected. If unsure, deactivate it, activate `Work email · Telegram (backup)` instead, and ask. |
| No row after 5 minutes | Look in **Executions** for a failed run of `Work email · Telegram` or `MailFlow · Process email`. |
| `received_at` is empty or invalid | The `date` header had an odd format. Look at the raw `date` value in an editor test and adjust. |
| `from_address` contains the name too | The `from` value had no `<...>`. Check the expression copied fully. |
| "Workflow not found / cannot be called" | Save `MailFlow · Process email` and check its **This workflow can be called by** setting. |

## What you learned

- One node output can feed two branches; each branch gets its own copy of the item.
- A collector's only job is to reshape fields into the common shape and hand them on.
- **Wait For Sub-Workflow Completion** off lets the caller finish without waiting for slow work.
