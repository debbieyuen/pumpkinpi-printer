// Perplexity Make (PumpkinPi) touchscreen UI.
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
// The top box asks for a new idea on Recipe/Camera ("Make"), and for a change on Design ("Update").
const PH = { make: "What should we pipe on the pie?", change: "Change the design, e.g. just a heart, no name" };
let boxMode = "make";
function setBox(mode) {
  if (mode === boxMode) return;
  const el = $("prompt");
  if (boxMode === "make") state.prompt = el.value; else state.change = el.value;
  boxMode = mode;
  el.value = (mode === "make" ? state.prompt : state.change) || "";
  el.placeholder = PH[mode]; el.setAttribute("aria-label", PH[mode]);
  if (!state.busy) $("askBtn").textContent = mode === "make" ? "Make" : "Update";
  syncClear();
}
function show(view) {
  document.body.dataset.view = view;
  setBox(view === "design" && state.plan ? "change" : "make");
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t.dataset.v === view);
  $("designView").hidden = view !== "design";
  $("recipeView").hidden = view !== "recipe";
  $("cameraView").hidden = view !== "camera";
  if (view === "design") window.Pie3D?.resize();
  liveCamera(view === "camera");
  updateGate();
}

// Live Pi camera preview (MJPEG). Closing the <img> stream lets the Pi stop the camera.
function liveCamera(on) {
  const img = $("camImg");
  if (on && !state.live) {   // no Pi server: show a drawn sample frame so the screen can be tried anywhere
    img.src = "sample-camera.jpg"; img.hidden = false; $("liveTag").hidden = false; $("liveTag").textContent = "Sample"; $("camEmpty").hidden = true;
    return;
  }
  if (!on || !state.live) {
    if (img.dataset.live) { img.removeAttribute("src"); delete img.dataset.live; img.hidden = true; $("liveTag").hidden = true; $("camEmpty").hidden = false; }
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
  const prompt = (boxMode === "make" ? $("prompt").value : state.prompt || "").trim();
  if (!prompt || state.busy) return;
  state.prompt = prompt; state.change = "";
  state.busy = true; state.checks = {}; state.ready = 0; state.open = null; state.plan = null;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Making"></span>';
  show("recipe"); state.strokes = []; drawPreview(); window.Pie3D?.thinking(true);
  renderRecipe(); updateGate();
  try {
    const res = state.live ? await apiJson("/api/design", { prompt, diets: state.diets })
      : (await sleep(1400), await (await fetch("demo.json")).json());
    state.demo = state.live ? null : res;
    applyDesign(res);
    await checkMissing();
  } catch (e) {
    window.Pie3D?.thinking(false);
    state.plan = null; state.strokes = []; drawPreview(); renderRecipe();
    $("ingCol").innerHTML = `<p class="msg">Couldn't make that: ${esc(e.message)}</p>`;
  } finally {
    state.busy = false; $("askBtn").textContent = boxMode === "make" ? "Make" : "Update"; renderDesign(); updateGate();
  }
}

// Show a design. res.strokes is the path read back from the real G-code (exact), res.path its length/time.
function applyDesign(res) {
  state.plan = res.plan; state.strokes = res.strokes; state.path = res.path || null;
  if (res.plan.text) state.name = res.plan.text;
  window.Pie3D?.thinking(false); drawPreview(); renderAll(); renderDesign();
}
async function checkMissing() {
  const todo = state.plan.ingredients.filter((i) => !state.checks[i]);
  if (todo.length) log(`Checking ${todo.length} ingredient${todo.length > 1 ? "s" : ""}…`);
  for (const ing of todo) await check(ing);
  log(allSafe() ? "All ingredients safe. Tap Start Designing." : "An ingredient needs a check.");
}

// ---------- Design changes: quick buttons (instant) or words ("just a heart, no name", Agent API) ----------
function demoVariant(shape, text) {   // sample mode: paths precomputed from the real G-code pipeline
  const v = state.demo?.variants || {};
  const t = v[`${shape}|${text}`] ? text : v[`${shape}|`] ? "" : null;
  if (t === null) throw new Error("not in the sample");
  const x = v[`${shape}|${t}`];
  return { plan: { ...state.plan, shape, text: t }, strokes: x.strokes, path: { mm: x.mm, seconds: x.seconds } };
}
async function revise() {
  const change = $("prompt").value.trim();
  if (!change || !state.plan || state.busy || state.job) return;
  state.change = change; state.busy = true;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Updating"></span>'; window.Pie3D?.thinking(true); renderDesign();
  try {
    let res;
    if (state.live) res = await apiJson("/api/revise", { change, diets: state.diets });
    else {  // sample only: understand the common changes locally
      await sleep(900);
      const c = change.toLowerCase();
      const shape = /heart/.test(c) ? "heart" : /star/.test(c) ? "star" : /smil/.test(c) ? "smiley" : /(only|just) (the )?(name|word|text)/.test(c) ? "text" : state.plan.shape;
      const noName = /(no|without|drop|remove)\b.*(name|text|word)|only a|just a/.test(c) && shape !== "text";
      res = demoVariant(shape, noName ? "" : state.plan.text || state.name || "");
    }
    applyDesign(res);
    $("prompt").value = ""; state.change = ""; syncClear();
    await checkMissing();   // only new ingredients need a new check
  } catch (e) { window.Pie3D?.thinking(false); drawPreview(); log(`Couldn't change it: ${e.message}`); }
  state.busy = false; $("askBtn").textContent = boxMode === "make" ? "Make" : "Update"; renderDesign(); updateGate();
}
function renderDesign() {}   // Design is just the pie

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

// ---------- recipe visuals ----------
// Ingredient pictures (simple flat drawings, matched by keyword) and step icons (by verb).
const ING_ART = [
  [/chocolate|cocoa|cacao/, `<svg viewBox="0 0 48 48"><path d="M24 9c5 8 13 13 13 21a13 13 0 0 1-26 0c0-8 8-13 13-21z" fill="#5a3420"/><path d="M19 27c0 4 2 6 5 7" stroke="#8a5a3c" stroke-width="2.5" fill="none" stroke-linecap="round"/></svg>`],
  [/coconut/, `<svg viewBox="0 0 48 48"><circle cx="24" cy="25" r="15" fill="#7a5233"/><circle cx="24" cy="25" r="10" fill="#fbf6ea"/><circle cx="20" cy="15" r="1.6" fill="#3d2816"/><circle cx="27" cy="15" r="1.6" fill="#3d2816"/></svg>`],
  [/cream|milk|half-and-half|half and half/, `<svg viewBox="0 0 48 48"><path d="M15 17l4-7h10l4 7v24H15z" fill="#fff" stroke="#20808d" stroke-width="2.2" stroke-linejoin="round"/><path d="M15 17h18" stroke="#20808d" stroke-width="2.2"/><rect x="19" y="24" width="10" height="9" rx="2" fill="#badfde"/></svg>`],
  [/butter/, `<svg viewBox="0 0 48 48"><path d="M8 29l10-9h22v10l-10 9H8z" fill="#f6d77b"/><path d="M8 29h22l10-9M30 29v10" stroke="#d4a93a" stroke-width="2" fill="none"/></svg>`],
  [/sugar|sweetener|stevia|monk|allulose|erythritol/, `<svg viewBox="0 0 48 48"><path d="M12 19l12-7 12 7v14l-12 7-12-7z" fill="#fff" stroke="#c9c3b5" stroke-width="2"/><path d="M12 19l12 7 12-7M24 26v14" stroke="#c9c3b5" stroke-width="2" fill="none"/></svg>`],
  [/vanilla|extract/, `<svg viewBox="0 0 48 48"><rect x="18" y="8" width="12" height="7" rx="1.5" fill="#20808d"/><path d="M16 17h16v22a3 3 0 0 1-3 3H19a3 3 0 0 1-3-3z" fill="#9a5b2a"/><rect x="18" y="24" width="12" height="8" rx="1" fill="#fbf6ea"/></svg>`],
  [/pumpkin/, `<svg viewBox="0 0 48 48"><ellipse cx="24" cy="28" rx="16" ry="12" fill="#e08c3e"/><path d="M24 16v24M15 19c-3 6-3 12 0 18M33 19c3 6 3 12 0 18" stroke="#c06a24" stroke-width="2" fill="none"/><path d="M24 16c0-4 2-6 5-7" stroke="#2f8a57" stroke-width="3" fill="none" stroke-linecap="round"/></svg>`],
];
const JAR = `<svg viewBox="0 0 48 48"><rect x="15" y="9" width="18" height="6" rx="2" fill="#20808d"/><path d="M14 16h20v22a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4z" fill="#f3f1ec" stroke="#5c6b6b" stroke-width="2"/></svg>`;
const ingArt = (name) => (ING_ART.find(([re]) => re.test(name.toLowerCase())) || [0, JAR])[1];
const I = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const STEP_ICON = [
  [/heat|simmer|warm|boil|microwave|melt/, I('<path d="M12 3c2 3 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-8z"/>')],
  [/pour|add/, I('<path d="M5 8h10v4a5 5 0 0 1-10 0z"/><path d="M15 9h2a2 2 0 0 1 0 4h-2"/><path d="M8 3v2M11 2v3"/>')],
  [/stir|whisk|mix|beat|blend/, I('<path d="M12 21V12"/><path d="M12 12c-3 0-5-3-5-6s2-3 5-3 5 0 5 3-2 6-5 6z"/><path d="M12 3v9"/>')],
  [/cool|chill|refrigerat|fridge|set/, I('<path d="M12 2v20M4.9 6.5l14.2 11M19.1 6.5 4.9 17.5"/>')],
  [/rest|wait|minute/, I('<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M10 2h4"/>')],
  [/syringe|spoon|fill|load|pipe/, I('<path d="m18 2 4 4M16 4l4 4M19 5l-9 9M14 6l4 4-8 8H6v-4z"/><path d="M3 21l3-3"/>')],
];
const stepIcon = (t) => (STEP_ICON.find(([re]) => re.test(t.toLowerCase())) || [0, I('<circle cx="12" cy="12" r="3"/>')])[1];
const STATUS_ICON = { green: I('<path d="m5 12 5 5 9-10"/>'), yellow: I('<path d="M12 7v6M12 17h.01"/>'), red: I('<path d="M6 6l12 12M18 6 6 18"/>') };
const favicon = (u) => `<img class="fav" alt="" src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(host(u))}&sz=64" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'fav letter',textContent:'${esc(host(u)[0] || "?").toUpperCase()}'}))">`;
// Topping colour for the hero swatch
const swatch = (t) => /white/.test(t) ? "#f4ead6" : /milk choc/.test(t) ? "#8a5a3c" : /choc|cocoa|ganache/.test(t) ? "#4a2a18" : /cream cheese|whipped|cream/.test(t) ? "#fbf6ea" : /caramel/.test(t) ? "#c27a32" : "#e08c3e";

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
        ${p.allergy_notes ? `<div class="dnote">${esc(p.allergy_notes)}</div>` : ""}
        ${c.error ? `<div>Check failed: ${esc(c.error)}</div>` : ""}</div>`;
    }
    const st = c.status === "wait" ? '<span class="spin sm"></span>' : STATUS_ICON[c.status];
    return `<button type="button" class="ing ${open ? "open" : ""}" data-ing="${esc(ing)}">
      <span class="art">${ingArt(ing)}</span>
      <span class="who">${esc(ing)}<span class="tag ${c.status}">${c.status === "wait" ? "Checking" : esc(c.tag || label[c.status])}</span></span>
      <span class="sicon ${c.status}">${st}</span></button>${detail}`;
  }).join("");
  $("ingCol").innerHTML = `<div class="hero"><span class="bowl" style="--c:${swatch((p.topping || "").toLowerCase())}"></span>
      <span><b>${esc(p.topping || "Topping")}</b><span class="muted">${p.ingredients.length} ingredients · ${(p.recipe || []).length} steps</span></span></div>${rows}`;
  const steps = (p.recipe || []).map((t, i) => `<li><span class="sico">${stepIcon(t)}<i>${i + 1}</i></span><span>${esc(t)}</span></li>`).join("");
  $("stepCol").innerHTML = `<h3>Steps</h3><ol class="steps">${steps}</ol>
    ${p.diet_notes ? `<p class="tip"><b>Diet</b> ${esc(p.diet_notes)}</p>` : ""}`;
  // Sources: recipe research (Agent API web search) + label pages per ingredient (Search API, judged by Decider).
  const seen = new Set();
  const all = [...(p.sources || []).slice(0, 4).map((s) => [s, ""]),
    ...p.ingredients.flatMap((ing) => ((state.checks[ing] || {}).sources || []).slice(0, 2).map((s) => [s, ing]))]
    .filter(([s]) => s.url && !seen.has(s.url) && seen.add(s.url)).slice(0, 6);
  $("srcCol").innerHTML = `<h3>Sources</h3><ol class="srcs">${all.map(([s, tag]) => `<li class="srcitem">${favicon(s.url)}<span class="st"><b>${esc(s.title || host(s.url))}</b>
    <span class="url">${esc(host(s.url))}${tag ? ` · ${esc(tag)}` : ""}</span></span></li>`).join("")}</ol>
    <p class="muted small by"><img src="brand/perplexity-symbol-ink.svg" alt=""> Perplexity search + Decider${state.live ? "" : " · sample"}</p>`;
}
$("ingCol").onclick = (e) => {
  const b = e.target.closest(".ing"); if (!b) return;
  state.open = state.open === b.dataset.ing ? null : b.dataset.ing; renderRecipe();
};
function renderAll() { renderRecipe(); renderDesign(); }

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
  if (c.red || c.yellow) return "An ingredient needs a check";
  if (state.ready < READY_AT) return document.body.dataset.view === "recipe" ? "All ingredients checked" : "Next: check the pie on Camera";
  return "Ready. Stay next to the printer.";
}
// Bottom button follows the flow: Recipe -> Start Designing, Design -> Check the Pie / Send to Printer.
function nextStep() {
  const view = document.body.dataset.view;
  if (state.job) return "stop";
  if (view === "recipe") return "design";
  if (view === "design" && state.ready < READY_AT) return "camera";
  return "send";
}
function updateGate() {
  const p = !!state.plan;
  $("dryBtn").disabled = !p || state.job;
  const ok = p && allSafe() && state.ready >= READY_AT;
  const b = $("sendBtn"), step = nextStep();
  b.classList.toggle("stop", step === "stop");
  if (step === "stop") { b.disabled = false; b.textContent = "Stop"; return; }
  $("why").textContent = reason();
  if (step === "design") { b.textContent = "Start Designing"; b.disabled = !p || state.busy; }
  else if (step === "camera") { b.textContent = "Check the Pie"; b.disabled = !p || state.busy; }
  else { b.textContent = "Send to Printer"; b.disabled = !ok || state.busy; }
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
  const step = nextStep();
  if (step === "design") return show("design");
  if (step === "camera") return show("camera");
  if (!state.job) return start(false);
  state.ready = 0;
  try { await api("/api/stop", {}); log("Stopped (M112). Power-cycle the printer before continuing."); }
  catch (e) { log(`Stop failed: ${e.message}. Switch the printer off now.`); }
};

// ---------- on-screen keyboard (kiosk Chromium has no OS keyboard) ----------
const KEYS = ["qwertyuiop", "asdfghjkl'", "zxcvbnm,.", ["shift", "space", "back", "Done"]];
// Drawn icons, not Unicode arrows: the kiosk fonts render those thin and off-center.
const KEY_ICON = {
  shift: (on) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 4 12.5h4.5V20h7v-7.5H20z" fill="${on ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>`,
  back: () => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5h11a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H9l-7-7z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="m11.5 9.5 5 5m0-5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
};
const KEY_LABEL = { shift: "Shift", back: "Delete", space: "Space", Done: "Done" };
let shift = false;
function drawKbd() {
  $("kbd").innerHTML = KEYS.map((row) => `<div class="krow">${(typeof row === "string" ? [...row] : row).map((k) => {
    const wide = k.length > 1, face = KEY_ICON[k] ? KEY_ICON[k](shift) : k === "space" ? "space" : shift && !wide ? k.toUpperCase() : k;
    return `<button type="button" class="key ${wide ? `wide k-${k}` : ""} ${k === "shift" && shift ? "on" : ""}" data-k="${esc(k)}" aria-label="${esc(KEY_LABEL[k] || k)}">${face}</button>`;
  }).join("")}</div>`).join("");
}
function showKbd() { drawKbd(); $("kbd").hidden = false; document.body.classList.add("typing"); syncClear(); }
function hideKbd() { $("kbd").hidden = true; document.body.classList.remove("typing"); syncClear(); window.Pie3D?.resize(); }
$("prompt").addEventListener("pointerdown", () => { if ($("kbd").hidden) showKbd(); });
$("prompt").addEventListener("focus", showKbd);
$("kbd").addEventListener("pointerdown", (e) => e.preventDefault()); // keep focus in the input
$("kbd").onclick = (e) => {
  const k = e.target.closest(".key")?.dataset.k; if (!k) return;
  const el = $("prompt");
  if (k === "back") el.value = el.value.slice(0, -1);
  else if (k === "space") el.value += " ";
  else if (k === "shift") { shift = !shift; drawKbd(); return; }
  else if (k === "Done") { hideKbd(); el.blur(); boxMode === "change" ? revise() : ask(); return; }
  else { el.value += shift ? k.toUpperCase() : k; if (shift) { shift = false; drawKbd(); } }
  syncClear();
};
$("askForm").onsubmit = (e) => { e.preventDefault(); hideKbd(); boxMode === "change" ? revise() : ask(); };

async function init() {
  await refreshStatus();
  renderRecipe(); renderDesign();
  updateGate();
}
init();
