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
// Sample mode (no Pi): real store products and labels from demo.json, and the pie drawn from your words
// with the same shapes and single-stroke fonts as shapes.py (ui/shapes.json, from scripts/export_ui_shapes.py).
const DIETS = [["vegan", "Vegan"], ["dairy-free", "Dairy-free"], ["gluten-free", "Gluten-free"], ["egg-free", "Egg-free"], ["low sugar", "Low sugar"]];
// Three toppings, three syringes. Each behaves differently, so each has its own settings (toolpath.TOPPINGS);
// these copies are only for sample mode. On the Pi they come from GET /api/toppings (incl. saved drip tests).
const TOPS = {
  chocolate: { label: "Melted chocolate", short: "Chocolate", tip: "small round tip", work_min: 12,
    prep: "Melt chips gently and keep it under 120°F. The syringe isn't heated, so pipe within about 10-15 minutes.",
    settings: { feed: 720, e_per_mm: 0.015, prime: 0.2, retract: 0.8, dwell: 1.0, gap: 1.0, lift_feed: 300, tip_offset: 0 } },
  frosting: { label: "Frosting", short: "Frosting", tip: "small round tip", work_min: 0,
    prep: "Room temperature, smooth, no air pockets.",
    settings: { feed: 600, e_per_mm: 0.02, prime: 0.3, retract: 0.6, dwell: 0.5, gap: 1.5, lift_feed: 300, tip_offset: 0 } },
  marshmallow: { label: "Melted marshmallow", short: "Marshmallow", tip: "wider round tip", work_min: 3,
    prep: "Cool about 3 minutes after melting, then pipe right away: it sets fast and gets stringy.",
    settings: { feed: 420, e_per_mm: 0.03, prime: 0.4, retract: 1.0, dwell: 1.5, gap: 2.0, lift_feed: 120, tip_offset: 0 } },
};
let SAMPLE = null, SHAPES = null;
async function loadSample() {
  if (!SAMPLE) SAMPLE = await (await fetch("demo.json")).json();
  state.demo = SAMPLE;
  if (!SHAPES) SHAPES = await (await fetch("shapes.json")).json();
}
function textStrokes(words, width, height, font) {
  const g = SHAPES.fonts[font] || SHAPES.fonts.print;
  let x = 0; const st = [];
  for (const c of [...words.trim()].slice(0, SHAPES.max_text)) {
    const gl = g[c] || g["?"];
    for (const s of gl.s) st.push(s.map(([px, py]) => [px + x, py]));
    x += gl.a;
  }
  if (!st.length) return [];
  const xs = st.flat().map((p) => p[0]), ys = st.flat().map((p) => p[1]);
  const w = Math.max(...xs) - Math.min(...xs) || 1, h = Math.max(...ys) - Math.min(...ys) || 1;
  const k = Math.min(width / w, height / h), cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
  return st.map((s) => s.map(([px, py]) => [(px - cx) * k, (py - cy) * k]));
}
const moveSt = (st, dy, k) => st.map((s) => s.map(([x, y]) => [x * k, y * k + dy]));
function splitLines(s) {   // mirrors shapes.split_lines: two short lines max, whole words only
  const words = s.split(/\s+/).filter(Boolean), M = SHAPES.max_line;
  for (let n = words.length; n > 0; n--) {
    const w = words.slice(0, n);
    if (w.join(" ").length <= M) return [w.join(" ")];
    const sp = [];
    for (let j = 1; j < n; j++) { const x = [w.slice(0, j).join(" "), w.slice(j).join(" ")]; if (Math.max(x[0].length, x[1].length) <= M) sp.push(x); }
    if (sp.length) return sp.reduce((a, b) => (Math.max(b[0].length, b[1].length) < Math.max(a[0].length, a[1].length) ? b : a));
  }
  return words.length ? [words[0].slice(0, M)] : [];
}
function strokesFor(plan) {   // mirrors shapes.strokes_for (incl. the cookie / cupcake shrink)
  const k = (SHAPES.bases || {})[plan.base || "pie"] ?? 1;
  return k === 1 ? strokesForPie(plan) : moveSt(strokesForPie(plan), 0, k);
}
function strokesForPie(plan) {
  const font = plan.font === "cursive" ? "cursive" : "print", cur = font === "cursive";
  let lines = splitLines((plan.text || "").trim());
  const T = (s, w, h, dy) => moveSt(textStrokes(s, w, h, font), dy, 1);
  if (plan.shape === "text" || !SHAPES.shapes[plan.shape]) {
    if (!lines.length) lines = ["Happy"];
    if (lines.length === 1) return textStrokes(lines[0], 80, cur ? 30 : 24, font);
    const h = cur ? 18 : 15; return T(lines[0], 72, h, 13).concat(T(lines[1], 72, h, -13));
  }
  const art = SHAPES.shapes[plan.shape];
  if (lines.length === 1) return moveSt(art, 12, 0.65).concat(T(lines[0], 50, cur ? 13 : 10, -28));
  if (lines.length === 2) { const h = cur ? 11 : 9; return moveSt(art, 18, 0.5).concat(T(lines[0], 60, h, -12), T(lines[1], 52, h, -29)); }
  return art;
}
// Understand the common requests locally: shape, name (quoted or a guest's), cursive, brands.
function readWords(said, cur) {
  const c = said.toLowerCase();
  // One picture per pie (simple pipes cleanly): if several are asked for, the last one named wins.
  const PICS = [["cat", /\b(cat|kitty|kitten)s?\b/g], ["dog", /\b(dog|puppy|pup|doggy)s?\b/g], ["heart", /\bhearts?\b/g], ["star", /\bstars?\b/g],
    ["smiley", /\bsmil(ey|e|ing)/g], ["pumpkin", /\bpumpkins?\b(?! pie)/g], ["leaf", /\b(leaf|leaves)\b/g]];
  const hits = PICS.flatMap(([k, re]) => [...c.matchAll(re)].map((m) => [m.index, k])).sort((a, b) => a[0] - b[0]);
  const picks = [...new Set(hits.map((h) => h[1]))];
  const shape0 = hits.length ? hits[hits.length - 1][1] : null;
  const shape = shape0 || (/(only|just) (the )?(name|word|text)/.test(c) ? "text" : cur ? cur.shape : null);
  const font = /cursive|script|handwrit/.test(c) ? "cursive" : /\b(print|block letters)\b/.test(c) ? "print" : cur ? cur.font || "print" : "print";
  const guest = (n) => state.guests.find((g) => g.name.toLowerCase() === n.toLowerCase());
  const quoted = said.match(/["“”]([^"“”]{1,40})["“”]/) || said.match(/(?:^|\s)['‘]([^'‘’]{1,40})['’](?:\s|$|[.,!])/)
    || said.match(/\b(happy thanksgiving|happy turkey day|gobble gobble|happy birthday|thank you|thankful|give thanks|love you)\b/i);
  let text = cur ? cur.text || "" : "";
  if (quoted) text = guest(quoted[1].trim())?.name || quoted[1].trim();
  else { const g = state.guests.find((g) => new RegExp(`\\b${g.name}\\b`, "i").test(said)); if (g) text = g.name; }
  if (/(no|without|drop|remove)\b.*(name|text|word)/.test(c)) text = "";
  const named = state.guests.find((g) => g.name === text);
  const lines = splitLines(text), kept = lines.join(" ");
  const notes = [];
  if (picks.length > 1) notes.push(`One picture per pie keeps the piping clean, so it's the ${shape}.`);
  if (text && kept !== text.split(/\s+/).filter(Boolean).join(" ")) notes.push(`Kept the words short enough to pipe: "${kept}".`);
  const asked = text.split(/\s+/).filter(Boolean).join(" ");
  return { shape: shape || (text ? "text" : "smiley"), font, text: kept, text_asked: kept !== asked ? asked : "", guest: named ? named.name : "", design_note: notes.join(" ") };
}
// Sample only: the Agent API does this on the Pi (design.py "too_detailed"). Things a syringe can't pipe as lines.
const TOO_DETAILED = [[/photo|picture of (my|our|the) |realistic|lifelike|3d\b/, "A photo-real picture needs shading a syringe can't pipe."],
  [/portrait|face of|likeness|selfie/, "A portrait needs fine detail a syringe can't pipe."],
  [/scene|landscape|table with|cornucopia/, "A whole scene is too many small parts for one 6-inch pie."],
  [/logo|feathers|detailed|intricate|lace|mandala|shading/, "That much fine detail blurs together with a few-mm bead."]];
function sampleDetail(said, name) {
  const c = said.toLowerCase(), hit = TOO_DETAILED.find(([rx]) => rx.test(c));
  if (!hit) return { too_detailed: "", simpler: "" };
  const pic = /turkey|feather|harvest|cornucopia/.test(c) ? "pumpkin" : "heart";
  return { too_detailed: hit[1], simpler: name && name.length <= 7 ? `A ${pic} with "${name}"` : `A ${pic}` };
}
function detailFor(plan, strokes) {   // same rules as pumpkinpi/detail.py (no pipe time in the sample)
  const reasons = []; let level = "ok";
  const flag = (l, why) => { reasons.push(why); if (l === "too_much" || level === "ok") level = l; };
  if (plan.too_detailed) flag("too_much", plan.too_detailed);
  if (plan.text_asked) flag("too_much", `"${plan.text_asked}" is too long: only two short lines fit, so it says "${plan.text}".`);
  const n = (strokes || []).length;
  if (n > 60) flag("too_much", `${n} separate lines; each start and stop leaves a dot.`);
  else if (n > 40) flag("busy", `${n} separate lines, so expect a few dots where the tip lifts.`);
  const tip = plan.simpler || (plan.text ? "Try just a shape, or a shape with a short name." : "Try a simpler shape.");
  return { level, reasons, try: level === "ok" ? "" : tip };
}
function samplePlan(said, cur, keepBase) {
  const w = readWords(said, cur), d = { ...w, ...sampleDetail(said, w.text) }, c = said.toLowerCase();
  const keys = [/hershey/.test(c) ? "hersheys" : cur && cur.ingredients.includes(SAMPLE.products.hersheys.ingredient) && !/enjoy life/.test(c) ? "hersheys" : "enjoy", "clover"];
  if (/m\s*&\s*m|\bm and m|\bmms\b|m&amp;m/.test(c) || (cur && cur.ingredients.includes(SAMPLE.products.mms.ingredient) && !/(no|without) m/.test(c))) keys.push("mms");
  // "bake a pumpkin pie ..." -> the whole pie (crust, filling) as store products, then the topping.
  const base = /cookie/.test(c) ? "cookie" : /cupcake/.test(c) ? "cupcake" : /\bcake\b/.test(c) ? "cake" : cur ? cur.base || "pie" : "pie";
  const pie = base === "pie" && (/\bpie\b/.test(c) || !!(cur && cur.pie));
  if (pie) keys.unshift(...SAMPLE.pie.keys);
  const tt = state.toppingType;
  if (tt !== "chocolate") keys.splice(keys.indexOf(keys.find((k) => k === "hersheys" || k === "enjoy")), 1);
  keys.splice(keys.indexOf("clover"), 1);   // melted chips need no cream
  const prods = keys.map((k) => SAMPLE.products[k]);
  // Sample mode has no store label for these, so they stay "check the label" (the Pi looks up real products).
  if (tt === "frosting") prods.unshift({ ingredient: "vanilla frosting (pick a brand)", brand: "", product: "vanilla frosting", probs: {}, diet: {}, sources: [] });
  if (tt === "marshmallow") prods.unshift({ ingredient: "marshmallows (contain gelatin)", brand: "", product: "marshmallows", probs: {}, diet: {}, sources: [] });
  const STEPS = {
    chocolate: ["Topping: melt the chips in 20-second bursts, stirring, until smooth (under 120°F).", "Topping: spoon into the syringe and pipe within about 10-15 minutes."],
    frosting: ["Topping: bring the frosting to room temperature and stir out air bubbles.", "Topping: spoon into the syringe."],
    marshmallow: ["Topping: melt the marshmallows with a few drops of water, 15 seconds at a time.", "Topping: cool about 3 minutes, fill the syringe and pipe right away."],
  };
  const notes = [SAMPLE.plan.allergy_notes];
  if (pie) notes.push("Low sugar for Dad and Mom: the Libby's recipe uses 3/4 cup sugar; many bakers cut it to 1/2 cup. Pillsbury crusts are made with lard (not vegan).");
  if (keys.includes("hersheys")) notes.unshift("Hershey's chips list natural flavor, so PumpkinPi asks you to check the label; Enjoy Life is the nut-free-facility swap.");
  if (keys.includes("mms")) notes.unshift("M&M's Milk Chocolate says \"May contain peanuts\": not for Debbie.");
  const shapeName = { cat: "cat", dog: "dog", heart: "heart", star: "star", smiley: "smiley", pumpkin: "pumpkin", leaf: "leaf", text: "name" }[d.shape];
  return { ...SAMPLE.plan, ...d, ingredients: prods.map((p) => p.ingredient), products: prods,
    topping_type: state.toppingType, pie, base: keepBase || base, makes: base !== "pie" ? `${base[0].toUpperCase()}${base.slice(1)} topping` : "", topping: pie ? `Pumpkin pie + ${TOPS[tt].label.toLowerCase()}` : TOPS[tt].label, sources: pie ? [...SAMPLE.pie.sources, ...(SAMPLE.plan.sources || [])] : SAMPLE.plan.sources,
    recipe: [...(pie ? SAMPLE.pie.recipe : []), ...STEPS[tt], ...(keys.includes("mms") ? ["Topping: press M&M's around the edge after piping."] : [])],
    allergy_notes: notes.join(" "), caption: `${pie ? "A pumpkin pie with a" : "A"} ${TOPS[state.toppingType].short.toLowerCase()} ${shapeName}${d.text ? ` for ${d.text}` : ""}${d.font === "cursive" ? " in cursive" : ""}` };
}

const state = { live: false, everLive: false, guests: DEMO_GUESTS, plan: null, strokes: [], checks: {},
  ready: 0, busy: false, open: null, job: false, photo: null, diets: [], scan: [], guide: null, openWatch: null,
  toppingType: "chocolate", layers: [], addLayer: false, loaded: null, workEnd: 0, tops: TOPS, drip: null };
const topOf = () => state.plan?.topping_type || state.toppingType;

const verdict = (p) => (p >= 0.7 ? "red" : p <= 0.1 ? "green" : "yellow");
const toColor = { found: "red", unsure: "yellow", safe: "green" };
const label = { red: "Allergen", yellow: "Check label", green: "Safe", wait: "Checking" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Printer/stop messages pop up briefly above the Send button (no permanent status line).
let note = "", toastTimer = null;
function log(msg) {
  note = msg; const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 6000);
}

const API = (window.API_BASE && !/^__PORT/.test(window.API_BASE)) ? window.API_BASE.replace(/\/$/, "") : "";
async function api(path, body) {
  const r = await fetch(API + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
    state.live = state.everLive = true; state.guests = s.guests; printer = !!s.printer; state.noCamera = s.camera === false;
    // Server restarted (e.g. after git pull): load the new UI, but never in the middle of piping.
    if (s.boot && state.boot && s.boot !== state.boot && !state.job) return location.reload();
    state.boot = s.boot;
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
const PH = { make: "Ask for a recipe for any diet, then a design to pipe on top", change: "Change the design, e.g. just a heart, no name" };
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
  if (view === "camera") pollRec();
  updateGate();
}

// Live Pi camera preview (MJPEG). Closing the <img> stream lets the Pi stop the camera.
function liveCamera(on) {
  const img = $("camImg");
  if (on && (!state.live || state.noCamera)) {   // no Pi server: show a drawn sample frame so the screen can be tried anywhere
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
  img.src = `${API}/api/camera.mjpg?t=${Date.now()}`;
}
document.querySelector(".tabs").onclick = (e) => { const t = e.target.closest(".tab"); if (t) show(t.dataset.v); };

// ---------- 1. Agent API: prompt -> plan ----------
async function ask() {
  const prompt = (boxMode === "make" ? $("prompt").value : state.prompt || "").trim();
  if (!prompt || state.busy) return;
  const layering = state.addLayer && !!state.plan, before = state.plan, beforeStrokes = state.strokes;
  state.prompt = prompt; state.change = "";
  const prev = { plan: state.plan, strokes: state.strokes, path: state.path, checks: state.checks, ready: state.ready };
  state.busy = true; state.answer = null; state.checks = {}; state.ready = 0; state.open = null; state.plan = null;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Making"></span>';
  show("recipe"); state.strokes = []; drawPreview(); window.Pie3D?.thinking(true);
  renderRecipe(); updateGate();
  try {
    let res;
    if (state.live) res = await apiJson("/api/design", { prompt, diets: state.diets, topping_type: state.toppingType, add_layer: layering });
    else {
      await sleep(1200); await loadSample(); const plan = samplePlan(prompt, null, layering ? before.base : null);
      res = { plan, strokes: strokesFor(plan),
        layers: layering ? [...state.layers, { topping_type: before.topping_type || "chocolate", strokes: beforeStrokes }] : [] };
    }
    if (res.question) { Object.assign(state, prev); showAnswer(res.question); return; }
    state.addLayer = false;
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

// A question ("what does free-range mean?"): cited answer card on the Recipe screen; the design stays.
function showAnswer(q) {
  state.answer = q; window.Pie3D?.thinking(false); drawPreview(); renderRecipe();
}
// Show a design. res.strokes is the path read back from the real G-code (exact), res.path its length/time.
function applyDesign(res) {
  const sameTopping = state.plan && JSON.stringify(state.plan.ingredients) === JSON.stringify(res.plan.ingredients);
  state.answer = res.plan.answer ? { answer: res.plan.answer, sources: res.plan.sources } : null;
  state.plan = res.plan; state.strokes = res.strokes; state.path = res.path || null;
  if (res.layers) state.layers = res.layers;
  if (res.plan.topping_type) state.toppingType = res.plan.topping_type;
  renderDiets(); renderLoad();
  state.scan = res.scan || (state.demo ? state.demo.scan || [] : []);
  if (!sameTopping) { state.guide = null; loadGuide(); }
  if (res.plan.text) state.name = res.plan.text;
  state.detail = res.detail || detailFor(res.plan, res.strokes); state.detailHidden = false;
  window.Pie3D?.thinking(false); drawPreview(); renderAll(); renderDesign();
  if (state.dish) renderDish(state.dish);   // redraw the design inside the dish outline
}
async function checkMissing() {
  const todo = state.plan.ingredients.filter((i) => !state.checks[i]);
  for (const ing of todo) await check(ing);
}

// Allergies and Dietary Restrictions: cited hidden-name lists + where THESE ingredients hide nuts (Agent API, allergy sites only).
async function loadGuide() {
  const plan = state.plan;
  try {
    const g = state.live ? await apiJson("/api/guide", {}) : (await sleep(700), state.demo?.guide || null);
    if (state.plan === plan) { state.guide = g; renderRecipe(); }
  } catch (e) { if (state.plan === plan) { state.guide = { allergens: [], error: e.message }; renderRecipe(); } }
}

// ---------- Design changes: quick buttons (instant) or words ("just a heart, no name", Agent API) ----------
async function revise(said) {
  const change = (said || $("prompt").value).trim();
  if (!change || !state.plan || state.busy || state.job) return;
  state.change = change; state.busy = true;
  $("askBtn").innerHTML = '<span class="spin" aria-label="Updating"></span>'; window.Pie3D?.thinking(true); renderDesign();
  try {
    let res;
    if (state.live) res = await apiJson("/api/revise", { change, diets: state.diets, topping_type: state.toppingType });
    else {  // sample only: understand the common changes locally
      await sleep(900); await loadSample();
      const plan = samplePlan(change, state.plan);
      res = { plan, strokes: strokesFor(plan), layers: state.layers };
    }
    if (res.question) { window.Pie3D?.thinking(false); drawPreview(); $("prompt").value = ""; state.change = ""; syncClear(); showAnswer(res.question); show("recipe"); return; }
    applyDesign(res);
    $("prompt").value = ""; state.change = ""; syncClear();
    await checkMissing();   // only new ingredients need a new check
  } catch (e) { window.Pie3D?.thinking(false); drawPreview(); log(`Couldn't change it: ${e.message}`); }
  state.busy = false; $("askBtn").textContent = boxMode === "make" ? "Make" : "Update"; renderDesign(); updateGate();
}
// Design is just the pie, plus a note when the design is too much for a syringe (pumpkinpi/detail.py).
function renderDesign() {
  const box = $("detailNote"), d = state.detail;
  if (!state.plan || !d || d.level === "ok" || state.detailHidden || state.busy) { box.hidden = true; return; }
  const title = d.level === "too_much" ? "That's too much detail to pipe" : "That's a lot of detail";
  box.className = `toomuch ${d.level}`;
  box.innerHTML = `<b>${title}</b>${d.reasons.map((r) => `<p>${esc(r)}</p>`).join("")}
    ${d.try ? `<p class="try">Try: ${esc(d.try)}</p>` : ""}
    <div class="row">${d.try ? '<button class="btn go sm" id="detailTry" type="button">Try that</button>' : ""}
    <button class="btn ghost sm" id="detailKeep" type="button">Keep mine</button></div>`;
  box.hidden = false;
  $("detailKeep").onclick = () => { state.detailHidden = true; renderDesign(); };
  const t = $("detailTry");
  if (t) t.onclick = () => { setBox("change"); $("prompt").value = d.try.replace(/^Try /, ""); syncClear(); revise(); };
}

function syncClear() { $("clearBtn").hidden = !$("prompt").value; }
$("clearBtn").addEventListener("pointerdown", (e) => e.preventDefault());
$("clearBtn").onclick = () => { $("prompt").value = ""; syncClear(); if ($("kbd").hidden) showKbd(); };

// ---------- 2. Search API + Decider per ingredient ----------
async function check(product) {
  state.checks[product] = { status: "wait" }; renderAll();
  try {
    let res;
    if (state.live) res = await apiJson("/api/check", { product, diets: state.diets });
    else {   // sample: real labels for these exact products (sources in demo.json)
      await sleep(900);
      const p = Object.values(SAMPLE.products).find((x) => x.ingredient === product) || { probs: {}, diet: {}, sources: [] };
      // Same rule as allergen_check.py: "natural flavor" on the label means check the label, never green.
      const v = (prob) => (p.flavor && prob <= 0.1 ? "unsure" : prob >= 0.7 ? "found" : prob <= 0.1 ? "safe" : "unsure");
      res = { label: p.label, relevance: 0.9,
        sources: [{ title: `Open Food Facts: ${p.brand} ${p.product}`, url: p.label?.url }, ...p.sources],
        results: state.guests.flatMap((g) => g.avoid.map((a) => ({ name: g.name, allergen: a, probability: p.probs[a] ?? 0.3, verdict: v(p.probs[a] ?? 0.3) })))
          .concat(state.diets.filter((d) => d in p.diet).map((d) => ({ name: d[0].toUpperCase() + d.slice(1), diet: d, allergen: d, probability: p.diet[d], verdict: v(p.diet[d]) }))) };
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
  $("diets").innerHTML = `<span class="seg" role="radiogroup" aria-label="Pipe with">${Object.entries(state.tops).map(([k, t]) =>
    `<button type="button" role="radio" class="segb ${state.toppingType === k ? "on" : ""}" data-t="${k}" aria-checked="${state.toppingType === k}">${t.short || TOPS[k].short}</button>`).join("")}</span>` +
    `<span class="chip on lock" title="${esc(avoid.join(", "))}">Allergy-safe</span>` +
    DIETS.map(([k, t]) => `<button type="button" class="chip ${state.diets.includes(k) ? "on" : ""}" data-d="${k}" aria-pressed="${state.diets.includes(k)}">${t}</button>`).join("");
}
$("diets").onclick = (e) => {
  const t = e.target.closest("[data-t]");
  if (t && !state.busy && !state.job) {
    if (t.dataset.t === state.toppingType) return;
    state.toppingType = t.dataset.t; renderDiets(); renderLoad();
    // Same design, different topping: the recipe changes (and gets re-checked), the path settings change.
    if (state.plan && !state.addLayer && state.plan.base !== "none") revise(`Pipe it with ${state.tops[t.dataset.t].label.toLowerCase()} instead.`);
    return;
  }
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

// Cited answer for a food question (labels, safety, how-to). Sources are the Agent API's own search results.
function answerCard(q) {
  if (!q || !q.answer) return "";
  const src = (q.sources || []).slice(0, 5).map((x, i) =>
    `<a class="src" href="${esc(x.url)}" target="_blank" rel="noopener">${favicon(x.url)}<span class="num">${i + 1}</span>${esc(host(x.url))}</a>`).join("");
  return `<div class="answer"><p>${esc(q.answer)}</p>${src ? `<div class="asrc">${src}</div>` : ""}</div>`;
}

function renderRecipe() {
  renderDiets();
  const p = state.plan;
  if (!p && state.answer && !state.busy) {   // just a question, no design yet
    const q = state.answer;
    $("ingCol").innerHTML = `<h3>Answer</h3>${answerCard(q)}`;
    $("stepCol").innerHTML = (q.recipe || []).length ? `<h3>Steps</h3><ol class="steps">${q.recipe.map((t, i) => `<li><span class="sico">${stepIcon(t)}<i>${i + 1}</i></span><span>${esc(t)}</span></li>`).join("")}</ol>` : "";
    $("srcCol").innerHTML = ""; return;
  }
  if (!p) {
    $("ingCol").innerHTML = state.busy ? `<p class="msg"><img class="think" src="brand/perplexity-symbol-ink.svg" alt=""> Perplexity is writing the recipe…</p>`
      : "";
    $("stepCol").innerHTML = ""; $("srcCol").innerHTML = ""; return;
  }
  const rows = p.ingredients.map((ing) => {
    const c = state.checks[ing] || { status: "wait" };
    const open = state.open === ing;
    const prod = (p.products || []).find((x) => x.ingredient === ing) || {};
    const lab = c.label || prod.label || null;
    const title = prod.brand ? `${prod.brand} ${prod.product}` : ing;
    const sub = [prod.size, prod.store].filter(Boolean).join(" · ");
    let detail = "";
    if (open && c.results) {
      const printed = lab ? `<div class="dlabel"><b>Label</b> Contains: ${esc((lab.allergens || []).join(", ") || "none listed")}.
        May contain: ${esc((lab.traces || []).join(", ") || "none listed")}.${lab.note ? ` ${esc(lab.note)}.` : ""}
        ${lab.ingredients ? `<span class="muted">Ingredients: ${esc(lab.ingredients)}</span>` : ""}</div>` : "";
      detail = `<div class="detail">${printed}${c.results.map((r) => `<div class="drow"><span class="pill sm ${r.color}">${label[r.color]}</span>${esc(r.name)}${r.diet ? "" : ` · ${esc(r.allergen)}`}<span class="prob">${Math.round(r.probability * 100)}%</span></div>${r.note ? `<div class="rnote">${esc(r.note)}</div>` : ""}`).join("") || `<div>No guest avoids an allergen for this.</div>`}
        ${p.allergy_notes ? `<div class="dnote">${esc(p.allergy_notes)}</div>` : ""}
        ${c.error ? `<div>Check failed: ${esc(c.error)}</div>` : ""}</div>`;
    }
    const st = c.status === "wait" ? '<span class="spin sm"></span>' : STATUS_ICON[c.status];
    const pic = lab && lab.image ? `<img src="${esc(lab.image)}" alt="${esc(title)} package" loading="lazy" onerror="this.parentNode.classList.remove('photo');this.parentNode.innerHTML=JAR">` : ingArt(ing);
    return `<button type="button" class="ing ${open ? "open" : ""}" data-ing="${esc(ing)}">
      <span class="art ${lab && lab.image ? "photo" : ""}">${pic}</span>
      <span class="who">${esc(title)}${sub ? `<span class="psub">${esc(sub)}</span>` : ""}<span class="tag ${c.status}">${c.status === "wait" ? "Checking" : esc(c.tag || label[c.status])}</span></span>
      <span class="sicon ${c.status}">${st}</span></button>${detail}`;
  }).join("");
  const dnote = p.design_note ? `<p class="dnote2">${esc(p.design_note)}</p>` : "";
  $("ingCol").innerHTML = `${state.answer ? answerCard(state.answer) : ""}<div class="hero"><span class="bowl" style="--c:${swatch((p.topping || "").toLowerCase())}"></span>
      <span><b>${esc(p.makes || p.topping || "Topping")}</b><span class="muted">${p.ingredients.length} ingredients · ${(p.recipe || []).length} steps</span></span></div>${dnote}${rows}`;
  const steps = (p.recipe || []).map((t, i) => `<li><span class="sico">${stepIcon(t)}<i>${i + 1}</i></span><span>${esc(t)}</span></li>`).join("");
  $("stepCol").innerHTML = `<h3>Steps</h3><ol class="steps">${steps}</ol>
    ${p.diet_notes ? `<p class="tip"><b>Diet</b> ${esc(p.diet_notes)}</p>` : ""}
    <h3 class="srch">Sources</h3>${renderSources(p)}
    <p class="muted small by"><img src="brand/perplexity-symbol-ink.svg" alt=""> Perplexity search + Decider${state.live ? "" : " · sample"}</p>`;
  $("srcCol").innerHTML = renderWatch();
}

// ---------- allergy watch ----------
const ALLERGEN_ART = {
  "tree nuts": `<svg viewBox="0 0 48 48"><path d="M10 20c0-6 6-10 14-10s14 4 14 10z" fill="#7a5233"/><path d="M24 10v-4" stroke="#7a5233" stroke-width="3" stroke-linecap="round"/><path d="M12 20h24c0 10-5 18-12 20-7-2-12-10-12-20z" fill="#c8894d"/><path d="M14 23h20" stroke="#a96d36" stroke-width="2"/></svg>`,
  peanuts: `<svg viewBox="0 0 48 48"><path d="M24 6c6 0 9 5 8 10-1 4-3 5-3 8s3 5 3 9c0 6-4 9-8 9s-8-3-8-9c0-4 3-6 3-9s-2-4-3-8c-1-5 2-10 8-10z" fill="#d9a35c" stroke="#a8742f" stroke-width="2"/><path d="M19 14h2M27 16h2M20 33h2M26 35h2" stroke="#a8742f" stroke-width="2" stroke-linecap="round"/></svg>`,
  fish: `<svg viewBox="0 0 48 48"><path d="M6 24c6-9 16-12 26-6l8-6v24l-8-6C22 36 12 33 6 24z" fill="#6aa9c9"/><circle cx="14" cy="22" r="2" fill="#0f2e3d"/></svg>`,
};
const keyFor = (a) => (/peanut/i.test(a) ? "peanuts" : /nut/i.test(a) ? "tree nuts" : /fish/i.test(a) && !/shell/i.test(a) ? "fish" : a);
const WATCH_LABEL = { "tree nuts": "Tree nuts", peanuts: "Peanuts", fish: "Fish" };

function renderWatch() {
  const g = state.guide, scan = state.scan || [];
  const blocks = scan.filter((h) => h.kind === "contains"), checks = scan.filter((h) => h.kind === "check");
  const banner = blocks.length ? `<div class="scan red">${STATUS_ICON.red}<span>The recipe names <b>${esc(blocks[0].term)}</b> (${esc(blocks[0].allergen)}) in ${esc(blocks[0].where)}. Change the design.</span></div>`
    : checks.length ? `<div class="scan yellow">${STATUS_ICON.yellow}<span><b>${esc(checks[0].term)}</b> in ${esc(checks[0].where)}: check the label for ${esc(checks[0].allergen)}.</span></div>` : "";
  if (!g) return `<h3>Allergies and Dietary Restrictions</h3>${banner}<p class="muted small by"><span class="spin sm"></span> Researching where nuts hide in this recipe…</p>`;
  const cards = (g.allergens || []).map((c) => {
    const k = keyFor(c.allergen), open = state.openWatch === c.allergen;
    // Closed: one line + a few hidden names. Open: every risk for this recipe, the cited facts, all names.
    const all = (c.watch || []).map((w) => `<li><b>${esc(w.ingredient)}</b> ${esc(w.risk)}</li>`);
    const lines = (open ? all : all.slice(0, 1)).join("") || (c.facts || []).slice(0, 1).map((f) => `<li>${esc(f)}</li>`).join("");
    const facts = open ? `<ul class="facts">${(c.facts || []).map((f) => `<li>${esc(f)}</li>`).join("")}</ul>${c.tip ? `<p class="wtip">${esc(c.tip)}</p>` : ""}` : "";
    const names = open ? c.names || [] : (c.names || []).slice(0, 4), more = (c.more || 0) + (c.names || []).length - names.length;
    return `<button type="button" class="wcard ${open ? "open" : ""}" data-w="${esc(c.allergen)}">
      <span class="wart">${ALLERGEN_ART[k] || JAR}</span>
      <span class="wbody"><span class="wtitle">${esc(WATCH_LABEL[k] || c.allergen)}<span class="wwho">${esc((c.guests || []).join(" · "))}</span></span>
        <ul class="wlines">${lines}</ul>${facts}
        <span class="names">${names.map((n) => `<i>${esc(n)}</i>`).join("")}${more ? `<i class="more">+${more} more</i>` : ""}</span></span></button>`;
  }).join("");
  return `<h3>Allergies and Dietary Restrictions</h3>${banner}<div class="watch">${cards}</div>`;
}
$("srcCol").onclick = (e) => {
  const b = e.target.closest(".wcard"); if (!b) return;
  state.openWatch = state.openWatch === b.dataset.w ? null : b.dataset.w; renderRecipe();
};

// Sources grouped: the recipe, each allergen (allergy groups + nut searches), then product labels.
function renderSources(p) {
  const seen = new Set(), groups = [];
  const add = (name, list, n) => {
    const items = list.filter(([s]) => s && s.url && !seen.has(s.url) && seen.add(s.url)).slice(0, n);
    if (items.length) groups.push([name, items]);
  };
  const fromChecks = (want) => p.ingredients.flatMap((ing) => ((state.checks[ing] || {}).sources || [])
    .filter((s) => (s.tag || "label") === want).map((s) => [s, ing]));
  add("Recipe", (p.sources || []).filter((s) => !/fda\.gov|foodallergy\.org/.test(s.url || "")).map((s) => [s, ""]), 2);
  for (const c of (state.guide?.allergens || [])) {
    const k = keyFor(c.allergen);
    add(WATCH_LABEL[k] || c.allergen, [...fromChecks(k), ...(c.sources || []).map((s) => [s, ""])], 3);
  }
  add("Product labels", fromChecks("label"), 3);
  return groups.map(([name, items]) => `<p class="sgroup">${esc(name)}</p><ol class="srcs">${items.map(([s, tag]) => `<li class="srcitem">${favicon(s.url)}<span class="st"><b>${esc(s.title || host(s.url))}</b>
    <span class="url">${esc(host(s.url))}${tag ? ` · ${esc(tag)}` : ""}</span></span></li>`).join("")}</ol>`).join("");
}
$("ingCol").onclick = (e) => {
  const b = e.target.closest(".ing"); if (!b) return;
  state.open = state.open === b.dataset.ing ? null : b.dataset.ing; renderRecipe();
};
function renderAll() { renderRecipe(); renderDesign(); }

// ---------- preview ----------
function drawPreview() {
  window.pieStrokes = state.strokes || [];
  window.pieBase = state.plan?.base || "pie";
  $("noPipe").hidden = window.pieBase !== "none";
  window.pieCandy = /m\s*&\s*m/i.test((state.plan?.ingredients || []).join(" "));
  window.pieTopping = topOf(); window.pieLayers = state.layers;
  if (window.Pie3D) { window.Pie3D.setBase?.(window.pieBase, window.pieCandy); window.Pie3D.setLayers?.(state.layers); window.Pie3D.show(window.pieStrokes, window.pieTopping); }
  // 2D fallback (only visible if WebGL is unavailable). SVG y is down; strokes use +Y away from you.
  $("strokes").innerHTML = (state.strokes || []).map((s) =>
    `<polyline points="${s.map(([x, y]) => `${x.toFixed(1)},${(-y).toFixed(1)}`).join(" ")}"/>`).join("");
}

// ---------- gate ----------
function allSafe() {
  if (!state.plan) return false;
  if ((state.scan || []).some((h) => h.kind === "contains")) return false;
  return state.plan.ingredients.every((i) => state.checks[i] && state.checks[i].status === "green");
}
function reason() {
  if (!state.plan) return state.busy ? "Perplexity is designing…" : "Make a design to start.";
  const c = counts();
  const block = (state.scan || []).find((h) => h.kind === "contains");
  if (block) return `Recipe names ${block.term} (${block.allergen})`;
  if (c.wait) return "Checking ingredients…";
  if (c.red || c.yellow) return "An ingredient needs a check";
  if (state.loaded !== topOf()) return `Load the ${state.tops[topOf()].label.toLowerCase()} syringe on Camera`;
  if (state.ready < READY_AT) return document.body.dataset.view === "recipe" ? "All ingredients checked" : "Next: check the pie on Camera";
  return "Ready. Stay next to the printer.";
}
const noun = () => ({ cookie: "Cookie", cake: "Cake", cupcake: "Cupcake" })[state.plan?.base] || "Pie";
// Bottom button follows the flow: Recipe -> Start Designing, Design -> Check the Pie / Send to Printer.
function nextStep() {
  const view = document.body.dataset.view;
  if (state.job) return "stop";
  if (view === "recipe") return "design";
  if (view === "design" && (state.ready < READY_AT || state.loaded !== topOf())) return "camera";
  return "send";
}
function updateGate() {
  const p = !!state.plan && state.plan.base !== "none";
  $("dryBtn").disabled = !p || state.job;
  $("dripBtn").disabled = !!state.job || (state.drip && state.drip.phase !== "done");
  const ok = p && allSafe() && state.ready >= READY_AT && state.loaded === topOf();
  const b = $("sendBtn"), step = nextStep();
  b.classList.toggle("stop", step === "stop");
  if (step === "stop") { b.disabled = false; b.textContent = "Stop"; return; }
  $("sendBtn").title = reason();
  if (step === "design") { b.textContent = "Start Designing"; b.disabled = !p || state.busy; }
  else if (step === "camera") { b.textContent = `Check the ${noun()}`; b.disabled = !p || state.busy; }
  else { b.textContent = "Send to Printer"; b.disabled = !ok || state.busy; }
}

// ---------- Check pie: Decider "ready?" + vision (which dish, where the crust is) ----------
const SAMPLE_DISH = { dish: "pumpkin pie", count: 1, surface: "smooth orange custard", calibrated: false, diameter_mm: 152,
  crust_mm: 10.8, fit_r: 61.2, off_mm: null, warnings: [], edges: { w: 800, h: 600, cx: 399.8, cy: 312.1, r: 205.8, r_in: 176.6, ring: true } };
function renderDish(v) {
  const ov = $("dishOv"), card = $("dishCard");
  state.dish = v || null;
  if (!v) { ov.toggleAttribute("hidden", true); card.hidden = true; return; }
  const e = v.edges;
  if (e) {
    ov.setAttribute("viewBox", `0 0 ${e.w} ${e.h}`); ov.setAttribute("preserveAspectRatio", "xMidYMid slice");
    const ring = e.ring && e.r_in < e.r - 2;
    const ppm = v.fit_r ? e.r_in / (v.fit_r + 4) : 0;   // px per mm (fit_r is 4 mm inside the filling edge)
    const k = state.strokes?.length && ppm ? ppm : 0;
    const path = k ? state.strokes.map((st) => "M" + st.map(([x, y]) => `${(e.cx + x * k).toFixed(1)},${(e.cy - y * k).toFixed(1)}`).join("L")).join("") : "";
    const t = v.target;
    ov.innerHTML = `<circle class="edge" cx="${e.cx}" cy="${e.cy}" r="${e.r}"/>
      ${ring ? `<circle class="fill" cx="${e.cx}" cy="${e.cy}" r="${e.r_in}"/>` : ""}
      ${path ? `<path class="design" d="${path}"/>` : ""}
      ${t ? `<circle class="target" cx="${t.cx}" cy="${t.cy}" r="${e.w / 60}"/><path class="target" d="M${t.cx - e.w / 30},${t.cy}h${e.w / 15}M${t.cx},${t.cy - e.w / 30}v${e.w / 15}"/>` : ""}`;
    ov.toggleAttribute("hidden", false);
  } else ov.toggleAttribute("hidden", true);
  const bits = [v.diameter_mm ? `${v.calibrated ? "" : "~"}${v.diameter_mm} mm` : "",
    v.crust_mm ? `crust ${Math.round(v.crust_mm)} mm` : "", v.fit_r ? `room for ${Math.round(2 * v.fit_r)} mm` : "",
    v.off_mm != null && v.off_mm <= 6 ? "centered" : ""].filter(Boolean).join(" · ");
  const crusted = ["pumpkin pie", "pie", "tart"].includes(v.dish);
  card.innerHTML = `<b>${esc(v.dish === "nothing" ? "Empty bed" : v.dish)}</b><span>${esc(bits)}</span>
    ${crusted && e && state.live ? `<button class="btn" id="centerBtn" type="button">${v.calibrated ? "Re-save center" : "Save as center"}</button>` : ""}
    ${(v.warnings || []).concat(state.fitNote ? [state.fitNote] : []).map((w) => `<span class="warn">${esc(w)}</span>`).join("")}`;
  card.hidden = false;
  const cb = $("centerBtn");
  if (cb) cb.onclick = async () => {
    try { const r = await apiJson("/api/dish/center", {}); if (r.design) applyFit(r.design); renderDish(r.dish); $("camMsg").textContent = "Saved. This spot is now the printer's center."; }
    catch (err) { $("camMsg").textContent = `Save center: ${err.message}`; }
  };
}
function applyFit(design) {   // the camera resized the design: same topping, so checks stay
  state.plan = design.plan; state.strokes = design.strokes; state.path = design.path || state.path;
  const f = design.fit || {};
  state.fitNote = f.small_text ? "The name will be small here. Try just a shape." : "";
  if (design.detail) { state.detail = design.detail; state.detailHidden = false; }
  drawPreview(); renderAll();
}
$("readyBtn").onclick = async () => {
  $("camMsg").innerHTML = '<span class="spin sm"></span> Looking at the dish…';
  renderLabel(null);
  try {
    let v;
    if (state.live) {
      const r = await apiJson("/api/ready", {});
      state.ready = r.probability; v = r.dish;
      if (r.design) applyFit(r.design);
    } else { await sleep(900); state.ready = 0.97; v = SAMPLE_DISH; }
    renderDish(v);
    const what = v && v.dish && !["other", "nothing"].includes(v.dish) ? v.dish[0].toUpperCase() + v.dish.slice(1) : "Dish";
    $("camMsg").textContent = state.ready >= READY_AT ? `${what} looks ready (${Math.round(state.ready * 100)}%).`
      : `Not ready (${Math.round(state.ready * 100)}%). Center it and clear the bed.`;
  } catch (e) { state.ready = 0; renderDish(null); $("camMsg").textContent = `Camera error: ${e.message}`; }
  updateGate();
};

// ---------- Scan label: camera photo -> Agent API reads it -> same Search API + Decider check ----------
function marked(text, hits) {   // highlight the printed words that made a row red or yellow
  let out = esc(text);
  for (const [t, cls] of hits) {
    const rx = new RegExp(`\\b(${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "[\\s-]*")})`, "gi");
    out = out.replace(rx, `<mark class="${cls}">$1</mark>`);
  }
  return out;
}
function renderLabel(res) {
  const sh = $("labelSheet");
  if (!res) { sh.hidden = true; return; }
  const read = res.read || {};
  const rows = res.results.map((r) => {
    const c = toColor[r.verdict] || verdict(r.probability);
    return `<div class="lrow"><span class="pill sm ${c}">${label[c]}</span><b>${esc(r.name)}</b><span>${esc(r.diet || r.allergen)}</span>${r.note ? `<span class="why2">${esc(r.note)}</span>` : ""}</div>`;
  }).join("");
  const hits = res.results.flatMap((r) => { const m = (r.note || "").match(/^label lists ([^:]+)/); return m ? [[m[1], toColor[r.verdict] === "red" ? "" : "y"]] : []; });
  const pic = res.photo ? `<img src="${esc(res.photo)}" alt="Photo of the label">` : "";
  const srcs = (res.sources || []).filter((x) => /^https?:/.test(x.url || "")).slice(0, 4)
    .map((x, i) => `<a class="src" href="${esc(x.url)}" target="_blank" rel="noopener"><span class="num">${i + 1}</span>${esc(host(x.url))}</a>`).join("");
  sh.innerHTML = `<div class="lhead">${pic}<div><h3>${esc(res.title || res.product)}</h3>
      <div class="lfor ${res.ingredient ? "" : "no"}">${res.ingredient ? "Matches your recipe" : "Not in this recipe. Just a check."}</div></div>
      <button class="btn sm" id="labelClose" type="button">Close</button></div>
    <div class="lrows">${rows}</div>
    <p class="ltext"><b>Ingredients:</b> ${marked(read.ingredients || "", hits)}</p>
    ${(read.contains || []).length ? `<p class="ltext"><b>Contains:</b> ${esc(read.contains.join(", "))}</p>` : ""}
    <p class="ltext"><b>May contain:</b> ${read.may_contain ? marked(read.may_contain, [["tree nuts?", ""], ["peanuts?", ""], ["fish", ""]]) : "nothing printed"}</p>
    ${read.complete === false ? `<p class="ltext"><b>Partly unreadable:</b> ${esc(read.problem || "rescan closer")}</p>` : ""}
    <div>${srcs}</div>`;
  sh.hidden = false;
  $("labelClose").onclick = () => renderLabel(null);
}
$("labelBtn").onclick = async () => {
  $("labelBtn").disabled = true; renderLabel(null);
  $("camMsg").innerHTML = '<span class="spin sm"></span> Reading the label…';
  try {
    let res;
    if (state.live) { res = await apiJson("/api/label", { diets: state.diets }); res.photo = res.label?.image; }
    else {   // sample: the Enjoy Life bag, read from its real label
      await sleep(1200);
      const p = SAMPLE.products.enjoy;
      const ing = state.plan?.ingredients.includes(p.ingredient) ? p.ingredient : null;
      res = { product: p.ingredient, title: `${p.brand} ${p.product} ${p.size}`, ingredient: ing, photo: p.label.image,
        read: { ingredients: p.label.ingredients, contains: [], may_contain: "", complete: true },
        sources: p.sources, results: state.guests.flatMap((g) => g.avoid.map((a) => ({ name: g.name, allergen: a, probability: p.probs[a] ?? 0.3, verdict: (p.probs[a] ?? 0.3) <= 0.1 ? "safe" : "unsure" }))) };
    }
    res.results.forEach((r) => (r.color = r.verdict ? toColor[r.verdict] : verdict(r.probability)));
    const worst = res.results.some((r) => r.color === "red") ? "red" : res.results.some((r) => r.color === "yellow") ? "yellow" : "green";
    if (res.ingredient) { state.checks[res.ingredient] = { status: worst, ...res }; renderAll(); }
    renderLabel(res);
    $("camMsg").textContent = worst === "green" ? "Label checked: safe for everyone." : worst === "red" ? "Label lists an allergen." : "Check the label: see notes.";
  } catch (e) { $("camMsg").textContent = `Label scan: ${e.message}`; }
  $("labelBtn").disabled = false; updateGate();
};

// ---------- Timelapse: Record button + automatic recording while piping ----------
let recTimer = null, recSample = 0;
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
async function pollRec() {
  clearTimeout(recTimer);
  let st;
  if (state.live) { try { st = await apiJson("/api/record"); } catch { return; } }
  else st = { recording: !!recSample, seconds: recSample ? Math.round((Date.now() - recSample) / 1000) : 0, clips: [] };
  $("recTag").hidden = !st.recording; $("recTag").textContent = `REC ${mmss(st.seconds)}`;
  $("recBtn").textContent = st.recording ? "Stop recording" : st.saving ? "Saving clip…" : "Record";
  $("recBtn").classList.toggle("on", st.recording); $("recBtn").disabled = !!st.saving;
  state.clips = st.clips || []; state.lastClip = st.last;
  $("clipBtn").hidden = !state.clips.length;
  if (st.error && !st.recording && state.recWas) $("camMsg").textContent = st.error;
  else if (state.recWas && !st.recording && !st.saving && st.last) $("camMsg").textContent = `Saved a ${st.last.seconds} s timelapse.`;
  state.recWas = st.recording || st.saving;
  if (st.recording || st.saving || state.job) recTimer = setTimeout(pollRec, 1000);
}
$("recBtn").onclick = async () => {
  const on = !$("recBtn").classList.contains("on");
  if (!state.live) { recSample = on ? Date.now() : 0; if (!on) $("camMsg").textContent = "Sample: recordings are saved on the Pi."; return pollRec(); }
  try { await apiJson("/api/record", { on }); state.recWas = true; } catch (e) { $("camMsg").textContent = `Record: ${e.message}`; }
  pollRec();
};
$("clipBtn").onclick = () => {
  const name = state.clips[0]; if (!name) return;
  renderLabel(null);
  $("clipVid").src = `/api/clips/${encodeURIComponent(name)}`;
  $("clipInfo").textContent = `${name}  ·  on the Pi in captures/timelapse/`;
  $("clipSheet").hidden = false; $("clipVid").play().catch(() => {});
};
$("clipClose").onclick = () => { $("clipVid").pause(); $("clipVid").removeAttribute("src"); $("clipSheet").hidden = true; };

async function start(dry_run) {
  if (!state.live) {
    log(dry_run ? "Sample: dry run would trace the path 15 mm above the pie." : "Sample: piped.");
    if (!dry_run) piped();
    return;
  }
  try {
    const r = await apiJson("/api/start", { dry_run });
    state.job = true; updateGate(); pollRec();
    $("jobFill").style.width = "0%"; $("jobMeter").classList.add("on");
    log(`Making G-code (${r.lines} moves)…`);
    const what = dry_run ? "Dry run" : "Piping";
    for (let i = 0; i < 7200; i++) {
      await sleep(500);
      const j = await apiJson("/api/job");
      $("jobFill").style.width = `${j.pct ?? Math.round((100 * j.done) / Math.max(1, j.total))}%`;
      if (j.phase === "upload") log(`Saving ${j.file} to the printer's SD card…`);
      else if (j.phase === "printing") log(`${what} ${j.file} from the SD card. Stay next to the printer.`);
      else if (j.phase === "streaming") log(`${what} over USB (no SD card). Stay next to the printer.`);
      if (!j.running) {
        log(j.error ? `Stopped: ${j.error}` : `${what} done${j.file ? ` (${j.file})` : ""}.`);
        if (!dry_run && !j.error) piped();
        break;
      }
    }
  } catch (e) { log(`Send refused: ${e.message}`); }
  state.job = false; updateGate();
  setTimeout(() => { if (!state.job) $("jobMeter").classList.remove("on"); }, 2000);
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


// ---------- syringes: one per topping, swapped by hand between layers ----------
async function loadToppings() {
  if (!state.live) return;
  try { const t = await apiJson("/api/toppings"); for (const k in t) state.tops[k] = { ...TOPS[k], ...t[k] }; renderLoad(); } catch {}
}
const setLine = (k) => { const v = state.tops[k].settings; return `Pause ${(+v.dwell).toFixed(1)} s · pull-back ${(+v.retract).toFixed(1)}`; };
function renderLoad() {
  const k = topOf(), t = state.tops[k], box = $("load");
  if (!box) return;
  const ok = state.loaded === k, left = Math.max(0, (state.workEnd - Date.now()) / 1000);
  box.className = `load ${ok ? "ok" : ""}`;
  box.innerHTML = ok
    ? `<b>${esc(t.label)} loaded</b><span>${esc(setLine(k))}</span>${state.workEnd ? `<span class="${left < 120 ? "warn" : ""}">${left > 0 ? `Pipe within ${mmss(left)}` : "May be too thick now. Rewarm it."}</span>` : ""}`
    : `<b>${state.loaded ? "Swap syringe" : "Load syringe"}: ${esc(t.label)}</b><span>${esc(t.tip)}. ${esc(t.prep)}</span><button class="btn" type="button" id="loadedBtn">Loaded</button>`;
  $("dripSet").textContent = `${t.short || TOPS[k].short}: ${setLine(k)}`;
}
$("load").onclick = (e) => {
  if (!e.target.closest("#loadedBtn")) return;
  const k = topOf();
  state.loaded = k; state.workEnd = state.tops[k].work_min ? Date.now() + state.tops[k].work_min * 60000 : 0;
  renderLoad(); updateGate();
};
setInterval(() => { if (state.workEnd && document.body.dataset.view === "camera") renderLoad(); }, 1000);

// After a topping is piped: offer the next one on the same food (chocolate first, then frosting, ...).
function piped() {
  const done = topOf(), box = $("more");
  box.hidden = false; box.parentElement.scrollTop = 0;
  box.innerHTML = `<b>${esc(state.tops[done].short || TOPS[done].short)} done.</b> Add another topping?<span class="morebtns">${Object.keys(state.tops).filter((k) => k !== done)
    .map((k) => `<button class="btn" type="button" data-more="${k}">${esc(state.tops[k].short || TOPS[k].short)}</button>`).join("")}</span>`;
}
$("more").onclick = (e) => {
  const b = e.target.closest("[data-more]"); if (!b) return;
  state.addLayer = true; state.toppingType = b.dataset.more; $("more").hidden = true;
  renderDiets(); show("recipe");
  const el = $("prompt"); el.value = ""; state.prompt = "";
  el.placeholder = `What should the ${state.tops[b.dataset.more].label.toLowerCase()} add? e.g. Debbie in cursive`;
  syncClear(); el.focus();
};

// ---------- drip test: pipe one line, pull back with no pause, time how long it keeps oozing ----------
let dripTick = null;
function drawDrip() {
  const d = state.drip, box = $("dripBox");
  box.hidden = !d;
  if (!d) return;
  const k = d.topping_type, name = state.tops[k].label.toLowerCase();
  if (d.phase === "ask") box.innerHTML = `<span>Put a plate with parchment where the food goes. It pipes one 4 cm line of ${esc(name)}.</span><button class="btn" type="button" data-drip="go">Start drip test</button><button class="btn ghost" type="button" data-drip="cancel">Cancel</button>`;
  else if (d.phase === "piping") box.innerHTML = `<span><span class="spin sm"></span> Piping the test line…</span>`;
  else if (d.phase === "watching") box.innerHTML = `<span>Watch the tip. Tap when it stops dripping.</span><b class="clock" id="dripClock">${(d.secs || 0).toFixed(1)} s</b><button class="btn go" type="button" data-drip="stop">Drip stopped</button>`;
  else if (d.phase === "result") box.innerHTML = `<span>Oozed for <b>${d.seconds.toFixed(1)} s</b>. Suggested: pause ${d.suggest.dwell.toFixed(1)} s after each line${d.suggest.retract ? `, pull-back ${d.suggest.retract.toFixed(1)}` : ""}.</span><button class="btn go" type="button" data-drip="save">Save for ${esc(state.tops[k].short || TOPS[k].short)}</button><button class="btn ghost" type="button" data-drip="cancel">Don't save</button>`;
  else if (d.phase === "error") box.innerHTML = `<span>Drip test stopped: ${esc(d.error)}</span><button class="btn ghost" type="button" data-drip="cancel">OK</button>`;
}
function watch(t0) {
  clearInterval(dripTick);
  dripTick = setInterval(() => { state.drip.secs = (Date.now() - t0) / 1000; const c = $("dripClock"); if (c) c.textContent = `${state.drip.secs.toFixed(1)} s`; }, 100);
}
$("dripBtn").onclick = () => { state.drip = { topping_type: topOf(), phase: "ask" }; drawDrip(); updateGate(); };
$("dripBox").onclick = async (e) => {
  const a = e.target.closest("[data-drip]")?.dataset.drip, d = state.drip; if (!a) return;
  try {
    if (a === "cancel") { clearInterval(dripTick); state.drip = null; }
    else if (a === "go") {
      d.phase = "piping"; drawDrip();
      if (!state.live) { await sleep(2500); d.phase = "watching"; watch(Date.now()); }
      else {
        await apiJson("/api/drip-test", { topping_type: d.topping_type }); state.job = true; updateGate();
        for (;;) {
          await sleep(300);
          const s = await apiJson("/api/drip-test");
          if (s.phase === "watching") { d.phase = "watching"; watch(Date.now() - (s.now - s.t_end) * 1000); break; }
          if (s.phase === "error") { d.phase = "error"; d.error = s.error; break; }
        }
        state.job = false;
      }
    } else if (a === "stop") {
      clearInterval(dripTick);
      const secs = (state.drip.secs || 0);
      const r = state.live ? await apiJson("/api/drip-test/result", { topping_type: d.topping_type, seconds: secs })
        : { seconds: secs, suggest: { dwell: Math.min(8, secs + 0.3), ...(secs > 3 ? { retract: state.tops[d.topping_type].settings.retract + 0.2 } : {}) } };
      Object.assign(d, { phase: "result", seconds: r.seconds, suggest: r.suggest });
    } else if (a === "save") {
      const vals = { dwell: d.suggest.dwell, ...(d.suggest.retract ? { retract: d.suggest.retract } : {}) };
      if (state.live) await apiJson("/api/toppings", { topping_type: d.topping_type, values: vals });
      Object.assign(state.tops[d.topping_type].settings, vals);
      log(`Saved for ${state.tops[d.topping_type].label.toLowerCase()}: ${setLine(d.topping_type)}.`);
      state.drip = null; renderLoad();
    }
  } catch (err) { state.job = false; Object.assign(d, { phase: "error", error: err.message }); }
  drawDrip(); updateGate();
};

async function init() {
  await refreshStatus();
  await loadToppings(); renderLoad();
  renderRecipe(); renderDesign();
  updateGate();
}
init();
