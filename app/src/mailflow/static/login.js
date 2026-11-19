"use strict";

const form = document.getElementById("login-form");
const error = document.getElementById("login-error");

if (new URLSearchParams(location.search).get("changed") === "1") {
  error.textContent = "Password changed. Log in with the new one.";
  error.classList.add("ok");
  error.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  error.hidden = true;
  error.classList.remove("ok");
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
    error.textContent = body.error || "Login failed.";
  } catch {
    error.textContent = "MailFlow could not be reached. Check your connection.";
  }
  error.hidden = false;
  form.password.value = "";
  form.password.focus();
  button.disabled = false;
});
