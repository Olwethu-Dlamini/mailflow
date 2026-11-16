# Lesson 7: Gmail and Google Workspace

## Goal

Connect a Gmail or Google Workspace mailbox with a collector `MailFlow · From <label> (Gmail)`.
Most of the work is a one-time Google Cloud setup so n8n may read the mailbox.
Design: [SYSTEM-DESIGN.md §2.1 and §6](../SYSTEM-DESIGN.md#6-logins-and-setup-per-provider).

```
Gmail Trigger → MailFlow shape → Process email
```

## What you need

- Lessons 2-4 done.
- From [WHAT-I-NEED.md §3](../WHAT-I-NEED.md#3-logins-per-type): whether the mailbox is Google
  Workspace (company domain) or plain @gmail.com, and someone who can create a Google Cloud
  project with that account.
- The **HTTPS address question settled** with your helper before you start (design §6).

## Steps

### A. Google Cloud (one time)

1. In n8n, open **Credentials** → **Create** → **Gmail OAuth2 API** (Google OAuth2). Copy the
   **OAuth Redirect URL** that n8n shows. Leave the form open.

   > **STOP if the redirect URL starts with `http://ai:5678`.** Google accepts only `https`
   > addresses or `localhost`, so it will refuse this one. Do not try to work around it alone.
   > Contact your helper: design section 6 lists the fix options (open n8n over Tailscale HTTPS for
   > the sign-in, or let the public n8n address pass the OAuth callback). Continue once n8n shows
   > an `https://` redirect URL.

2. Go to the Google Cloud console with the mailbox's account and **create a project** named `MailFlow`.
3. **APIs & Services** → **Library** → search **Gmail API** → **Enable**.
4. **OAuth consent screen**:
   - **Audience**: **Internal** if it is Google Workspace (no Google review, no expiry).
   - Plain @gmail.com must use **External**: it stays in **Testing** mode. Add the mailbox under
     **Test users**. Testing-mode logins expire after **7 days**, so you will need to sign in
     again weekly; plan a Workspace account for anything long-term.
   - **Branding** → **Authorized domains**: add the domain of n8n's https redirect URL.
5. **Credentials** → **Create credentials** → **OAuth client ID** → **Web application**. Under
   **Authorized redirect URIs** paste n8n's OAuth Redirect URL exactly. **Create**.
6. Copy the **Client ID** and **Client Secret** into the n8n credential form. Name the credential
   e.g. `Gmail <label>`. Click **Sign in with Google**, choose the mailbox account, allow access.
   n8n shows the credential as connected. Never paste the secret anywhere else.

### B. The collector

7. **Create Workflow** `MailFlow · From <label> (Gmail)`, tag `mailflow`.
8. Add **Gmail Trigger**, credential from step 6:
   - **Event**: Message Received.
   - **Poll Times**: **Every Minute**.
   - **Simplify**: **off**. With it on you get only headers and a short snippet, not the text.
   - **Filters** → **Read Status**: **Unread and read emails**. The default (unread only) misses
     mail someone opened in Gmail before the poll.
   - **Options** → **Max Emails per Poll** (if shown): `50`.
9. Click **Fetch test event** so one email appears in the output.
10. Add **Edit Fields (Set)** `MailFlow shape`, Manual Mapping, Include Other Input Fields off,
    8 String fields:

    > **Field names not verified.** n8n does not document the Gmail Trigger's fields with
    > Simplify off. The names below are likely. **Drag** each real field from the input panel;
    > if a name differs, use the dragged one.

    | Name | Likely value (confirm by dragging) |
    |---|---|
    | `message_id` | `{{ $json.messageId }}` |
    | `mailbox` | your label, e.g. `sales@` |
    | `source` | `gmail` |
    | `from_name` | `{{ $json.from.value[0].name }}` |
    | `from_address` | `{{ $json.from.value[0].address }}` |
    | `subject` | `{{ $json.subject }}` |
    | `received_at` | `{{ new Date($json.date).toISOString() }}` |
    | `body` | see below |

    ```
    {{ ($json.text || ($json.html || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')).slice(0, 4000) }}
    ```

    If there is no `messageId`, use Gmail's own message id (`{{ $json.id }}`, also to confirm by
    dragging): the design allows the provider's id when there is no Message-ID.
11. Add **Execute Sub-workflow** `Process email` → `MailFlow · Process email`, map the 8 inputs,
    **Wait For Sub-Workflow Completion** off.
12. **Save**, **Active**.

## Check it works

1. Send a test email to the Gmail mailbox.
2. Within about 2 minutes a row appears with `source` = `gmail`.
3. Send a second test email and open it in Gmail straight away, before the next poll. It still
   appears in the table, because Read Status includes read mail.
4. Gmail itself is unchanged: nothing marked, moved or labelled. Delete the test rows.

## If something goes wrong

| Problem | What to do |
|---|---|
| `redirect_uri_mismatch` | The URI in Google must match n8n's redirect URL exactly (https, no extra slash). |
| `invalid_client` | Client ID or Secret copied wrong; paste again. |
| `access_denied` / "app not verified" | External audience: add the mailbox under **Test users**. |
| Stops working after a week | External in Testing mode: tokens expire after 7 days. Sign in again, or use Workspace with Internal. |
| Body empty | **Simplify** is still on. |
| Read emails missing | **Read Status** is still "Unread emails only". |

## What you learned

- Google needs a Cloud project, the Gmail API and an OAuth client before n8n may read mail.
- OAuth redirect addresses must be https; `http://ai:5678` will not work.
- Simplify off and Read Status "Unread and read emails" make the collector complete.
