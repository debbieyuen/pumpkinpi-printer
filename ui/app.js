// PumpkinPi touchscreen UI.
// Live mode: served by pumpkinpi/server.py on the Pi (Agent API, Search API, Decider, printer).
// Demo mode: used automatically when /api/status is unreachable. No real search, no printer.

const $ = (id) => document.getElementById(id);
const READY_AT = 0.9;

const DEMO_GUESTS = [
  { name: "Michael", avoid: ["tree nuts"] },
  { name: "Debbie", avoid: ["tree nuts", "peanuts", "fish"] },
  { name: "Dad", avoid: [] }, { name: "Mom", avoid: [] }, { name: "Kathy", avoid: [] },
];
const DEMO_PROBS = {
  "semi-sweet chocolate chips": { "tree nuts": 0.35, peanuts: 0.12, fish: 0.01 },  // many chips carry may-contain warnings
  "heavy cream": { "tree nuts": 0.01, peanuts: 0.01, fish: 0.01 },
};

const state = { live: false, guests: DEMO_GUESTS, plan: null, strokes: [], checks: {}, ready: 0, busy: false, open: null };

function log(msg) {
  const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("log").textContent = `${t}  ${msg}`;
}
const verdict = (p) => (p >= 0.7 ? "red" : p <= 0.1 ? "green" : "yellow");
const toColor = { found: "red", unsure: "yellow", safe: "green" };
const label = { red: "Allergen", yellow: "Check label", green: "Safe", wait: "Checking" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.json();
}

async function init() {
  try {
    const s = await api("/api/status");
    state.live = true;
    state.guests = s.guests;
    $("modeBadge").textContent = s.printer ? "Printer connected" : "Printer offline";
    $("modeBadge").classList.add("live");
    log("Connected to PumpkinPi.");
  } catch {
    log("Demo mode: sample results only. No real search and no printer.");
  }
  updateGate();
}

// ---------- 1. Agent API: prompt -> plan ----------
async function ask() {
  const prompt = $("prompt").value.trim();
  if (!prompt || state.busy) return;
  state.busy = true; state.checks = {}; state.ready = 0; state.open = null;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Planning"></span>';
  $("result").hidden = false; $("idle").hidden = true; state.strokes = []; drawPreview();
  $("plan").innerHTML = `<p class="msg"><img class="think" src="brand/perplexity-symbol-offwhite.svg" alt=""> Perplexity is planning…</p>`;
  updateGate();
  try {
    let res;
    if (state.live) res = await api("/api/design", { prompt });
    else { await sleep(1200); res = await (await fetch("demo.json")).json(); }
    state.plan = res.plan; state.strokes = res.strokes;
    drawPreview();
    renderPlan();
    log(`Checking ${res.plan.ingredients.length} ingredients…`);
    for (const ing of res.plan.ingredients) await check(ing);
    log(allSafe() ? "All ingredients safe. Tap Camera next." : "Start is locked. Tap an ingredient to see why.");
  } catch (e) {
    $("plan").innerHTML = `<p class="msg">Couldn't plan that: ${esc(e.message)}</p>`;
    state.plan = null; state.strokes = []; drawPreview();
  } finally {
    state.busy = false; $("askBtn").textContent = "Ask"; updateGate();
  }
}

// ---------- 2. Search API + Decider per ingredient ----------
async function check(product) {
  state.checks[product] = { status: "wait" }; renderPlan();
  try {
    let res;
    if (state.live) res = await api("/api/check", { product });
    else {
      await sleep(900);
      const p = DEMO_PROBS[product] || {};
      res = { sources: [{ title: "Demo: product label page", url: "https://example.com/label" }], relevance: 0.9,
        results: state.guests.flatMap((g) => g.avoid.map((a) => ({ name: g.name, allergen: a, probability: p[a] ?? 0.3 }))) };
    }
    res.results.forEach((r) => (r.color = r.verdict ? toColor[r.verdict] : verdict(r.probability)));
    const worst = res.results.some((r) => r.color === "red") ? "red" : res.results.some((r) => r.color === "yellow") ? "yellow" : "green";
    state.checks[product] = { status: worst, ...res };
  } catch (e) {
    state.checks[product] = { status: "yellow", error: e.message, results: [], sources: [] };
  }
  renderPlan(); updateGate();
}

function renderPlan() {
  const p = state.plan; if (!p) return;
  const rows = p.ingredients.map((ing) => {
    const c = state.checks[ing] || { status: "wait" };
    const open = state.open === ing;
    let detail = "";
    if (open && c.results) {
      detail = `<div class="detail">${c.results.map((r) => `<div class="drow"><span class="pill sm ${r.color}">${label[r.color]}</span>${esc(r.name)} · ${esc(r.allergen)}<span class="prob">${Math.round(r.probability * 100)}%</span></div>`).join("") || `<div>No guest avoids an allergen for this.</div>`}
        ${c.error ? `<div>Check failed: ${esc(c.error)}</div>` : ""}${(c.sources || []).slice(0, 4).map((s, i) => `<div class="src"><span class="num">${i + 1}</span>${esc(host(s.url))}</div>`).join("")}</div>`;
    }
    return `<button type="button" class="ing ${open ? "open" : ""}" data-ing="${esc(ing)}">
      <span class="pill ${c.status}">${c.status === "wait" ? '<span class="spin sm"></span>' : label[c.status]}</span>
      <span class="who">${esc(ing)}</span></button>${detail}`;
  }).join("");
  $("plan").innerHTML = `<div class="cap">${esc(p.caption)}</div>${rows}`;
}

$("plan").onclick = (e) => {
  const b = e.target.closest(".ing"); if (!b) return;
  state.open = state.open === b.dataset.ing ? null : b.dataset.ing; renderPlan();
};

// ---------- preview ----------
function drawPreview() {
  // SVG y is down; strokes use +Y away from you, so flip.
  $("strokes").innerHTML = (state.strokes || []).map((s) =>
    `<polyline points="${s.map(([x, y]) => `${x.toFixed(1)},${(-y).toFixed(1)}`).join(" ")}"/>`).join("");
}

// ---------- gate ----------
function allSafe() {
  if (!state.plan) return false;
  return state.plan.ingredients.every((i) => state.checks[i] && state.checks[i].status === "green");
}

function updateGate() {
  const p = !!state.plan, safe = allSafe();
  const statuses = p ? state.plan.ingredients.map((i) => (state.checks[i] || {}).status) : [];
  const bad = statuses.includes("red") || statuses.includes("yellow");
  $("gDesign").className = "dot " + (p ? "ok" : "");
  $("gSafe").className = "dot " + (safe ? "ok" : bad ? "bad" : statuses.includes("wait") ? "wait" : "");
  $("safeText").textContent = bad ? "Check ingredients" : "Ingredients";
  $("gReady").className = "dot " + (state.ready >= READY_AT ? "ok" : state.ready > 0 ? "wait" : "");
  $("dryBtn").disabled = !p;
  $("startBtn").disabled = !(p && safe && state.ready >= READY_AT);
}

$("readyBtn").onclick = async () => {
  $("readyText").textContent = "Looking…";
  try {
    state.ready = state.live ? (await api("/api/ready", {})).probability : (await sleep(800), 0.97);
    $("readyText").textContent = state.ready >= READY_AT ? "Pie ready" : "Pie not ready";
  } catch (e) { state.ready = 0; $("readyText").textContent = "Camera error"; log(e.message); }
  updateGate();
};

async function start(dry_run) {
  if (!state.live) { log(dry_run ? "Demo: dry run would trace the path 15 mm above the pie." : "Demo: would pipe now."); return; }
  try {
    const r = await api("/api/start", { dry_run });
    log(`${dry_run ? "Dry run" : "Piping"} started (${r.lines} moves). Stay next to the printer.`);
    for (let i = 0; i < 3600; i++) {
      await sleep(500);
      const j = await api("/api/job");
      $("jobFill").style.width = `${Math.round((100 * j.done) / Math.max(1, j.total))}%`;
      if (!j.running) { log(j.error ? `Stopped: ${j.error}` : `${dry_run ? "Dry run" : "Piping"} done.`); break; }
    }
  } catch (e) { log(`Start refused: ${e.message}`); }
}
$("dryBtn").onclick = () => start(true);
$("startBtn").onclick = () => start(false);

$("stopBtn").onclick = async () => {
  state.ready = 0; updateGate();
  if (!state.live) { log("Demo: STOP pressed (M112 would be sent)."); return; }
  try { await api("/api/stop", {}); log("STOP sent (M112). Power-cycle the printer before continuing."); }
  catch (e) { log(`STOP failed: ${e.message}. Switch the printer off now.`); }
};

// ---------- on-screen keyboard (kiosk Chromium has no OS keyboard) ----------
const KEYS = ["qwertyuiop", "asdfghjkl'", "zxcvbnm,.", ["⇧", "space", "⌫", "Done"]];
let shift = false;
function drawKbd() {
  $("kbd").innerHTML = KEYS.map((row) => `<div class="krow">${(typeof row === "string" ? [...row] : row).map((k) =>
    `<button type="button" class="key ${k.length > 1 ? "wide " + (k === "space" ? "space" : "") : ""}" data-k="${esc(k)}">${esc(k === "space" ? "space" : shift && k.length === 1 ? k.toUpperCase() : k)}</button>`).join("")}</div>`).join("");
}
function showKbd() { drawKbd(); $("kbd").hidden = false; document.body.classList.add("typing"); }
$("prompt").addEventListener("pointerdown", () => { if ($("kbd").hidden) showKbd(); });
function hideKbd() { $("kbd").hidden = true; document.body.classList.remove("typing"); }
$("prompt").addEventListener("focus", showKbd);
$("kbd").addEventListener("pointerdown", (e) => e.preventDefault()); // keep focus in the input
$("kbd").onclick = (e) => {
  const k = e.target.closest(".key")?.dataset.k; if (!k) return;
  const el = $("prompt");
  if (k === "⌫") el.value = el.value.slice(0, -1);
  else if (k === "space") el.value += " ";
  else if (k === "⇧") { shift = !shift; drawKbd(); return; }
  else if (k === "Done") { hideKbd(); el.blur(); ask(); return; }
  else { el.value += shift ? k.toUpperCase() : k; if (shift) { shift = false; drawKbd(); } }
};

$("askForm").onsubmit = (e) => { e.preventDefault(); hideKbd(); ask(); };
init();
