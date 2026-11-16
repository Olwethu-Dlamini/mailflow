# Lesson 8: Microsoft 365

## Goal

Connect Microsoft 365 / Outlook mailboxes with `MailFlow · From <label> (M365)`, using an app
login from the company's Microsoft Entra, so no user password is stored.
Design: [SYSTEM-DESIGN.md §2.1 and §6](../SYSTEM-DESIGN.md#6-logins-and-setup-per-provider).

```
Microsoft Outlook Trigger → MailFlow shape → Process email
```

## What you need

- Lessons 2-4 done.
- A Microsoft 365 / Entra administrator. Send them this list (from
  [WHAT-I-NEED.md §3](../WHAT-I-NEED.md#microsoft-365-lesson-8)):
  1. Register an app called `MailFlow` in Microsoft Entra.
  2. Give it the **Mail.Read** *application* permission and grant **admin consent**.
  3. Restrict it to the MailFlow mailboxes only (Exchange application access rules), not every
     mailbox in the company.
  4. Send you the **tenant ID**, **client ID** and a **client secret**, with the secret's expiry
     date. Put a calendar reminder one month before it expires.
- Receive the secret privately (not by plain email, never in this repo).

## Steps

1. **Create Workflow** `MailFlow · From <label> (M365)`, tag `mailflow`.
2. Add **Microsoft Outlook Trigger**. **Event**: Message Received.
3. **Authentication**: **Microsoft Entra Service Principal (App-Only)**. Create a new credential
   named e.g. `M365 MailFlow app` and enter the tenant ID, client ID and client secret from the
   admin. App-Only means n8n signs in as the app, with no user sign-in.
4. Choose the mailbox to watch (the field the node shows for the user/mailbox; with App-Only you
   name the mailbox, since there is no signed-in user) and set the poll to **Every Minute**.
5. Click **Fetch test event** so one email appears in the output.
6. Add **Edit Fields (Set)** `MailFlow shape`, Manual Mapping, Include Other Input Fields off,
   8 String fields:

   > **Field names not verified.** n8n does not document this trigger's output. The names below
   > are Microsoft Graph's usual message fields. **Drag** each real field from the input panel;
   > if a name differs, use the dragged one.

   | Name | Likely value (confirm by dragging) |
   |---|---|
   | `message_id` | `{{ $json.internetMessageId }}` |
   | `mailbox` | your label, e.g. `support@` |
   | `source` | `outlook` |
   | `from_name` | `{{ $json.from.emailAddress.name }}` |
   | `from_address` | `{{ $json.from.emailAddress.address }}` |
   | `subject` | `{{ $json.subject }}` |
   | `received_at` | `{{ $json.receivedDateTime }}` |
   | `body` | `{{ $json.bodyPreview }}` |

   **Why `bodyPreview`:** the full body (`body.content`) is HTML. For v1, `bodyPreview` (a plain
   text start of the email) is enough for the AI and the page. Later you can add n8n's
   **Markdown** node (HTML to Markdown) on `body.content` for the full text.
7. Add **Execute Sub-workflow** `Process email` → `MailFlow · Process email`, map the 8 inputs,
   **Wait For Sub-Workflow Completion** off.
8. **Save**, **Active**. For the next M365 mailbox: Duplicate, pick the new mailbox in the
   trigger, change the `mailbox` label. The same credential works if the admin allowed that mailbox.

## Check it works

1. Send a test email to the mailbox.
2. Within about 2 minutes a row appears with `source` = `outlook`.
3. The email is still unread in Outlook. Delete the test row.

## If something goes wrong

| Problem | What to do |
|---|---|
| Credential fails with "unauthorized" / consent error | Admin consent was not granted, or the permission is *delegated* instead of *application*. Ask the admin. |
| Access denied to the mailbox | The admin's access rule does not include it. Ask them to add it. |
| Worked for months, then stopped | The client secret expired. Get a new one, update the credential. Errors also reach Telegram after lesson 9. |
| `from_address` empty | Field name differs; drag it from the trigger output. |

## What you learned

- App-Only logins use a tenant ID, client ID and secret; no user password lives in n8n.
- The admin should limit the app to the MailFlow mailboxes only.
- `bodyPreview` gives plain text without converting HTML; good enough for v1.
