// PumpkinPi touchscreen UI.
// Online: served by pumpkinpi/server.py on the Pi (Agent API, Search API, Decider, printer).
// No server (not on the Pi): sample results only, behind the "Printer Not Connected" screen.

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

// Diet chips. Checked diets go to the Decider like allergens; "low sugar" only changes the recipe.
const DIETS = [["vegan", "Vegan"], ["dairy-free", "Dairy-free"], ["gluten-free", "Gluten-free"], ["egg-free", "Egg-free"], ["low sugar", "Low sugar"]];
const DEMO_DIET_PROBS = {  // offline sample only
  vegan: { "heavy cream": 0.99, "semi-sweet chocolate chips": 0.4 }, "dairy-free": { "heavy cream": 0.99, "semi-sweet chocolate chips": 0.4 },
  "gluten-free": { "heavy cream": 0.02, "semi-sweet chocolate chips": 0.2 }, "egg-free": { "heavy cream": 0.02, "semi-sweet chocolate chips": 0.05 },
};

const state = { live: false, everLive: false, guests: DEMO_GUESTS, plan: null, strokes: [], checks: {},
  ready: 0, busy: false, open: null, job: false, photo: null, diets: [] };

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

// ---------- printer connection: gray out the app until the Pi sees the printer on USB ----------
let statusTimer = null;
async function refreshStatus() {
  let printer = false;
  try {
    const s = await apiJson("/api/status");
    state.live = state.everLive = true; state.guests = s.guests; printer = !!s.printer;
  } catch {
    // Never fall back to sample "Safe" results once the real Pi server has been seen.
    if (!state.everLive) state.live = false;
  }
  if (printer) state.skipPrinter = false;  // show the screen again if it gets unplugged later
  const blocked = !printer && !state.skipPrinter;
  $("noPrinter").hidden = !blocked;
  document.body.classList.toggle("nop", blocked);
  state.printer = printer;
  clearTimeout(statusTimer);
  statusTimer = setTimeout(refreshStatus, printer ? 10000 : 3000);
}
$("skipPrinter").onclick = () => { state.skipPrinter = true; $("noPrinter").hidden = true; document.body.classList.remove("nop"); };

// ---------- screens ----------
function show(view) {
  document.body.dataset.view = view;
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t.dataset.v === view);
  $("designView").hidden = view !== "design";
  $("recipeView").hidden = view !== "recipe";
  $("cameraView").hidden = view !== "camera";
  if (view === "design") window.Pie3D?.resize();
  liveCamera(view === "camera");
}

// Live Pi camera preview (MJPEG). Closing the <img> stream lets the Pi stop the camera.
function liveCamera(on) {
  const img = $("camImg");
  if (!on || !state.live) {
    if (img.dataset.live) { img.removeAttribute("src"); delete img.dataset.live; img.hidden = true; $("liveTag").hidden = true; $("camEmpty").hidden = false; }
    if (on) $("camEmpty").textContent = "The live camera runs on the Pi.";
    return;
  }
  if (img.dataset.live) return;
  img.dataset.live = "1";
  $("camEmpty").textContent = "Starting camera…";
  img.onload = () => { img.hidden = false; $("liveTag").hidden = false; $("camEmpty").hidden = true; };
  img.onerror = () => { delete img.dataset.live; img.hidden = true; $("liveTag").hidden = true; $("camEmpty").hidden = false; $("camEmpty").textContent = "Camera not available. Check the ribbon cable."; };
  img.src = `/api/camera.mjpg?t=${Date.now()}`;
}
document.querySelector(".tabs").onclick = (e) => { const t = e.target.closest(".tab"); if (t) show(t.dataset.v); };

// ---------- 1. Agent API: prompt -> plan ----------
async function ask() {
  const prompt = $("prompt").value.trim();
  if (!prompt || state.busy) return;
  remember(prompt);
  state.busy = true; state.checks = {}; state.ready = 0; state.open = null; state.plan = null;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Making"></span>';
  show("recipe"); state.strokes = []; drawPreview(); window.Pie3D?.thinking(true);
  renderRecipe(); updateGate();
  try {
    const res = state.live ? await apiJson("/api/design", { prompt, diets: state.diets })
      : (await sleep(1400), await (await fetch("demo.json")).json());
    state.plan = res.plan; state.strokes = res.strokes;
    window.Pie3D?.thinking(false); drawPreview();
    renderAll();
    log(`Checking ${res.plan.ingredients.length} ingredients…`);
    for (const ing of res.plan.ingredients) await check(ing);
    log(allSafe() ? "All ingredients safe. See Design, then check the pie on Camera." : "An ingredient needs a check.");
  } catch (e) {
    window.Pie3D?.thinking(false);
    state.plan = null; state.strokes = []; drawPreview(); renderRecipe();
    $("ingCol").innerHTML = `<p class="msg">Couldn't make that: ${esc(e.message)}</p>`;
  } finally {
    state.busy = false; $("askBtn").textContent = "Make"; updateGate();
  }
}

// ---------- recent prompts (kept on this Pi's browser, newest first) ----------
const RECENT_KEY = "pumpkinpi.recent";
const recent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; } catch { return []; } };
function remember(p) {
  const list = [p, ...recent().filter((x) => x.toLowerCase() !== p.toLowerCase())].slice(0, 6);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch {}
}
function renderRecent() {
  const list = recent();
  $("recent").innerHTML = list.length ? `<span class="lbl">Recent</span>` +
    list.map((p, i) => `<button type="button" class="chip" data-i="${i}">${esc(p)}</button>`).join("") : "";
  $("recent").hidden = !list.length || $("kbd").hidden;
}
$("recent").addEventListener("pointerdown", (e) => e.preventDefault());  // keep the keyboard open
$("recent").onclick = (e) => {
  const b = e.target.closest("[data-i]"); if (!b) return;
  $("prompt").value = recent()[+b.dataset.i]; syncClear();   // edit it, or tap Make / Done
};
function syncClear() { $("clearBtn").hidden = !$("prompt").value; }
$("clearBtn").addEventListener("pointerdown", (e) => e.preventDefault());
$("clearBtn").onclick = () => { $("prompt").value = ""; syncClear(); if ($("kbd").hidden) showKbd(); };

// ---------- 2. Search API + Decider per ingredient ----------
async function check(product) {
  state.checks[product] = { status: "wait" }; renderAll();
  try {
    let res;
    if (state.live) res = await apiJson("/api/check", { product, diets: state.diets });
    else {
      await sleep(900);
      const p = DEMO_PROBS[product] || {};
      res = { sources: [{ title: "Have Food Allergies? Read the Label", url: "https://www.fda.gov/consumers/consumer-updates/have-food-allergies-read-label" }], relevance: 0.9,
        results: state.guests.flatMap((g) => g.avoid.map((a) => ({ name: g.name, allergen: a, probability: p[a] ?? 0.3 })))
          .concat(state.diets.filter((d) => DEMO_DIET_PROBS[d]).map((d) => ({ name: d[0].toUpperCase() + d.slice(1), diet: d, allergen: d, probability: DEMO_DIET_PROBS[d][product] ?? 0.3 }))) };
    }
    res.results.forEach((r) => (r.color = r.verdict ? toColor[r.verdict] : verdict(r.probability)));
    const worst = res.results.some((r) => r.color === "red") ? "red" : res.results.some((r) => r.color === "yellow") ? "yellow" : "green";
    // Red only because of a diet chip (e.g. cream with Vegan on) reads "Not vegan", not "Allergen".
    const redRows = res.results.filter((r) => r.color === "red");
    const tag = worst === "red" && redRows.every((r) => r.diet) ? `Not ${redRows[0].diet}` : null;
    state.checks[product] = { status: worst, tag, ...res };
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

const srcItem = (src, n, tag) => `<li class="srcitem"><span class="num">${n}</span><span class="st"><b>${esc(src.title || host(src.url))}</b>
  <span class="url">${esc(host(src.url))}${tag ? ` · ${esc(tag)}` : ""}</span></span></li>`;

function renderDiets() {
  const avoid = [...new Set(state.guests.flatMap((g) => g.avoid))];
  $("diets").innerHTML = `<span class="chip on lock" title="${esc(avoid.join(", "))}">Allergy-safe</span>` +
    DIETS.map(([k, t]) => `<button type="button" class="chip ${state.diets.includes(k) ? "on" : ""}" data-d="${k}" aria-pressed="${state.diets.includes(k)}">${t}</button>`).join("");
}
$("diets").onclick = (e) => {
  const b = e.target.closest("[data-d]"); if (!b || state.busy) return;
  const d = b.dataset.d;
  state.diets = state.diets.includes(d) ? state.diets.filter((x) => x !== d) : [...state.diets, d];
  renderDiets();
  if (state.plan && $("prompt").value.trim()) ask();  // remake the recipe for the new diet
};

function renderRecipe() {
  renderDiets();
  const p = state.plan;
  if (!p) {
    $("ingCol").innerHTML = state.busy ? `<p class="msg"><img class="think" src="brand/perplexity-symbol-ink.svg" alt=""> Perplexity is writing the recipe…</p>`
      : `<p class="muted big">Type what you'd like, then tap Make.</p>`;
    $("stepCol").innerHTML = ""; $("srcCol").innerHTML = ""; return;
  }
  const rows = p.ingredients.map((ing) => {
    const c = state.checks[ing] || { status: "wait" };
    const open = state.open === ing;
    let detail = "";
    if (open && c.results) {
      detail = `<div class="detail">${c.results.map((r) => `<div class="drow"><span class="pill sm ${r.color}">${label[r.color]}</span>${esc(r.name)}${r.diet ? "" : ` · ${esc(r.allergen)}`}<span class="prob">${Math.round(r.probability * 100)}%</span></div>`).join("") || `<div>No guest avoids an allergen for this.</div>`}
        ${c.error ? `<div>Check failed: ${esc(c.error)}</div>` : ""}</div>`;
    }
    return `<button type="button" class="ing ${open ? "open" : ""}" data-ing="${esc(ing)}">
      <span class="pill ${c.status}">${c.status === "wait" ? '<span class="spin sm"></span>' : esc(c.tag || label[c.status])}</span>
      <span class="who">${esc(ing)}</span></button>${detail}`;
  }).join("");
  $("ingCol").innerHTML = `<h3>Ingredients</h3>${rows}
    ${p.allergy_notes ? `<p class="tip"><b>Allergies</b> ${esc(p.allergy_notes)}</p>` : ""}
    <p class="muted small">Tap an ingredient to see each guest's check.</p>`;
  const steps = (p.recipe || []).map((s) => `<li>${esc(s)}</li>`).join("");
  $("stepCol").innerHTML = `<h3>Steps</h3><ol class="steps">${steps}</ol>
    ${p.piping_notes ? `<p class="tip"><b>Piping</b> ${esc(p.piping_notes)}</p>` : ""}
    ${p.diet_notes ? `<p class="tip"><b>Diet</b> ${esc(p.diet_notes)}</p>` : ""}`;
  // Sources: recipe research (Agent API web search) + label pages per ingredient (Search API, judged by Decider).
  let n = 0;
  const recipe = (p.sources || []).slice(0, 4).map((s) => srcItem(s, ++n, "")).join("");
  const seen = new Set();
  const labels = p.ingredients.flatMap((ing) => ((state.checks[ing] || {}).sources || []).slice(0, 2).map((s) => [s, ing]))
    .filter(([s]) => !seen.has(s.url) && seen.add(s.url)).slice(0, 4).map(([s, ing]) => srcItem(s, ++n, ing)).join("");
  $("srcCol").innerHTML = `<h3>Sources</h3><ol class="srcs">${recipe}${labels}</ol>
    <p class="muted small">Found with Perplexity search. Allergen and diet checks by Decider.${state.live ? "" : " Sample results."}</p>`;
}
$("ingCol").onclick = (e) => {
  const b = e.target.closest(".ing"); if (!b) return;
  state.open = state.open === b.dataset.ing ? null : b.dataset.ing; renderRecipe();
};
function renderAll() { renderRecipe(); }

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
  if (c.red || c.yellow) return "Locked: an ingredient needs a check";
  if (state.ready < READY_AT) return "Locked: check the pie on Camera";
  return "Ready. Stay next to the printer.";
}
function updateGate() {
  const p = !!state.plan;
  $("dryBtn").disabled = !p || state.job;
  const ok = p && allSafe() && state.ready >= READY_AT;
  const b = $("sendBtn");
  if (state.job) { b.disabled = false; b.textContent = "Stop"; b.classList.add("stop"); }
  else { b.disabled = !ok; b.textContent = "Send to Printer"; b.classList.remove("stop"); $("why").textContent = reason(); }
}

$("readyBtn").onclick = async () => {
  $("camMsg").innerHTML = '<span class="spin sm"></span> Taking a photo and asking Perplexity…';
  try {
    if (state.live) {
      state.ready = (await apiJson("/api/ready", {})).probability;
    } else { await sleep(800); state.ready = 0.97; }
    $("camMsg").textContent = state.ready >= READY_AT ? `Pie looks ready (${Math.round(state.ready * 100)}%).`
      : `Not ready (${Math.round(state.ready * 100)}%). Center the pie and clear the bed.`;
  } catch (e) { state.ready = 0; $("camMsg").textContent = `Camera error: ${e.message}`; }
  updateGate();
};

async function start(dry_run) {
  if (!state.live) { log(dry_run ? "Sample: dry run would trace the path 15 mm above the pie." : "Sample: would pipe now."); return; }
  try {
    const r = await apiJson("/api/start", { dry_run });
    state.job = true; updateGate();
    log(`Making G-code (${r.lines} moves)…`);
    const what = dry_run ? "Dry run" : "Piping";
    for (let i = 0; i < 7200; i++) {
      await sleep(500);
      const j = await apiJson("/api/job");
      $("jobFill").style.width = `${j.pct ?? Math.round((100 * j.done) / Math.max(1, j.total))}%`;
      if (j.phase === "upload") $("why").textContent = `Saving ${j.file} to the printer's SD card…`;
      else if (j.phase === "printing") $("why").textContent = `${what} ${j.file} from the SD card. Stay next to the printer.`;
      else if (j.phase === "streaming") $("why").textContent = `${what} over USB (no SD card). Stay next to the printer.`;
      if (!j.running) { log(j.error ? `Stopped: ${j.error}` : `${what} done${j.file ? ` (${j.file})` : ""}.`); break; }
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
function showKbd() { drawKbd(); $("kbd").hidden = false; document.body.classList.add("typing"); renderRecent(); syncClear(); }
function hideKbd() { $("kbd").hidden = true; $("recent").hidden = true; document.body.classList.remove("typing"); syncClear(); window.Pie3D?.resize(); }
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
  syncClear();
};
$("askForm").onsubmit = (e) => { e.preventDefault(); hideKbd(); ask(); };

async function init() {
  await refreshStatus();
  renderRecipe();
  updateGate();
}
init();
