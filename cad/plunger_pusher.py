"""Plunger pusher v0.1: carries the Tr8x2 brass nut and captures the syringe thumb pad.

Layout (looking down the syringe axis, Z = syringe axis, plunger pushes toward -Z):
  - Syringe axis at (0, 0). Lead screw axis at (SCREW_OFFSET, 0), parallel to the syringe.
  - The thumb pad slides in sideways from the -X side into a pocket, so the pusher
    can both push (dispense) and pull (retract / suck-back).
  - The brass nut flange sits on the top face, its body drops into a bore, and
    4x M3x12 screws thread into 2.8 mm pilot holes (8.5 mm of thread engagement).
  - A guide key on the +X end rides in a channel in the motor mount frame so the
    pusher can't spin with the lead screw.

Run:  python3 cad/plunger_pusher.py   -> cad/out/plunger_pusher.{step,stl}
"""
from pathlib import Path
import math
import cadquery as cq

from params import (THUMB_PAD_D, THUMB_PAD_THICK, PLUNGER_STEM_WIDTH, FLANGE_WIDTH,
                    NUT_FLANGE_D, NUT_FLANGE_THICK, NUT_BODY_D, NUT_HOLE_PCD, LEAD_SCREW_D,
                    CLEAR)

# --- Design parameters --------------------------------------------------------
WALL = 4.0
LIP = 3.0                      # under the thumb pad (pulls the plunger back)
TOP = 4.5                      # above the thumb pad (pushes the plunger)
POCKET_H = THUMB_PAD_THICK + 2 * CLEAR + 0.2
H = LIP + POCKET_H + TOP       # total thickness
POCKET_D = THUMB_PAD_D + 2 * CLEAR + 0.4
SLOT_W = PLUNGER_STEM_WIDTH + 2 * CLEAR
R_SYR = POCKET_D / 2 + WALL
R_NUT = NUT_FLANGE_D / 2 + WALL
# Screw must clear the syringe finger flange (half width) with margin
SCREW_OFFSET = max(R_SYR + NUT_FLANGE_D / 2 - 2.0, FLANGE_WIDTH / 2 + LEAD_SCREW_D / 2 + 4.0)
KEY_W, KEY_L = 8.0, 6.0        # guide key (Y width, X length)
NUT_SCREW_LEN = 12.0           # M3x12 from the Fgruh kit
M3_PILOT = 2.8                 # tap-in pilot hole for M3 in PETG


def build():
    # Outline: hull of syringe circle and nut circle (tangent lines)
    body = (cq.Workplane("XY")
            .circle(R_SYR).extrude(H)
            .union(cq.Workplane("XY").center(SCREW_OFFSET, 0).circle(R_NUT).extrude(H))
            .union(cq.Workplane("XY").center(SCREW_OFFSET / 2, 0)
                   .rect(SCREW_OFFSET, 2 * min(R_SYR, R_NUT)).extrude(H)))
    # Guide key
    body = body.union(cq.Workplane("XY")
                      .center(SCREW_OFFSET + R_NUT + KEY_L / 2 - 1.0, 0)
                      .rect(KEY_L + 2.0, KEY_W).extrude(H))

    # Thumb-pad pocket: circle + entry channel open to -X
    pocket = (cq.Workplane("XY").workplane(offset=LIP)
              .circle(POCKET_D / 2).extrude(POCKET_H)
              .union(cq.Workplane("XY").workplane(offset=LIP)
                     .center(-R_SYR, 0).rect(2 * R_SYR, POCKET_D).extrude(POCKET_H)))
    body = body.cut(pocket)

    # Stem slot through the lip, open to -X
    stem = (cq.Workplane("XY").circle(SLOT_W / 2).extrude(LIP)
            .union(cq.Workplane("XY").center(-R_SYR, 0)
                   .rect(2 * R_SYR, SLOT_W).extrude(LIP)))
    body = body.cut(stem)

    # Nut body bore (through) + 4x M3 clearance holes + captive nut traps on the bottom
    body = body.cut(cq.Workplane("XY").center(SCREW_OFFSET, 0)
                    .circle(NUT_BODY_D / 2 + CLEAR / 2 + 0.1).extrude(H))
    pts = [(SCREW_OFFSET + NUT_HOLE_PCD / 2 * math.cos(math.radians(a)),
            NUT_HOLE_PCD / 2 * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
    # M3x12 screws thread straight into PETG pilot holes (no room for captive nuts on a 16 mm PCD)
    body = body.cut(cq.Workplane("XY").pushPoints(pts).circle(M3_PILOT / 2).extrude(H))

    # Soften vertical outside edges a little (skip if the kernel refuses)
    try:
        body = body.edges("|Z").fillet(0.8)
    except Exception:
        pass
    return body


if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    part = build()
    cq.exporters.export(part, str(out / "plunger_pusher.step"))
    cq.exporters.export(part, str(out / "plunger_pusher.stl"), tolerance=0.02, angularTolerance=0.1)
    bb = part.val().BoundingBox()
    print(f"H={H:.2f} SCREW_OFFSET={SCREW_OFFSET:.2f} pocket D={POCKET_D:.2f} slot={SLOT_W:.2f}")
    print(f"bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, volume {part.val().Volume()/1000:.1f} cm^3")
