# Lesson 2: Process email (the shared brain)

## Goal

Build `MailFlow · Process email`: one sub-workflow that every mailbox collector calls. It skips
emails already saved, tags obvious mail with simple rules, asks the AI about the rest, saves the
row, and sends a Telegram alert for urgent, negative emails.
Design: [SYSTEM-DESIGN.md §2.2 and §2.3](../SYSTEM-DESIGN.md#23-process-email-the-shared-brain),
picture: [workflows.png](../images/workflows.png).

When you are done the canvas looks like this:

```
When Executed by Another Workflow → Already saved? → Obvious mail? ─true──→ Rule tags ──────────┐
                                                                  └false─→ Sort with AI → AI tags ┴→ Save email → Urgent and angry? ─true→ Telegram alert
                                                                              ↑
                                                                      Ollama Chat Model
```

## What you need

- Lesson 1 done (`MailFlow emails` exists).
- Decisions D1 (categories), D2 (what "High" means), D3 (AI choice) and D8 (who gets alerts) from
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
   Mapping. **Include Other Input Fields**: off. Add these 14 fields (all String). The names must be
   exactly the table's column names:

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
   | `category` | `Newsletter` |
   | `sentiment` | `Neutral` |
   | `urgency` | `Low` |
   | `summary` | `{{ $json.subject }}` |
   | `sorted_by` | `rule` |
   | `status` | `new` |

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
     other categories in D1, change the `category` list here:

     ```json
     {
       "type": "object",
       "properties": {
         "category":  { "type": "string", "enum": ["Billing","Support","Sales","Internal","Newsletter","Other"], "description": "What the email is about" },
         "sentiment": { "type": "string", "enum": ["Positive","Neutral","Negative"], "description": "The sender's mood" },
         "urgency":   { "type": "string", "enum": ["High","Normal","Low"], "description": "High if it needs an answer today" },
         "summary":   { "type": "string", "description": "One short sentence, at most 15 words" }
       },
       "required": ["category","sentiment","urgency","summary"]
     }
     ```

9. Under `Sort with AI`, click the **Model** connector (+) and add **Ollama Chat Model**.
   - **Credential**: `Ollama (local)`.
   - **Model**: `mistral:latest`.
   - **Options** → **Add Option** → **Sampling Temperature** → `0`. Temperature 0 means the same
     email always gets the same answer.

10. After `Sort with AI` add **Edit Fields (Set)**. Rename it `AI tags`. Manual Mapping, **Include
    Other Input Fields** off. The AI node only outputs `output`, so the email's own fields are read
    back from the trigger node by name:

    | Name | Value |
    |---|---|
    | `message_id` | `{{ $('When Executed by Another Workflow').item.json.message_id }}` |
    | `mailbox` | `{{ $('When Executed by Another Workflow').item.json.mailbox }}` |
    | `source` | `{{ $('When Executed by Another Workflow').item.json.source }}` |
    | `from_name` | `{{ $('When Executed by Another Workflow').item.json.from_name }}` |
    | `from_address` | `{{ $('When Executed by Another Workflow').item.json.from_address }}` |
    | `subject` | `{{ $('When Executed by Another Workflow').item.json.subject }}` |
    | `received_at` | `{{ $('When Executed by Another Workflow').item.json.received_at }}` |
    | `body` | `{{ ($('When Executed by Another Workflow').item.json.body \|\| '').slice(0, 4000) }}` |
    | `category` | `{{ $json.output.category }}` |
    | `sentiment` | `{{ $json.output.sentiment }}` |
    | `urgency` | `{{ $json.output.urgency }}` |
    | `summary` | `{{ $json.output.summary }}` |
    | `sorted_by` | `ai` |
    | `status` | `new` |

    Tip: drag `output → category` etc. from the input panel rather than typing.

### E. Save and alert

11. Add a **Data Table** node. Rename it `Save email`. **Operation**: **Insert**. **Data table**:
    `MailFlow emails`. **Mapping Column Mode**: **Map Automatically**. This copies every field
    whose name equals a column name, which is why steps 7 and 10 used the exact column names.
12. Connect **both** `Rule tags` and `AI tags` into `Save email` (drag from each node's output
    dot to the same input).
13. After `Save email` add an **If** node `Urgent and angry?`, combinator **AND**:
    - `{{ $json.urgency }}` **is equal to** `High`
    - `{{ $json.sentiment }}` **is equal to** `Negative`

    The Insert node outputs the saved row. Run it once (section "Check") and confirm `urgency` and
    `sentiment` appear in its output; if they sit under another name, drag them from there.
14. On the **true** output add **Telegram** → **Send Message**. Rename it `Telegram alert`.
    - **Credential**: `RI Email`.
    - **Chat ID**: paste the chat ID you copied from `Format alert`.
    - **Text**:

      ```
      Urgent and negative email
      Mailbox: {{ $json.mailbox }}
      From: {{ $json.from_name }} <{{ $json.from_address }}>
      Subject: {{ $json.subject }}
      Summary: {{ $json.summary }}
      ```

15. **Save** the workflow. A sub-workflow must be saved and error-free before others can call it.
    Do not activate it: sub-workflows run when they are called.

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
   | Charged twice for November | false → `Sort with AI` | Billing · Negative · High; Telegram alert arrives | about **100 s** on the first run (the model is loading), about **25 s** on later runs |
   | November product newsletter | true → `Rule tags` | Newsletter · Neutral · Low, summary = subject, `sorted_by` = `rule` | instant |

   Measured on this server (design §5): first email after loading 99.1 s, then 22-30 s each.
   A long wait on the first run is normal, not a fault.
3. Open **Data tables** → `MailFlow emails`: two new rows with `status` = `new`.
4. Your phone gets one Telegram message, for the billing email only.
5. Click **Execute workflow** again. This time both items stop at `Already saved?` (no output),
   no new rows, no second alert. Duplicate protection works.
6. **Clean up**: in `MailFlow emails`, delete the two rows whose `mailbox` is `test@`. Then unpin
   the trigger's data (pin icon) so it does not linger, and **Save**.

## If something goes wrong

| Problem | What to do |
|---|---|
| `Sort with AI` runs for minutes | The first run loads Mistral (~100 s). If it goes past 3 minutes, Ollama may be busy with another workflow; it answers one request at a time. Wait and try again. |
| Error "could not parse" / output missing a field | Check Temperature is `0` and the schema was pasted whole, including `required`. |
| Row saved but `category` etc. are empty | A field name in `AI tags` or `Rule tags` does not match the column. Compare letter by letter with lesson 1. |
| Nothing after `Already saved?` | That `message_id` is already in the table. Delete the test rows or change the id. |
| No Telegram message | Check the chat ID was copied fully from `Format alert` and the credential is `RI Email`. Check `Urgent and angry?` used **AND**. |
| `received_at` error on insert | The value must be an ISO date like `2026-11-16T08:41:00+02:00`. Look at what the collector sent. |

## What you learned

- One shared sub-workflow keeps rules, AI and saving in one place for every mailbox.
- Cheap rules first, the slow AI only when needed; the Information Extractor returns a fixed set of fields.
- **Map Automatically** works only when field names equal column names.
