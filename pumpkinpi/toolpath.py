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
    x_min: float = 5.0
    x_max: float = 150.0        # syringe hangs off the right of the head
    y_min: float = 5.0
    y_max: float = 215.0
    z_max: float = 120.0

    @classmethod
    def load(cls, path: Path = MACHINE_FILE) -> "Machine":
        return cls(**json.loads(path.read_text())) if path.exists() else cls()


class OutOfBounds(ValueError):
    pass


def to_gcode(strokes, m: Machine, dry_run: bool = False) -> list[str]:
    """dry_run: same path 15 mm higher with no extrusion. Always do one before real frosting."""
    z0 = m.z_surface + (15.0 if dry_run else 0.0)
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
        out.append(f"G0 Z{zt:.2f} F600")
    out += [f"G0 Z{zt + 20:.2f} F600", "M400", "M117 PumpkinPi done"]
    check_bounds(out, m)
    return out


def check_bounds(lines: list[str], m: Machine) -> None:
    for ln in lines:
        for word in ln.split()[1:]:
            ax, val = word[0], word[1:]
            if ax not in "XYZ":
                continue
            v = float(val)
            lo, hi = {"X": (m.x_min, m.x_max), "Y": (m.y_min, m.y_max), "Z": (m.z_surface, m.z_max)}[ax]
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
