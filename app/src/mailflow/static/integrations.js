"use strict";
// Integrations (admins): connect mailboxes, set up replies over SMTP, choose the AI that sorts the
// emails, and where the Telegram alerts go. Uses app.js's helpers (el, api, icon, toast, openDialog).
// Passwords and keys are sent once and never come back from the server.

const MAILBOX_PRESETS = {
  gmail: {
    label: "Gmail or Google Workspace", imap: ["imap.gmail.com", 993], smtp: ["smtp.gmail.com", 465, "ssl"],
    hint: "Use an app password: Google Account → Security → 2-Step Verification → App passwords.",
  },
  microsoft: {
    label: "Outlook or Microsoft 365", imap: ["outlook.office365.com", 993], smtp: ["smtp.office365.com", 587, "starttls"],
    hint: "The mailbox must allow IMAP and SMTP AUTH; many Microsoft 365 tenants turn password sign-in off.",
  },
  other: { label: "Another provider", imap: ["", 993], smtp: ["", 587, "starttls"], hint: "Your provider's IMAP settings, with TLS (usually port 993)." },
};
const SINCE = [["0", "From today"], ["7", "From the last 7 days"], ["30", "From the last 30 days"]];
const NEW_KEY = "__new__";

let integrations = null; // the last overview from the server
let integrationsTab = "mailboxes";
let smtpFor = null; // the mailbox whose reply settings are open

function field(label, input, hint = null) {
  return el("label", {}, label, input, hint ? el("span", { class: "hint", text: hint }) : null);
}

function select(name, pairs, value) {
  const box = el("select", { name });
  for (const [key, text] of pairs) box.append(el("option", { value: key, text, selected: key === value }));
  return box;
}

function errorLine() {
  return el("p", { class: "error", role: "alert", hidden: true });
}

function busy(button, text) {
  const before = button.textContent;
  button.disabled = true;
  button.textContent = text;
  return () => { button.disabled = false; button.textContent = before; };
}

// Run a request from a form: errors show in the form, success shows a toast and reloads the overview.
async function attempt(form, button, working, request, done) {
  const box = form.querySelector(".error");
  box.hidden = true;
  box.classList.remove("ok");
  const restore = busy(button, working);
  try {
    const result = await request();
    if (done) await done(result, box);
  } catch (error) {
    box.textContent = error.message;
    box.hidden = false;
  } finally {
    restore();
  }
}

function said(box, text) {
  box.textContent = text;
  box.classList.add("ok");
  box.hidden = false;
}

async function loadIntegrations() {
  integrations = await api("/api/integrations");
  renderIntegrations();
}

function renderIntegrations() {
  const tabs = [["mailboxes", "Mailboxes"], ["ai", "AI that sorts"], ["alerts", "Alerts"]];
  const panel = { mailboxes: mailboxesPanel, ai: aiPanel, alerts: alertsPanel }[integrationsTab]();
  $("integrations-body").replaceChildren(
    integrations.error ? el("p", { class: "note warn" }, icon("warning"), el("span", { text: integrations.error })) : "",
    el("div", { class: "tabs", role: "tablist" }, tabs.map(([key, text]) => el("button", {
      type: "button", role: "tab", class: key === integrationsTab ? "tab active" : "tab",
      "aria-selected": String(key === integrationsTab),
      onclick: () => { integrationsTab = key; smtpFor = null; renderIntegrations(); },
    }, text))),
    el("div", { class: "tab-panel", role: "tabpanel" }, panel));
}

// --- mailboxes -----------------------------------------------------------------

function mailboxRow(box) {
  const replies = box.smtp ? `SMTP · ${box.smtp.from_address}` : box.replies === "gmail" ? "Gmail, through n8n" : "Not set up";
  const actions = [
    // A mailbox known only for its SMTP replies has no collector in n8n to pause.
    box.workflow_id ? el("button", {
      type: "button", class: "btn small",
      onclick: () => mailboxAction(`/api/integrations/mailboxes/${encodeURIComponent(box.label)}/${box.active ? "pause" : "resume"}`, "POST",
        box.active ? `${box.label} is paused: no new emails are collected.` : `${box.label} collects again.`),
    }, box.active ? "Pause" : "Resume") : null,
    el("button", { type: "button", class: "btn small", onclick: () => { smtpFor = box.label; renderIntegrations(); } }, "Replies…"),
    box.managed ? el("button", {
      type: "button", class: "btn small danger",
      onclick: () => {
        if (confirm(`Remove ${box.label}? MailFlow stops collecting from it; emails already in the list stay.`)) {
          mailboxAction(`/api/integrations/mailboxes/${encodeURIComponent(box.label)}`, "DELETE", `${box.label} removed.`);
        }
      },
    }, "Remove") : null,
  ];
  return el("tr", {},
    el("td", {}, el("span", { class: "mailbox-name" }, el("span", { class: `dot ${colourOf(box.label)}`, "aria-hidden": "true" }), el("b", { text: box.label }))),
    el("td", {}, el("span", { class: box.active ? "chip on" : "chip off", text: box.workflow_id ? (box.active ? "Collecting" : "Paused") : "No collector" })),
    el("td", { class: "muted", text: box.last_run ? `Last email ${showTime(box.last_run, fullTime)}` : "No email yet" }),
    el("td", { text: replies }),
    el("td", {}, el("span", { class: "row-actions" }, actions)));
}

async function mailboxAction(path, method, message) {
  try {
    await api(path, { method });
    await loadIntegrations();
    toast(message);
  } catch (error) {
    toast(error.message, true);
  }
}

function mailboxesPanel() {
  const boxes = integrations.mailboxes;
  return [
    el("p", { class: "muted small", text: "Each mailbox is checked about every minute; new emails are sorted and listed here." }),
    boxes.length ? el("table", { class: "users mailboxes" },
      el("thead", {}, el("tr", {}, ["Mailbox", "State", "Collected", "Replies", ""].map((h) => el("th", { text: h })))),
      el("tbody", {}, boxes.map(mailboxRow))) : el("p", { class: "muted", text: "No mailboxes yet." }),
    // The reply settings of the mailbox picked, or (none picked, or it is gone) the connect form.
    (smtpFor && smtpForm(boxes.find((box) => box.label === smtpFor))) || connectForm(),
  ];
}

function connectForm() {
  const preset = select("preset", Object.entries(MAILBOX_PRESETS).map(([key, p]) => [key, p.label]), "gmail");
  const host = el("input", { name: "host", required: true, placeholder: "imap.example.com" });
  const port = el("input", { name: "port", type: "number", min: "1", max: "65535", required: true });
  const hint = el("p", { class: "muted small" });
  const fill = () => {
    const p = MAILBOX_PRESETS[preset.value];
    [host.value, port.value] = p.imap;
    hint.textContent = p.hint;
  };
  preset.addEventListener("change", fill);
  fill();
  const test = el("button", { type: "button", class: "btn" }, "Test sign-in");
  const connect = el("button", { type: "submit", class: "btn primary" }, "Connect");
  const form = el("form", { class: "add-user integration", novalidate: true },
    el("h3", { text: "Connect a mailbox" }),
    el("div", { class: "grid" },
      field("Provider", preset),
      field("Name in MailFlow", el("input", { name: "label", required: true, placeholder: "support@", maxlength: "32" }),
        "Lowercase, shown on every email from it"),
      field("Email address (sign-in)", el("input", { name: "user", type: "email", required: true, autocomplete: "off" })),
      field("Password", el("input", { name: "password", type: "password", required: true, autocomplete: "new-password" })),
      field("IMAP server", host),
      field("Port", port),
      field("Collect", select("since_days", SINCE, "0"), "Older emails stay out of the list")),
    hint,
    errorLine(),
    el("div", { class: "row-buttons" }, connect, test));
  const login = () => ({ host: form.host.value, port: Number(form.port.value), user: form.user.value, password: form.password.value });
  test.addEventListener("click", () => attempt(form, test, "Testing…",
    () => api("/api/integrations/imap/check", { method: "POST", body: login() }),
    (_, box) => said(box, "Signed in: MailFlow can read this mailbox.")));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    attempt(form, connect, "Connecting…",
      () => api("/api/integrations/mailboxes", {
        method: "POST", body: { ...login(), label: form.label.value, since_days: Number(form.since_days.value) },
      }),
      async (box) => {
        smtpPrefill = { label: box.label, preset: preset.value, user: form.user.value };
        smtpFor = box.label;
        await loadIntegrations();
        toast(`${box.label} is connected. New emails appear within a few minutes.`);
      });
  });
  return form;
}

let smtpPrefill = null; // right after connecting a mailbox: its provider and address for the reply settings

function smtpForm(box) {
  if (!box) return null;
  const saved = box.smtp;
  const fresh = smtpPrefill && smtpPrefill.label === box.label ? smtpPrefill : null;
  const preset = MAILBOX_PRESETS[fresh ? fresh.preset : "other"];
  const value = (key, fallback) => (saved ? String(saved[key] ?? "") : fallback);
  const save = el("button", { type: "submit", class: "btn primary" }, "Test and save");
  const form = el("form", { class: "add-user integration", novalidate: true },
    el("h3", { text: `Replies from ${box.label}` }),
    integrations.secret_key ? null : el("p", { class: "note warn" }, icon("warning"), el("span", {
      text: "The server has no MAILFLOW_SECRET_KEY, so it cannot keep an SMTP password. The next deploy makes one.",
    })),
    el("p", { class: "muted small", text: box.replies === "gmail" && !saved
      ? "This mailbox replies through n8n's Gmail workflow. Set up SMTP to send from the app instead."
      : "Replies leave in the same conversation, from the address below." }),
    el("div", { class: "grid" },
      field("SMTP server", el("input", { name: "host", required: true, value: value("host", preset.smtp[0]), placeholder: "smtp.example.com" })),
      field("Port", el("input", { name: "port", type: "number", min: "1", max: "65535", value: value("port", String(preset.smtp[1])) })),
      field("Security", select("security", [["ssl", "SSL/TLS (usually 465)"], ["starttls", "STARTTLS (usually 587)"]], value("security", preset.smtp[2]))),
      field("Sign-in", el("input", { name: "user", required: true, autocomplete: "off", value: value("user", fresh ? fresh.user : "") })),
      field("Password", el("input", {
        name: "password", type: "password", autocomplete: "new-password",
        placeholder: saved ? "Unchanged" : "", required: !saved,
      }), fresh ? "Often the same as for IMAP" : null),
      field("From address", el("input", { name: "from_address", type: "email", required: true, value: value("from_address", fresh ? fresh.user : "") })),
      field("From name", el("input", { name: "from_name", maxlength: "100", value: value("from_name", ""), placeholder: "Support team" }))),
    errorLine(),
    el("div", { class: "row-buttons" }, save,
      saved ? el("button", {
        type: "button", class: "btn danger",
        onclick: () => mailboxAction(`/api/integrations/mailboxes/${encodeURIComponent(box.label)}/smtp`, "DELETE", `SMTP replies from ${box.label} are off.`),
      }, "Turn off SMTP replies") : null,
      el("button", { type: "button", class: "btn", onclick: () => { smtpFor = null; smtpPrefill = null; renderIntegrations(); } }, "Back")));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    attempt(form, save, "Testing…",
      () => api(`/api/integrations/mailboxes/${encodeURIComponent(box.label)}/smtp`, {
        method: "PUT",
        body: {
          host: form.host.value, port: Number(form.port.value), security: form.security.value, user: form.user.value,
          password: form.password.value, from_address: form.from_address.value, from_name: form.from_name.value,
        },
      }),
      async () => {
        smtpFor = null;
        smtpPrefill = null;
        await loadIntegrations();
        toast(`Replies from ${box.label} now go out over SMTP.`);
      });
  });
  return form;
}

// --- the AI model ---------------------------------------------------------------

function keyChoice(kind, name, newText) {
  const saved = (integrations.credentials[kind] || []).map((c) => [c.id, c.name]);
  return select(name, [...saved, ...(newText ? [[NEW_KEY, newText]] : [])], saved.length ? saved[0][0] : NEW_KEY);
}

function aiPanel() {
  const now = integrations.ai;
  const providers = integrations.providers;
  const current = now && now.provider
    ? `${providers[now.provider]?.label || "Another model"} · ${now.model}${now.credential ? ` · key “${now.credential}”` : ""}`
    : "No AI model is attached to Sort with AI.";
  const provider = select("provider", Object.entries(providers).map(([key, p]) => [key, p.label]), now?.provider in providers ? now.provider : "ollama");
  const model = el("input", { name: "model", required: true, list: "ai-models", autocomplete: "off" });
  const models = el("datalist", { id: "ai-models" });
  const keyHolder = el("div");
  const privacy = el("p", { class: "note" }, icon("info"), el("span"));
  const check = el("button", { type: "button", class: "btn" }, "Check key");
  const save = el("button", { type: "submit", class: "btn primary" }, "Use this model");
  const form = el("form", { class: "add-user integration", novalidate: true });
  const showProvider = () => {
    const p = providers[provider.value];
    model.value = provider.value === now?.provider ? now.model : p.model;
    models.replaceChildren();
    const saved = integrations.credentials[p.credential_type] || [];
    if (!p.needs_key && !saved.length) {
      // Nothing to choose and nothing to enter: the connection to the server is made in n8n.
      keyHolder.replaceChildren(el("p", { class: "note warn" }, icon("warning"),
        el("span", { text: "n8n has no connection to Ollama yet: add an Ollama credential in n8n, then come back here." })));
      save.disabled = true;
      check.hidden = true;
    } else {
      const choice = keyChoice(p.credential_type, "credential", p.needs_key ? "Enter a new key…" : null);
      const key = el("input", { name: "api_key", type: "password", autocomplete: "off", placeholder: "Paste the API key" });
      const keyField = field("New key", key);
      const toggle = () => { keyField.hidden = choice.value !== NEW_KEY; check.hidden = choice.value !== NEW_KEY; };
      choice.addEventListener("change", toggle);
      keyHolder.replaceChildren(el("div", { class: "grid" }, field(p.needs_key ? "Key" : "Server", choice), keyField));
      toggle();
      save.disabled = false;
    }
    privacy.lastChild.textContent = p.needs_key
      ? `Each email's sender, subject and first 4,000 characters go to ${p.label} to be sorted. Check that the team agrees.`
      : "Emails are sorted on your own server; nothing leaves it.";
  };
  provider.addEventListener("change", showProvider);
  form.append(
    el("h3", { text: "Choose the AI" }),
    el("div", { class: "grid" }, field("Provider", provider), field("Model", model)),
    models, keyHolder, privacy, errorLine(),
    el("div", { class: "row-buttons" }, save, check));
  showProvider();
  check.addEventListener("click", () => attempt(form, check, "Checking…",
    () => api("/api/integrations/ai/check", { method: "POST", body: { provider: provider.value, api_key: form.api_key.value } }),
    (result, box) => {
      models.replaceChildren(...result.models.map((id) => el("option", { value: id })));
      said(box, `The key works${result.models.length ? `: ${result.models.length} models to choose from` : ""}.`);
    }));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const fresh = form.credential.value === NEW_KEY;
    attempt(form, save, "Switching…",
      () => api("/api/integrations/ai", {
        method: "POST",
        body: { provider: provider.value, model: form.model.value, credential_id: fresh ? "" : form.credential.value, api_key: fresh ? form.api_key.value : "" },
      }),
      async () => {
        await loadIntegrations();
        toast("The next emails are sorted with the new model. Check the first few, and switch back here if needed.");
      });
  });
  return [
    el("p", {}, el("span", { class: "muted", text: "Sorting with: " }), el("b", { text: current })),
    el("p", { class: "muted small", text: "Process email is saved before every change, and you can switch back here at any time." }),
    form,
  ];
}

// --- Telegram alerts ------------------------------------------------------------

function alertsPanel() {
  const now = integrations.alerts;
  const bot = keyChoice("telegramApi", "credential", "Enter a new bot token…");
  const token = el("input", { name: "token", type: "password", autocomplete: "off", placeholder: "123456:ABC… from @BotFather" });
  const tokenField = field("Bot token", token);
  const test = el("button", { type: "button", class: "btn" }, "Send a test");
  const save = el("button", { type: "submit", class: "btn primary" }, "Save");
  const toggle = () => { tokenField.hidden = bot.value !== NEW_KEY; test.hidden = bot.value !== NEW_KEY; };
  bot.addEventListener("change", toggle);
  const form = el("form", { class: "add-user integration", novalidate: true },
    el("h3", { text: "Where alerts go" }),
    el("div", { class: "grid" },
      field("Chat id", el("input", { name: "chat_id", required: true, value: now?.chat_id || "", placeholder: "7769198902" }),
        "A person's or group's id (groups start with -100), or @channel"),
      field("Bot", bot), tokenField),
    errorLine(),
    el("div", { class: "row-buttons" }, save, test));
  toggle();
  test.addEventListener("click", () => attempt(form, test, "Sending…",
    () => api("/api/integrations/alerts/check", { method: "POST", body: { token: form.token.value, chat_id: form.chat_id.value } }),
    (result, box) => said(box, `${result.bot} sent a test message. Check the chat.`)));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const fresh = bot.value === NEW_KEY;
    attempt(form, save, "Saving…",
      () => api("/api/integrations/alerts", {
        method: "POST",
        body: { chat_id: form.chat_id.value, credential_id: fresh ? "" : bot.value, token: fresh ? form.token.value : "" },
      }),
      async () => {
        await loadIntegrations();
        toast("Alerts go to the new chat from now on.");
      });
  });
  return [
    el("p", {}, el("span", { class: "muted", text: "Now: " }),
      el("b", { text: now?.chat_id ? `chat ${now.chat_id}${now.credential ? ` with the bot “${now.credential}”` : ""}` : "no Telegram alerts set up" })),
    el("p", { class: "muted small", text: "A P1 email and any MailFlow error send a Telegram message." }),
    form,
  ];
}

$("open-integrations").addEventListener("click", async () => {
  try {
    integrationsTab = "mailboxes";
    smtpFor = null;
    await loadIntegrations();
    openDialog($("integrations-dialog"));
  } catch (error) {
    toast(error.message, true);
  }
});
