# Lesson 6: The email page and the status buttons

## Goal

Build `MailFlow · Email page`: clicking an email on the inbox page opens it with its AI tags,
summary, next step and full text. Buttons move it along `open` → `waiting` (replied, waiting on
the customer) → `done`, or back to `open`, and return to the list.
Design: [SYSTEM-DESIGN.md §2.4](../SYSTEM-DESIGN.md#24-the-pages).

One workflow with two Webhook triggers:

```
Webhook        (GET mailflow/email)  → Get email → Build page → Respond
Status webhook (GET mailflow/status) → Set status → Respond status
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
// MailFlow · Email page → Build page (customer-service view)
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
    return new Date(t).toLocaleString('en-GB', { timeZone: TIME_ZONE, weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return new Date(t).toISOString().slice(0, 16).replace('T', ' ');
  }
}

const row = $input.all().map((i) => i.json).find((r) => r && r.message_id);
const status = row ? (row.status === 'new' || !row.status ? 'open' : row.status) : '';
const needsReply = row && (row.needs_reply === true || row.needs_reply === 'true');
const statusLink = (to) => 'status?id=' + encodeURIComponent(id) + '&to=' + to;
const button = (to, label, cls) => `<a class="btn ${cls}" href="${esc(statusLink(to))}">${esc(label)}</a>`;
const buttons = !row ? '' : {
  open: button('waiting', 'Replied · waiting on customer', 'wait') + button('done', 'Done', 'done'),
  waiting: button('done', 'Done', 'done') + button('open', 'Reopen', 'plain'),
  done: button('open', 'Reopen', 'plain'),
}[status] || button('open', 'Reopen', 'plain');
const statusText = { open: 'Open', waiting: 'Waiting on customer', done: 'Done' }[status] || status;

const content = row ? `
  <h1>${esc(row.subject)}</h1>
  <p class="who">From <b>${esc(row.from_name)}</b> &lt;${esc(row.from_address)}&gt;<br>
     To mailbox <b>${esc(row.mailbox)}</b> · ${esc(showTime(row.received_at))} · status <b>${esc(statusText)}</b></p>
  <div class="ai">
    <div class="tags">
      <span class="prio ${esc(row.priority)}">${esc(row.priority)}</span>
      <span class="chip">${esc(row.type)}</span>
      <span class="chip">${esc(row.mood)}</span>
      <span class="chip">${needsReply ? 'needs a reply' : 'no reply needed'}</span>
      <span class="by">sorted by ${row.sorted_by === 'rule' ? 'a rule' : 'AI'}</span>
    </div>
    <p class="summary">${esc(row.summary)}</p>
    ${needsReply ? `<p class="next">Next step: ${esc(row.next_step)}</p>` : ''}
  </div>
  <div class="body">${esc(row.body).replace(/\n/g, '<br>')}</div>
  <p class="hint">Reply from the <b>${esc(row.mailbox)}</b> mailbox in your mail app, then mark it here.</p>
  <div class="actions">${buttons}</div>`
  : '<h1>This email was not found.</h1><p>It may have been cleaned up after 90 days.</p>';

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${row ? esc(row.subject) : 'Not found'} · MailFlow</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; color: #1f2328; background: #f4f5f7; }
  header { background: #1f3a5f; padding: 12px 20px; }
  header a { color: #fff; text-decoration: none; }
  .page { max-width: 820px; margin: 20px auto; padding: 0 20px; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  .who { color: #57606a; font-size: 14px; margin: 0 0 14px; }
  .ai { background: #fff; border-left: 4px solid #1f3a5f; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; }
  .tags { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .prio { font-weight: 700; font-size: 12px; padding: 2px 8px; border-radius: 5px; background: #e1e4e8; color: #57606a; }
  .prio.P1 { background: #d1242f; color: #fff; }
  .prio.P2 { background: #f0b429; color: #3a2a00; }
  .chip { font-size: 12px; background: #eef1f5; padding: 1px 8px; border-radius: 10px; }
  .by { font-size: 12px; color: #6a737d; }
  .summary { margin: 8px 0 0; }
  .next { margin: 6px 0 0; color: #0550ae; font-weight: 500; }
  .body { background: #fff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 14px; line-height: 1.5; overflow-wrap: anywhere; }
  .hint { color: #6a737d; font-size: 13px; }
  .actions { display: flex; gap: 10px; }
  .btn { padding: 8px 14px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 14px; }
  .btn.wait { background: #0969da; color: #fff; }
  .btn.done { background: #1a7f37; color: #fff; }
  .btn.plain { background: #fff; color: #1f2328; border: 1px solid #d0d7de; }
</style>
</head>
<body>
<header><a href="../mailflow">← Back to inbox</a></header>
<div class="page">${content}</div>
</body>
</html>`;

return [{ json: { html } }];
```

The code shows the subject, sender, mailbox, received time and status; the AI box with the
P1/P2/P3 badge, type, mood, "needs a reply" or "no reply needed" and who sorted it (a rule or
AI); the summary and, if a reply is needed, **Next step**; then the body. The buttons depend on
the status:

| Status | Buttons |
|---|---|
| `open` (or old `new`) | **Replied · waiting on customer** (→ `waiting`), **Done** (→ `done`) |
| `waiting` | **Done**, **Reopen** (→ `open`) |
| `done` | **Reopen** |

Each button is a link to `status?id=…&to=…`. The page lives at `/webhook/mailflow/email`, so the
browser turns it into `/webhook/mailflow/status?id=…&to=…`.

### B. The status link

6. In the same workflow add a second trigger: another **Webhook**, rename it `Status webhook`.
   - **HTTP Method**: GET. **Path**: `mailflow/status`.
   - **Authentication**: Basic Auth, `MailFlow page login`.
   - **Respond**: Using 'Respond to Webhook' Node.
7. Add a **Data Table** node `Set status`: **Operation** **Update**, table `MailFlow emails`.
   Condition `message_id` **Equals** `{{ $json.query.id }}`. **Mapping Column Mode**: **Map Each
   Column Manually**; set only `status` =

   ```
   {{ ['open','waiting','done'].includes($json.query.to) ? $json.query.to : 'open' }}
   ```

   Only the three known statuses are accepted; anything else in the address becomes `open`.
   **Settings** → **Always Output Data**: on, so the browser still gets an answer if the id was
   not found.
8. Add **Respond to Webhook** `Respond status`: Respond With **Text**, header `Content-Type` =
   `text/html; charset=utf-8`, Response Body (no expressions needed):

   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
   <meta charset="utf-8">
   <meta http-equiv="refresh" content="0; url=../mailflow">
   <title>Saved · MailFlow</title>
   </head>
   <body style="font-family: system-ui, sans-serif; padding: 20px;">
   <p>Status saved. <a href="../mailflow">Back to the inbox</a></p>
   </body>
   </html>
   ```

   The page lives at `/webhook/mailflow/status`, so `../mailflow` is the inbox. The browser jumps
   there at once (meta refresh).
9. **Save**, switch **Active**.

## Check it works

1. Open the inbox page and click an email. Its page shows the subject, sender, the AI box with
   the priority badge, type, mood and reply chips, the summary, the next step (if it needs a
   reply) and the body with its line breaks.
2. Click **Replied · waiting on customer**. You land back on the inbox; the email has left
   **Needs reply** and appears under **Waiting on customer**.
3. Open it again: it shows **Done** and **Reopen**. Click **Done**: it moves to the **Done** view,
   faded. Open it: only **Reopen** is left. Click it: it is back in **Needs reply**.
4. Open `http://ai:5678/webhook/mailflow/email?id=nothing`: the page says "This email was not found".
5. Open `http://ai:5678/webhook/mailflow/status?id=nothing&to=bogus`: you land on the inbox and
   nothing changed.

## If something goes wrong

| Problem | What to do |
|---|---|
| Clicking an email on the inbox gives 404 | This workflow is not active, or the path is not exactly `mailflow/email`. |
| Always "not found" | The `id` in the address must reach the node: check `Get email` uses `{{ $json.query.id }}` and the condition is **Equals**. |
| A status button does nothing | Check `Set status` is **Update**, the condition uses `{{ $json.query.id }}` and `status` uses the expression from step 7. |
| Body shows `&lt;p&gt;` everywhere | That mailbox sent HTML as body; the collector should strip tags (lessons 4, 8). The page is still safe. |
| Asked for the password again | The browser keeps one login per site; enter the same `MailFlow page login`. |

## What you learned

- One workflow can have several Webhook triggers, each with its own path.
- The page reads one row by `message_id`; the status links update one column of that row.
- Checking the `to` value against a fixed list keeps odd addresses from writing junk statuses.
- Relative links (`status`, `../mailflow`) work on both the tailnet and test addresses.
