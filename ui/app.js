// PumpkinPi touchscreen UI.
// Online: served by pumpkinpi/server.py on the Pi (Agent API, Search API, Decider, printer).
// Offline: used when /api/status is unreachable. Sample results only, no printer.

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

const state = { live: false, everLive: false, guests: DEMO_GUESTS, plan: null, strokes: [], checks: {},
  ready: 0, busy: false, open: null, job: false, photo: null };

const verdict = (p) => (p >= 0.7 ? "red" : p <= 0.1 ? "green" : "yellow");
const toColor = { found: "red", unsure: "yellow", safe: "green" };
const label = { red: "Allergen", yellow: "Check label", green: "Safe", wait: "Checking" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let note = "";  // last event message; shown in the bottom bar
function log(msg) { note = msg; $("why").textContent = msg; }

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r;
}
const apiJson = async (path, body) => (await api(path, body)).json();

// ---------- status pill: Online (Pi + printer) / No printer / Offline ----------
function setMode(cls, text) { $("modeBadge").className = "mode " + cls; $("modeText").textContent = text; }
async function refreshStatus() {
  try {
    const s = await apiJson("/api/status");
    state.live = state.everLive = true; state.guests = s.guests;
    s.printer ? setMode("on", "Online") : setMode("warn", "No printer");
  } catch {
    // Never fall back to sample "Safe" results once the real Pi server has been seen.
    if (!state.everLive) state.live = false;
    setMode("off", "Offline");
  }
}

// ---------- screens ----------
function show(view) {
  document.body.dataset.view = view;
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t.dataset.v === view);
  $("designView").hidden = view !== "design";
  $("recipeView").hidden = view !== "recipe";
  $("cameraView").hidden = view !== "camera";
  if (view === "design") window.Pie3D?.resize();
}
document.querySelector(".tabs").onclick = (e) => { const t = e.target.closest(".tab"); if (t) show(t.dataset.v); };

// ---------- 1. Agent API: prompt -> plan ----------
async function ask() {
  const prompt = $("prompt").value.trim();
  if (!prompt || state.busy) return;
  state.busy = true; state.checks = {}; state.ready = 0; state.open = null; state.plan = null;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Making"></span>';
  show("design"); state.strokes = []; drawPreview(); window.Pie3D?.thinking(true);
  $("summary").innerHTML = `<p class="msg"><img class="think" src="brand/perplexity-symbol-offwhite.svg" alt=""> Perplexity is designing…</p>`;
  renderRecipe(); updateGate();
  try {
    const res = state.live ? await apiJson("/api/design", { prompt })
      : (await sleep(1400), await (await fetch("demo.json")).json());
    state.plan = res.plan; state.strokes = res.strokes;
    window.Pie3D?.thinking(false); drawPreview();
    renderAll();
    log(`Checking ${res.plan.ingredients.length} ingredients…`);
    for (const ing of res.plan.ingredients) await check(ing);
    log(allSafe() ? "All ingredients safe. Check the pie on the Camera screen." : "An ingredient needs a check. See Recipe.");
  } catch (e) {
    window.Pie3D?.thinking(false);
    $("summary").innerHTML = `<p class="msg">Couldn't make that: ${esc(e.message)}</p>`;
    state.plan = null; state.strokes = []; drawPreview();
  } finally {
    state.busy = false; $("askBtn").textContent = "Make"; updateGate();
  }
}

// ---------- 2. Search API + Decider per ingredient ----------
async function check(product) {
  state.checks[product] = { status: "wait" }; renderAll();
  try {
    let res;
    if (state.live) res = await apiJson("/api/check", { product });
    else {
      await sleep(900);
      const p = DEMO_PROBS[product] || {};
      res = { sources: [{ title: "Sample: product label page", url: "https://example.com/label" }], relevance: 0.9,
        results: state.guests.flatMap((g) => g.avoid.map((a) => ({ name: g.name, allergen: a, probability: p[a] ?? 0.3 }))) };
    }
    res.results.forEach((r) => (r.color = r.verdict ? toColor[r.verdict] : verdict(r.probability)));
    const worst = res.results.some((r) => r.color === "red") ? "red" : res.results.some((r) => r.color === "yellow") ? "yellow" : "green";
    state.checks[product] = { status: worst, ...res };
  } catch (e) {
    state.checks[product] = { status: "yellow", error: e.message, results: [], sources: [] };
  }
  renderAll(); updateGate();
}

function counts() {
  const ing = state.plan ? state.plan.ingredients : [];
  const st = ing.map((i) => (state.checks[i] || { status: "wait" }).status);
  return { n: ing.length, safe: st.filter((s) => s === "green").length, red: st.filter((s) => s === "red").length,
    yellow: st.filter((s) => s === "yellow").length, wait: st.filter((s) => s === "wait").length };
}

function renderSummary() {
  const p = state.plan; if (!p) return;
  const ready = state.ready >= READY_AT ? ["green", "Pie looks ready"] : state.ready > 0 ? ["yellow", "Pie not ready"] : ["", "Pie not checked yet"];
  $("summary").innerHTML = `
    <h2 class="cap">${esc(p.caption)}</h2>
    ${p.guest ? `<p class="for">For <b>${esc(p.guest)}</b></p>` : ""}
    <button type="button" class="stat ${ready[0]}" data-go="camera"><span class="sdot"></span>${ready[1]}<span class="go">Camera ›</span></button>`;
}
$("summary").onclick = (e) => { const b = e.target.closest("[data-go]"); if (b) show(b.dataset.go); };

function renderRecipe() {
  const p = state.plan;
  if (!p) { $("ingCol").innerHTML = `<p class="muted">${state.busy ? "Perplexity is writing the recipe…" : "Make a design first."}</p>`; $("stepCol").innerHTML = ""; return; }
  const rows = p.ingredients.map((ing) => {
    const c = state.checks[ing] || { status: "wait" };
    const open = state.open === ing;
    let detail = "";
    if (open && c.results) {
      detail = `<div class="detail">${c.results.map((r) => `<div class="drow"><span class="pill sm ${r.color}">${label[r.color]}</span>${esc(r.name)} · ${esc(r.allergen)}<span class="prob">${Math.round(r.probability * 100)}%</span></div>`).join("") || `<div>No guest avoids an allergen for this.</div>`}
        ${c.error ? `<div>Check failed: ${esc(c.error)}</div>` : ""}<div>${(c.sources || []).slice(0, 4).map((s, i) => `<span class="src"><span class="num">${i + 1}</span>${esc(host(s.url))}</span>`).join("")}</div></div>`;
    }
    return `<button type="button" class="ing ${open ? "open" : ""}" data-ing="${esc(ing)}">
      <span class="pill ${c.status}">${c.status === "wait" ? '<span class="spin sm"></span>' : label[c.status]}</span>
      <span class="who">${esc(ing)}</span></button>${detail}`;
  }).join("");
  $("ingCol").innerHTML = `<h3>Ingredients</h3>${rows}<p class="muted small">Tap an ingredient to see each guest's check.</p>`;
  const steps = (p.recipe || []).map((s) => `<li>${esc(s)}</li>`).join("");
  $("stepCol").innerHTML = `<h3>Steps</h3><ol class="steps">${steps}</ol>
    ${p.piping_notes ? `<p class="tip"><b>Piping</b> ${esc(p.piping_notes)}</p>` : ""}
    ${p.diet_notes ? `<p class="tip"><b>Diet</b> ${esc(p.diet_notes)}</p>` : ""}
    <div>${(p.sources || []).slice(0, 5).map((s, i) => `<span class="src"><span class="num">${i + 1}</span>${esc(host(s.url))}</span>`).join("")}</div>`;
}
$("ingCol").onclick = (e) => {
  const b = e.target.closest(".ing"); if (!b) return;
  state.open = state.open === b.dataset.ing ? null : b.dataset.ing; renderRecipe();
};
function renderAll() { renderSummary(); renderRecipe(); }

// ---------- preview ----------
function drawPreview() {
  window.pieStrokes = state.strokes || [];
  if (window.Pie3D) window.Pie3D.show(window.pieStrokes);
  // 2D fallback (only visible if WebGL is unavailable). SVG y is down; strokes use +Y away from you.
  $("strokes").innerHTML = (state.strokes || []).map((s) =>
    `<polyline points="${s.map(([x, y]) => `${x.toFixed(1)},${(-y).toFixed(1)}`).join(" ")}"/>`).join("");
}

// ---------- gate ----------
function allSafe() {
  if (!state.plan) return false;
  return state.plan.ingredients.every((i) => state.checks[i] && state.checks[i].status === "green");
}
function reason() {
  if (!state.plan) return state.busy ? "Perplexity is designing…" : "Make a design to start.";
  const c = counts();
  if (c.wait) return "Checking ingredients…";
  if (c.red || c.yellow) return "Send is locked: an ingredient needs a check (Recipe).";
  if (state.ready < READY_AT) return "Send is locked: check the pie on the Camera screen.";
  return "Ready. Stay next to the printer, then tap Send.";
}
function updateGate() {
  const p = !!state.plan;
  $("dryBtn").disabled = !p || state.job;
  const ok = p && allSafe() && state.ready >= READY_AT;
  const b = $("sendBtn");
  if (state.job) { b.disabled = false; b.textContent = "Stop"; b.classList.add("stop"); }
  else { b.disabled = !ok; b.textContent = "Send"; b.classList.remove("stop"); $("why").textContent = reason(); }
  renderSummary();
}

$("readyBtn").onclick = async () => {
  $("camMsg").innerHTML = '<span class="spin sm"></span> Taking a photo and asking Perplexity…';
  try {
    if (state.live) {
      state.ready = (await apiJson("/api/ready", {})).probability;
      $("camImg").src = `/api/photo?t=${Date.now()}`; $("camImg").hidden = false; $("camEmpty").hidden = true;
    } else { await sleep(800); state.ready = 0.97; $("camEmpty").textContent = "Offline: sample check, no photo."; }
    $("camMsg").textContent = state.ready >= READY_AT ? `Pie looks ready (${Math.round(state.ready * 100)}%).`
      : `Not ready (${Math.round(state.ready * 100)}%). Center the pie and clear the bed.`;
  } catch (e) { state.ready = 0; $("camMsg").textContent = `Camera error: ${e.message}`; }
  updateGate();
};

async function start(dry_run) {
  if (!state.live) { log(dry_run ? "Offline: dry run would trace the path 15 mm above the pie." : "Offline: would pipe now."); return; }
  try {
    const r = await apiJson("/api/start", { dry_run });
    state.job = true; updateGate();
    log(`${dry_run ? "Dry run" : "Piping"} started (${r.lines} moves). Stay next to the printer.`);
    for (let i = 0; i < 7200; i++) {
      await sleep(500);
      const j = await apiJson("/api/job");
      $("jobFill").style.width = `${Math.round((100 * j.done) / Math.max(1, j.total))}%`;
      if (!j.running) { log(j.error ? `Stopped: ${j.error}` : `${dry_run ? "Dry run" : "Piping"} done.`); break; }
    }
  } catch (e) { log(`Send refused: ${e.message}`); }
  state.job = false; updateGate(); if (note) $("why").textContent = note;
}
$("dryBtn").onclick = () => start(true);

// Send turns into Stop while the printer is moving (sends M112).
$("sendBtn").onclick = async () => {
  if (!state.job) return start(false);
  state.ready = 0;
  try { await api("/api/stop", {}); log("Stopped (M112). Power-cycle the printer before continuing."); }
  catch (e) { log(`Stop failed: ${e.message}. Switch the printer off now.`); }
};

// ---------- on-screen keyboard (kiosk Chromium has no OS keyboard) ----------
const KEYS = ["qwertyuiop", "asdfghjkl'", "zxcvbnm,.", ["⇧", "space", "⌫", "Done"]];
let shift = false;
function drawKbd() {
  $("kbd").innerHTML = KEYS.map((row) => `<div class="krow">${(typeof row === "string" ? [...row] : row).map((k) =>
    `<button type="button" class="key ${k.length > 1 ? "wide " + (k === "space" ? "space" : "") : ""}" data-k="${esc(k)}">${esc(k === "space" ? "space" : shift && k.length === 1 ? k.toUpperCase() : k)}</button>`).join("")}</div>`).join("");
}
function showKbd() { drawKbd(); $("kbd").hidden = false; document.body.classList.add("typing"); }
function hideKbd() { $("kbd").hidden = true; document.body.classList.remove("typing"); window.Pie3D?.resize(); }
$("prompt").addEventListener("pointerdown", () => { if ($("kbd").hidden) showKbd(); });
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

async function init() {
  await refreshStatus();
  if (!state.live) log("Offline: sample results only, no printer.");
  setInterval(refreshStatus, 10000);
  updateGate();
}
init();
