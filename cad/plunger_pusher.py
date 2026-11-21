"""Plunger pusher v0.2: carries the Tr8x2 brass nut and grabs the syringe thumb pad.

Matches carriage.py: lead screw axis is SCREW_DY (= -42 mm, toward the front) from the
syringe axis. The thumb pad slides in from +X, the same direction the syringe slides out of
the carriage, so the whole syringe comes off in one sideways pull.
No anti-rotation guide is needed: the plunger (held by the barrel) stops the pusher spinning.

Print flat, top face up, as exported. Nut flange goes on the top face.
"""
from pathlib import Path
import math
import cadquery as cq
from params import (THUMB_PAD_D, THUMB_PAD_THICK, PLUNGER_STEM_WIDTH, NUT_FLANGE_D,
                    NUT_BODY_D, NUT_HOLE_PCD, CLEAR, SCREW_DY)

WALL = 4.0
LIP = 3.0                                   # under the pad: pulls the plunger back
TOP = 4.5                                   # over the pad: pushes the plunger in
POCKET_H = THUMB_PAD_THICK + 1.6            # loose: fits pads up to ~3.4 mm thick
H = LIP + POCKET_H + TOP
POCKET_D = THUMB_PAD_D + 2 * CLEAR + 0.4
SLOT_W = PLUNGER_STEM_WIDTH + 2 * CLEAR
R_SYR = POCKET_D / 2 + WALL
R_NUT = NUT_FLANGE_D / 2 + WALL
SY = SCREW_DY                               # screw at (0, SY)
M3_PILOT = 2.8                              # M3x12 self-threads into PETG


def build():
    body = (cq.Workplane("XY").circle(R_SYR).extrude(H)
            .union(cq.Workplane("XY").center(0, SY).circle(R_NUT).extrude(H))
            .union(cq.Workplane("XY").center(0, SY / 2).rect(2 * R_NUT, abs(SY)).extrude(H)))
    # pad pocket + stem slot, both open to +X
    body = body.cut(cq.Workplane("XY").workplane(offset=LIP).circle(POCKET_D / 2).extrude(POCKET_H)
                    .union(cq.Workplane("XY").workplane(offset=LIP).center(R_SYR, 0)
                           .rect(2 * R_SYR, POCKET_D).extrude(POCKET_H)))
    body = body.cut(cq.Workplane("XY").circle(SLOT_W / 2).extrude(LIP + 0.01)
                    .union(cq.Workplane("XY").center(R_SYR, 0).rect(2 * R_SYR, SLOT_W)
                           .extrude(LIP + 0.01)))
    # nut bore + 4 pilot holes
    body = body.cut(cq.Workplane("XY").center(0, SY).circle(NUT_BODY_D / 2 + 0.3).extrude(H))
    pts = [(NUT_HOLE_PCD / 2 * math.cos(math.radians(a)),
            SY + NUT_HOLE_PCD / 2 * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
    body = body.cut(cq.Workplane("XY").pushPoints(pts).circle(M3_PILOT / 2).extrude(H))
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
    print(f"pusher bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}  vol {part.val().Volume()/1000:.1f} cm3")
