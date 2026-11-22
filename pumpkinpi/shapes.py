"""Turn a design plan into piping strokes (polylines in mm, centered on the pie, +Y away from you).

Shapes are drawn by code, not by the model, so every stroke is known to fit the pie.
Text uses the single-stroke Hershey "futural" font (MIT-licensed Hershey-Fonts package),
so each letter is one bead of frosting instead of an outline.
"""
from __future__ import annotations

import math

Stroke = list[tuple[float, float]]
SHAPES = ("smiley", "heart", "star", "text")
MAX_R = 45.0          # keep everything inside this radius (6-inch pie, away from the crust)
MAX_TEXT = 12


def circle(cx: float, cy: float, r: float, start: float = 0, end: float = 360, n: int = 48) -> Stroke:
    k = max(8, int(n * abs(end - start) / 360))
    return [(cx + r * math.cos(math.radians(start + (end - start) * i / k)),
             cy + r * math.sin(math.radians(start + (end - start) * i / k))) for i in range(k + 1)]


def smiley(r: float = 40) -> list[Stroke]:
    return [circle(0, 0, r),
            circle(-0.33 * r, 0.3 * r, 0.1 * r, n=16),
            circle(0.33 * r, 0.3 * r, 0.1 * r, n=16),
            circle(0, 0.05 * r, 0.6 * r, 200, 340, n=40)]


def heart(r: float = 40) -> list[Stroke]:
    pts = []
    for i in range(73):
        t = 2 * math.pi * i / 72
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x * r / 17, (y + 2) * r / 17))
    return [pts]


def star(r: float = 40) -> list[Stroke]:
    pts = [((r if i % 2 == 0 else 0.42 * r) * math.cos(math.radians(90 + 36 * i)),
            (r if i % 2 == 0 else 0.42 * r) * math.sin(math.radians(90 + 36 * i))) for i in range(11)]
    return [pts]


def text(s: str, width: float = 70, height: float = 18) -> list[Stroke]:
    from HersheyFonts import HersheyFonts

    s = s.strip()[:MAX_TEXT]
    if not s:
        return []
    f = HersheyFonts()
    f.load_default_font("futural")
    f.normalize_rendering(10)
    strokes = [list(st) for st in f.strokes_for_text(s)]
    xs = [x for st in strokes for x, _ in st]
    ys = [y for st in strokes for _, y in st]
    w, h = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
    k = min(width / w, height / h)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return [[((x - cx) * k, (y - cy) * k) for x, y in st] for st in strokes]


def move(strokes: list[Stroke], dx: float = 0, dy: float = 0, k: float = 1) -> list[Stroke]:
    return [[(x * k + dx, y * k + dy) for x, y in st] for st in strokes]


def strokes_for(plan: dict) -> list[Stroke]:
    """plan: {"shape": one of SHAPES, "text": optional words under the shape}."""
    shape = plan.get("shape", "text")
    words = (plan.get("text") or "").strip()
    if shape not in SHAPES:
        raise ValueError(f"Unknown shape {shape!r}; choose one of {SHAPES}")
    if shape == "text":
        out = text(words or "Happy", width=80, height=24)
    else:
        art = {"smiley": smiley, "heart": heart, "star": star}[shape]()
        out = move(art, dy=12, k=0.65) + move(text(words, width=50, height=10), dy=-28) if words else art
    for st in out:
        for x, y in st:
            if math.hypot(x, y) > MAX_R + 0.01:
                raise ValueError(f"Design leaves the safe area ({math.hypot(x, y):.1f} mm > {MAX_R} mm)")
    return out
