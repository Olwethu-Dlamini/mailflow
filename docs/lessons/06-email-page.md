# Lesson 6: The email page and the Done button

## Goal

Build `MailFlow · Email page`: clicking an email on the inbox page opens it with its AI tags and
full text. A **Mark as done** link sets its `status` to `done` and goes back to the list.
Design: [SYSTEM-DESIGN.md §2.4](../SYSTEM-DESIGN.md#24-the-pages).

One workflow with two Webhook triggers:

```
Webhook      (GET mailflow/email) → Get email → Build page → Respond
Done webhook (GET mailflow/done)  → Mark done → Respond done
```

## What you need

- Lesson 5 done (the inbox page works and the credential `MailFlow page login` exists).

## Steps

### A. The email page

1. **Create Workflow** `MailFlow · Email page`, tag `mailflow`.
2. Add a **Webhook** trigger, keep the name `Webhook`.
   - **HTTP Method**: GET. **Path**: `mailflow/email`.
   - **Authentication**: Basic Auth, credential `MailFlow page login` (the same one).
   - **Respond**: Using 'Respond to Webhook' Node.
3. Add a **Data Table** node `Get email`: **Operation** Get, table `MailFlow emails`, condition
   `message_id` **Equals** `{{ $json.query.id }}`, **Limit** `1`. **Settings** → **Always Output
   Data**: on (so an unknown id still reaches the code and shows "not found").
4. Add a **Code** node `Build page` (JavaScript, Run Once for All Items) with the code below.
5. Add **Respond to Webhook** `Respond`: Respond With **Text**, Response Body `{{ $json.html }}`,
   Options → Response Headers `Content-Type` = `text/html; charset=utf-8`.

```javascript
// MailFlow · Email page → Build page
const id = String(($('Webhook').first().json.query || {}).id || '');
const TIME_ZONE = 'Africa/Mbabane';

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function showTime(value) {
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return '';
  try {
    return new Date(t).toLocaleString('en-GB', {
      timeZone: TIME_ZONE, weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (e) {
    return new Date(t).toISOString().slice(0, 16).replace('T', ' ');
  }
}

// This page lives at /webhook/mailflow/email, so '../mailflow' is the inbox and 'done' is /webhook/mailflow/done.
const INBOX = '../mailflow';

const row = $input.all()
  .map((item) => item.json)
  .find((r) => r && r.message_id && r.message_id === id);

const moodColour = { Negative: '#d9534f', Neutral: '#9aa0a6', Positive: '#2e9d5b' };

let content;
if (!row) {
  content = `<p class="empty">This email was not found. It may be older than 90 days and cleaned up.</p>`;
} else {
  const isDone = (row.status || 'new') === 'done';
  const doneLink = isDone
    ? '<span class="isdone">Done</span>'
    : `<a class="button" href="${esc('done?id=' + encodeURIComponent(row.message_id))}">Mark as done</a>`;
  const body = esc(row.body).replace(/\r?\n/g, '<br>');
  content = `
  <h1>${esc(row.subject) || '(no subject)'}</h1>
  <p class="meta">
    From <strong>${esc(row.from_name)}</strong> &lt;${esc(row.from_address)}&gt;<br>
    To mailbox <strong>${esc(row.mailbox)}</strong> (${esc(row.source)}) · ${esc(showTime(row.received_at))}
  </p>
  <div class="ai">
    <div class="tags">
      <span class="dot" style="background:${moodColour[row.sentiment] || '#9aa0a6'}"></span>
      <span class="chip">${esc(row.category)}</span>
      <span class="chip">${esc(row.sentiment)}</span>
      <span class="chip${row.urgency === 'High' ? ' urgent' : ''}">${esc(row.urgency)}</span>
      <span class="by">sorted by ${row.sorted_by === 'ai' ? 'AI' : 'rule'}</span>
    </div>
    <p class="summary">${esc(row.summary)}</p>
  </div>
  <div class="body">${body || '<em>(empty)</em>'}</div>
  <p class="actions">${doneLink}</p>`;
}

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${row ? esc(row.subject) : 'Not found'} · MailFlow</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; color: #222; background: #f5f6f8; }
  header { background: #1f3a5f; padding: 12px 20px; }
  header a { color: #fff; text-decoration: none; }
  main { max-width: 820px; margin: 0 auto; padding: 16px 20px; }
  h1 { font-size: 22px; margin: 8px 0; }
  .meta { color: #555; font-size: 14px; }
  .ai { background: #fff; border: 1px solid #e3e5e8; border-left: 4px solid #1f3a5f; border-radius: 6px; padding: 10px 14px; margin: 14px 0; }
  .tags { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .dot { width: 12px; height: 12px; border-radius: 50%; }
  .chip { font-size: 12px; background: #eef1f5; padding: 1px 7px; border-radius: 10px; }
  .chip.urgent { background: #d9534f; color: #fff; }
  .by { font-size: 12px; color: #777; }
  .summary { margin: 8px 0 0; }
  .body { background: #fff; border: 1px solid #e3e5e8; border-radius: 6px; padding: 14px; line-height: 1.5; overflow-wrap: anywhere; }
  .button { display: inline-block; background: #2e9d5b; color: #fff; padding: 8px 16px; border-radius: 6px; text-decoration: none; }
  .isdone { color: #2e9d5b; font-weight: 600; }
  .empty { color: #666; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<header><a href="${INBOX}">&larr; Back to inbox</a></header>
<main>${content}</main>
</body>
</html>`;

return [{ json: { html } }];
```

### B. The Done link

6. In the same workflow add a second trigger: another **Webhook**, rename it `Done webhook`.
   - **HTTP Method**: GET. **Path**: `mailflow/done`.
   - **Authentication**: Basic Auth, `MailFlow page login`.
   - **Respond**: Using 'Respond to Webhook' Node.
7. Add a **Data Table** node `Mark done`: **Operation** **Update**, table `MailFlow emails`.
   Condition `message_id` **Equals** `{{ $json.query.id }}`. **Mapping Column Mode**: **Map Each
   Column Manually**; set only `status` = `done`. **Settings** → **Always Output Data**: on, so the
   browser still gets an answer if the id was not found.
8. Add **Respond to Webhook** `Respond done`: Respond With **Text**, header `Content-Type` =
   `text/html; charset=utf-8`, Response Body (no expressions needed):

   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
   <meta charset="utf-8">
   <meta http-equiv="refresh" content="0; url=../mailflow">
   <title>Done · MailFlow</title>
   </head>
   <body style="font-family: system-ui, sans-serif; padding: 20px;">
   <p>Marked as done. <a href="../mailflow">Back to the inbox</a></p>
   </body>
   </html>
   ```

   The page lives at `/webhook/mailflow/done`, so `../mailflow` is the inbox. The browser jumps
   there at once (meta refresh).
9. **Save**, switch **Active**.

## Check it works

1. Open the inbox page and click an email. Its page shows the subject, sender, the AI box with
   coloured mood dot and chips, and the body with its line breaks.
2. Click **Mark as done**. You land back on the inbox; that email now looks faded. Filter
   **Status → done**: it is there.
3. Open the email again: it shows **Done** instead of the button.
4. Open `http://ai:5678/webhook/mailflow/email?id=nothing`: the page says "This email was not found".
5. If this was a real email, set its `status` back to `new` in the data table.

## If something goes wrong

| Problem | What to do |
|---|---|
| Clicking an email on the inbox gives 404 | This workflow is not active, or the path is not exactly `mailflow/email`. |
| Always "not found" | The `id` in the address must reach the node: check `Get email` uses `{{ $json.query.id }}` and the condition is **Equals**. |
| Mark as done does nothing | Check `Mark done` is **Update**, the condition uses `{{ $json.query.id }}` and `status` is set to `done`. |
| Body shows `&lt;p&gt;` everywhere | That mailbox sent HTML as body; the collector should strip tags (lessons 4, 8). The page is still safe. |
| Asked for the password again | The browser keeps one login per site; enter the same `MailFlow page login`. |

## What you learned

- One workflow can have several Webhook triggers, each with its own path.
- The page reads one row by `message_id`; the Done link updates one column of that row.
- Relative links (`done`, `../mailflow`) work on both the tailnet and test addresses.
