// 3D pumpkin pie preview (three.js, bundled locally so it works offline on the Pi).
// Starts at a side angle, orbits up to the top view, then "pipes" the design on.
// Units are mm. Strokes use +Y away from you; world is x right, y up, -z away.
import * as THREE from "./vendor/three.module.min.js";

const canvas = document.getElementById("pie3d");
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
} catch (e) {
  console.warn("WebGL unavailable, using 2D preview", e);
}

if (renderer) {
  document.body.classList.add("webgl");
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.setClearColor(0xfcfaf6, 1);  // match the page background exactly
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 2000);

  // ---- lights ----
  scene.add(new THREE.HemisphereLight(0xfff1e0, 0x0b1a1c, 1.1));
  const key = new THREE.DirectionalLight(0xffe2c0, 2.6);
  key.position.set(90, 200, 110);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  Object.assign(key.shadow.camera, { left: -90, right: 90, top: 90, bottom: -90, near: 10, far: 500 });
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x20b8cd, 0.9); // Perplexity teal rim light
  rim.position.set(-120, 60, -140);
  scene.add(rim);

  // ---- textures (procedural, no image files) ----
  function canvasTex(size, draw) {
    const c = document.createElement("canvas"); c.width = c.height = size;
    draw(c.getContext("2d"), size);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return t;
  }
  const rand = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();
  const fillingTex = canvasTex(512, (g, n) => {
    const grd = g.createRadialGradient(n / 2, n / 2, n * 0.05, n / 2, n / 2, n / 2);
    grd.addColorStop(0, "#d9852f"); grd.addColorStop(0.8, "#cf7426"); grd.addColorStop(1, "#a9561a");
    g.fillStyle = grd; g.fillRect(0, 0, n, n);
    for (let i = 0; i < 2600; i++) {           // spice speckle + soft mottling
      const x = rand() * n, y = rand() * n, r = rand() * 1.6 + 0.3;
      g.fillStyle = rand() < 0.5 ? "rgba(110,50,15,.16)" : "rgba(255,190,120,.10)";
      g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
    }
  });
  const crustTex = canvasTex(256, (g, n) => {
    g.fillStyle = "#d39a5a"; g.fillRect(0, 0, n, n);
    for (let i = 0; i < 1800; i++) {
      const x = rand() * n, y = rand() * n, r = rand() * 2.2 + 0.4;
      g.fillStyle = rand() < 0.55 ? "rgba(140,75,25,.20)" : "rgba(255,230,180,.16)";
      g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
    }
  });
  crustTex.wrapS = crustTex.wrapT = THREE.RepeatWrapping; crustTex.repeat.set(6, 1);

  const crustMat = new THREE.MeshStandardMaterial({ map: crustTex, roughness: 0.82, color: 0xffffff });
  const fillingMat = new THREE.MeshStandardMaterial({ map: fillingTex, roughness: 0.42, metalness: 0 });
  // Ganache: very dark brown, satin (not mirror) sheen, fine surface bumps so highlights break up.
  const ganacheBump = canvasTex(256, (g, n) => {
    g.fillStyle = "#808080"; g.fillRect(0, 0, n, n);
    for (let i = 0; i < 1400; i++) {
      const x = rand() * n, y = rand() * n, r = rand() * 6 + 2, c = 90 + rand() * 80 | 0;
      const grd = g.createRadialGradient(x, y, 0, x, y, r);
      grd.addColorStop(0, `rgba(${c},${c},${c},.55)`); grd.addColorStop(1, "rgba(128,128,128,0)");
      g.fillStyle = grd; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
    }
  });
  ganacheBump.colorSpace = THREE.NoColorSpace;
  ganacheBump.wrapS = ganacheBump.wrapT = THREE.RepeatWrapping; ganacheBump.repeat.set(14, 1);
  const ganacheMat = new THREE.MeshPhysicalMaterial({
    color: 0x2a140a, roughness: 0.5, metalness: 0, bumpMap: ganacheBump, bumpScale: 0.6,
    clearcoat: 0.35, clearcoatRoughness: 0.55, sheen: 0.4, sheenColor: new THREE.Color(0x6b3a20), sheenRoughness: 0.6,
  });

  const pie = new THREE.Group();
  scene.add(pie);

  // ---- crust shell: tapered pie-tin profile, lathed ----
  const R_TOP = 56, R_BOT = 45, H = 17, T = 3;
  const prof = [
    [0, 0], [R_BOT, 0], [R_BOT + 2, 0.6], [R_TOP, H - 2],                 // outside
    [R_TOP - T, H - 2], [R_BOT - 1, T], [0, T],                            // inside
  ].map(([r, y]) => new THREE.Vector2(r, y));
  const shell = new THREE.Mesh(new THREE.LatheGeometry(prof, 160), crustMat);
  shell.castShadow = shell.receiveShadow = true;
  pie.add(shell);

  // ---- filling: slightly domed disc ----
  const FILL_Y = H - 3.2, R_FILL = R_TOP - 4;
  const fillGeo = new THREE.CircleGeometry(R_FILL, 128);
  fillGeo.rotateX(-Math.PI / 2);
  const pos = fillGeo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const r = Math.hypot(pos.getX(i), pos.getZ(i));
    pos.setY(i, 0.9 * (1 - (r / R_FILL) ** 2));
  }
  fillGeo.computeVertexNormals();
  const filling = new THREE.Mesh(fillGeo, fillingMat);
  filling.position.y = FILL_Y; filling.receiveShadow = true;
  pie.add(filling);

  // ---- fluted crimped rim: torus with scalloped radius ----
  const RIM_R = R_TOP - 2.2, CRIMPS = 22;
  const rimGeo = new THREE.TorusGeometry(RIM_R, 3.6, 20, 440);
  rimGeo.rotateX(Math.PI / 2);
  const rp = rimGeo.attributes.position, v = new THREE.Vector3();
  for (let i = 0; i < rp.count; i++) {
    v.fromBufferAttribute(rp, i);
    const a = Math.atan2(v.z, v.x), flute = Math.cos(a * CRIMPS);
    // Shift the whole tube in and out (rounded scallops, not spikes) and lift each crimp a little.
    const dr = 1.6 * flute;
    v.x += Math.cos(a) * dr; v.z += Math.sin(a) * dr; v.y = v.y * (1 + 0.18 * flute) + 0.5 * flute;
    rp.setXYZ(i, v.x, v.y, v.z);
  }
  rimGeo.computeVertexNormals();
  const rimMesh = new THREE.Mesh(rimGeo, crustMat);
  rimMesh.position.y = H - 1.2; rimMesh.castShadow = rimMesh.receiveShadow = true;
  pie.add(rimMesh);

  // ---- soft contact shadow on the "table" ----
  const shadowTex = canvasTex(256, (g, n) => {
    // light page: keep the shadow tight and soft so the canvas edge never shows
    const grd = g.createRadialGradient(n / 2, n / 2, 0, n / 2, n / 2, n / 2);
    grd.addColorStop(0, "rgba(40,30,20,.34)"); grd.addColorStop(0.66, "rgba(40,30,20,.26)"); grd.addColorStop(1, "rgba(40,30,20,0)");
    g.fillStyle = grd; g.fillRect(0, 0, n, n);
  });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(140, 140),
    new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.2;
  scene.add(floor);

  // ---- piped strokes as tubes ----
  const strokeGroup = new THREE.Group();
  pie.add(strokeGroup);
  let tubes = [];   // {mesh, count}
  // A piped line is not a perfect tube: it settles (wider than tall), its width wobbles with hand/
  // plunger pressure, and each line starts and ends in a soft blob.
  const RAD = 1.55, RADIAL = 14, FLAT = 0.58;
  function surfaceY(x, y) { const r = Math.hypot(x, y); return FILL_Y + 0.9 * (1 - (r / R_FILL) ** 2); }
  function ganacheGeo(curve, len, seed) {
    const segs = Math.max(10, Math.ceil(len * 2));
    const geo = new THREE.TubeGeometry(curve, segs, RAD, RADIAL, false);
    const p = geo.attributes.position, c = new THREE.Vector3(), d = new THREE.Vector3();
    const ph1 = seed * 1.7, ph2 = seed * 3.1;
    for (let i = 0; i <= segs; i++) {
      const u = i / segs, s = u * len;
      curve.getPointAt(u, c);
      const wobble = 1 + 0.09 * Math.sin(s * 0.55 + ph1) + 0.05 * Math.sin(s * 1.9 + ph2);
      const endSwell = 1 + 0.22 * Math.exp(-((s / 2.2) ** 2)) + 0.14 * Math.exp(-(((len - s) / 2.2) ** 2));
      const k = wobble * endSwell;
      for (let j = 0; j <= RADIAL; j++) {
        const idx = i * (RADIAL + 1) + j;
        d.fromBufferAttribute(p, idx).sub(c);
        d.x *= k; d.z *= k; d.y = d.y * k * FLAT;
        if (d.y < 0) d.y *= 0.35;                       // flat bottom where it meets the filling
        p.setXYZ(idx, c.x + d.x, c.y + d.y, c.z + d.z);
      }
    }
    geo.computeVertexNormals();
    return { geo, segs };
  }
  function blob(at, r) {   // rounded dollop to close each end of a line
    const g = new THREE.SphereGeometry(r, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2);
    const m = new THREE.Mesh(g, ganacheMat);
    m.scale.set(1, FLAT * 1.05, 1); m.position.copy(at); m.position.y -= 0.05;
    m.castShadow = true; m.visible = false; strokeGroup.add(m);
    return m;
  }
  function setStrokes(strokes) {
    for (const t of tubes) { for (const m of [t.mesh, t.a, t.b]) { m.geometry.dispose(); strokeGroup.remove(m); } }
    tubes = [];
    (strokes || []).forEach((s, n) => {
      if (s.length < 2) return;
      const pts = s.map(([x, y]) => new THREE.Vector3(x, surfaceY(x, y) + RAD * FLAT * 0.35, -y));
      const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal", 0.5);
      const len = curve.getLength();
      const closed = pts[0].distanceTo(pts[pts.length - 1]) < 0.5;
      const { geo } = ganacheGeo(curve, len, n + 1);
      const mesh = new THREE.Mesh(geo, ganacheMat);
      mesh.castShadow = true; mesh.receiveShadow = true;
      geo.setDrawRange(0, 0);
      strokeGroup.add(mesh);
      const a = blob(pts[0], RAD * (closed ? 1.05 : 1.22)), b = blob(pts[pts.length - 1], RAD * (closed ? 1.05 : 1.14));
      tubes.push({ mesh, a, b, curve, end: pts[pts.length - 1], count: geo.index.count, len });
    });
  }
  function reveal(f) {   // f in 0..1 over total stroke length, in order
    const total = tubes.reduce((a, t) => a + t.len, 0) || 1;
    let left = f * total;
    for (const t of tubes) {
      const take = Math.max(0, Math.min(1, left / t.len)); left -= t.len;
      const per = RADIAL * 6;                                  // indices per tube segment
      const segs = Math.floor((take * t.count) / per) * per;
      t.mesh.geometry.setDrawRange(0, take >= 1 ? t.count : segs);
      t.a.visible = take > 0; t.b.visible = take > 0;
      if (take > 0 && take < 1) { t.curve.getPointAt(take, t.b.position); t.b.position.y -= 0.05; }   // blob follows the tip
      else if (take >= 1) { t.b.position.copy(t.end); t.b.position.y -= 0.05; }
    }
  }

  // ---- camera path: side view -> orbit -> top view ----
  const DIST = 265, SIDE = THREE.MathUtils.degToRad(16), TOP = THREE.MathUtils.degToRad(89.6);
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  let mode = "idle", t0 = performance.now(), az = -0.9, el = SIDE, azFrom = az, elFrom = el;
  const ORBIT_MS = 3600, PIPE_DELAY = 2000, PIPE_MS = 2800;

  function place() {
    camera.position.set(DIST * Math.cos(el) * Math.sin(az), DIST * Math.sin(el) + 6, DIST * Math.cos(el) * Math.cos(az));
    camera.lookAt(0, 6, 0);
  }

  function frame(now) {
    const dt = now - t0;
    if (mode === "idle" || mode === "thinking") {
      az += (mode === "thinking" ? 0.012 : 0.004);
      el += (SIDE - el) * 0.05;
    } else if (mode === "show") {
      const k = ease(Math.min(1, dt / ORBIT_MS));
      az = azFrom + (azTarget - azFrom) * k;
      el = elFrom + (TOP - elFrom) * k;
      reveal(Math.max(0, Math.min(1, (dt - PIPE_DELAY) / PIPE_MS)));
      if (dt > PIPE_DELAY + PIPE_MS && dt > ORBIT_MS) { reveal(1); mode = "done"; }
    }
    // Only draw while visible and while something is moving (keeps the Pi cool).
    if (canvas.offsetParent !== null && (mode !== "done" || dirty)) {
      place(); renderer.render(scene, camera); dirty = false;
    }
    requestAnimationFrame(frame);
  }
  let azTarget = 0, dirty = true;

  function resize() {
    const box = canvas.parentElement.getBoundingClientRect();
    const s = Math.max(10, Math.min(box.width, box.height));
    renderer.setSize(s, s, true); dirty = true;
    camera.aspect = 1; camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(canvas.parentElement);

  window.Pie3D = {
    show(strokes) {
      setStrokes(strokes);
      if (!strokes || !strokes.length) { mode = "idle"; return; }
      // Always come in from the side, then orbit forward to the top view (camera ends on +z, so +Y reads "up").
      azFrom = az; elFrom = el;
      azTarget = Math.ceil((az + 2.4) / (2 * Math.PI)) * 2 * Math.PI;
      mode = "show"; t0 = performance.now();
    },
    thinking(on) { if (on) setStrokes([]); mode = on ? "thinking" : "idle"; },
    replay() { el = SIDE; this.show(window.pieStrokes); },
    resize,
    seek(ms) {   // for screenshots/tests: jump to a point in the side -> top animation
      if (!tubes.length) return;
      azFrom = azTarget - 2.4 - Math.PI; elFrom = SIDE; mode = "show"; t0 = performance.now() - ms; dirty = true;
    },   // for screenshots/tests
  };
  resize();
  requestAnimationFrame(frame);
  if (window.pieStrokes && window.pieStrokes.length) window.Pie3D.show(window.pieStrokes);
  canvas.addEventListener("click", () => window.Pie3D.replay());   // tap the pie to replay
}
