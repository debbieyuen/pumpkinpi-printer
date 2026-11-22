"""Piping strokes (mm, pie-centered) -> G-code for the syringe, with hard bounds checks.

Machine numbers live in machine.json (git-ignored; copy machine.example.json). Measure them
with the bed EMPTY first, then once with the pie on, never homing with food on the bed:

  pie_x, pie_y   printer X/Y (from M114) when the SYRINGE TIP is over the pie center
  z_surface      printer Z when the syringe tip just touches the chilled pie (paper test)
  e_per_mm       E units per mm of path. Calibrate: `python -m pumpkinpi.toolpath --calibrate`

The pancake motor is on the printer's E port, so E moves push the plunger.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MACHINE_FILE = Path(os.environ.get("PUMPKINPI_MACHINE", ROOT / "machine.json"))


@dataclass
class Machine:
    pie_x: float = 90.0
    pie_y: float = 110.0
    z_surface: float = 30.0
    gap: float = 1.5            # tip height above the pie while piping
    lift: float = 8.0           # travel height above the pie between strokes
    feed: float = 600.0         # mm/min while piping
    travel: float = 1500.0      # mm/min between strokes
    e_per_mm: float = 0.02      # plunger E units per mm of path (calibrate!)
    prime: float = 0.3          # E push before each stroke
    retract: float = 0.6        # E pull-back after each stroke (stops drips)
    dwell: float = 0.5          # seconds to wait after the pull-back, tip still down, so the drip lands on the line
    lift_feed: float = 300.0    # mm/min lifting off the line (slow = snaps marshmallow strings)
    tip_offset: float = 0.0     # mm: this topping's tip is longer (+, carriage stays higher) or shorter (-) than the one z_surface was measured with
    topping: str = ""
    x_min: float = 5.0
    x_max: float = 150.0        # syringe hangs off the right of the head
    y_min: float = 5.0
    y_max: float = 215.0
    z_max: float = 120.0
    pie_mm: float = 152.0       # outer diameter of the pie used for the camera "Save as center" (6-inch)

    @classmethod
    def load(cls, path: Path = MACHINE_FILE, topping: str | None = None) -> "Machine":
        """machine.json, then the settings for this topping (starting values below, your saved ones on top)."""
        data = json.loads(path.read_text()) if path.exists() else {}
        saved = data.pop("toppings", {}) or {}
        m = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        if topping:
            prof = {**TOPPINGS.get(topping, {}), **saved.get(topping, {})}
            for k, v in prof.items():
                if k in cls.__dataclass_fields__ and k != "topping":
                    setattr(m, k, float(v))
            m.topping = topping
        return m


# How each topping behaves, and starting settings. These are starting points only: run the drip test for
# each topping and nozzle (Camera > Drip test) and it saves your measured pause into machine.json.
#   frosting     room-temperature paste, holds a line, drips little        -> short pause
#   chocolate    melted chips: runny while warm, thickens as it cools       -> thinner bead, longer pull-back + pause
#   marshmallow  melted: very sticky and stringy, sets fast as it cools     -> slow line, long pull-back, slow lift
TOPPINGS: dict[str, dict] = {
    "frosting": {"feed": 600, "e_per_mm": 0.02, "prime": 0.3, "retract": 0.6, "dwell": 0.5, "gap": 1.5, "lift_feed": 300},
    "chocolate": {"feed": 720, "e_per_mm": 0.015, "prime": 0.2, "retract": 0.8, "dwell": 1.0, "gap": 1.0, "lift_feed": 300},
    "marshmallow": {"feed": 420, "e_per_mm": 0.03, "prime": 0.4, "retract": 1.0, "dwell": 1.5, "gap": 2.0, "lift_feed": 120},
}
TOPPING_INFO = {   # shown on screen when you load the syringe
    "frosting": {"label": "Frosting", "tip": "small round tip", "work_min": 0,
                 "prep": "Room temperature, smooth, no air pockets."},
    "chocolate": {"label": "Melted chocolate", "tip": "small round tip", "work_min": 12,
                  "prep": "Melt chips gently and keep it under 120°F. The syringe isn't heated, so pipe within about 10-15 minutes."},
    "marshmallow": {"label": "Melted marshmallow", "tip": "wider round tip", "work_min": 3,
                    "prep": "Cool about 3 minutes after melting, then pipe right away: it sets fast and gets stringy."},
}


def save_topping(name: str, values: dict, path: Path = MACHINE_FILE) -> dict:
    """Save measured settings (e.g. the drip-test pause) for one topping into machine.json."""
    if name not in TOPPINGS:
        raise ValueError(f"Unknown topping {name!r}")
    data = json.loads(path.read_text()) if path.exists() else {}
    keep = {k: round(float(v), 3) for k, v in values.items() if k in ("dwell", "retract", "prime", "e_per_mm", "feed", "gap", "lift_feed", "tip_offset")}
    data.setdefault("toppings", {}).setdefault(name, {}).update(keep)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return {**TOPPINGS[name], **data["toppings"][name]}


class OutOfBounds(ValueError):
    pass


def to_gcode(strokes, m: Machine, dry_run: bool = False) -> list[str]:
    """dry_run: same path 15 mm higher with no extrusion. Always do one before real frosting."""
    z0 = m.z_surface + m.tip_offset + (15.0 if dry_run else 0.0)
    zp, zt = z0 + m.gap, z0 + m.lift
    out = ["G90", "M83", f"G0 Z{zt:.2f} F600"]
    for st in strokes:
        if len(st) < 2:
            continue
        x, y = st[0]
        out += [f"G0 X{m.pie_x + x:.2f} Y{m.pie_y + y:.2f} F{m.travel:.0f}", f"G1 Z{zp:.2f} F300"]
        if not dry_run:
            out.append(f"G1 E{m.prime:.3f} F120")
        for (ax, ay), (bx, by) in zip(st, st[1:]):
            e = "" if dry_run else f" E{math.hypot(bx - ax, by - ay) * m.e_per_mm:.4f}"
            out.append(f"G1 X{m.pie_x + bx:.2f} Y{m.pie_y + by:.2f}{e} F{m.feed:.0f}")
        if not dry_run:
            out.append(f"G1 E-{m.retract:.3f} F300")
            if m.dwell > 0:
                out.append(f"G4 P{round(m.dwell * 1000)}")   # pause: let the last drip land on the line
        out.append(f"G1 Z{zt:.2f} F{m.lift_feed:.0f}")
    out += [f"G0 Z{zt + 20:.2f} F600", "M400", "M117 PumpkinPi done"]
    check_bounds(out, m)
    return out


def drip_test_gcode(m: Machine, length: float = 40.0) -> list[str]:
    """One straight line across the middle, then pull back with NO pause, so you can time the ooze."""
    m2 = Machine(**{**asdict(m), "dwell": 0.0})
    lines = to_gcode([[(-length / 2, 0.0), (length / 2, 0.0)]], m2)
    # stop right after the pull-back and lift a little, so the tip stays in view of the camera
    cut = next(i for i, ln in enumerate(lines) if ln.startswith("G1 E-"))
    zp = m.z_surface + m.tip_offset + m.gap + 3
    return lines[:cut + 1] + [f"G1 Z{zp:.2f} F{m.lift_feed:.0f}", "M400"]


def piped_path(lines: list[str], m: Machine) -> dict:
    """Read G-code back into what actually gets piped, so the screen shows the exact design.

    Returns {"strokes": pie-centered polylines of every move that pushes the plunger (E > 0 with X/Y),
    "mm": piped length, "seconds": rough time from feed rates}.
    """
    x = y = 0.0
    strokes: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    mm = secs = 0.0
    for ln in lines:
        w = ln.split()
        if w and w[0] == "G4":
            secs += sum(float(t[1:]) / 1000 for t in w[1:] if t[0] == "P")
            continue
        if not w or w[0] not in ("G0", "G1"):
            continue
        a = {t[0]: float(t[1:]) for t in w[1:] if t[0] in "XYZEF"}
        nx, ny = a.get("X", x), a.get("Y", y)
        d = math.hypot(nx - x, ny - y)
        if "F" in a and d:
            secs += d / a["F"] * 60
        if w[0] == "G1" and a.get("E", 0) > 0 and ("X" in a or "Y" in a):
            if not cur:
                cur = [(round(x - m.pie_x, 2), round(y - m.pie_y, 2))]
            cur.append((round(nx - m.pie_x, 2), round(ny - m.pie_y, 2)))
            mm += d
        elif cur and ("X" in a or "Y" in a or "Z" in a or a.get("E", 0) < 0):
            strokes.append(cur)
            cur = []
        x, y = nx, ny
    if cur:
        strokes.append(cur)
    return {"strokes": strokes, "mm": round(mm), "seconds": round(secs)}


def check_bounds(lines: list[str], m: Machine) -> None:
    for ln in lines:
        for word in ln.split()[1:]:
            ax, val = word[0], word[1:]
            if ax not in "XYZ":
                continue
            v = float(val)
            lo, hi = {"X": (m.x_min, m.x_max), "Y": (m.y_min, m.y_max), "Z": (m.z_surface + min(0.0, m.tip_offset), m.z_max)}[ax]
            if not lo <= v <= hi:
                raise OutOfBounds(f"{ln!r}: {ax}={v} outside {lo}..{hi}. Check pie_x/pie_y/z_surface in machine.json")


def main() -> None:
    ap = argparse.ArgumentParser(description="Write G-code for a design, or calibrate the plunger.")
    ap.add_argument("--shape", default="smiley")
    ap.add_argument("--text", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--calibrate", action="store_true", help="print a 10 E-unit plunger push to measure")
    args = ap.parse_args()
    if args.calibrate:
        print("M302 P1\nM83\nG1 E10 F60\n; measure how far the pusher moved (mm) and how much frosting came out")
        return
    from .shapes import strokes_for
    m = Machine.load()
    print(f"; machine {json.dumps(asdict(m))}")
    print("\n".join(to_gcode(strokes_for({"shape": args.shape, "text": args.text}), m, args.dry_run)))


if __name__ == "__main__":
    main()
