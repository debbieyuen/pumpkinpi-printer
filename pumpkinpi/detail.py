"""Is this design too much for a cold syringe? Tell the user instead of piping a blob.

A 60 mL syringe with a narrow tip lays a bead a few mm wide, so fine detail merges. Two checks:
  1. The request itself (from the Agent API): a photo, portrait, scene, shading or several pictures can't be
     piped as lines. design.py asks the model to fill "too_detailed" with the reason and "simpler" with an idea.
  2. The real path (measured here): letters too small to read, too many separate strokes (each lift leaves a
     dot), a message longer than fits, or a long pipe time (the topping softens and the syringe runs low).

Returns {"level": "ok" | "busy" | "too_much", "reasons": [...], "try": "..."}; the screen shows it on Design.
It never blocks Send: the user decides, but they hear it first.
"""
from __future__ import annotations

from .shapes import BASES, extent, split_lines, strokes_for, text

MIN_LETTER_MM = 6.0      # below this a ~2-3 mm bead fills the letter in
BUSY_STROKES = 40        # separate beads (each start/stop leaves a dot)
MAX_STROKES = 60
BUSY_SECONDS = 150       # piping time at the plan's feed rate
MAX_SECONDS = 240


# Text boxes (width, height) in mm, as laid out by shapes.strokes_for: alone or under a picture, 1 or 2 lines.
BOXES = {("text", 1): [(80, 24, 30)], ("text", 2): [(72, 15, 18)] * 2,
         ("art", 1): [(50, 10, 13)], ("art", 2): [(60, 9, 11), (52, 9, 11)]}


def letter_mm(plan: dict, strokes: list) -> float | None:
    """Height in mm of the smallest line of words as piped: long lines are squeezed by width, a cookie or
    cupcake shrinks everything, and the camera fit (fit_r) can shrink it more."""
    lines = split_lines(plan.get("text") or "")
    if not lines:
        return None
    cur = plan.get("font") == "cursive"
    boxes = BOXES[("text" if plan.get("shape") == "text" else "art", len(lines))]
    def tall(st):
        ys = [y for s in st for _, y in s]
        return max(ys) - min(ys) if ys else 0.0
    h = min(tall(text(ln, w, hc if cur else hp, plan.get("font") or "print")) for ln, (w, hp, hc) in zip(lines, boxes))
    full = extent(strokes_for({**plan, "fit_r": None}))
    k = extent(strokes) / full if full else 1.0
    return h * BASES.get(plan.get("base") or "pie", 1.0) * k


def check(plan: dict, strokes: list, path: dict | None = None) -> dict:
    reasons: list[str] = []
    level = "ok"

    def flag(lvl: str, why: str) -> None:
        nonlocal level
        reasons.append(why)
        if lvl == "too_much" or level == "ok":
            level = lvl

    asked = (plan.get("too_detailed") or "").strip()
    if asked:
        flag("too_much", asked)
    wanted = (plan.get("text_asked") or "").strip()
    if wanted and wanted != plan.get("text"):
        flag("too_much", f"\"{wanted}\" is too long: only two short lines fit, so it says \"{plan.get('text', '')}\".")
    h = letter_mm(plan, strokes)
    if h is not None and h < MIN_LETTER_MM:
        flag("too_much", f"The letters would be only {h:.0f} mm tall and blur together.")
    n = len(strokes)
    if n > MAX_STROKES:
        flag("too_much", f"{n} separate lines; each start and stop leaves a dot.")
    elif n > BUSY_STROKES:
        flag("busy", f"{n} separate lines, so expect a few dots where the tip lifts.")
    secs = (path or {}).get("seconds") or 0
    if secs > MAX_SECONDS:
        flag("too_much", f"About {secs // 60} minutes of piping; the topping softens before it's done.")
    elif secs > BUSY_SECONDS:
        flag("busy", f"About {round(secs / 60, 1)} minutes of piping. Keep the topping cold.")

    tip = (plan.get("simpler") or "").strip()
    if not tip and level != "ok":
        tip = "Try just a shape, or a shape with a short name." if plan.get("text") else "Try a simpler shape."
    return {"level": level, "reasons": reasons, "try": tip if level != "ok" else ""}
