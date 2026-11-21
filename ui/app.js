// PumpkinPi touchscreen UI.
// Live mode: served by pumpkinpi/server.py on the Pi (talks to the Decisions API and the printer).
// Demo mode: used automatically when /api/status is unreachable (e.g. the hosted preview). No real search, no printer.

const $ = (id) => document.getElementById(id);
const READY_AT = 0.9;

const DEMO_GUESTS = [
  { name: "Michael", avoid: ["tree nuts"] },
  { name: "Debbie", avoid: ["tree nuts", "peanuts", "fish"] },
  { name: "Dad", avoid: [], limit: ["sugar"] },
  { name: "Mom", avoid: [], limit: ["sugar"] },
  { name: "Kathy", avoid: [] },
];
const DEMO_PRODUCTS = {
  "Almond sparkling wine": { "tree nuts": 0.96, peanuts: 0.04, fish: 0.01 },
  "Canned pumpkin puree": { "tree nuts": 0.02, peanuts: 0.01, fish: 0.01 },
  "Hot pot soup base": { "tree nuts": 0.05, peanuts: 0.08, fish: 0.42 },
};

const state = { live: false, guests: DEMO_GUESTS, checked: {}, ready: 0, busy: false };

function log(msg) {
  const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("log").textContent = `${t}  ${msg}`;
}
const verdict = (p) => (p >= 0.7 ? "red" : p <= 0.1 ? "green" : "yellow");
const label = { red: "Found", yellow: "Check label", green: "Safe" };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

async function init() {
  try {
    const s = await api("/api/status");
    state.live = true;
    state.guests = s.guests;
    $("eventName").textContent = s.event || "PumpkinPi";
    $("modeBadge").textContent = s.printer ? "Live · printer connected" : "Live · printer offline";
    $("modeBadge").classList.add("live");
    log("Connected to PumpkinPi on the Pi.");
  } catch {
    $("modeBadge").textContent = "Demo mode";
    log("Demo mode: sample results only. No real search and no printer.");
  }
  $("guest").innerHTML = state.guests.map((g) => `<option>${esc(g.name)}</option>`).join("");
  $("chips").innerHTML = Object.keys(DEMO_PRODUCTS).map((p) => `<button type="button" class="chip">${esc(p)}</button>`).join("");
  $("chips").onclick = (e) => { if (e.target.classList.contains("chip")) { $("product").value = e.target.textContent; check(); } };
  updateGate();
}

async function check() {
  const product = $("product").value.trim();
  if (!product || state.busy) return;
  state.busy = true;
  $("checkBtn").innerHTML = '<span class="spin" aria-label="Checking"></span>';
  $("results").innerHTML = `<div class="empty"><p>Checking ${esc(product)}…</p><p class="muted">Searching labels and recalls for each guest.</p></div>`;
  try {
    let rows;
    if (state.live) {
      rows = (await api("/api/check", { product })).results;
    } else {
      await new Promise((r) => setTimeout(r, 900));
      const probs = DEMO_PRODUCTS[product] || { "tree nuts": 0.3, peanuts: 0.2, fish: 0.15 };
      rows = state.guests.flatMap((g) => g.avoid.map((a) => ({ name: g.name, allergen: a, probability: probs[a] ?? 0.2, sources: [] })));
    }
    rows.forEach((r) => (r.verdict = r.verdict ? { found: "red", unsure: "yellow", safe: "green" }[r.verdict] || r.verdict : verdict(r.probability)));
    state.checked[product] = rows;
    render(product, rows);
    const worst = rows.some((r) => r.verdict === "red") ? "red" : rows.some((r) => r.verdict === "yellow") ? "yellow" : "green";
    log(`${product}: ${worst === "green" ? "safe for everyone" : worst === "red" ? "allergen found, printer blocked" : "needs a label check"}`);
  } catch (e) {
    $("results").innerHTML = `<div class="empty"><p>Check failed</p><p class="muted">${esc(e.message)}. The printer stays locked.</p></div>`;
    state.checked[product] = [{ verdict: "yellow" }];
    log("Check failed; printer locked.");
  } finally {
    state.busy = false;
    $("checkBtn").textContent = "Check";
    updateGate();
  }
}

function render(product, rows) {
  const reds = rows.filter((r) => r.verdict === "red");
  const yel = rows.filter((r) => r.verdict === "yellow");
  let head;
  if (reds.length) head = `<div class="summary red">${esc(product)}: ${[...new Set(reds.map((r) => r.allergen))].join(", ")} found. ${[...new Set(reds.map((r) => r.name))].join(" and ")} ${reds.length > 1 && new Set(reds.map((r) => r.name)).size > 1 ? "are" : "is"} allergic.</div>`;
  else if (yel.length) head = `<div class="summary yellow">${esc(product)}: unsure. Check the label before serving.</div>`;
  else head = `<div class="summary green">${esc(product)}: safe for everyone checked.</div>`;
  const body = rows.map((r) => {
    const srcs = (r.sources || []).slice(0, 2).map((u) => `<a class="src" href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\//, ""))}</a>`).join("");
    return `<div class="rowr"><span class="pill ${r.verdict}">${label[r.verdict]}</span>
      <div><div class="who">${esc(r.name)} · ${esc(r.allergen)}</div>${srcs || `<div class="why">${state.live ? "No sources returned. Read the label." : "Demo result, no real search"}</div>`}</div>
      <span class="prob">${Math.round(r.probability * 100)}%</span></div>`;
  }).join("");
  $("results").innerHTML = head + (body || `<div class="why">No guest avoids an allergen for this product.</div>`);
}

function allSafe() {
  const lists = Object.values(state.checked);
  return lists.length > 0 && lists.every((rows) => rows.every((r) => r.verdict === "green"));
}

function updateGate() {
  const safe = allSafe();
  const any = Object.keys(state.checked).length > 0;
  $("gSafe").className = "dot " + (safe ? "ok" : any ? "bad" : "");
  $("gReady").className = "dot " + (state.ready >= READY_AT ? "ok" : state.ready > 0 ? "wait" : "");
  $("readyFill").style.width = `${Math.round(state.ready * 100)}%`;
  $("startBtn").disabled = !(safe && state.ready >= READY_AT);
}

$("readyBtn").onclick = async () => {
  $("readyText").textContent = "Checking pie…";
  try {
    state.ready = state.live ? (await api("/api/ready", {})).probability : (await new Promise((r) => setTimeout(r, 800)), 0.97);
    $("readyText").textContent = `Decider: ${state.ready >= READY_AT ? "ready" : "not ready"} ${Math.round(state.ready * 100)}%`;
  } catch (e) {
    state.ready = 0;
    $("readyText").textContent = "Camera check unavailable";
    log(e.message);
  }
  updateGate();
};

$("startBtn").onclick = async () => {
  const name = $("guest").value;
  if (!state.live) { log(`Demo: would pipe "${name}" now.`); return; }
  try { await api("/api/start", { name }); log(`Piping "${name}". Stay next to the printer.`); }
  catch (e) { log(`Start refused: ${e.message}`); }
};

$("stopBtn").onclick = async () => {
  state.ready = 0; updateGate();
  if (!state.live) { log("Demo: STOP pressed (M112 would be sent)."); return; }
  try { await api("/api/stop", {}); log("STOP sent (M112). Power-cycle the printer before continuing."); }
  catch (e) { log(`STOP failed: ${e.message}. Switch the printer off now.`); }
};

$("checkForm").onsubmit = (e) => { e.preventDefault(); check(); };
init();
