# Lesson 2: Process email (the shared brain)

## Goal

Build `MailFlow · Process email`: one sub-workflow that every mailbox collector calls. It skips
emails already saved, tags obvious mail with simple rules, asks the AI about the rest, saves the
row, and sends a Telegram alert for every P1 email (answer today).
Design: [SYSTEM-DESIGN.md §2.2 and §2.3](../SYSTEM-DESIGN.md#23-process-email-the-shared-brain),
picture: [workflows.png](../images/workflows.png).

When you are done the canvas looks like this:

```
When Executed by Another Workflow → Has message id? → Already saved? → Obvious mail? ─true──→ Rule tags ─────────────────────────┐
                                                                                   └false─→ Sort with AI ─→ Email + AI answer → AI tags ┴→ Save email → P1? ─true→ Telegram alert
                                                                                        └──────────────────↗        ↑
                                                                                                         Ollama Chat Model (under Sort with AI)
```

## What you need

- Lesson 1 done (`MailFlow emails` exists).
- Decisions D1 (types), D2 (what P1, P2 and P3 mean), D3 (AI choice) and D8 (who gets alerts) from
  [WHAT-I-NEED.md](../WHAT-I-NEED.md). This lesson uses the defaults.
- Credentials that already exist in n8n: `Ollama (local)` and `RI Email` (Telegram).
- Your Telegram chat ID: open the live workflow `Work email · Telegram`, open the Code node
  `Format alert`, and copy the chat ID from there. Do **not** write it anywhere outside n8n.

## Steps

### A. The workflow and its input

1. **Create Workflow**. Name it `MailFlow · Process email`. Add the tag `mailflow`.
2. **Add first step** → search **When Executed by Another Workflow** (the Execute Sub-workflow
   Trigger).
3. Set **Input data mode** to **Define using fields below**. Add these 8 fields, all of type
   **String** (this is the common shape every collector sends, design §2.2):

   `message_id`, `mailbox`, `source`, `from_name`, `from_address`, `subject`, `received_at`, `body`

4. Open the workflow **Settings** (⋯ menu → **Settings**) and check **This workflow can be called
   by** allows your other workflows (the default, workflows in the same project, is fine if all
   MailFlow workflows live in one place).

   4b. Add a **Filter** node right after the trigger. Rename it `Has message id?`. Condition:
   `{{ $json.message_id }}` **String → is not empty**. This stops a test run with no email (for
   example clicking **Execute workflow** with nothing pinned) from saving an empty row: that
   happened once on 2026-11-16.

### B. Skip emails already saved

5. Add a **Data Table** node. Rename it `Already saved?`.
   - **Resource**: Row. **Operation**: **If Row Does Not Exist**.
   - **Data table**: From list → `MailFlow emails`.
   - Condition: `message_id` **Equals** `{{ $json.message_id }}`.

   If no row has this `message_id`, the item passes through unchanged. If the email is already in
   the table, nothing comes out and the run stops here. So a collector that sends the same email
   twice does no harm.

### C. Obvious mail: rules, no AI

6. Add an **If** node. Rename it `Obvious mail?`. Add four conditions, each **String → contains**,
   and set the combinator at the top to **OR** (any condition is enough):

   | Value 1 (expression) | Operator | Value 2 |
   |---|---|---|
   | `{{ ($json.body \|\| '').toLowerCase() }}` | contains | `unsubscribe` |
   | `{{ ($json.from_address \|\| '').toLowerCase() }}` | contains | `noreply` |
   | `{{ ($json.from_address \|\| '').toLowerCase() }}` | contains | `no-reply` |
   | `{{ ($json.from_address \|\| '').toLowerCase() }}` | contains | `newsletter` |

   `||` means "or, if empty, use". (Reading this file as raw text? Ignore the `\` before each `|`
   in the tables of this lesson; it is only there so the table displays.)
   `.toLowerCase()` makes "Unsubscribe" and "UNSUBSCRIBE" match too.

7. On the **true** output add **Edit Fields (Set)**. Rename it `Rule tags`. **Mode**: Manual
   Mapping. **Include Other Input Fields**: off. Add these 16 fields (all String except
   `needs_reply`, which is **Boolean**). The names must be exactly the table's column names:

   | Name | Value |
   |---|---|
   | `message_id` | `{{ $json.message_id }}` |
   | `mailbox` | `{{ $json.mailbox }}` |
   | `source` | `{{ $json.source }}` |
   | `from_name` | `{{ $json.from_name }}` |
   | `from_address` | `{{ $json.from_address }}` |
   | `subject` | `{{ $json.subject }}` |
   | `received_at` | `{{ $json.received_at }}` |
   | `body` | `{{ ($json.body \|\| '').slice(0, 4000) }}` |
   | `type` | `{{ /no-?reply/i.test($json.from_address \|\| '') ? 'Notification' : 'Marketing' }}` |
   | `priority` | `P3` |
   | `mood` | `Neutral` |
   | `needs_reply` | `false` |
   | `summary` | `{{ $json.subject }}` |
   | `next_step` | `No reply needed` |
   | `sorted_by` | `rule` |
   | `status` | `open` |

   Mail from a `noreply` / `no-reply` sender is an automatic **Notification**; the rest caught
   here (newsletters, anything with "unsubscribe") is **Marketing**. Neither needs a reply.

### D. Everything else: ask the AI

8. On the **false** output of `Obvious mail?` add **Information Extractor**. Rename it
   `Sort with AI`.
   - **Text** (expression):

     ```
     From: {{ $json.from_name }} <{{ $json.from_address }}>
     Subject: {{ $json.subject }}

     {{ ($json.body || '').slice(0, 4000) }}
     ```

   - **Schema Type**: **Define using JSON Schema**. Paste this schema (design §2.3). If you chose
     other types in D1, change the `type` list here (and `TYPES` in lesson 5):

     ```json
     {
       "type": "object",
       "properties": {
         "type": {"type": "string", "enum": ["Complaint", "Question", "Request", "Order", "Payment", "Technical", "Cancellation", "Feedback", "Marketing", "Notification", "Other"], "description": "What the sender wants. Complaint: unhappy about something that went wrong. Question: asks for information. Request: asks us to do or change something. Order: wants to buy or asks for a quote. Payment: invoices, charges, refunds. Technical: something does not work. Cancellation: wants to stop a service. Feedback: praise or suggestions. Marketing: newsletters and promotions. Notification: automatic messages from systems. Other: anything else."},
         "priority": {"type": "string", "enum": ["P1", "P2", "P3"], "description": "P1: answer today (angry customer, service down, money taken wrongly, threat to cancel or leave, legal). P2: answer this week (normal customer questions, requests, orders). P3: no rush or no answer needed (thanks, newsletters, notifications)."},
         "mood": {"type": "string", "enum": ["Angry", "Frustrated", "Neutral", "Happy"], "description": "The sender's mood"},
         "needs_reply": {"type": "boolean", "description": "true if a person must answer this email, false for automatic messages, newsletters and simple thank-yous"},
         "summary": {"type": "string", "description": "What the email says, one short sentence, at most 15 words"},
         "next_step": {"type": "string", "description": "What our staff should do next, at most 12 words, starting with a verb"}
       },
       "required": ["type", "priority", "mood", "needs_reply", "summary", "next_step"]
     }
     ```

     The descriptions are the instructions the model reads: P1 means answer today (angry
     customer, service down, money taken wrongly, threat to cancel, legal), P2 this week, P3 no
     rush. `next_step` tells staff what to do, starting with a verb.

9. Under `Sort with AI`, click the **Model** connector (+) and add **Ollama Chat Model**.
   - **Credential**: `Ollama (local)`.
   - **Model**: `mistral:latest`.
   - **Options** → **Add Option** → **Sampling Temperature** → `0`. Temperature 0 means the same
     email always gets the same answer.

10. Add a **Merge** node. Rename it `Email + AI answer`. **Mode**: Combine. **Combine By**:
    Position.
    - Connect the **false** output of `Obvious mail?` to its **Input 1** (a second line from the
      same output; the first still goes to `Sort with AI`).
    - Connect `Sort with AI` to its **Input 2**.

    The AI node only outputs `output`. The Merge puts each email and its AI answer back together,
    first with first, second with second, so nothing gets mixed up when several emails arrive at
    once.

11. After the Merge add **Edit Fields (Set)**. Rename it `AI tags`. Manual Mapping, **Include
    Other Input Fields** off. Now everything is in `$json`. All fields are String except
    `needs_reply`, which is **Boolean**:

    | Name | Value |
    |---|---|
    | `message_id` | `{{ $json.message_id }}` |
    | `mailbox` | `{{ $json.mailbox }}` |
    | `source` | `{{ $json.source }}` |
    | `from_name` | `{{ $json.from_name }}` |
    | `from_address` | `{{ $json.from_address }}` |
    | `subject` | `{{ $json.subject }}` |
    | `received_at` | `{{ $json.received_at }}` |
    | `body` | `{{ ($json.body \|\| '').slice(0, 4000) }}` |
    | `type` | `{{ $json.output.type }}` |
    | `priority` | `{{ $json.output.priority }}` |
    | `mood` | `{{ $json.output.mood }}` |
    | `needs_reply` | `{{ $json.output.needs_reply }}` |
    | `summary` | `{{ $json.output.summary }}` |
    | `next_step` | `{{ $json.output.next_step }}` |
    | `sorted_by` | `ai` |
    | `status` | `open` |

    Tip: drag `output → type` etc. from the input panel rather than typing.

### E. Save and alert

12. Add a **Data Table** node. Rename it `Save email`. **Operation**: **Insert**. **Data table**:
    `MailFlow emails`. **Mapping Column Mode**: **Map Automatically**. This copies every field
    whose name equals a column name, which is why steps 7 and 11 used the exact column names.
13. Connect **both** `Rule tags` and `AI tags` into `Save email` (drag from each node's output
    dot to the same input).
14. After `Save email` add an **If** node `P1?` with one condition:
    `{{ $json.priority }}` **String → is equal to** `P1`.

    The Insert node outputs the saved row. Run it once (section "Check") and confirm `priority`
    appears in its output; if it sits under another name, drag it from there.
15. On the **true** output add **Telegram** → **Send Message**. Rename it `Telegram alert`.
    - **Credential**: `RI Email`.
    - **Chat ID**: paste the chat ID you copied from `Format alert`.
    - **Text**:

      ```
      🔴 P1 email: answer today
      Mailbox: {{ $json.mailbox }} · {{ $json.type }} · {{ $json.mood }}
      From: {{ $json.from_name }} <{{ $json.from_address }}>
      Subject: {{ $json.subject }}
      {{ $json.summary }}
      Next: {{ $json.next_step }}
      ```

16. **Save** the workflow, then switch it **Active** (publish it). On this n8n version a workflow
    that calls it can only be published once this one is: n8n refused with "references workflow …
    which is not published. Please publish all referenced sub-workflows first." (seen 2026-11-16).
    Being active does not make it run by itself; it still only runs when a collector calls it.

## Check it works

Test with two made-up emails instead of real mail.

1. Open **When Executed by Another Workflow**. In its output panel choose to edit the output
   (pencil icon / **Edit Output**), paste the JSON below, and **Save**. The data is now pinned.

   ```json
   [
     {
       "message_id": "<test-billing-1@mail.example.com>",
       "mailbox": "test@",
       "source": "imap",
       "from_name": "Sipho Mamba",
       "from_address": "sipho@example.com",
       "subject": "Charged twice for November",
       "received_at": "2026-11-16T08:41:00+02:00",
       "body": "Hello,\n\nMy card was debited twice for the November invoice INV-2291. This is the second time this happens. I want one payment refunded today, or I will cancel my contract.\n\nSipho"
     },
     {
       "message_id": "<test-news-1@mail.example.com>",
       "mailbox": "test@",
       "source": "imap",
       "from_name": "Example Router Co",
       "from_address": "newsletter@example.com",
       "subject": "November product newsletter",
       "received_at": "2026-11-16T07:00:00+02:00",
       "body": "New firmware, webinar dates and our holiday schedule.\n\nTo stop these emails, click unsubscribe."
     }
   ]
   ```

2. Click **Execute workflow**. Expected:

   | Email | Path | Result | Time |
   |---|---|---|---|
   | Charged twice for November | false → `Sort with AI` | P1 · Complaint · Angry, needs a reply, next step like "Refund one payment today"; Telegram alert arrives | up to a few minutes on the first run (the model is loading), about **40-60 s** on later runs |
   | November product newsletter | true → `Rule tags` | P3 · Marketing · Neutral, no reply needed, summary = subject, `sorted_by` = `rule` | under a second |

   Measured on this server with this schema (design §5): four AI-sorted test emails took 226 s
   together including the model load, about 40-60 s each once loaded. The earlier, shorter
   4-field schema took 22-30 s; the longer answer (summary plus next step) costs the extra time.
   A long wait on the first run is normal, not a fault.
3. Open **Data tables** → `MailFlow emails`: two new rows with `status` = `open`.
4. Your phone gets one Telegram message ("🔴 P1 email: answer today"), for the billing email only.
5. Click **Execute workflow** again. This time both items stop at `Already saved?` (no output),
   no new rows, no second alert. Duplicate protection works.
6. **Clean up**: in `MailFlow emails`, delete the two rows whose `mailbox` is `test@`. Then unpin
   the trigger's data (pin icon) so it does not linger, and **Save**.

## If something goes wrong

| Problem | What to do |
|---|---|
| `Sort with AI` runs for minutes | The first run loads Mistral (~100 s), then each email takes 40-60 s. If one email goes past 3 minutes, Ollama may be busy with another workflow; it answers one request at a time. Wait and try again. |
| Error "could not parse" / output missing a field | Check Temperature is `0` and the schema was pasted whole, including `required`. |
| Row saved but `type`, `priority` etc. are empty | A field name in `AI tags` or `Rule tags` does not match the column. Compare letter by letter with lesson 1. |
| Nothing after `Already saved?` | That `message_id` is already in the table. Delete the test rows or change the id. |
| No Telegram message | Check the chat ID was copied fully from `Format alert` and the credential is `RI Email`. Check `P1?` compares `{{ $json.priority }}` with `P1` (capital P). |
| `received_at` error on insert | The value must be an ISO date like `2026-11-16T08:41:00+02:00`. Look at what the collector sent. |

## What you learned

- One shared sub-workflow keeps rules, AI and saving in one place for every mailbox.
- Cheap rules first, the slow AI only when needed; the Information Extractor returns a fixed set of fields.
- **Map Automatically** works only when field names equal column names.
