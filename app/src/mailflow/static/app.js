"use strict";
// MailFlow page. Every piece of email data goes into the page as text (textContent), never as
// HTML, so an email cannot inject markup or script.

const VIEWS = [
  ["reply", "Needs reply"],
  ["p1", "P1 · answer today"],
  ["waiting", "Waiting on customer"],
  ["done", "Done"],
  ["all", "Everything"],
];
const STATUS_TEXT = { open: "Open", waiting: "Waiting on customer", done: "Done" };
const MOOD_CLASS = { Angry: "angry", Frustrated: "frustrated", Neutral: "neutral", Happy: "happy" };
const BUTTONS = {
  open: [["waiting", "Replied · waiting on customer", "wait"], ["done", "Done", "done"]],
  waiting: [["done", "Done", "done"], ["open", "Reopen", ""]],
  done: [["open", "Reopen", ""]],
};
const REFRESH_MS = 60_000;
const TIME_ZONE = "Africa/Mbabane";
const listTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const fullTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "short", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

const $ = (id) => document.getElementById(id);
let me = null;
let inbox = null;

// --- helpers ---------------------------------------------------------------

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function showTime(value, format) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : format.format(date);
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function api(path, { method = "GET", body } = {}) {
  const options = { method, headers: { "X-MailFlow": "1" }, credentials: "same-origin" };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(0, "MailFlow could not be reached. Check your connection.");
  }
  if (response.status === 401 && path !== "/api/me/password") {
    location.href = "/login";
    throw new ApiError(401, "Please log in.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, data.error || `Error ${response.status}`);
  return data;
}

let toastTimer = null;
function toast(message, isError = false) {
  const box = $("toast");
  box.textContent = message;
  box.classList.toggle("error", isError);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, isError ? 8000 : 3500);
}

// --- state in the address bar ----------------------------------------------

function state() {
  const q = new URLSearchParams(location.search);
  return {
    view: q.get("view") || "reply",
    mailbox: q.get("mailbox") || "",
    type: q.get("type") || "",
    mood: q.get("mood") || "",
    id: q.get("id") || "",
  };
}

function go(changes) {
  const next = { ...state(), ...changes };
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(next)) {
    if (value && !(key === "view" && value === "reply")) q.set(key, value);
  }
  const query = q.toString();
  history.pushState(null, "", query ? `/?${query}` : "/");
  render();
}

window.addEventListener("popstate", render);

// --- left: views and filters -----------------------------------------------

function navLink(label, count, active, onclick) {
  return el("li", {},
    el("button", { type: "button", class: active ? "nav-item active" : "nav-item", onclick },
      el("span", { text: label }),
      count === undefined ? null : el("span", { class: "n", text: String(count) })));
}

function filterGroup(title, name, pairs) {
  const current = state()[name];
  return [
    el("h3", { text: title }),
    el("ul", {},
      navLink("All", undefined, !current, () => go({ [name]: "", id: "" })),
      pairs.map(([value, count]) => navLink(value, count, current === value, () => go({ [name]: value, id: "" })))),
  ];
}

function renderSidebar() {
  const side = $("sidebar");
  side.replaceChildren(
    el("h3", { text: "Views" }),
    el("ul", {}, VIEWS.map(([key, label]) => navLink(label, inbox.counts[key], inbox.view === key, () => go({ view: key, id: "" })))),
    ...filterGroup("Mailbox", "mailbox", inbox.mailboxes),
    ...filterGroup("Type", "type", inbox.types),
    ...filterGroup("Mood", "mood", inbox.moods),
  );
}

// --- middle: the list -------------------------------------------------------

function renderList() {
  const s = state();
  const list = $("list");
  const viewLabel = (VIEWS.find(([key]) => key === inbox.view) || VIEWS[0])[1];
  const filters = [s.mailbox, s.type, s.mood].filter(Boolean).join(" · ");
  const header = el("div", { class: "list-head" },
    el("strong", { text: viewLabel }),
    filters ? el("span", { class: "muted", text: ` · ${filters}` }) : null,
    el("span", { class: "muted right", text: `${inbox.items.length}` }));
  if (!inbox.items.length) {
    list.replaceChildren(header, el("p", { class: "empty", text: "Nothing here. 🎉" }));
    return;
  }
  const rows = inbox.items.map((item) => {
    const selected = String(item.id) === s.id;
    return el("button", {
      type: "button",
      class: `item ${item.status}${selected ? " selected" : ""}`,
      "aria-current": selected ? "true" : null,
      onclick: () => go({ id: String(item.id) }),
    },
      el("span", { class: `prio ${item.priority || ""}`, text: item.priority || "–" }),
      el("span", { class: "item-main" },
        el("span", { class: "item-top" },
          el("span", { class: "from", text: item.from_name || item.from_address || "(unknown sender)" }),
          el("span", { class: "time", text: showTime(item.received_at, listTime) })),
        el("span", { class: "subject", text: item.subject || "(no subject)" }),
        el("span", { class: "summary", text: item.summary || "" }),
        item.needs_reply && item.status !== "done" && item.next_step ? el("span", { class: "next", text: `→ ${item.next_step}` }) : null,
        el("span", { class: "chips" },
          el("span", { class: "chip", text: item.type || "" }),
          el("span", { class: `chip mood ${MOOD_CLASS[item.mood] || ""}`, text: item.mood || "" }),
          el("span", { class: "chip box", text: item.mailbox || "" }),
          el("span", { class: `chip st ${item.status}`, text: STATUS_TEXT[item.status] || item.status }),
          item.waiting ? el("span", { class: item.late ? "age late" : "age", text: `waiting ${item.waiting}` }) : null)));
  });
  list.replaceChildren(header, ...rows);
}

// --- right: one email -------------------------------------------------------

let detailToken = 0;

async function renderDetail() {
  const s = state();
  const detail = $("detail");
  document.body.classList.toggle("has-detail", Boolean(s.id));
  if (!s.id) {
    detail.replaceChildren(el("p", { class: "placeholder", text: "Pick an email from the list." }));
    return;
  }
  const token = ++detailToken;
  if (detail.dataset.id !== s.id) detail.replaceChildren(el("p", { class: "placeholder", text: "Loading…" }));
  let email;
  try {
    email = await api(`/api/emails/${encodeURIComponent(s.id)}`);
  } catch (error) {
    if (token !== detailToken) return;
    detail.dataset.id = "";
    detail.replaceChildren(backButton(), el("p", { class: "placeholder", text: error.message }));
    return;
  }
  if (token !== detailToken) return;
  detail.dataset.id = s.id;
  const keepDraft = detail.querySelector("textarea")?.value || "";
  detail.replaceChildren(
    backButton(),
    el("h1", { class: "detail-subject", text: email.subject || "(no subject)" }),
    el("p", { class: "who" },
      "From ", el("b", { text: email.from_name || "" }), ` <${email.from_address || ""}>`, el("br"),
      "To mailbox ", el("b", { text: email.mailbox || "" }), ` · ${showTime(email.received_at, fullTime)} · `,
      el("span", { class: `chip st ${email.status}`, text: STATUS_TEXT[email.status] || email.status })),
    el("div", { class: "ai" },
      el("div", { class: "chips" },
        el("span", { class: `prio ${email.priority || ""}`, text: email.priority || "–" }),
        el("span", { class: "chip", text: email.type || "" }),
        el("span", { class: `chip mood ${MOOD_CLASS[email.mood] || ""}`, text: email.mood || "" }),
        el("span", { class: "chip", text: email.needs_reply ? "needs a reply" : "no reply needed" }),
        el("span", { class: "muted small", text: `sorted by ${email.sorted_by === "rule" ? "a rule" : "AI"}` })),
      el("p", { class: "summary", text: email.summary || "" }),
      email.needs_reply ? el("p", { class: "next", text: `Next step: ${email.next_step || ""}` }) : null),
    el("div", { class: "body", text: email.body || "" }),
    replyBox(email, keepDraft),
    el("div", { class: "actions" },
      (BUTTONS[email.status] || BUTTONS.done).map(([to, label, cls]) =>
        el("button", { type: "button", class: `btn ${cls}`, onclick: () => setStatus(email.id, to) }, label))),
  );
}

function backButton() {
  return el("button", { type: "button", class: "btn ghost back", onclick: () => go({ id: "" }) }, "← Back to the list");
}

function replyBox(email, draft) {
  if (!email.can_reply) {
    return el("p", { class: "hint" }, "Reply from the ", el("b", { text: email.mailbox || "" }), " mailbox in your mail app, then mark it here.");
  }
  if (email.status === "done") return null;
  const text = el("textarea", { rows: "7", required: true, placeholder: "Write your reply…", "aria-label": "Reply" });
  text.value = draft;
  const send = el("button", { type: "submit", class: "btn primary" }, "Send reply");
  const form = el("form", {
    class: "reply",
    onsubmit: async (event) => {
      event.preventDefault();
      if (!text.value.trim()) return;
      send.disabled = true;
      send.textContent = "Sending…";
      try {
        await api(`/api/emails/${email.id}/reply`, { method: "POST", body: { text: text.value } });
        text.value = "";
        toast("Reply sent. The email is now waiting on the customer.");
        await render();
      } catch (error) {
        toast(error.message, true);
      } finally {
        send.disabled = false;
        send.textContent = "Send reply";
      }
    },
  },
    el("label", {}, `Reply to ${email.from_name || email.from_address} from the `, el("b", { text: email.mailbox }), " mailbox"),
    text,
    el("div", { class: "row-buttons" }, send,
      el("span", { class: "hint", text: "Sent in the same Gmail conversation; the email then moves to Waiting on customer." })));
  return form;
}

async function setStatus(id, to) {
  try {
    await api(`/api/emails/${id}/status`, { method: "POST", body: { to } });
    toast(`Marked ${STATUS_TEXT[to]}.`);
    await render();
  } catch (error) {
    toast(error.message, true);
  }
}

// --- top bar and loading ----------------------------------------------------

function renderTop() {
  $("need-reply").textContent = `${inbox.counts.reply} need a reply`;
  const p1 = $("p1-count");
  p1.hidden = !inbox.counts.p1;
  p1.textContent = `${inbox.counts.p1} × P1`;
  const total = $("total");
  total.classList.remove("stale");
  total.textContent = `${inbox.total} emails · last 30 days`;
}

let loadedAt = null;
// The 60-second refresh must not fail silently: say since when the list is old, and why.
async function backgroundRefresh() {
  if (document.hidden) return;
  try {
    await loadInbox();
  } catch (error) {
    const total = $("total");
    total.classList.add("stale");
    total.textContent = `⚠ not refreshed since ${loadedAt ? showTime(loadedAt, listTime) : "opening"}: ${error.message}`;
  }
}

// Each load gets a number; an answer that arrives after a newer load started is dropped, so a
// click during a slow load is never lost and an old answer never overwrites a newer one.
let inboxToken = 0;
async function loadInbox() {
  const token = ++inboxToken;
  const s = state();
  const q = new URLSearchParams({ view: s.view, mailbox: s.mailbox, type: s.type, mood: s.mood });
  const data = await api(`/api/inbox?${q}`);
  if (token !== inboxToken) return;
  inbox = data;
  loadedAt = new Date();
  renderTop();
  renderSidebar();
  renderList();
}

async function render() {
  try {
    await Promise.all([loadInbox(), renderDetail()]);
  } catch (error) {
    if (error.status !== 401) {
      $("list").replaceChildren(el("p", { class: "empty error", text: error.message }));
    }
  }
}

// --- account dialogs --------------------------------------------------------

function openDialog(dialog) {
  for (const box of dialog.querySelectorAll(".error")) box.hidden = true;
  dialog.showModal();
}
for (const button of document.querySelectorAll("[data-close]")) {
  button.addEventListener("click", () => button.closest("dialog").close());
}

function formError(form, message) {
  const box = form.querySelector(".error");
  box.textContent = message;
  box.hidden = false;
}

$("open-password").addEventListener("click", () => openDialog($("password-dialog")));
$("password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  if (form.new.value !== form.again.value) return formError(form, "The two new passwords differ.");
  try {
    await api("/api/me/password", { method: "POST", body: { current: form.current.value, new: form.new.value } });
    location.href = "/login?changed=1";
  } catch (error) {
    formError(form, error.message);
  }
});

async function loadUsers() {
  const users = await api("/api/users");
  $("users-body").replaceChildren(...users.map((user) => {
    const self = user.id === me.id;
    const actions = self ? [el("span", { class: "muted", text: "you" })] : [
      el("button", {
        type: "button", class: "btn small",
        onclick: () => userAction(`/api/users/${user.id}/${user.active ? "disable" : "enable"}`),
      }, user.active ? "Disable" : "Enable"),
      el("button", {
        type: "button", class: "btn small",
        onclick: () => {
          const password = prompt(`New password for ${user.email} (at least 12 characters):`);
          if (password) userAction(`/api/users/${user.id}/reset`, { password });
        },
      }, "Reset password"),
    ];
    return el("tr", { class: user.active ? "" : "disabled" },
      el("td", { text: user.name }),
      el("td", { text: user.email }),
      el("td", { text: `${user.is_admin ? "Admin" : "Staff"}${user.active ? "" : " · disabled"}` }),
      el("td", { class: "row-buttons" }, actions));
  }));
}

async function userAction(path, body = {}) {
  try {
    await api(path, { method: "POST", body });
    toast("Saved.");
    await loadUsers();
  } catch (error) {
    toast(error.message, true);
  }
}

$("open-users").addEventListener("click", async () => {
  try {
    await loadUsers();
    openDialog($("users-dialog"));
  } catch (error) {
    toast(error.message, true);
  }
});
$("add-user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  try {
    await api("/api/users", {
      method: "POST",
      body: { name: form.name.value, email: form.email.value, password: form.password.value, is_admin: form.is_admin.checked },
    });
    form.reset();
    form.querySelector(".error").hidden = true;
    toast("User added. Give them their first password; they can change it after logging in.");
    await loadUsers();
  } catch (error) {
    formError(form, error.message);
  }
});

$("logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
  } finally {
    location.href = "/login";
  }
});
$("refresh").addEventListener("click", render);

// --- start ------------------------------------------------------------------

(async () => {
  try {
    me = await api("/api/me");
  } catch {
    return;
  }
  $("me").textContent = me.name;
  $("open-users").hidden = !me.is_admin;
  await render();
  setInterval(backgroundRefresh, REFRESH_MS);
  document.addEventListener("visibilitychange", backgroundRefresh);
})();
