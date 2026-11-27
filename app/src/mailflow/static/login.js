"use strict";

const form = document.getElementById("login-form");
const notice = document.getElementById("login-error");
const toggle = form.querySelector(".pw-toggle");

// Codes the server puts on /login after a Google sign-in that did not work out.
const GOOGLE_ERRORS = {
  google_denied: "Google sign-in was cancelled.",
  google_state: "That Google sign-in expired or was started in another tab. Try again.",
  google_failed: "Google sign-in did not work. Try again, or use your password.",
  google_no_account: "That Google account cannot open MailFlow. Ask an admin to add your email address, or sign in with your password (Google links itself only for Gmail and Google Workspace addresses).",
  google_busy: "Too many sign-ins at once. Try again in a moment.",
};

function show(message, ok = false) {
  notice.textContent = message;
  notice.classList.toggle("ok", ok);
  notice.hidden = false;
}

const query = new URLSearchParams(location.search);
if (query.get("changed") === "1") show("Password changed. Sign in with the new one.", true);
const googleError = query.get("error");
if (Object.hasOwn(GOOGLE_ERRORS, googleError ?? "")) show(GOOGLE_ERRORS[googleError]);
if (query.has("changed") || query.has("error")) history.replaceState(null, "", "/login");

toggle.addEventListener("click", () => {
  const showing = form.password.type === "text";
  form.password.type = showing ? "password" : "text";
  toggle.textContent = showing ? "Show" : "Hide";
  toggle.setAttribute("aria-pressed", String(!showing));
  toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  form.password.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Signing in…";
  notice.hidden = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MailFlow": "1" },
      body: JSON.stringify({ email: form.email.value, password: form.password.value }),
    });
    if (response.ok) {
      location.href = "/";
      return;
    }
    const body = await response.json().catch(() => ({}));
    show(body.error || "Sign-in failed.");
  } catch {
    show("MailFlow could not be reached. Check your connection.");
  }
  form.password.value = "";
  form.password.focus();
  button.disabled = false;
  button.textContent = "Sign in";
});
