"""Turn a design plan into piping strokes (polylines in mm, centered on the pie, +Y away from you).

Shapes are drawn by code, not by the model, so every stroke is known to fit the pie.
Text uses single-stroke Hershey fonts (MIT-licensed Hershey-Fonts package): "futural" for print
and "scripts" for cursive, so each letter is one bead of frosting instead of an outline.
"""
from __future__ import annotations

import math

Stroke = list[tuple[float, float]]
SHAPES = ("smiley", "heart", "star", "cat", "dog", "pumpkin", "leaf", "text")
FONTS = {"print": "futural", "cursive": "scripts"}
MAX_R = 45.0          # keep everything inside this radius (6-inch pie, away from the crust)
MAX_TEXT = 26        # keep it simple: one picture + at most two short lines
MAX_LINE = 13
# What the design is piped on, and how much to shrink it: a 6-inch pie or cake uses the full area,
# a ~4-inch cookie about 3/4, a cupcake about half. "none" = nothing to pipe (e.g. a roast turkey).
BASES = {"pie": 1.0, "cake": 1.0, "cookie": 0.75, "cupcake": 0.55, "none": 1.0}


def split_lines(s: str) -> list[str]:
    """Up to two lines of at most MAX_LINE letters ("Happy" / "Thanksgiving"). Words that don't fit are
    dropped whole, never cut mid-word, so the pie stays readable."""
    words = s.split()
    for n in range(len(words), 0, -1):              # keep as many words as fit
        w = words[:n]
        if len(" ".join(w)) <= MAX_LINE:
            return [" ".join(w)]
        splits = [[" ".join(w[:j]), " ".join(w[j:])] for j in range(1, n)]
        splits = [x for x in splits if max(map(len, x)) <= MAX_LINE]
        if splits:
            return min(splits, key=lambda x: max(map(len, x)))
    return [words[0][:MAX_LINE]] if words else []


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


def ellipse(cx: float, cy: float, rx: float, ry: float, start: float = 0, end: float = 360, n: int = 48) -> Stroke:
    return [(cx + (x - cx) * rx, cy + (y - cy) * ry) for x, y in circle(cx, cy, 1, start, end, n)]


def cat(r: float = 34) -> list[Stroke]:
    """Cat face: head with two pointed ears in one bead, then eyes, nose, mouth and whiskers."""
    rx, ry = r, 0.82 * r
    head = ellipse(0, 0, rx, ry, 120, 420, n=64)                     # from upper left, round the chin, to upper right
    rx_, ry_ = head[-1]
    right_ear = [(rx_, ry_), (0.78 * r, 1.22 * r), (0.32 * r, 0.78 * r)]
    top = ellipse(0, 0, rx, ry, 67, 113, n=10)
    left_ear = [(-0.32 * r, 0.78 * r), (-0.78 * r, 1.22 * r), head[0]]
    outline = head + right_ear[1:] + top[1:-1] + left_ear
    eyes = [ellipse(-0.38 * r, 0.22 * r, 0.11 * r, 0.16 * r, n=16), ellipse(0.38 * r, 0.22 * r, 0.11 * r, 0.16 * r, n=16)]
    nose = [(-0.09 * r, -0.08 * r), (0.09 * r, -0.08 * r), (0, -0.2 * r), (-0.09 * r, -0.08 * r)]
    mouth = circle(-0.14 * r, -0.2 * r, 0.14 * r, 200, 360, n=12) + circle(0.14 * r, -0.2 * r, 0.14 * r, 180, 340, n=12)
    whiskers = [[(s * 0.3 * r, -0.12 * r), (s * 0.9 * r, -0.02 * r)] for s in (-1, 1)] + \
               [[(s * 0.3 * r, -0.22 * r), (s * 0.88 * r, -0.32 * r)] for s in (-1, 1)]
    out = [outline, *eyes, nose, mouth, *whiskers]
    return move(out, dy=-0.2 * r)        # ears reach 1.22 r; centre the face on the pie


def rotate(st: Stroke, deg: float, cx: float = 0, cy: float = 0) -> Stroke:
    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (x - cx) * c - (y - cy) * s_, cy + (x - cx) * s_ + (y - cy) * c) for x, y in st]


def smooth(pts: list[tuple[float, float]], n: int = 8) -> Stroke:
    """Catmull-Rom through the points, so a few control points become one smooth bead."""
    p = [pts[0], *pts, pts[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(n):
            t = k / n
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    return out + [pts[-1]]


def dog(r: float = 34) -> list[Stroke]:
    """Dog face: round head, two floppy ears hanging from the top, eyes, nose and a smile."""
    rx, ry = 0.78 * r, 0.8 * r
    head = ellipse(0, 0, rx, ry, n=64)
    at = lambda deg: (rx * math.cos(math.radians(deg)), ry * math.sin(math.radians(deg)))  # noqa: E731
    ear = smooth([at(112), (-0.75 * r, 0.9 * r), (-1.12 * r, 0.35 * r), (-1.05 * r, -0.3 * r), (-0.82 * r, -0.42 * r), at(195)])
    ears = [ear, [(-x, y) for x, y in ear]]
    eyes = [circle(s * 0.28 * r, 0.2 * r, 0.08 * r, n=14) for s in (-1, 1)]
    nose = ellipse(0, -0.16 * r, 0.15 * r, 0.1 * r, n=20)
    mouth = circle(-0.13 * r, -0.4 * r, 0.13 * r, 200, 360, n=10)[::-1][:-1] + [(0, -0.26 * r), (0, -0.4 * r)] + \
        circle(0.13 * r, -0.4 * r, 0.13 * r, 180, 340, n=10)
    return [head, *ears, *eyes, nose, mouth]


def pumpkin(r: float = 40) -> list[Stroke]:
    body = ellipse(0, 0, r, 0.72 * r, n=64)
    ribs = [ellipse(-0.18 * r, 0, 0.42 * r, 0.7 * r, 100, 260, n=24), ellipse(0.18 * r, 0, 0.42 * r, 0.7 * r, -80, 80, n=24)]
    stem = [(-0.08 * r, 0.7 * r), (-0.1 * r, 0.95 * r), (0.12 * r, 1.0 * r), (0.1 * r, 0.71 * r)]
    return move([body, *ribs, stem], dy=-0.12 * r)


def leaf(r: float = 40) -> list[Stroke]:
    pts = []
    for i in range(49):                    # pointed oval, tip at the top
        t = math.pi * i / 24
        pts.append((0.55 * r * abs(math.sin(t)) ** 1.2, -r * math.cos(t)))
    outline = pts + [(-x, y) for x, y in reversed(pts[:-1])]
    vein = [(0, -1.1 * r), (0, 0.85 * r)]
    side = [[(0, -0.35 * r + k * r), (s * 0.35 * r, -0.05 * r + k * r)] for k in (0, 0.4) for s in (-1, 1)]
    return move([outline, vein, *side], dy=0.1 * r, k=0.95)


def text(s: str, width: float = 70, height: float = 18, font: str = "print") -> list[Stroke]:
    from HersheyFonts import HersheyFonts

    s = s.strip()[:MAX_TEXT]
    if not s:
        return []
    f = HersheyFonts()
    f.load_default_font(FONTS.get(font, "futural"))
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


def extent(strokes: list[Stroke]) -> float:
    return max((math.hypot(x, y) for st in strokes for x, y in st), default=0.0)


def strokes_for(plan: dict) -> list[Stroke]:
    """plan: {"shape": one of SHAPES, "text": optional words under the shape, "font": "print" | "cursive",
    "fit_r": optional usable radius in mm (smaller dish or wide crust)}."""
    shape = plan.get("shape", "text")
    words = (plan.get("text") or "").strip()
    font = plan.get("font") if plan.get("font") in FONTS else "print"
    if shape not in SHAPES:
        raise ValueError(f"Unknown shape {shape!r}; choose one of {SHAPES}")
    lines = split_lines(words)
    cur = font == "cursive"
    if shape == "text":
        lines = lines or ["Happy"]
        if len(lines) == 1:
            out = text(lines[0], width=80, height=30 if cur else 24, font=font)
        else:
            h = 18 if cur else 15
            out = move(text(lines[0], 72, h, font), dy=13) + move(text(lines[1], 72, h, font), dy=-13)
    else:
        art = {"smiley": smiley, "heart": heart, "star": star, "cat": cat, "dog": dog, "pumpkin": pumpkin, "leaf": leaf}[shape]()
        if len(lines) == 1:
            out = move(art, dy=12, k=0.65) + move(text(lines[0], width=50, height=13 if cur else 10, font=font), dy=-28)
        elif len(lines) == 2:
            h = 11 if cur else 9
            out = move(art, dy=18, k=0.5) + move(text(lines[0], 60, h, font), dy=-12) + move(text(lines[1], 52, h, font), dy=-29)
        else:
            out = art
    out = move(out, k=BASES.get(plan.get("base") or "pie", 1.0))
    fit = plan.get("fit_r")   # usable radius the camera measured (vision.py): only ever shrinks the design
    if fit and fit > 0:
        ext = extent(out)
        if ext > fit:
            out = move(out, k=fit / ext)
    for st in out:
        for x, y in st:
            if math.hypot(x, y) > MAX_R + 0.01:
                raise ValueError(f"Design leaves the safe area ({math.hypot(x, y):.1f} mm > {MAX_R} mm)")
    return out
