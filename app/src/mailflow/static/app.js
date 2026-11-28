"use strict";
// MailFlow page. Every piece of email data goes into the page as text (textContent), never as
// HTML, so an email cannot inject markup or script.

const VIEWS = [
  ["reply", "Needs reply", "reply"],
  ["mine", "Mine", "user"],
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
  person: "Sorted by AI, corrected by a person",
};
// [to, label, class, icon, shortcut, tooltip] for each state an email can be in
const BUTTONS = {
  open: [
    ["waiting", "Waiting", "wait", "clock", "W", "Replied: now waiting on the customer"],
    ["done", "Done", "done", "check", "E", "Nothing more to do"],
  ],
  waiting: [["done", "Done", "done", "check", "E", "Nothing more to do"], ["open", "Reopen", "", "undo", "U", "Back to open"]],
  done: [["open", "Reopen", "", "undo", "U", "Back to open"]],
};
const REFRESH_MS = 60_000;
// The zone set on the server (MAILFLOW_TIME_ZONE, in the boot data; the script is deferred, so the
// element is already there). Missing, or unknown to this browser: the browser's own zone.
const TIME_ZONE = (() => {
  try {
    const zone = JSON.parse(document.getElementById("boot")?.textContent || "{}").timeZone;
    if (zone) {
      new Intl.DateTimeFormat("en-GB", { timeZone: zone });
      return zone;
    }
  } catch {
    // unreadable boot data, or a zone this browser does not know
  }
  return undefined;
})();
const listTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const fullTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "short", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const clockTime = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit" });
const dayKey = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const shortDay = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, day: "numeric", month: "short" });

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
  sparkles: ["M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z", "M19 17v4", "M17 19h4"],
  arrowLeft: ["m12 19-7-7 7-7", "M19 12H5"],
  undo: ["M3 7v6h6", "M21 17a9 9 0 0 0-15-6.7L3 13"],
  info: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 16v-4", "M12 8h.01"],
  keyboard: ["M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z", "M6 9h.01", "M10 9h.01", "M14 9h.01", "M18 9h.01", "M8 15h8"],
  user: ["M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", "M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"],
  userPlus: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M19 8v6", "M22 11h-6"],
  pencil: ["M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"],
  plug: ["M12 22v-5", "M9 8V2", "M15 8V2", "M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z"],
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

// Run a page change as a short cross-fade where rows slide into place (View Transitions); as is
// where the browser has none or the reader asked for less motion.
const calm = matchMedia("(prefers-reduced-motion: reduce)");
function smoothly(update) {
  if (!document.startViewTransition || calm.matches || document.hidden) return update();
  document.startViewTransition(update);
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
// A short message at the bottom; with an action (Undo) it stays a little longer. Undo lives exactly
// as long as its toast: any other toast replaces the offer, and Z then does nothing.
function toast(message, isError = false, action = null) {
  const box = $("toast");
  if (!action) undo = null;
  box.replaceChildren(el("span", { text: message }));
  if (action) {
    box.append(el("button", { type: "button", class: "toast-action", onclick: action[1] }, action[0], el("kbd", { text: "Z" })));
  }
  box.classList.toggle("error", isError);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; undo = null; }, isError ? 8000 : action ? 6000 : 3500);
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

// What the page shows now; go() compares against it to do as little as the change needs.
const LIST_KEYS = ["view", "mailbox", "topic", "sender"];
let shown = null;

// The lists already loaded, by view and filters: switching back to one shows it at once while a
// fresh copy loads. Any status change empties it (it moves emails between views).
const lists = new Map();
const listKey = (s) => LIST_KEYS.map((key) => s[key]).join("\u0000");

// Bring the page in line with the address bar. Only a new view or filter asks the server for the
// list again; opening another email or searching works on the list already loaded.
function show() {
  const s = state();
  const before = shown;
  shown = s;
  if (!inbox || !before || LIST_KEYS.some((key) => s[key] !== before[key])) {
    const known = lists.get(listKey(s));
    if (!known) {
      // Not the old view's rows under the new view's name while it loads.
      if (inbox) $("list").replaceChildren(...listSkeleton());
      return render();
    }
    showInbox(known, { remembered: true });
    backgroundRefresh();
    return renderDetail();
  }
  if (s.q !== before.q) renderList();
  else markSelected();
  return renderDetail();
}

// Load the working views for the same filters in the background, so switching to them is instant
// (Done and Everything can be long, so they load when asked for).
function loadOtherViews() {
  const s = state();
  for (const view of ["reply", "p1", "waiting"]) {
    const key = listKey({ ...s, view });
    if (lists.has(key)) continue;
    const q = new URLSearchParams({ view, mailbox: s.mailbox, topic: s.topic, sender: s.sender });
    const seen = statusChanges;
    api(`/api/inbox?${q}`).then((data) => {
      // Changes made since it was asked for may be missing from it: make them again (moving rows
      // is safe to repeat; the counts, the same for every list, come from the list on screen).
      if (seen !== statusChanges) {
        for (const change of recentChanges.filter((c) => c.n > seen)) placeRow(key, data, change.now);
        data.counts = { ...inbox.counts };
      }
      if (!lists.has(key)) lists.set(key, data);
    }, () => {});
  }
}

function go(changes) {
  history.pushState(null, "", urlFor(changes));
  closeDrawer();
  return show();
}

window.addEventListener("popstate", () => {
  $("search").value = state().q;
  show();
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
      : inbox?.stale ? "Updating from n8n…" : `Updated ${loadedAt ? showTime(loadedAt, clockTime) : "…"} · last 30 days` }));
}

function renderUser() {
  $("user-btn").replaceChildren(
    avatar(me.name, "sm"),
    el("span", { class: "who" }, el("b", { text: me.name }), el("span", { text: me.email })),
    icon("chevronUp", "icon chev"));
  $("open-users").hidden = !me.is_admin;
  $("open-integrations").hidden = !me.is_admin;
  // A Google-only account has no password to change.
  $("open-password").hidden = Boolean(me.google_only);
  for (const item of document.querySelectorAll("[data-icon]")) item.prepend(icon(item.dataset.icon));
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
  shown = state();
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

// "14:20" today, "Yesterday", else "20 Nov": the full time is in the tooltip.
function shortTime(value, today, yesterday) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const day = dayKey.format(date);
  if (day === today) return clockTime.format(date);
  if (day === yesterday) return "Yesterday";
  return shortDay.format(date);
}

const EMPTY = {
  reply: ["All caught up", "Nothing needs a reply right now."],
  p1: ["No P1s open", "Nothing urgent is waiting for you."],
  waiting: ["Nobody to wait for", "Emails you have answered show here until the sender writes back."],
  done: ["Nothing done yet", "Emails marked Done in the last 30 days show here."],
  all: ["No email yet", "Nothing arrived in the last 30 days."],
  mine: ["Nothing taken", "Emails you take (A) show here until they are done."],
};

function emptyState({ kind = "", iconName, title, text, action }) {
  return el("div", { class: `empty ${kind}`.trim() },
    el("span", { class: "empty-icon" }, icon(iconName)),
    el("b", { text: title }),
    el("p", { text }),
    action ? el("button", { type: "button", class: "btn", onclick: action[1] }, action[0]) : null);
}

// Grey bars where the rows will be, while the first list loads.
function listSkeleton() {
  return Array.from({ length: 6 }, () => el("div", { class: "skeleton", "aria-hidden": "true" },
    el("i", { class: "round" }),
    el("span", { class: "lines" }, el("i", { class: "w40" }), el("i", { class: "w85" }), el("i", { class: "w65" }))));
}

function row(item, ctx) {
  const name = item.from_name || item.from_address || "(unknown sender)";
  const selected = String(item.id) === ctx.selected;
  return el("button", {
    type: "button",
    class: `item ${item.status} ${item.status !== "done" ? item.priority || "" : ""}${selected ? " selected" : ""}`,
    "aria-current": selected ? "true" : null,
    "data-id": String(item.id),
    onclick: () => go({ id: String(item.id) }),
    // A pointer resting on a row fetches that email, so the click opens it at once.
    onpointerenter: () => prefetch(String(item.id)),
  },
    avatar(name),
    el("span", { class: "item-main" },
      el("span", { class: "item-top" },
        el("span", { class: "from", text: name }),
        item.waiting ? el("span", { class: item.late ? "age late" : "age", title: item.late ? "Waiting longer than its priority allows" : "Waiting for a reply" },
          icon("clock"), item.waiting) : null,
        el("span", { class: "time", title: showTime(item.received_at, fullTime), text: shortTime(item.received_at, ctx.today, ctx.yesterday) })),
      el("span", { class: "subject-line" },
        item.priority ? el("span", { class: `prio ${item.priority}`, text: item.priority }) : null,
        el("span", { class: "subject", text: item.subject || "(no subject)" })),
      item.needs_reply && item.status === "open" && item.next_step
        ? el("span", { class: "next" }, icon("reply"), el("span", { text: item.next_step }))
        : el("span", { class: "summary", text: item.summary || "" }),
      el("span", { class: "chips" },
        item.type ? el("span", { class: `chip topic ${TOPIC_CLASS[item.type] || ""}`.trim(), text: item.type }) : null,
        item.sender ? el("span", { class: "chip role", text: item.sender }) : null,
        // the state only where a view mixes them
        ctx.mixed && item.status !== "open" ? el("span", { class: `chip st ${item.status}`, text: STATUS_TEXT[item.status] }) : null,
        ctx.hideBox ? null : el("span", { class: "boxname" }, el("span", { class: `dot ${colourOf(item.mailbox)}` }), item.mailbox || ""),
        item.assignee ? holder(item.assignee) : null)));
}

// A small avatar for whoever has the email, "You" for your own.
function holder(userId) {
  const name = personName(userId);
  const mine = userId === me?.id;
  return el("span", { class: mine ? "holder mine" : "holder", title: mine ? "You have it" : `${name} has it` },
    avatar(name, "xs"), mine ? "You" : name.split(" ")[0]);
}

// Long lists render a page of rows at a time: the next page is added when the reader scrolls near
// the end (or J moves past it), so a 3,000-email view costs no more than a short one.
const PAGE_ROWS = 80;
let scrolledTo = "";
let rowsToShow = [];
let rowsShown = 0;
let rowContext = null;
const more = el("div", { class: "more", "aria-hidden": "true" });
const moreWatcher = new IntersectionObserver((entries) => {
  if (entries.some((entry) => entry.isIntersecting)) showMoreRows(rowsShown + PAGE_ROWS);
}, { root: $("list"), rootMargin: "800px 0px" });
moreWatcher.observe(more);

function showMoreRows(upTo) {
  const until = Math.min(rowsToShow.length, upTo);
  if (until <= rowsShown) return;
  more.before(...rowsToShow.slice(rowsShown, until).map((item, k) => {
    const node = row(item, rowContext);
    // The first rows get a name so a view transition can slide each into its new place.
    if (rowsShown + k < 40) node.style.viewTransitionName = `row-${item.id}`;
    return node;
  }));
  rowsShown = until;
  more.hidden = rowsShown >= rowsToShow.length;
}

function renderList() {
  const s = state();
  const list = $("list");
  const items = visibleItems();
  const header = listHead(items.length);
  if (!items.length) {
    const filtered = s.mailbox || s.topic || s.sender || s.q;
    const [title, text] = EMPTY[inbox.view] || EMPTY.all;
    list.replaceChildren(header, filtered
      ? emptyState({ iconName: "search", title: "No emails match", text: "Nothing in this view matches the filters.", action: ["Clear filters", () => {
        $("search").value = "";
        go({ mailbox: "", topic: "", sender: "", q: "", id: "" });
      }] })
      : emptyState({ kind: ["reply", "p1"].includes(inbox.view) ? "good" : "", iconName: inbox.view === "reply" || inbox.view === "p1" ? "check" : "inbox", title, text }));
    return;
  }
  // Worked out once per list, not once per row.
  rowContext = {
    selected: s.id,
    mixed: ["all", "p1"].includes(inbox.view),
    hideBox: Boolean(s.mailbox),
    today: dayKey.format(new Date()),
    yesterday: dayKey.format(new Date(Date.now() - 86_400_000)),
  };
  rowsToShow = items;
  rowsShown = 0;
  list.replaceChildren(header, more);
  const at = s.id ? items.findIndex((item) => String(item.id) === s.id) : -1;
  showMoreRows(Math.max(PAGE_ROWS, at + 1 + PAGE_ROWS / 2));
  keepSelectedInSight();
}

// Move the highlight without rebuilding the list.
function markSelected() {
  const id = state().id;
  if (rowContext) rowContext.selected = id;
  for (const node of $("list").querySelectorAll(".item.selected, .item[aria-current]")) {
    node.classList.remove("selected");
    node.removeAttribute("aria-current");
  }
  const at = id ? rowsToShow.findIndex((item) => String(item.id) === id) : -1;
  if (at >= rowsShown) showMoreRows(at + 1 + PAGE_ROWS / 2);
  const node = id && $("list").querySelector(`.item[data-id="${CSS.escape(id)}"]`);
  if (node) {
    node.classList.add("selected");
    node.setAttribute("aria-current", "true");
  }
  keepSelectedInSight();
}

// Keep the open email in sight when J/K move past the edge of the list (only when it changes,
// so a background refresh never scrolls the list away from where the reader left it).
function keepSelectedInSight() {
  const id = state().id;
  if (id && id !== scrolledTo) $("list").querySelector(".item.selected")?.scrollIntoView({ block: "nearest" });
  scrolledTo = id;
}

// --- right: one email -------------------------------------------------------

let detailToken = 0;
let openEmail = null; // the email on the right, for the E/W/U keys

function placeholder(iconName, title, text) {
  return el("div", { class: "placeholder" },
    el("span", { class: "empty-icon" }, icon(iconName)), el("b", { text: title }), text ? el("p", { text }) : null);
}

// The email above or below the open one in the list as shown (search included).
function neighbour(step) {
  if (!inbox) return null;
  const items = visibleItems();
  const at = items.findIndex((item) => String(item.id) === state().id);
  const next = at === -1 ? items[0] : items[at + step];
  return next ? String(next.id) : null;
}

function statusButtons(email) {
  return (BUTTONS[email.status] || BUTTONS.done).map(([to, label, cls, iconName, key, title]) =>
    el("button", { type: "button", class: `btn ${cls}`, title, "aria-label": label, onclick: () => setStatus(email.id, to) },
      icon(iconName), el("span", { class: "btn-label", text: label }), el("kbd", { text: key })));
}

// Who has it: staff Take an email or Let go of theirs (key A); an admin picks anyone, or nobody.
function assignControl(email) {
  const current = assigneeOf(email);
  if (me.is_admin) {
    const people = inbox?.people || []; // empty until the list has loaded
    const select = el("select", {
      "aria-label": "Who has it", onchange: (event) => assign(email.id, event.target.value ? Number(event.target.value) : null),
    },
      // A holder no longer on the team still shows, so "Nobody" can be picked to free the email.
      current !== null && !people.some((person) => person.id === current)
        ? el("option", { value: String(current), text: personName(current), selected: true, disabled: true }) : null,
      el("option", { value: "", text: "Nobody", selected: current === null }),
      people.map((person) => el("option", { value: String(person.id), selected: person.id === current, text: person.id === me.id ? `${person.name} (you)` : person.name })));
    return el("span", { class: current ? "pick on assign" : "pick assign", title: "Who has it  A" },
      current ? avatar(personName(current), "xs") : icon("userPlus"),
      el("span", { text: current ? (current === me.id ? "You" : personName(current)) : "Assign" }), icon("chevronDown"), select);
  }
  if (current === null) {
    return el("button", { type: "button", class: "btn", title: "Take it: it shows under Mine", onclick: () => assign(email.id, me.id) },
      icon("userPlus"), "Take", el("kbd", { text: "A" }));
  }
  if (current === me.id) {
    return el("button", { type: "button", class: "btn", title: "Let it go: nobody has it then", onclick: () => assign(email.id, null) },
      avatar(me.name, "xs"), "Yours · let go", el("kbd", { text: "A" }));
  }
  return el("span", { class: "holder big", title: `${personName(current)} has it; an admin can give it to someone else` },
    avatar(personName(current), "xs"), personName(current));
}
function detailBar(email) {
  const arrow = (step, iconName, label, key) => {
    const id = neighbour(step);
    return el("button", {
      type: "button", class: "icon-btn", title: `${label}  ${key}`, "aria-label": label, disabled: !id,
      onclick: () => id && go({ id }),
    }, icon(iconName));
  };
  return el("div", { class: "detail-bar" },
    el("button", { type: "button", class: "icon-btn back", "aria-label": "Back to the list", onclick: () => go({ id: "" }) }, icon("arrowLeft")),
    el("span", { class: "nav-arrows" }, arrow(-1, "chevronUp", "Previous email", "K"), arrow(1, "chevronDown", "Next email", "J")),
    email ? el("span", { class: `chip st ${email.status}`, text: STATUS_TEXT[email.status] || email.status }) : null,
    el("span", { class: "spacer" }),
    email ? assignControl(email) : null,
    email ? el("span", { class: "divider" }) : null,
    email ? statusButtons(email) : null);
}

// Emails already fetched (or on their way), by id. The text of an email never changes; its status
// is taken from the list, which is kept current.
const emails = new Map();
const fetched = new Set(); // ids whose fetch has finished: those render with no wait at all
function fetchEmail(id) {
  if (!emails.has(id)) {
    emails.set(id, api(`/api/emails/${encodeURIComponent(id)}`).then((email) => {
      fetched.add(id);
      return email;
    }, (error) => {
      emails.delete(id);
      throw error;
    }));
  }
  return emails.get(id);
}
function prefetch(id) {
  if (id) fetchEmail(id).catch(() => {});
}
function setCachedStatus(id, to) {
  emails.get(String(id))?.then((email) => { email.status = to; }, () => {});
}

async function renderDetail() {
  const s = state();
  const detail = $("detail");
  document.body.classList.toggle("has-detail", Boolean(s.id));
  if (!s.id) {
    openEmail = null;
    detail.dataset.id = "";
    detail.replaceChildren(placeholder("inbox", "No email open", "Pick one from the list, or press J to start at the top."));
    return;
  }
  const token = ++detailToken;
  const listed = inbox?.items.find((item) => String(item.id) === s.id);
  const keepDraft = detail.dataset.id === s.id ? detail.querySelector("textarea")?.value || "" : "";
  const fresh = detail.dataset.id !== s.id; // another email: it eases in; the same one is redrawn still
  // Not fetched yet: show what the list already knows (all but the text) straight away, and
  // let E/W/U act on it; the text follows.
  const preview = !fetched.has(s.id) && fresh;
  if (preview) {
    openEmail = listed ? { ...listed, can_reply: inbox.reply_mailboxes.includes(listed.mailbox) } : null;
    detail.dataset.id = listed ? s.id : "";
    detail.replaceChildren(...(listed ? emailView(listed, { loading: true, enter: true }) : [detailBar(null), placeholder("inbox", "Opening…")]));
  }
  let email;
  try {
    email = await fetchEmail(s.id);
  } catch (error) {
    if (token !== detailToken) return;
    openEmail = null;
    detail.dataset.id = "";
    detail.replaceChildren(detailBar(null), placeholder("warning", "This email could not open", error.message));
    return;
  }
  if (token !== detailToken) return;
  if (listed) email.status = listed.status;
  detail.dataset.id = s.id;
  openEmail = email;
  detail.replaceChildren(...emailView(email, { draft: keepDraft, enter: fresh && !(preview && listed) }));
  if (fresh) loadActivity(s.id);
  // J and K (and E, which opens the next one) will want these.
  prefetch(neighbour(1));
  prefetch(neighbour(-1));
}

// A label that is also a menu: what the AI chose, which a person can change (a native <select>
// laid over the chip does the choosing).
function labelPick(cls, text, label, options, current, onpick) {
  const select = el("select", { "aria-label": label, onchange: (event) => onpick(event.target.value) },
    // Nothing chosen yet (an unsorted email): a placeholder, so every real choice fires a change.
    options.some(([value]) => value === current) ? null : el("option", { value: "", text: "–", selected: true, disabled: true }),
    options.map(([value, name]) => el("option", { value, text: name, selected: value === current })));
  return el("span", { class: `${cls} editable`, title: `${label}: change it if the AI got it wrong` }, text, select);
}

function labelPicks(email) {
  const reply = email.needs_reply ? "yes" : "no";
  return [
    labelPick(`prio ${email.priority || ""}`, email.priority || "–", "Priority",
      ["P1", "P2", "P3"].map((p) => [p, p]), email.priority, (value) => relabel(email.id, { priority: value })),
    labelPick(`chip topic ${TOPIC_CLASS[email.type] || ""}`, email.type || "No topic", "Topic",
      (inbox?.all_topics || []).map((t) => [t, t]), email.type, (value) => relabel(email.id, { type: value })),
    labelPick("chip", email.needs_reply ? "Needs a reply" : "No reply needed", "Needs a reply",
      [["yes", "Needs a reply"], ["no", "No reply needed"]], reply, (value) => relabel(email.id, { needs_reply: value === "yes" })),
  ];
}

// Who did what to the email, newest first (loaded each time it is opened, and after a change).
const activityCache = new Map();
function activityView(id) {
  const entries = activityCache.get(id);
  return el("section", { class: "activity", id: "activity", "aria-label": "Activity" },
    el("h2", { text: "Activity" }),
    !entries ? el("p", { class: "muted small", text: "Loading…" })
      : !entries.length ? el("p", { class: "muted small", text: "Nobody has done anything with it yet." })
        : el("ol", {}, entries.map((entry) => el("li", {},
          avatar(entry.name, "xs"),
          el("span", {}, el("b", { text: entry.name }), ` ${entry.text}`),
          el("time", { text: showTime(entry.at * 1000, listTime) })))));
}
async function loadActivity(id) {
  const entries = await api(`/api/emails/${encodeURIComponent(id)}/activity`).catch(() => null);
  if (!entries) return;
  activityCache.set(id, entries);
  if (state().id === id) $("activity")?.replaceWith(activityView(id));
}

// The open email: the action bar, then subject and labels, the AI card, the message and the reply
// box. `loading`: the text is on its way, so grey lines stand in for it and there is no reply box yet.
function emailView(email, { loading = false, draft = "", enter = false } = {}) {
  const name = email.from_name || email.from_address || "";
  const unsorted = email.sorted_by === "unsorted";
  const text = loading
    ? el("div", { class: "body loading", "aria-busy": "true" }, el("i", { class: "w85" }), el("i", { class: "w65" }), el("i", { class: "w40" }))
    : (email.body || "").trim()
      ? el("div", { class: "body", text: email.body })
      : el("div", { class: "body none", text: "This email has no text." });
  return [
    detailBar(email),
    el("article", { class: enter ? "detail-body enter" : "detail-body" },
      el("h1", { class: "detail-subject", text: email.subject || "(no subject)" }),
      el("div", { class: "chips detail-tags" },
        loading ? [
          email.priority ? el("span", { class: `prio ${email.priority}`, text: email.priority }) : null,
          email.type ? el("span", { class: `chip topic ${TOPIC_CLASS[email.type] || ""}`.trim(), text: email.type }) : null,
        ] : labelPicks(email),
        email.sender ? el("span", { class: "chip role", text: email.sender }) : null,
        el("span", { class: "boxname" }, el("span", { class: `dot ${colourOf(email.mailbox)}` }), email.mailbox || "")),
      el("section", { class: unsorted ? "ai unsorted" : "ai", "aria-label": "What the AI made of it" },
        el("div", { class: "ai-label" }, icon(unsorted ? "warning" : "sparkles"), SORTED_BY[email.sorted_by] || SORTED_BY.ai),
        el("p", { class: "summary", text: email.summary || "" }),
        email.needs_reply && email.next_step
          ? el("div", { class: "next-step" }, icon("reply"), el("span", {}, el("b", { text: "Next step: " }), email.next_step))
          : null),
      el("section", { class: "message", "aria-label": "The email" },
        el("div", { class: "sender" },
          avatar(name, "lg"),
          el("div", { class: "sender-text" },
            el("div", {}, el("span", { class: "sender-name", text: name }),
              email.from_name ? el("span", { class: "muted", text: ` <${email.from_address || ""}>` }) : null),
            el("div", { class: "muted small", text: `to ${email.mailbox || ""}` })),
          el("span", { class: "when", text: showTime(email.received_at, fullTime) })),
        text),
      loading ? null : replyBox(email, draft),
      activityView(String(email.id))),
  ];
}

function replyBox(email, draft) {
  if (!email.can_reply) {
    return el("p", { class: "note" }, icon("info"),
      el("span", {}, "Replies from this page are not set up for the ", el("b", { text: email.mailbox || "" }),
        " mailbox: answer from your mail app, then mark it Waiting or Done here. An admin can set up SMTP under Integrations."));
  }
  if (email.status === "done") return null;
  const text = el("textarea", { rows: "6", required: true, placeholder: `Write to ${email.from_name || email.from_address}…`, "aria-label": "Reply" });
  text.value = draft;
  const send = el("button", { type: "submit", class: "btn primary" }, "Send", el("kbd", { text: "Ctrl ↵" }));
  // Ctrl+Enter (⌘+Enter on a Mac) sends, as in Gmail and Front.
  text.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  const form = el("form", {
    class: "reply",
    onsubmit: async (event) => {
      event.preventDefault();
      if (!text.value.trim()) return;
      send.disabled = true;
      send.firstChild.textContent = "Sending…";
      try {
        await api(`/api/emails/${email.id}/reply`, { method: "POST", body: { text: text.value } });
        setCachedStatus(email.id, "waiting");
        text.value = "";
        toast("Reply sent. The email is now waiting on the customer.");
        await render();
        loadActivity(String(email.id));
      } catch (error) {
        toast(error.message, true);
      } finally {
        send.disabled = false;
        send.firstChild.textContent = "Send";
      }
    },
  },
    el("div", { class: "reply-to" }, icon("reply"), el("span", {}, "Reply from ", el("b", { text: email.mailbox }), " to ", el("b", { text: email.from_address || "" }))),
    text,
    el("div", { class: "reply-foot" },
      el("span", { class: "hint", text: "Sent in the same conversation; the email then moves to Waiting." }),
      send));
  return form;
}

// Which views an email belongs to: the server's rules (queue.py IN_VIEW), so the page can move an
// email at once instead of waiting for the server.
const IN_VIEW = {
  reply: (item) => item.needs_reply && item.status === "open",
  mine: (item) => item.assignee === me?.id && item.status !== "done",
  p1: (item) => item.priority === "P1" && item.status !== "done",
  waiting: (item) => item.status === "waiting",
  done: (item) => item.status === "done",
  all: () => true,
};
// And its order (queue.py build): the working views P1 to P3 then oldest first, Done and
// Everything newest first. received_at is ISO 8601 in one format, so text order is time order.
const RANK = { P1: 0, P2: 1, P3: 2 };
function comesBefore(view, a, b) {
  if (view === "done" || view === "all") return a.received_at > b.received_at;
  const ra = RANK[a.priority] ?? 3;
  const rb = RANK[b.priority] ?? 3;
  return ra !== rb ? ra < rb : a.received_at < b.received_at;
}
// A kept list's filters, from its key (view, mailbox, topic, sender).
function passesFilters(key, item) {
  const [, mailbox, topic, sender] = key.split("\u0000");
  return (!mailbox || item.mailbox === mailbox) && (!topic || item.type === topic) && (!sender || item.sender === sender);
}
let undo = null; // the last status change, while its toast is up
function runUndo() {
  const u = undo;
  undo = null;
  if (u) {
    $("toast").hidden = true;
    u();
  }
}

// Change the lists on the page now, the one on screen and every kept one: the counts, and the row
// updated, leaving a view it no longer belongs to, or joining one it now belongs to, in the
// server's order. `patch` holds the fields that change (status, assignee, labels); `known` is the
// email as last seen, for one no longer on screen (Undo). Returns the email after the change.
function applyLocally(id, patch, known = null) {
  const listed = inbox?.items.find((item) => item.id === id) || known;
  if (!listed) return null;
  const was = { ...listed };
  const now = { ...listed, ...patch };
  if (patch.status && patch.status !== "open") Object.assign(now, { waiting: "", late: false });
  for (const [key, list] of new Map([...lists, [listKey(state()), inbox]])) {
    for (const [view, inView] of Object.entries(IN_VIEW)) list.counts[view] += (inView(now) ? 1 : 0) - (inView(was) ? 1 : 0);
    placeRow(key, list, now);
  }
  recentChanges.push({ n: statusChanges + 1, now });
  if (recentChanges.length > 50) recentChanges.shift();
  return now;
}

// Put one email where it now belongs in one list: in its place, gone, or inserted in order.
function placeRow(key, list, now) {
  const at = list.items.findIndex((item) => item.id === now.id);
  if (at >= 0) list.items.splice(at, 1);
  if (!((IN_VIEW[list.view] || IN_VIEW.all)(now) && passesFilters(key, now))) return;
  const place = list.items.findIndex((other) => comesBefore(list.view, now, other));
  list.items.splice(place < 0 ? list.items.length : place, 0, { ...now });
}
const recentChanges = []; // the last changes made here, for lists that were on their way meanwhile

// Change an email on the page at once, then tell the server in the background (as Superhuman and
// Front do). If the email leaves the view and it was open, the next one opens. Saves for one email
// go one after another, and no list is fetched while a save is under way (it would show the old
// state); if the server refuses, the list is loaded again so the page shows the truth.
let pending = 0;
const saving = new Map(); // email id → its last save, which the next one waits for
async function change(id, patch, path, body, known = null) {
  const listed = inbox?.items.find((item) => item.id === id) || known;
  const wasOpen = state().id === String(id);
  const leaves = Boolean(listed && inbox) && !(IN_VIEW[inbox.view] || IN_VIEW.all)({ ...listed, ...patch });
  const next = wasOpen && leaves ? neighbour(1) || neighbour(-1) || "" : null;

  const now = applyLocally(id, patch, known);
  emails.get(String(id))?.then((email) => Object.assign(email, patch), () => {});
  if (openEmail?.id === id) Object.assign(openEmail, patch);
  inboxToken += 1; // a list already on its way predates this change: drop it
  statusChanges += 1; // likewise the other views being loaded ahead
  // The row moves and the next email opens as one short animation (the next email shows from
  // what the list knows, synchronously, so the animation never waits for the network).
  smoothly(() => {
    if (inbox) {
      renderSidebar();
      renderList();
    }
    if (next !== null) go({ id: next });
    else if (wasOpen) renderDetail();
  });

  pending += 1;
  const run = (saving.get(id) || Promise.resolve()).catch(() => {}).then(() => api(path, { method: "POST", body }));
  saving.set(id, run);
  try {
    await run;
  } catch (error) {
    pending -= 1;
    toast(`Not saved: ${error.message}`, true);
    emails.delete(String(id));
    await render();
    return { now, saved: false };
  } finally {
    if (saving.get(id) === run) saving.delete(id);
  }
  pending -= 1;
  if (state().id === String(id)) loadActivity(String(id));
  // Once every change is saved, take the server's list (late flags, waiting times) quietly.
  if (pending === 0) {
    backgroundRefresh();
    loadOtherViews();
  }
  return { now, saved: true };
}

// Done / Waiting / Reopen, with Undo, which puts the status back and reopens the email.
function setStatus(id, to, { quiet = false, known = null } = {}) {
  const listed = inbox?.items.find((item) => item.id === id) || known;
  const before = listed?.status ?? (openEmail?.id === id ? openEmail.status : undefined);
  const result = change(id, { status: to }, `/api/emails/${id}/status`, { to }, known);
  if (quiet) {
    toast(`Back to ${STATUS_TEXT[to]}.`);
  } else if (before && before !== to) {
    // Undo needs the email as it was; one never in the list on screen is only reopened, not re-listed.
    const was = listed ? { ...listed, status: to, ...(to === "open" ? {} : { waiting: "", late: false }) } : null;
    undo = () => {
      setStatus(id, before, { quiet: true, known: was });
      go({ id: String(id) });
    };
    toast(`Marked ${STATUS_TEXT[to]}.`, false, ["Undo", runUndo]);
  } else {
    toast(`Marked ${STATUS_TEXT[to]}.`);
  }
  return result;
}

// Who has an email. Staff take one or let theirs go; an admin gives it to anyone.
function personName(id) {
  return inbox?.people.find((person) => person.id === id)?.name || "someone";
}
function assign(id, userId) {
  const text = userId === null ? "Nobody has it now." : userId === me.id ? "It's yours." : `Given to ${personName(userId)}.`;
  change(id, { assignee: userId }, `/api/emails/${id}/assign`, { user_id: userId }).then(({ saved }) => saved && toast(text));
}
function assigneeOf(email) {
  const listed = inbox?.items.find((item) => item.id === email.id);
  return listed ? listed.assignee : email.assignee ?? null;
}

// A person's correction of the AI's labels; the email is marked as sorted by a person.
function relabel(id, patch) {
  scrolledTo = ""; // a new priority can move the row: bring it back into sight
  change(id, { ...patch, sorted_by: "person" }, `/api/emails/${id}/labels`, patch).then(({ saved }) => saved && toast("Labels saved."));
}

// --- loading ------------------------------------------------------------------

// The 60-second refresh must not fail silently: say since when the list is old, and why.
async function backgroundRefresh() {
  if (document.hidden || pending) return; // a save under way refreshes when it is done
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
let statusChanges = 0; // made on this page; a list asked for before one is out of date
let staleTimer = null;
let staleDelay = 2000;
async function loadInbox() {
  const token = ++inboxToken;
  const s = state();
  const q = new URLSearchParams({ view: s.view, mailbox: s.mailbox, topic: s.topic, sender: s.sender });
  const data = await api(`/api/inbox?${q}`);
  if (token !== inboxToken) return;
  showInbox(data);
}

function showInbox(data, { remembered = false } = {}) {
  inbox = data;
  lists.set(listKey(state()), data);
  if (!remembered) {
    loadedAt = new Date();
    syncError = "";
  }
  renderSync();
  renderSidebar();
  renderList();
  if (!state().id) prefetch(neighbour(1)); // what J would open first
  if (remembered) return;
  // The server sent the list it had while it reads a fresh one from n8n: ask again shortly, and
  // again, waiting longer each time (2 s, 4 s … 30 s) while n8n is slow or away.
  clearTimeout(staleTimer);
  if (data.stale) {
    staleTimer = setTimeout(backgroundRefresh, staleDelay);
    staleDelay = Math.min(staleDelay * 2, 30_000);
  } else {
    staleDelay = 2000;
  }
  setTimeout(loadOtherViews, 300);
}

// A failed load keeps the list already on screen (flagged as not refreshed); with nothing to keep
// it says what went wrong and offers to try again.
async function render() {
  try {
    await Promise.all([loadInbox(), renderDetail()]);
  } catch (error) {
    if (error.status === 401) return;
    syncError = error.message;
    renderSync();
    if (inbox) {
      toast(error.message, true);
      return;
    }
    $("list").replaceChildren(emptyState({
      kind: "bad", iconName: "warning", title: "The list could not load", text: error.message, action: ["Try again", render],
    }));
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
$("open-shortcuts").addEventListener("click", () => openDialog($("shortcuts-dialog")));
$("open-guide").addEventListener("click", () => openDialog($("guide-dialog")));
$("guide-tip").hidden = localStorage.getItem("mf-guide-dismissed") === "1";
$("guide-tip-open").addEventListener("click", () => openDialog($("guide-dialog")));
$("guide-tip-close").addEventListener("click", () => {
  localStorage.setItem("mf-guide-dismissed", "1");
  $("guide-tip").hidden = true;
});
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

let googleSignIn = false; // whether "Continue with Google" is on; then a user may have no password

function badge(text, cls = "") {
  return el("span", { class: `chip ${cls}`.trim(), text });
}

async function loadUsers() {
  const users = await api("/api/users");
  $("users-body").replaceChildren(...users.map((user) => {
    const self = user.id === me.id;
    const ways = [
      user.google_only ? null : badge("Password"),
      user.google_linked ? badge("Google", "google") : user.google_only ? badge("Google, not yet used", "google") : null,
    ];
    const actions = self ? [el("span", { class: "muted small", text: "That's you" })] : [
      el("button", {
        type: "button", class: "btn small",
        onclick: () => openReset(user),
      }, user.google_only ? "Set a password" : "Reset password"),
      el("button", {
        type: "button", class: user.active ? "btn small danger" : "btn small",
        onclick: () => userAction(`/api/users/${user.id}/${user.active ? "disable" : "enable"}`),
      }, user.active ? "Disable" : "Enable"),
    ];
    return el("tr", { class: user.active ? "" : "disabled" },
      el("td", {}, el("span", { class: "person" }, avatar(user.name, "sm"),
        el("span", { class: "who" }, el("b", { text: user.name }), el("span", { text: user.email })))),
      el("td", {}, badge(user.is_admin ? "Admin" : "Staff", user.is_admin ? "role" : ""), user.active ? null : badge("Disabled", "off")),
      el("td", {}, el("span", { class: "chips" }, ways)),
      el("td", {}, el("span", { class: "row-actions" }, actions)));
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

let resetting = null;
function openReset(user) {
  resetting = user;
  $("reset-who").textContent = `${user.name} · ${user.email}`;
  $("reset-form").reset();
  openDialog($("reset-dialog"));
}
$("reset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api(`/api/users/${resetting.id}/reset`, { method: "POST", body: { password: event.target.password.value } });
    $("reset-dialog").close();
    toast(`New password set for ${resetting.name}.`);
    await loadUsers();
  } catch (error) {
    formError(event.target, error.message);
  }
});

// With Google sign-in on, the first password may stay empty: that person signs in with Google only.
function setPasswordRule() {
  const input = $("add-user-form").password;
  input.required = !googleSignIn;
  if (googleSignIn) input.removeAttribute("minlength");
  $("first-password-label").textContent = googleSignIn
    ? "First password (leave empty: Google sign-in only)"
    : "First password (12+ characters)";
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
    const googleOnly = !form.password.value;
    form.reset();
    form.querySelector(".error").hidden = true;
    toast(googleOnly
      ? "User added. They sign in with Continue with Google, using that email address."
      : "User added. Give them their first password; they can change it after signing in.");
    await loadUsers();
  } catch (error) {
    formError(form, error.message);
  }
});

$("logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
    location.href = "/login";
  } catch (error) {
    // Not signed out on the server: say so rather than show the sign-in page over a live session.
    toast(`Not signed out: ${error.message}`, true);
  }
});
$("sync").addEventListener("click", render);

// --- keyboard ---------------------------------------------------------------

// Single keys as in Gmail, Front and Superhuman. They stay out of the way while typing and
// while a dialog is open; Ctrl/Alt/Cmd combinations belong to the browser.
function typing(target) {
  return target.closest("input, textarea, select, [contenteditable]") !== null;
}

function act(to) {
  if (openEmail && (BUTTONS[openEmail.status] || []).some(([status]) => status === to)) setStatus(openEmail.id, to);
}

// A: take the open email, or let it go if it is yours (an admin uses the menu to give it away).
function takeOrLetGo() {
  if (!openEmail) return;
  const current = assigneeOf(openEmail);
  if (current === null) assign(openEmail.id, me.id);
  else if (current === me.id) assign(openEmail.id, null);
  else toast(`${personName(current)} has it.${me.is_admin ? " Use the menu to give it to someone else." : ""}`);
}

function step(by) {
  const id = neighbour(by);
  if (id) go({ id });
}

const KEYS = {
  j: () => step(1), ArrowDown: () => step(1),
  k: () => step(-1), ArrowUp: () => step(-1),
  e: () => act("done"), w: () => act("waiting"), u: () => act("open"),
  z: runUndo,
  a: takeOrLetGo,
  r: () => $("detail").querySelector(".reply textarea")?.focus(),
  "/": () => $("search").focus(),
  "[": () => $("collapse").click(),
  "?": () => openDialog($("shortcuts-dialog")),
  Escape: () => state().id && go({ id: "" }),
  // 1–6: the views, in the sidebar's order
  ...Object.fromEntries(VIEWS.map(([view], i) => [String(i + 1), () => go({ view, id: "" })])),
};

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
  if (document.querySelector("dialog[open]") || typing(event.target) || !$("user-menu").hidden) return;
  const handler = KEYS[event.key];
  if (!handler) return;
  event.preventDefault();
  handler();
});

// --- start ------------------------------------------------------------------

(async () => {
  $("search").value = state().q;
  shown = state();
  // The server sends the account, whether Google sign-in is on, and the list and open email when
  // it has them in memory, with the page; what it did not send is loaded now.
  const boot = JSON.parse($("boot").textContent);
  me = boot.me;
  googleSignIn = boot.google;
  if (boot.email) {
    emails.set(String(boot.email.id), Promise.resolve(boot.email));
    fetched.add(String(boot.email.id));
  }
  let first;
  if (boot.inbox) {
    showInbox(boot.inbox);
    first = renderDetail();
  } else {
    $("list").replaceChildren(...listSkeleton());
    first = render();
  }
  renderUser();
  setPasswordRule();
  await first;
  setInterval(backgroundRefresh, REFRESH_MS);
  document.addEventListener("visibilitychange", backgroundRefresh);
})();
