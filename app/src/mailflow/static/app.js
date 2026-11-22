"use strict";
// MailFlow page. Every piece of email data goes into the page as text (textContent), never as
// HTML, so an email cannot inject markup or script.

const VIEWS = [
  ["reply", "Needs reply", "reply"],
  ["p1", "P1 · answer today", "flame"],
  ["waiting", "Waiting on customer", "clock"],
  ["done", "Done", "check"],
  ["all", "Everything", "inbox"],
];
const STATUS_TEXT = { open: "Open", waiting: "Waiting on customer", done: "Done" };
// Topics that must stand out wherever they appear.
const TOPIC_CLASS = { "Code of conduct": "alert" };
const SORTED_BY = {
  ai: "Sorted by AI",
  rule: "Sorted by a rule",
  unsorted: "Not sorted: the AI's answer was unusable, so the labels below are placeholders",
};
const BUTTONS = {
  open: [["waiting", "Replied · waiting on customer", "wait"], ["done", "Done", "done"]],
  waiting: [["done", "Done", "done"], ["open", "Reopen", ""]],
  done: [["open", "Reopen", ""]],
};
const REFRESH_MS = 60_000;
const TIME_ZONE = "Africa/Mbabane";
const listTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const fullTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "short", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const clockTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit" });

// Line icons, 24×24, drawn with the current text colour (shapes after Lucide, ISC licence).
const ICONS = {
  reply: ["M9 14 4 9l5-5", "M4 9h10.5a5.5 5.5 0 0 1 0 11H11"],
  flame: ["M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"],
  clock: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7v5l3 2"],
  check: ["M21 11.08V12a9 9 0 1 1-5.34-8.23", "M21 4 12 13.01l-3-3"],
  inbox: ["M22 12h-6l-2 3h-4l-2-3H2", "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"],
  search: ["M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16z", "m21 21-4.3-4.3"],
  sidebar: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M9 3v18"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  chevronDown: ["m6 9 6 6 6-6"],
  chevronUp: ["m18 15-6-6-6 6"],
  x: ["M18 6 6 18", "m6 6 12 12"],
  users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M22 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
  key: ["M7.5 13a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9z", "m10.7 14.3 9.8-9.8", "m15.5 7.5 3 3", "m18 5 2.5 2.5"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "m16 17 5-5-5-5", "M21 12H9"],
  refresh: ["M3 12a9 9 0 0 1 15-6.7L21 8", "M21 3v5h-5", "M21 12a9 9 0 0 1-15 6.7L3 16", "M8 16H3v5"],
  warning: ["m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z", "M12 9v4", "M12 17h.01"],
};
const SVG = "http://www.w3.org/2000/svg";

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

function icon(name, cls = "icon") {
  const svg = document.createElementNS(SVG, "svg");
  for (const [key, value] of Object.entries({
    class: cls, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  })) svg.setAttribute(key, value);
  for (const d of ICONS[name] || []) {
    const path = document.createElementNS(SVG, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function showTime(value, format) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : format.format(date);
}

// One of six soft colours, always the same for the same text (a sender, a mailbox).
function colourOf(text) {
  let hash = 0;
  for (const c of String(text || "")) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  return `c${hash % 6}`;
}

function avatar(name, size = "") {
  const words = String(name || "?").replace(/[<>"@].*$/, "").split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  const initials = (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "?").slice(0, 2)).toUpperCase();
  return el("span", { class: `avatar ${colourOf(name)} ${size}`.trim(), "aria-hidden": "true", text: initials });
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
    topic: q.get("topic") || "",
    sender: q.get("sender") || "",
    q: q.get("q") || "",
    id: q.get("id") || "",
  };
}

function urlFor(changes) {
  const next = { ...state(), ...changes };
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(next)) {
    if (value && !(key === "view" && value === "reply")) q.set(key, value);
  }
  const query = q.toString();
  return query ? `/?${query}` : "/";
}

function go(changes) {
  history.pushState(null, "", urlFor(changes));
  closeDrawer();
  render();
}

window.addEventListener("popstate", () => {
  $("search").value = state().q;
  render();
});

// --- left: views, mailboxes, account ---------------------------------------

function navItem({ label, count, active, hot, lead, onclick }) {
  return el("button", {
    type: "button", class: active ? "nav-item active" : "nav-item", "aria-current": active ? "page" : null, title: label, onclick,
  },
    lead,
    el("span", { class: "label", text: label }),
    count === undefined ? null : el("span", { class: hot && count ? "n hot" : "n", text: String(count) }));
}

function renderSidebar() {
  const s = state();
  $("nav").replaceChildren(
    el("div", { class: "nav-group" },
      VIEWS.map(([key, label, iconName]) => navItem({
        label, count: inbox.counts[key], active: inbox.view === key, hot: key === "p1", lead: icon(iconName),
        onclick: () => go({ view: key, id: "" }),
      }))),
    inbox.mailboxes.length ? el("div", { class: "nav-title", text: "Mailboxes" }) : null,
    el("div", { class: "nav-group" },
      inbox.mailboxes.map(([name, count]) => navItem({
        label: name, count, active: s.mailbox === name, lead: el("span", { class: `dot ${colourOf(name)}`, "aria-hidden": "true" }),
        // A second click on the chosen mailbox shows every mailbox again.
        onclick: () => go({ mailbox: s.mailbox === name ? "" : name, id: "" }),
      }))),
  );
}

let loadedAt = null;
let syncError = "";
function renderSync() {
  const sync = $("sync");
  sync.classList.toggle("stale", Boolean(syncError));
  sync.title = syncError ? `Not refreshed: ${syncError}. Click to try again.` : "Refresh now";
  sync.replaceChildren(
    icon(syncError ? "warning" : "refresh"),
    el("span", { class: "sync-text", text: syncError
      ? `Not refreshed since ${loadedAt ? showTime(loadedAt, clockTime) : "opening"}`
      : `Updated ${loadedAt ? showTime(loadedAt, clockTime) : "…"} · last 30 days` }));
}

function renderUser() {
  $("user-btn").replaceChildren(
    avatar(me.name, "sm"),
    el("span", { class: "who" }, el("b", { text: me.name }), el("span", { text: me.email })),
    icon("chevronUp", "icon chev"));
  $("open-users").hidden = !me.is_admin;
  // A Google-only account has no password to change.
  $("open-password").hidden = Boolean(me.google_only);
  for (const item of document.querySelectorAll("#user-menu [data-icon]")) item.prepend(icon(item.dataset.icon));
}

function toggleMenu(open = $("user-menu").hidden) {
  $("user-menu").hidden = !open;
  $("user-btn").setAttribute("aria-expanded", String(open));
  if (open) $("user-menu").querySelector("button:not([hidden])").focus();
}
$("user-btn").addEventListener("click", () => toggleMenu());
document.addEventListener("click", (event) => {
  if (!$("user-menu").hidden && !event.target.closest(".side-foot")) toggleMenu(false);
});
$("user-menu").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    toggleMenu(false);
    $("user-btn").focus();
  }
});

// Collapsed, the sidebar is a rail of icons; the choice is remembered on this device.
function setCollapsed(collapsed) {
  document.body.classList.toggle("side-collapsed", collapsed);
  localStorage.setItem("mailflow.sidebar", collapsed ? "collapsed" : "open");
  const label = collapsed ? "Expand the sidebar" : "Collapse the sidebar";
  $("collapse").setAttribute("aria-label", label);
  $("collapse").title = `${label}  [`;
}
$("collapse").append(icon("sidebar"));
$("collapse").addEventListener("click", () => setCollapsed(!document.body.classList.contains("side-collapsed")));
setCollapsed(localStorage.getItem("mailflow.sidebar") === "collapsed");

// On a phone the sidebar is a drawer.
function openDrawer() {
  document.body.classList.add("drawer-open");
  $("scrim").hidden = false;
}
function closeDrawer() {
  document.body.classList.remove("drawer-open");
  $("scrim").hidden = true;
}
$("scrim").addEventListener("click", closeDrawer);

// --- search ------------------------------------------------------------------

// Searches the list already loaded (sender, subject, AI summary and labels); typing does not
// add a history entry for every letter.
$("search").parentElement.querySelector(".search-icon").replaceWith(icon("search"));
$("search").addEventListener("input", () => {
  history.replaceState(null, "", urlFor({ q: $("search").value.trim() }));
  if (inbox) renderList();
});
$("search").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    $("search").value = "";
    $("search").dispatchEvent(new Event("input"));
    $("search").blur();
  }
});

function matches(item, words) {
  const text = [item.from_name, item.from_address, item.subject, item.summary, item.next_step, item.type, item.sender, item.mailbox]
    .join(" ").toLowerCase();
  return words.every((word) => text.includes(word));
}

function visibleItems() {
  const words = state().q.toLowerCase().split(/\s+/).filter(Boolean);
  return words.length ? inbox.items.filter((item) => matches(item, words)) : inbox.items;
}

// --- middle: the list -------------------------------------------------------

// A filter that looks like a chip: a native <select> laid over it does the choosing.
function pick(title, name, pairs) {
  const current = state()[name];
  const select = el("select", { "aria-label": title, onchange: (event) => go({ [name]: event.target.value, id: "" }) },
    el("option", { value: "", text: `Any ${title.toLowerCase()}` }),
    pairs.map(([value, count]) => el("option", { value, selected: value === current, text: `${value} (${count})` })));
  return el("span", { class: current ? "pick on" : "pick" },
    el("span", { text: current || title }), icon("chevronDown"), select);
}

function pill(text, onclear) {
  return el("span", { class: "pill" }, el("span", { text }),
    el("button", { type: "button", class: "pill-x", "aria-label": `Remove ${text}`, onclick: onclear }, icon("x")));
}

function listHead(shown) {
  const s = state();
  const viewLabel = (VIEWS.find(([key]) => key === inbox.view) || VIEWS[0])[1];
  return el("div", { class: "list-head" },
    el("div", { class: "list-title-row" },
      el("button", { type: "button", class: "icon-btn menu-btn", "aria-label": "Views and mailboxes", onclick: openDrawer }, icon("menu")),
      el("h1", { class: "list-title", text: viewLabel }),
      el("span", { class: "count", text: s.q ? `${shown} of ${inbox.items.length}` : `${inbox.items.length}` })),
    el("div", { class: "filter-bar" },
      pick("Topic", "topic", inbox.topics),
      pick("Sender", "sender", inbox.senders),
      s.mailbox ? pill(s.mailbox, () => go({ mailbox: "", id: "" })) : null,
      s.q ? pill(`“${s.q}”`, () => { $("search").value = ""; go({ q: "" }); }) : null));
}

function renderList() {
  const s = state();
  const list = $("list");
  const items = visibleItems();
  const header = listHead(items.length);
  if (!items.length) {
    list.replaceChildren(header, el("p", { class: "empty", text: "Nothing here." }));
    return;
  }
  const rows = items.map((item) => {
    const selected = String(item.id) === s.id;
    return el("button", {
      type: "button",
      class: `item ${item.status}${selected ? " selected" : ""}`,
      "aria-current": selected ? "true" : null,
      onclick: () => go({ id: String(item.id) }),
    },
      avatar(item.from_name || item.from_address),
      el("span", { class: "item-main" },
        el("span", { class: "item-top" },
          el("span", { class: "from", text: item.from_name || item.from_address || "(unknown sender)" }),
          el("span", { class: "time", text: showTime(item.received_at, listTime) })),
        el("span", { class: "subject-line" },
          el("span", { class: `prio ${item.priority || ""}`, text: item.priority || "–" }),
          el("span", { class: "subject", text: item.subject || "(no subject)" })),
        el("span", { class: "summary", text: item.summary || "" }),
        item.needs_reply && item.status !== "done" && item.next_step ? el("span", { class: "next", text: item.next_step }) : null,
        el("span", { class: "chips" },
          el("span", { class: `chip topic ${TOPIC_CLASS[item.type] || ""}`.trim(), text: item.type || "" }),
          item.sender ? el("span", { class: "chip role", text: item.sender }) : null,
          el("span", { class: "chip box", text: item.mailbox || "" }),
          item.status !== "open" ? el("span", { class: `chip st ${item.status}`, text: STATUS_TEXT[item.status] || item.status }) : null,
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
    el("div", { class: "detail-head" },
      el("h1", { class: "detail-subject", text: email.subject || "(no subject)" }),
      el("div", { class: "toolbar" },
        el("span", { class: `chip st ${email.status}`, text: STATUS_TEXT[email.status] || email.status }),
        el("span", { class: "spacer" }),
        (BUTTONS[email.status] || BUTTONS.done).map(([to, label, cls]) =>
          el("button", { type: "button", class: `btn ${cls}`, onclick: () => setStatus(email.id, to) }, label)))),
    el("div", { class: "sender" },
      avatar(email.from_name || email.from_address, "lg"),
      el("div", { class: "sender-text" },
        el("div", {}, el("span", { class: "sender-name", text: email.from_name || email.from_address || "" }),
          email.from_name ? el("span", { class: "muted", text: ` <${email.from_address || ""}>` }) : null),
        el("div", { class: "muted small", text: `to ${email.mailbox || ""} · ${showTime(email.received_at, fullTime)}` }))),
    el("section", { class: "ai" },
      el("div", { class: "ai-label", text: SORTED_BY[email.sorted_by] || SORTED_BY.ai }),
      el("p", { class: "summary", text: email.summary || "" }),
      email.needs_reply ? el("p", { class: "next", text: email.next_step || "" }) : null,
      el("div", { class: "chips" },
        el("span", { class: `prio ${email.priority || ""}`, text: email.priority || "–" }),
        el("span", { class: `chip topic ${TOPIC_CLASS[email.type] || ""}`.trim(), text: email.type || "" }),
        email.sender ? el("span", { class: "chip role", text: email.sender }) : null,
        el("span", { class: "chip", text: email.needs_reply ? "Needs a reply" : "No reply needed" }))),
    (email.body || "").trim() ? el("div", { class: "body", text: email.body }) : null,
    replyBox(email, keepDraft),
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

// --- loading ------------------------------------------------------------------

// The 60-second refresh must not fail silently: say since when the list is old, and why.
async function backgroundRefresh() {
  if (document.hidden) return;
  try {
    await loadInbox();
  } catch (error) {
    syncError = error.message;
    renderSync();
  }
}

// Each load gets a number; an answer that arrives after a newer load started is dropped, so a
// click during a slow load is never lost and an old answer never overwrites a newer one.
let inboxToken = 0;
async function loadInbox() {
  const token = ++inboxToken;
  const s = state();
  const q = new URLSearchParams({ view: s.view, mailbox: s.mailbox, topic: s.topic, sender: s.sender });
  const data = await api(`/api/inbox?${q}`);
  if (token !== inboxToken) return;
  inbox = data;
  loadedAt = new Date();
  syncError = "";
  renderSync();
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
  toggleMenu(false);
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
$("sync").addEventListener("click", render);

// --- start ------------------------------------------------------------------

(async () => {
  try {
    me = await api("/api/me");
  } catch {
    return;
  }
  renderUser();
  $("search").value = state().q;
  await render();
  setInterval(backgroundRefresh, REFRESH_MS);
  document.addEventListener("visibilitychange", backgroundRefresh);
})();
