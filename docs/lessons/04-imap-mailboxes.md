# Lesson 4: IMAP mailboxes

## Goal

Build one collector per IMAP mailbox: `MailFlow · From <label> (IMAP)`. It notices new mail,
reshapes it into the common shape and hands it to `MailFlow · Process email`. Then copy it for
every other IMAP mailbox. Design: [SYSTEM-DESIGN.md §2.1](../SYSTEM-DESIGN.md#21-collectors-one-per-mailbox),
picture: [workflows.png](../images/workflows.png).

```
Email Trigger (IMAP) → MailFlow shape → Process email
```

## What you need

- Lessons 2 and 3 done.
- For each IMAP mailbox (from your private list, [WHAT-I-NEED.md §3](../WHAT-I-NEED.md#3-logins-per-type)):
  server name, port (usually 993), user name, password or app password, and a short label such as
  `accounts@`. Keep these out of this repo; they go only into the n8n credential.

## Steps

1. **Create Workflow**. Name it `MailFlow · From accounts@ (IMAP)` (use your label). Tag `mailflow`.
2. Add the trigger **Email Trigger (IMAP)**.
3. **Credential** → **Create new** (type IMAP): **User**, **Password**, **Host**, **Port** `993`,
   **SSL/TLS** on. Name the credential after the label, e.g. `IMAP accounts@`. **Save**; n8n tests
   the login.
4. Node settings:
   - **Mailbox Name**: `INBOX`.
   - **Action**: **None**. This leaves emails unread, so people still see them as new in their
     mail app. Never choose Mark as Read.
   - **Download Attachments**: off (v1 does not use attachments).
   - **Format**: **Resolved** (the email is parsed into fields).
   - Leave **Custom Email Rules** empty: the default fetches unread (UNSEEN) mail.
5. Click **Execute step** (or **Fetch test event**) and, if needed, send a test email to the
   mailbox so one item appears. You need a real item in the output to see the field names.
6. Add **Edit Fields (Set)** after the trigger. Rename it `MailFlow shape`. Manual Mapping,
   **Include Other Input Fields** off. Add the 8 String fields:

   > **Field names not verified.** n8n does not document the exact field names of the IMAP
   > trigger's Resolved format. The names below are what it is expected to give. For each one,
   > look at the trigger's output in the input panel and **drag** the real field into the value
   > box instead of typing. If a name differs, use the dragged one.

   | Name | Expected value (confirm by dragging) |
   |---|---|
   | `message_id` | `{{ $json.messageId }}` |
   | `mailbox` | `accounts@` (fixed text: your label) |
   | `source` | `imap` |
   | `from_name` | `{{ $json.from.value[0].name }}` |
   | `from_address` | `{{ $json.from.value[0].address }}` |
   | `subject` | `{{ $json.subject }}` |
   | `received_at` | `{{ new Date($json.date).toISOString() }}` |
   | `body` | see below |

   For `body`, use the plain text, or the HTML with tags stripped when there is no plain text,
   cut to 4,000 characters:

   ```
   {{ ($json.text || ($json.html || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')).slice(0, 4000) }}
   ```

   If an email has no Message-ID, `message_id` comes out empty and duplicate checks stop working
   for it. That is rare; if you see it, ask for a fallback expression.
7. Add **Execute Sub-workflow**, rename it `Process email`. **Workflow**: From list →
   `MailFlow · Process email`. Map the 8 inputs from the input panel (`{{ $json.message_id }}`
   and so on). **Options** → **Wait For Sub-Workflow Completion**: off.
8. **Save**, then switch the workflow to **Active** (toggle top right).

### Copy it for the next IMAP mailbox

1. **Overview** → ⋯ on the workflow → **Duplicate**. Name it `MailFlow · From <next label> (IMAP)`.
2. In the trigger, create a new IMAP credential for that mailbox.
3. In `MailFlow shape`, change `mailbox` to the new label.
4. **Save**, **Active**. About 5 minutes per mailbox.

## Check it works

1. Send a test email to the mailbox from another account.
2. Within about 2 minutes a row appears in `MailFlow emails` with your label and `source` = `imap`.
3. Open the mailbox in a normal mail app: the test email is still **unread**.
4. Delete the test row.

## If something goes wrong

| Problem | What to do |
|---|---|
| Credential test fails | Check host, port 993 and SSL. Many providers need an **app password**, not the normal one. |
| Active, but nothing arrives | Some servers do not push new mail (IMAP IDLE). Try **Force Reconnect Every Minutes** in the options. The old work server is the known example; that is why it uses POP3. |
| `from_address` or `subject` empty | The field name differs from the expected one. Drag it from the trigger output. |
| Emails got marked as read | **Action** is not **None**. Fix it. |
| Mail read in an app while n8n was down is missing | Expected: the trigger fetches unread mail only (design §2.1). |

## What you learned

- Each provider needs its own collector, but all collectors end the same way.
- **Action: None** keeps MailFlow invisible to mailbox users.
- When field names are not documented, drag them from the input panel.
