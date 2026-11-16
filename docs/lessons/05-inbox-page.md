# Lesson 5: The inbox page

## Goal

Build `MailFlow · Inbox page`: one web page, behind a password, that lists the last 30 days of
mail from every mailbox, newest first, with filters by mailbox, category, mood and status.
Design: [SYSTEM-DESIGN.md §2.4 and §7](../SYSTEM-DESIGN.md#24-the-pages), picture:
[inbox-mockup.png](../images/inbox-mockup.png).

```
Webhook → Get emails → Build page → Respond
```

## What you need

- Rows in `MailFlow emails` (lessons 3-4, or the test emails from lesson 2).
- Decision D5 (who may open the page; default one shared login) and D6 (tailnet only, or also
  the internet) from [WHAT-I-NEED.md](../WHAT-I-NEED.md).
- A strong password for the page, kept in your password manager.

## Steps

1. **Create Workflow** `MailFlow · Inbox page`, tag `mailflow`.
2. Add a **Webhook** trigger. Keep its name `Webhook` (the code below refers to it by name).
   - **HTTP Method**: GET.
   - **Path**: `mailflow`.
   - **Authentication**: **Basic Auth** → **Create new** credential named `MailFlow page login`
     with a user name and your strong password.
   - **Respond**: **Using 'Respond to Webhook' Node**.
3. Add a **Data Table** node, rename it `Get emails`.
   - **Operation**: **Get**. **Data table**: `MailFlow emails`.
   - Condition: `received_at` **Greater Than or Equal** `{{ $now.minus({days: 30}).toISO() }}`.
   - **Limit**: `300` (Return All off).
   - **Order By**: `received_at`, descending.
   - Node **Settings** tab → **Always Output Data**: **on**. Without this, an empty table makes the
     node output nothing, the next nodes never run and the browser gets no page. With it on, the
     node passes one empty item, and the code below shows "No emails".
4. Add a **Code** node, rename it `Build page`, language JavaScript, **Mode**: Run Once for All
   Items. Paste the full code below.
5. Add **Respond to Webhook**, rename it `Respond`.
   - **Respond With**: **Text**.
   - **Response Body**: `{{ $json.html }}`.
   - **Options** → **Response Headers** → add `Content-Type` = `text/html; charset=utf-8`.
6. **Save** and switch the workflow **Active**.

### The `Build page` code

It reads the filters from the address (`?mailbox=&category=&sentiment=&status=`), filters the
rows, and builds one complete HTML page with its own styles. No outside scripts or fonts. All
email text is escaped, so a subject like `<b>hi</b>` shows as text and cannot break the page.

The email links go to `mailflow/email?id=...`. Because the page's address is `/webhook/mailflow`,
a browser turns that link into `/webhook/mailflow/email?id=...`, the page from lesson 6.

```javascript
// MailFlow · Inbox page → Build page
const query = $('Webhook').first().json.query || {};
const want = {
  mailbox: String(query.mailbox || ''),
  category: String(query.category || ''),
  sentiment: String(query.sentiment || ''),
  status: String(query.status || ''),
};

// Keep this list the same as the category enum in Process email (lesson 2).
const CATEGORIES = ['Billing', 'Support', 'Sales', 'Internal', 'Newsletter', 'Other'];
const MOODS = ['Negative', 'Neutral', 'Positive'];
const STATUSES = ['new', 'done'];
const TIME_ZONE = 'Africa/Mbabane';

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function timeOf(value) {
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? 0 : t;
}

function showTime(value) {
  const t = timeOf(value);
  if (!t) return '';
  try {
    return new Date(t).toLocaleString('en-GB', {
      timeZone: TIME_ZONE, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch (e) {
    return new Date(t).toISOString().slice(0, 16).replace('T', ' ');
  }
}

// A link to this page with one filter changed ('' removes that filter).
function filterLink(name, value) {
  const next = { ...want, [name]: value };
  const parts = Object.keys(next)
    .filter((k) => next[k])
    .map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(next[k]));
  return parts.length ? '?' + parts.join('&') : '?';
}

// Rows from the table. "Always Output Data" sends one empty item when there are none: skip it.
const all = $input.all()
  .map((item) => item.json)
  .filter((row) => row && row.message_id);

const rows = all
  .filter((r) => !want.mailbox || r.mailbox === want.mailbox)
  .filter((r) => !want.category || r.category === want.category)
  .filter((r) => !want.sentiment || r.sentiment === want.sentiment)
  .filter((r) => !want.status || (r.status || 'new') === want.status)
  .sort((a, b) => timeOf(b.received_at) - timeOf(a.received_at));

const mailboxes = [...new Set(all.map((r) => r.mailbox).filter(Boolean))].sort();
const newest = all.reduce((max, r) => Math.max(max, timeOf(r.received_at)), 0);

function filterGroup(title, name, values) {
  const links = [['', 'All'], ...values.map((v) => [v, v])].map(([value, label]) => {
    const active = want[name] === value ? ' class="active"' : '';
    return `<li><a${active} href="${esc(filterLink(name, value))}">${esc(label)}</a></li>`;
  });
  return `<h3>${esc(title)}</h3><ul>${links.join('')}</ul>`;
}

const moodColour = { Negative: '#d9534f', Neutral: '#9aa0a6', Positive: '#2e9d5b' };

const list = rows.map((r) => {
  const dot = moodColour[r.sentiment] || '#9aa0a6';
  const urgent = r.urgency === 'High' ? ' urgent' : '';
  const done = (r.status || 'new') === 'done' ? ' done' : '';
  const href = 'mailflow/email?id=' + encodeURIComponent(r.message_id);
  return `<a class="row${done}" href="${esc(href)}">
    <span class="dot" style="background:${dot}" title="${esc(r.sentiment)}"></span>
    <span class="main">
      <span class="top">
        <span class="from">${esc(r.from_name || r.from_address)}</span>
        <span class="chip">${esc(r.category)}</span>
        <span class="chip${urgent}">${esc(r.urgency)}</span>
        <span class="chip box">${esc(r.mailbox)}</span>
      </span>
      <span class="subject">${esc(r.subject)}</span>
      <span class="summary">${esc(r.summary)}</span>
    </span>
    <span class="time">${esc(showTime(r.received_at))}</span>
  </a>`;
}).join('');

const empty = '<p class="empty">No emails match these filters.</p>';
const filtered = Object.values(want).some(Boolean);

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MailFlow inbox</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; color: #222; background: #f5f6f8; }
  header { background: #1f3a5f; color: #fff; padding: 12px 20px; display: flex; gap: 20px; align-items: baseline; }
  header h1 { margin: 0; font-size: 20px; }
  header .meta { font-size: 14px; opacity: .85; }
  .wrap { display: flex; }
  nav { width: 190px; padding: 12px 16px; background: #fff; border-right: 1px solid #e3e5e8; min-height: 100vh; }
  nav h3 { font-size: 12px; text-transform: uppercase; color: #666; margin: 16px 0 4px; }
  nav ul { list-style: none; margin: 0; padding: 0; }
  nav a { display: block; padding: 3px 6px; color: #1f3a5f; text-decoration: none; border-radius: 4px; font-size: 14px; }
  nav a.active { background: #1f3a5f; color: #fff; }
  main { flex: 1; padding: 12px 20px; }
  .row { display: flex; gap: 12px; align-items: flex-start; background: #fff; padding: 10px 12px; margin-bottom: 6px;
         border-radius: 6px; text-decoration: none; color: inherit; border: 1px solid #e3e5e8; }
  .row:hover { border-color: #1f3a5f; }
  .row.done { opacity: .55; }
  .dot { width: 12px; height: 12px; border-radius: 50%; margin-top: 4px; flex: none; }
  .main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .top { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .from { font-weight: 600; }
  .chip { font-size: 12px; background: #eef1f5; padding: 1px 7px; border-radius: 10px; }
  .chip.urgent { background: #d9534f; color: #fff; }
  .chip.box { background: #fff; border: 1px solid #ccd; }
  .subject { font-weight: 500; }
  .summary { color: #555; font-size: 14px; }
  .time { color: #666; font-size: 13px; white-space: nowrap; }
  .empty { color: #666; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>MailFlow</h1>
  <span class="meta">${rows.length} email${rows.length === 1 ? '' : 's'}${filtered ? ' (filtered)' : ''} · last 30 days</span>
  <span class="meta">Newest email: ${newest ? esc(showTime(newest)) : 'none yet'}</span>
</header>
<div class="wrap">
  <nav>
    ${filterGroup('Mailbox', 'mailbox', mailboxes)}
    ${filterGroup('Category', 'category', CATEGORIES)}
    ${filterGroup('Mood', 'sentiment', MOODS)}
    ${filterGroup('Status', 'status', STATUSES)}
  </nav>
  <main>${rows.length ? list : empty}</main>
</div>
</body>
</html>`;

return [{ json: { html } }];
```

## Test URL vs Production URL

The Webhook node shows two addresses:

- **Test URL** (`.../webhook-test/mailflow`): works only right after you click **Listen for test
  event** in the editor, for one request. You see the run on the canvas. Use it while building.
- **Production URL** (`.../webhook/mailflow`): works only when the workflow is **Active**. This is
  the address people bookmark. On the tailnet: `http://ai:5678/webhook/mailflow`.

## Security, in plain words

- The page shows company email, so it is behind **Basic Auth**: the browser asks for the user
  name and password from `MailFlow page login` before n8n sends anything.
- n8n's `/webhook/...` addresses are also reachable from the internet through the public n8n
  address. Decision **D6** chooses: tailnet only (recommended), or internet plus password.
- If D6 = tailnet only, your helper adds a rule to the Caddy web server on srv1 that blocks
  `/webhook/mailflow*` from the internet. Then the page opens only at `http://ai:5678/webhook/mailflow`
  on computers in the tailnet. Until that rule is in place, the password is the only lock, so make
  it long.

## Check it works

1. Open `http://ai:5678/webhook/mailflow` (workflow active). The browser asks for a password; enter
   the `MailFlow page login` details.
2. The page lists your emails, newest first; the header shows the count and the newest time.
3. Click **Negative** under Mood: only negative emails remain and the address ends `?sentiment=Negative`.
   Click **All** to clear it.
4. Temporarily test the empty case: open `http://ai:5678/webhook/mailflow?category=NoSuchThing`.
   The page says "No emails match these filters." (not an error).
5. Wrong password → the browser asks again; the page does not show.

## If something goes wrong

| Problem | What to do |
|---|---|
| The browser downloads a file or shows raw HTML | The `Content-Type` header is missing or misspelt in `Respond`. |
| Page hangs, then errors, when the table is empty | **Always Output Data** is off in `Get emails`. |
| "Webhook not registered" / 404 | Workflow not active (production URL) or not listening (test URL). |
| Error `Node 'Webhook' not found` in the code | You renamed the Webhook node. Rename it back to `Webhook` or change the first line of the code. |
| Times are 2 hours off | Change `TIME_ZONE` in the code. |
| Fewer emails than expected | Only the last 30 days and at most 300 rows are read. |

## What you learned

- A Webhook plus Respond to Webhook turns a workflow into a web page.
- The Code node builds the HTML; escaping keeps email text from breaking it.
- Test URL is for building; Production URL needs the workflow active; Basic Auth plus the Caddy rule protect it.
