"""What's on the bed, and where its crust is, from one camera photo.

  identify()    Agent API reads the photo: pumpkin pie, cookie, cupcake... (image input,
                https://docs.perplexity.ai/docs/agent-api/image-attachments)
  find_edges()  OpenCV on the Pi finds the round outer edge (Hough circle, or the biggest blob if
                that fails), then walks outward from the center until the color changes: that is
                where the filling stops and the crust starts. https://docs.opencv.org/4.x/da/d53/tutorial_py_houghcircles.html
  inspect()     both, plus sizes in mm and how far the dish sits from the printer's center.

Sizes: after a one-time "Save as center" (camera_cal.json) we know pixels per mm and the pixel where
the printer's pie_x/pie_y lands. Before that, the filling ratio times the pie size in machine.json
(pie_mm) still sizes the design. Vision only ever shrinks the design to fit and warns about
centering; it never moves the printer, never homes, and the toolpath bounds checks still apply.
The camera must be fixed above the bed (not on the moving head), and photos taken with the bed parked
where it was during calibration.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path

from . import pplx

ROOT = Path(__file__).resolve().parent.parent
CAL_FILE = Path(os.environ.get("PUMPKINPI_CAMERA_CAL", ROOT / "camera_cal.json"))
DISHES = ("pumpkin pie", "pie", "tart", "cookie", "cupcake", "cake", "brownie", "other", "nothing")
CRUSTED = {"pumpkin pie", "pie", "tart"}
TYPICAL_MM = {"cookie": 75.0, "cupcake": 70.0}   # only used before calibration, when the pie size doesn't apply
MARGIN_MM = 4.0          # stay this far inside the filling (or the cookie edge)
OFF_CENTER_MM = 6.0      # warn past this

SCHEMA = {
    "type": "object",
    "properties": {
        "dish": {"type": "string", "enum": list(DISHES)},
        "count": {"type": "integer", "description": "How many separate food items are on the bed"},
        "round": {"type": "boolean"},
        "surface": {"type": "string", "description": "A few words: e.g. smooth orange custard, cracked top, frosted"},
        "confidence": {"type": "number", "description": "0-1"},
    },
    "required": ["dish", "count", "round", "surface", "confidence"],
}
INSTRUCTIONS = """You look at an overhead photo of a 3D printer bed for a food-decorating printer. Say what food is on
the bed. Use "pumpkin pie" only for an orange custard pie, "pie" for other pies, "nothing" if the bed is empty.
Do not guess beyond what you can see."""


def identify(client, jpeg: bytes) -> dict:
    text = pplx.agent_image(client, instructions=INSTRUCTIONS, jpeg=jpeg, schema=SCHEMA, name="dish",
                            text="What food is on the printer bed?")
    try:
        raw = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        raw = json.loads(m.group(0)) if m else {}
    dish = raw.get("dish") if raw.get("dish") in DISHES else "other"
    return {"dish": dish, "count": int(raw.get("count") or 0), "round": bool(raw.get("round")),
            "surface": str(raw.get("surface") or ""), "confidence": float(raw.get("confidence") or 0)}


def find_edges(jpeg: bytes) -> dict | None:
    """{"w","h","cx","cy","r","r_in","ring"} in photo pixels, or None if no round dish is found.
    r = outer edge, r_in = where the filling stops (== r when no ring of a different color is seen)."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    H, W = img.shape[:2]
    s = 640.0 / max(H, W)
    small = cv2.resize(img, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)

    circle = _blob(small, lab) or _hough(small)
    if not circle:
        return None
    cx, cy, r = circle
    for _ in range(2):   # re-center on the filling itself (a shadow drags the blob's center sideways)
        cx, cy = _filling_center(lab, cx, cy, r)
        cx, cy, r = _refine(small, lab, cx, cy, circle[2])
    r_in, ring = _filling_edge(lab, cx, cy, r)
    k = 1 / s
    return {"w": W, "h": H, "cx": cx * k, "cy": cy * k, "r": r * k, "r_in": r_in * k, "ring": ring}


def _hough(small):
    import cv2
    gray = cv2.medianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 5)
    m = min(gray.shape)
    c = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=m, param1=100, param2=40,
                         minRadius=int(m * 0.12), maxRadius=int(m * 0.5))
    if c is None:
        return None
    x, y, r = c[0][0]
    return float(x), float(y), float(r)


def _blob(small, lab):
    """Biggest region that doesn't look like the bed (the photo's border color), as a circle."""
    import cv2
    import numpy as np
    h, w = lab.shape[:2]
    b = max(4, min(h, w) // 40)
    border = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3), lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    bed = np.median(border, axis=0)
    mask = (np.linalg.norm(lab - bed, axis=2) > 22).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    (x, y), r = cv2.minEnclosingCircle(c)
    area = cv2.contourArea(c)
    if r < min(h, w) * 0.1 or area < 0.6 * math.pi * r * r:   # too small, or not round
        return None
    return float(x), float(y), float(r)


def _filling_center(lab, cx, cy, r):
    import numpy as np
    h, w = lab.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    center = np.median(lab[d < 0.3 * r], axis=0)
    m = (d < r) & (np.linalg.norm(lab - center, axis=2) < 14)
    if m.sum() < 50:
        return cx, cy
    return float(xx[m].mean()), float(yy[m].mean())


def _refine(small, lab, cx, cy, r):
    """Pull the outer edge in past a shadow: the outermost ring that still looks like the dish rim."""
    import numpy as np
    h, w = lab.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    rim = np.median(lab[(d >= 0.86 * r) & (d < 0.92 * r)], axis=0)
    out = r
    for f in np.linspace(0.92, 1.0, 17):
        ring = lab[(d >= f * r - 1.5) & (d < f * r + 1.5)]
        if len(ring) and np.mean(np.linalg.norm(ring - rim, axis=1) < 20) < 0.5:
            out = f * r
            break
    return cx, cy, float(out)


def _filling_edge(lab, cx, cy, r):
    """Walk outward in rings; the first sustained color change from the center is the crust."""
    import numpy as np
    h, w = lab.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    center = np.median(lab[d < 0.3 * r], axis=0)
    steps = np.linspace(0.35, 0.98, 32)
    dist = []
    for a, b in zip(steps, steps[1:]):
        ring = lab[(d >= a * r) & (d < b * r)]
        dist.append(np.linalg.norm(np.median(ring, axis=0) - center) if len(ring) else 0.0)
    for i in range(len(dist) - 1):
        if dist[i] > 14 and dist[i + 1] > 14:
            return float(steps[i] * r), True
    return float(r), False


# ---------- calibration + sizes ----------
def load_cal() -> dict | None:
    try:
        return json.loads(CAL_FILE.read_text())
    except (OSError, ValueError):
        return None


def save_cal(edges: dict, pie_mm: float) -> dict:
    """Run with the pie sitting where pie_x/pie_y was measured (README: Calibrate)."""
    cal = {"cx": edges["cx"] / edges["w"], "cy": edges["cy"] / edges["h"],
           "px_per_mm": edges["r"] / (pie_mm / 2) / edges["w"],   # per unit of photo width
           "pie_mm": pie_mm, "saved": time.strftime("%Y-%m-%d %H:%M")}
    CAL_FILE.write_text(json.dumps(cal, indent=2))
    return cal


def sizes(edges: dict | None, dish: str, pie_mm: float, cal: dict | None) -> dict:
    """Diameter, crust width, usable radius for the design (mm), and offset from the printer center."""
    if not edges:
        return {"fit_r": None, "diameter_mm": None, "crust_mm": None, "off_mm": None}
    if cal:
        ppm = cal["px_per_mm"] * edges["w"]
        R = edges["r"] / ppm
        off = math.hypot(edges["cx"] / edges["w"] - cal["cx"], (edges["cy"] / edges["h"] - cal["cy"]) * edges["h"] / edges["w"]) \
            * edges["w"] / ppm
    else:
        R = TYPICAL_MM.get(dish, pie_mm) / 2
        off = None
    inner = R if dish in TYPICAL_MM else R * edges["r_in"] / edges["r"]   # cookies have no crust ring
    return {"diameter_mm": round(2 * R), "crust_mm": round(R - inner, 1) if inner < R else 0.0,
            "fit_r": round(max(0.0, inner - MARGIN_MM), 1), "off_mm": None if off is None else round(off, 1)}


def inspect(client, jpeg: bytes, pie_mm: float) -> dict:
    """Everything the Camera screen shows after Check pie."""
    try:
        what = identify(client, jpeg)
    except Exception as e:   # noqa: BLE001 - the crust finder still works without the label
        what = {"dish": "other", "count": 0, "round": True, "surface": "", "confidence": 0.0, "error": str(e)[:160]}
    try:
        edges = find_edges(jpeg)
    except ImportError:
        edges, what["error"] = None, "OpenCV missing: .venv/bin/pip install -r requirements.txt"
    cal = load_cal()
    out = {**what, "edges": edges, "calibrated": bool(cal), **sizes(edges, what["dish"], pie_mm, cal)}
    if cal and edges:
        out["target"] = {"cx": cal["cx"] * edges["w"], "cy": cal["cy"] * edges["h"]}
    out["warnings"] = warnings(out)
    return out


def warnings(v: dict) -> list[str]:
    w = []
    if v["dish"] == "nothing":
        w.append("The bed looks empty.")
    if v.get("count", 1) > 1:
        w.append("More than one item on the bed. Pipe one at a time.")
    if not v.get("edges"):
        w.append("Couldn't find a round edge, so the design keeps its normal size.")
    if v.get("off_mm") is not None and v["off_mm"] > OFF_CENTER_MM:
        w.append(f"{v['off_mm']:.0f} mm off center. Slide it onto the target circle.")
    return w
