/* KIT Services — Virtual Platform terminal */
"use strict";

const $ = (s) => document.querySelector(s);

const BOOT_LINES = [
  ["> KIT GRID TERMINAL v3.1.4", "t-blue"],
  ["> handshake ............ OK", "t-ok"],
  ["> tunnel ......... AES-256", "t-ok"],
  ["> register ....... SYNCHRONIZED", "t-sys"],
  ["> module scan ... 6/6 NODES RESPONDING", "t-sys"],
  ["> uptime ......... STABLE", "t-ok"],
];

const HEARTBEAT_LINES = [
  ["heartbeat ack received ............... 12ms", "t-ok"],
  ["anomaly scan: 0 threats ............. CLEAR", "t-ok"],
  ["cloud egress ........................ balanced", "t-sys"],
  ["vault replication lag ............... 0.00s", "t-ok"],
  ["firewall rule sync .................. converged", "t-sys"],
  ["grid gossip ......................... quorum stable", "t-ok"],
  ["monitor probe ....................... 198/198 up", "t-sys"],
  ["threat intel feed updated ........... STANDBY", "t-dim"],
];

function fmtTime() {
  const d = new Date();
  return d.toISOString().substring(11, 19) + " UTC";
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
  return { ok: res.ok, data };
}

function outEl(...spans) {
  const out = $("#consoleOut");
  spans.forEach((s) => out.appendChild(s));
  out.scrollTop = out.scrollHeight;
}

function log(line, cls) {
  const row = document.createElement("span");
  row.className = cls || "";
  row.textContent = line + "\n";
  outEl(row);
}

function sys(line) {
  const t = document.createElement("span");
  t.className = "t-dim";
  t.textContent = "[" + fmtTime() + "] ";
  const m = document.createElement("span");
  m.textContent = line + "\n";
  outEl(t, m);
}

async function main() {
  const res = await api("/api/me");
  if (!res.ok || !res.data.user) {
    window.location.replace("/"); // not authenticated -> landing page
    return;
  }
  const user = res.data.user;
  $("#identityName").textContent = user.name;
  $("#identityEmail").textContent = user.email;
  $("#identityHandle").textContent = user.email;
  $("#year").textContent = new Date().getFullYear();

  try {
    const st = await api("/api/stats");
    if (st.ok) $("#memberCount").textContent = st.data.members.toLocaleString();
  } catch (_) {}

  setTimeout(() => {
    BOOT_LINES.forEach(([line, cls]) => log(line, cls));
    sys("KIT GRID TERMINAL READY — all systems nominal.");
  }, 350);

  const feed = $("#feed");
  const feedSeed = [
    "Perimeter scan completed across 1,247 endpoints.",
    "Cloud Routing rebalanced node <span class='accent-blue'>EU-WEST-03</span>.",
    "Defense grid blocked <span class='accent-blue'>3</span> intrusion probes (moderate).",
    "Data Vault completed snapshot <span class='accent-blue'>#8841</span>.",
    "Maintenance window queued for <span class='accent-blue'>Grid Networking</span>.",
    "Support queue normalized — 0 escalated tickets.",
    "Certificate rotation finished on <span class='accent-blue'>api.kit.grid</span>.",
    "Thermal profile nominal across all managed nodes.",
  ];
  let fi = 0;

  const pushFeed = () => {
    const li = document.createElement("li");
    const dot = document.createElement("i");
    dot.className = "f-dot" + (Math.random() > 0.75 ? " red" : "");
    li.appendChild(dot);
    const text = document.createElement("span");
    text.className = "f-text";
    text.innerHTML = feedSeed[fi % feedSeed.length];
    li.appendChild(text);
    const time = document.createElement("span");
    time.className = "f-time";
    time.textContent = fmtTime().slice(0, 5);
    li.appendChild(time);
    feed.prepend(li);
    while (feed.children.length > 6) feed.lastElementChild.remove();
    fi += 1 + Math.floor(Math.random() * 3);
  };

  feedSeed.slice(0, 4).forEach(pushFeed);
  setInterval(pushFeed, 6000);

  let tick = 0;
  setInterval(() => {
    const [line, cls] = HEARTBEAT_LINES[tick % HEARTBEAT_LINES.length];
    sys("[t++] " + line);
    tick += 1;
  }, 4500);

  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", "POST");
    window.location.assign("/");
  });
}

main();