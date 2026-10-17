/* KIT Services — client-side auth logic */
"use strict";

const $ = (sel) => document.querySelector(sel);

const UI = {
  memberCount: $("#memberCount"),
  linkStatus: $("#linkStatus"),
  signupForm: $("#signupForm"),
  loginForm: $("#loginForm"),
  welcomePanel: $("#welcomePanel"),
  loginPanel: $("#loginPanel"),
  welcomeName: $("#welcomeName"),
  welcomeEmail: $("#welcomeEmail"),
  logoutBtn: $("#logoutBtn"),
  year: $("#year"),
};

const msg = {
  signup: { ok: $("#suMsg"), err: $("#suErr") },
  login: { ok: $("#liMsg"), err: $("#liErr") },
};

function setMessage(channel, kind, text) {
  const other = kind === "ok" ? "err" : "ok";
  msg[channel][other].hidden = true;
  const el = msg[channel][kind];
  el.textContent = text;
  el.hidden = !text;
}

async function api(path, method = "GET", body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (_) {}
  return { ok: res.ok, status: res.status, data };
}

function setBusy(form, busy) {
  const btn = form === "signup" ? $("#suBtn") : $("#liBtn");
  btn.disabled = busy;
  btn.textContent = busy ? "PROCESSING…" : form === "signup" ? "Initialize Account" : "Authenticate";
}

function showLoggedIn(user) {
  UI.loginPanel.hidden = true;
  UI.welcomePanel.hidden = false;
  UI.welcomeName.textContent = user.name;
  UI.welcomeEmail.textContent = user.email;
}

function showLoggedOut() {
  UI.welcomePanel.hidden = true;
  UI.loginPanel.hidden = false;
}

UI.signupForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  setMessage("signup", "ok", "");
  setMessage("signup", "err", "");

  const name = $("#su-name").value.trim();
  const email = $("#su-email").value.trim().toLowerCase();
  const password = $("#su-pass").value;

  if (name.length < 2) return setMessage("signup", "err", "Enter your designation (name).");
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
    return setMessage("signup", "err", "Enter a valid e-mail handle.");
  if (password.length < 8)
    return setMessage("signup", "err", "Access key must be at least 8 characters.");

  setBusy("signup", true);
  try {
    const res = await api("/api/signup", "POST", { name, email, password });
    if (res.ok) {
      setMessage("signup", "ok", "Identity registered. Opening the Virtual Platform…");
      window.location.assign("/virtual-platform.html");
      return;
    } else {
      setMessage("signup", "err", res.data.error || "Registration failed.");
    }
  } catch (_) {
    setMessage("signup", "err", "Channel unstable — check your connection and retry.");
  } finally {
    setBusy("signup", false);
  }
});

UI.loginForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  setMessage("login", "ok", "");
  setMessage("login", "err", "");

  const email = $("#li-email").value.trim().toLowerCase();
  const password = $("#li-pass").value;

  if (!email || !password)
    return setMessage("login", "err", "Provide both your e-mail handle and access key.");

  setBusy("login", true);
  try {
    const res = await api("/api/login", "POST", { email, password });
    if (res.ok) {
      setMessage("login", "ok", "Authentication successful. Opening the Virtual Platform…");
      window.location.assign("/virtual-platform.html");
      return;
    } else {
      setMessage("login", "err", res.data.error || "Authentication failed.");
    }
  } catch (_) {
    setMessage("login", "err", "Channel unstable — check your connection and retry.");
  } finally {
    setBusy("login", false);
  }
});

UI.logoutBtn.addEventListener("click", async () => {
  await api("/api/logout", "POST");
  showLoggedOut();
});

async function refreshCount() {
  try {
    const res = await api("/api/stats");
    if (res.ok) UI.memberCount.textContent = res.data.members.toLocaleString();
  } catch (_) {}
}

async function restoreSession() {
  try {
    const res = await api("/api/me");
    if (res.ok && res.data.user) {
      showLoggedIn(res.data.user);
    }
  } catch (_) {}
}

UI.year.textContent = new Date().getFullYear();
refreshCount();
restoreSession();
setTimeout(() => { UI.linkStatus.textContent = "SECURE"; }, 800);