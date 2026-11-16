# Lesson 5: The inbox page

## Goal

Build `MailFlow · Inbox page`: one web page, behind a password, that lists the last 30 days of
mail from every mailbox as a customer-service queue: what needs a reply, most urgent (P1) first,
with views by status and filters by mailbox, type and mood.
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
     node passes one empty item, which the code skips, and the page shows "Nothing here. 🎉".
4. Add a **Code** node, rename it `Build page`, language JavaScript, **Mode**: Run Once for All
   Items. Paste the full code below.
5. Add **Respond to Webhook**, rename it `Respond`.
   - **Respond With**: **Text**.
   - **Response Body**: `{{ $json.html }}`.
   - **Options** → **Response Headers** → add `Content-Type` = `text/html; charset=utf-8`.
6. **Save** and switch the workflow **Active**.

### The `Build page` code

It reads the view and filters from the address (`?view=&mailbox=&type=&mood=`), filters the
rows, and builds one complete HTML page with its own styles. No outside scripts or fonts. All
email text is escaped, so a subject like `<b>hi</b>` shows as text and cannot break the page.

The email links go to `mailflow/email?id=...`. Because the page's address is `/webhook/mailflow`,
a browser turns that link into `/webhook/mailflow/email?id=...`, the page from lesson 6.

**Views** (left column, each with its count; the address carries `?view=`):

| View | Shows | Order |
|---|---|---|
| **Needs reply** (default, no `view=` in the address) | `needs_reply` is true and `status` is `open` | P1 → P2 → P3, then oldest first |
| **P1 · answer today** | `priority` P1 and not `done` | P1 → P3, then oldest first |
| **Waiting on customer** | `status` is `waiting` (someone replied, the customer must answer) | P1 → P3, then oldest first |
| **Done** | `status` is `done` (rows look faded) | newest first |
| **Everything** | every row of the last 30 days | newest first |

Older rows with `status` `new` (before the switch to the customer-service model) count as `open`.

**Filters** under the views: **Mailbox** (the mailboxes that have mail), **Type** (only the types
that occur) and **Mood**, each value with its count. They combine with the view; **All** clears one.

**Each row** shows the P1/P2/P3 badge (P1 red, P2 amber, P3 grey), the sender, chips for type,
mood (Angry red, Frustrated orange, Happy green) and mailbox, a "waiting on customer" chip when
status is `waiting`, the subject, the AI summary and, while a reply is still needed, `→ next step`.
On the right: the received time and, for open emails that need a reply, **waiting X h**. That
label turns **red** when the email is late: more than **4 hours** for P1, more than **24 hours**
for P2 (`LATE_AFTER` in the code). P3 is never late.

The header shows how many need a reply, a red "N × P1" badge when there are P1 emails, and the
number of emails in the last 30 days.

```javascript
// MailFlow · Inbox page → Build page (customer-service view)
const query = $('Webhook').first().json.query || {};
const want = {
  view: String(query.view || 'reply'),
  mailbox: String(query.mailbox || ''),
  type: String(query.type || ''),
  mood: String(query.mood || ''),
};

// Keep these lists the same as the enums in Process email.
const TYPES = ['Complaint', 'Question', 'Request', 'Order', 'Payment', 'Technical', 'Cancellation', 'Feedback', 'Marketing', 'Notification', 'Other'];
const MOODS = ['Angry', 'Frustrated', 'Neutral', 'Happy'];
const VIEWS = [
  ['reply', 'Needs reply'],
  ['p1', 'P1 · answer today'],
  ['waiting', 'Waiting on customer'],
  ['done', 'Done'],
  ['all', 'Everything'],
];
// Hours before an open email counts as late.
const LATE_AFTER = { P1: 4, P2: 24 };
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
    return new Date(t).toLocaleString('en-GB', { timeZone: TIME_ZONE, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return new Date(t).toISOString().slice(0, 16).replace('T', ' ');
  }
}
function age(value) {
  const hours = (Date.now() - timeOf(value)) / 3600000;
  if (!timeOf(value) || hours < 0) return { text: '', hours: 0 };
  if (hours < 1) return { text: `${Math.max(1, Math.round(hours * 60))} min`, hours };
  if (hours < 48) return { text: `${Math.round(hours)} h`, hours };
  return { text: `${Math.round(hours / 24)} days`, hours };
}
function link(changes) {
  const next = { ...want, ...changes };
  const parts = Object.keys(next)
    .filter((k) => next[k] && !(k === 'view' && next[k] === 'reply'))
    .map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(next[k]));
  return parts.length ? '?' + parts.join('&') : '?';
}
const statusOf = (r) => (r.status === 'new' || !r.status ? 'open' : r.status);
const replyNeeded = (r) => r.needs_reply === true || r.needs_reply === 'true';

// Rows. "Always Output Data" sends one empty item when there are none: skip it.
const all = $input.all().map((i) => i.json).filter((r) => r && r.message_id);

const inView = {
  reply: (r) => replyNeeded(r) && statusOf(r) === 'open',
  p1: (r) => r.priority === 'P1' && statusOf(r) !== 'done',
  waiting: (r) => statusOf(r) === 'waiting',
  done: (r) => statusOf(r) === 'done',
  all: () => true,
};
const viewTest = inView[want.view] || inView.reply;
const prioRank = { P1: 0, P2: 1, P3: 2 };

const rows = all
  .filter(viewTest)
  .filter((r) => !want.mailbox || r.mailbox === want.mailbox)
  .filter((r) => !want.type || r.type === want.type)
  .filter((r) => !want.mood || r.mood === want.mood)
  .sort((a, b) => want.view === 'done' || want.view === 'all'
    ? timeOf(b.received_at) - timeOf(a.received_at)
    : (prioRank[a.priority] ?? 3) - (prioRank[b.priority] ?? 3) || timeOf(a.received_at) - timeOf(b.received_at));

const count = (test) => all.filter(test).length;
const mailboxes = [...new Set(all.map((r) => r.mailbox).filter(Boolean))].sort();

function group(title, name, values, counts) {
  const items = [['', 'All'], ...values.map((v) => [v, v])].map(([value, label]) => {
    const active = want[name] === value ? ' class="active"' : '';
    const n = counts && value ? ` <span class="n">${counts(value)}</span>` : '';
    return `<li><a${active} href="${esc(link({ [name]: value }))}">${esc(label)}${n}</a></li>`;
  });
  return `<h3>${esc(title)}</h3><ul>${items.join('')}</ul>`;
}
const views = VIEWS.map(([key, label]) => {
  const active = want.view === key ? ' class="active"' : '';
  return `<li><a${active} href="${esc(link({ view: key }))}">${esc(label)} <span class="n">${count(inView[key])}</span></a></li>`;
}).join('');

const moodClass = { Angry: 'angry', Frustrated: 'frustrated', Neutral: 'neutral', Happy: 'happy' };
const list = rows.map((r) => {
  const st = statusOf(r);
  const a = age(r.received_at);
  const late = st === 'open' && replyNeeded(r) && LATE_AFTER[r.priority] && a.hours > LATE_AFTER[r.priority];
  const href = 'mailflow/email?id=' + encodeURIComponent(r.message_id);
  return `<a class="row ${esc(st)}" href="${esc(href)}">
    <span class="prio ${esc(r.priority)}">${esc(r.priority)}</span>
    <span class="main">
      <span class="top">
        <span class="from">${esc(r.from_name || r.from_address)}</span>
        <span class="chip">${esc(r.type)}</span>
        <span class="chip mood ${moodClass[r.mood] || ''}">${esc(r.mood)}</span>
        <span class="chip box">${esc(r.mailbox)}</span>
        <span class="chip st ${esc(st)}">${esc({ open: 'Open', waiting: 'Waiting on customer', done: 'Done' }[st] || st)}</span>
      </span>
      <span class="subject">${esc(r.subject)}</span>
      <span class="summary">${esc(r.summary)}</span>
      ${replyNeeded(r) && st !== 'done' ? `<span class="next">→ ${esc(r.next_step)}</span>` : ''}
    </span>
    <span class="side">
      <span class="time">${esc(showTime(r.received_at))}</span>
      ${st === 'open' && replyNeeded(r) && a.text ? `<span class="age${late ? ' late' : ''}">waiting ${esc(a.text)}</span>` : ''}
    </span>
  </a>`;
}).join('');

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MailFlow</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; color: #1f2328; background: #f4f5f7; }
  header { background: #1f3a5f; color: #fff; padding: 12px 20px; display: flex; gap: 24px; align-items: baseline; }
  header h1 { margin: 0; font-size: 20px; }
  header .meta { font-size: 14px; opacity: .85; }
  header .p1 { background: #d1242f; padding: 2px 8px; border-radius: 10px; font-size: 13px; }
  .wrap { display: flex; }
  nav { width: 210px; padding: 8px 14px; background: #fff; border-right: 1px solid #e1e4e8; min-height: 100vh; }
  nav h3 { font-size: 11px; text-transform: uppercase; color: #6a737d; margin: 16px 0 4px; letter-spacing: .04em; }
  nav ul { list-style: none; margin: 0; padding: 0; }
  nav a { display: flex; justify-content: space-between; padding: 4px 8px; color: #1f3a5f; text-decoration: none; border-radius: 5px; font-size: 14px; }
  nav a:hover { background: #eef2f7; }
  nav a.active { background: #1f3a5f; color: #fff; }
  nav .n { opacity: .7; font-size: 12px; }
  main { flex: 1; padding: 12px 20px; max-width: 1100px; }
  .row { display: flex; gap: 12px; align-items: flex-start; background: #fff; padding: 10px 12px; margin-bottom: 6px;
         border-radius: 8px; text-decoration: none; color: inherit; border: 1px solid #e1e4e8; }
  .row:hover { border-color: #1f3a5f; }
  .row.done { opacity: .5; }
  .prio { flex: none; width: 30px; text-align: center; font-weight: 700; font-size: 12px; padding: 3px 0; border-radius: 5px; background: #e1e4e8; color: #57606a; }
  .prio.P1 { background: #d1242f; color: #fff; }
  .prio.P2 { background: #f0b429; color: #3a2a00; }
  .main { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .top { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .from { font-weight: 600; }
  .chip { font-size: 12px; background: #eef1f5; padding: 1px 8px; border-radius: 10px; }
  .chip.box { background: #fff; border: 1px solid #d0d7de; }
  .chip.st.open { background: #fff8c5; color: #7d4e00; }
  .chip.st.waiting { background: #ddf4ff; color: #0550ae; }
  .chip.st.done { background: #dafbe1; color: #116329; }
  .mood.angry { background: #ffebe9; color: #a40e26; }
  .mood.frustrated { background: #fff1e5; color: #953800; }
  .mood.happy { background: #dafbe1; color: #116329; }
  .subject { font-weight: 500; }
  .summary { color: #57606a; font-size: 14px; }
  .next { color: #0550ae; font-size: 14px; }
  .side { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex: none; }
  .time { color: #6a737d; font-size: 13px; white-space: nowrap; }
  .age { font-size: 12px; color: #57606a; white-space: nowrap; }
  .age.late { color: #fff; background: #d1242f; padding: 1px 6px; border-radius: 8px; }
  .empty { color: #6a737d; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>MailFlow</h1>
  <span class="meta">${count(inView.reply)} need a reply</span>
  ${count(inView.p1) ? `<span class="p1">${count(inView.p1)} × P1</span>` : ''}
  <span class="meta">${all.length} emails · last 30 days</span>
</header>
<div class="wrap">
  <nav>
    <h3>Views</h3><ul>${views}</ul>
    ${group('Mailbox', 'mailbox', mailboxes, (v) => count((r) => r.mailbox === v))}
    ${group('Type', 'type', TYPES.filter((t) => all.some((r) => r.type === t)), (v) => count((r) => r.type === v))}
    ${group('Mood', 'mood', MOODS, (v) => count((r) => r.mood === v))}
  </nav>
  <main>${rows.length ? list : '<p class="empty">Nothing here. 🎉</p>'}</main>
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
2. The page opens on **Needs reply**: P1 emails at the top, then P2, then P3, oldest first within
   each. The header shows "N need a reply" and the P1 count.
3. Click **Angry** under Mood: only angry emails remain and the address ends `?mood=Angry`.
   Click **All** to clear it. Click **Everything**: every email, newest first, `?view=all`.
4. Temporarily test the empty case: open `http://ai:5678/webhook/mailflow?type=NoSuchThing`.
   The page says "Nothing here. 🎉" (not an error).
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
- Views, priority order and the waiting-time label turn a list of mail into a queue: answer the red ones first.
- Test URL is for building; Production URL needs the workflow active; Basic Auth plus the Caddy rule protect it.
