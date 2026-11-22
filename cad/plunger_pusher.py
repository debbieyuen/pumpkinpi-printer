"""Plunger pusher v0.6: carries the Tr8x2 brass nut and presses on the syringe thumb pad.

v0.6 (2026-11-21): pad pocket now opens toward -X (the print head side), mirrored from v0.5.
The Tr8x2 screw is right-hand, so driving the nut DOWN turns the screw counterclockwise (seen
from above) and friction drags the pusher counterclockwise too. With the arm pointing +Y from the
screw, that swings the pocket toward -X. In v0.5 the open side was +X, so the pad slid out
(Debbie's hand test). Now the closed wall is on +X and catches the pad.
Loading: swing the pusher toward the head, slide the syringe in from +X, then swing the pusher
back (clockwise) until the wall touches the pad.

v0.5: v0.4 geometry with a fixed (valid) solid.

v0.4 (2026-11-21): nut flange holes are M3 clearance (3.4 mm) with hex nut traps on the bottom;
use 4x M3x16 + 4x M3 nuts. Nut lobe is 3 mm thicker on the bottom. Screw axis now 47 mm from the
syringe (follows SCREW_DY).

v0.3: push-only. The thumb pad sits in a 3.6 mm recess (open toward +X); there is no lip under
it, so the part prints with no support. Retract (to relieve pressure) at most ~1 mm so the pad
stays in the recess.

Matches carriage.py: lead screw axis is SCREW_DY (= -47 mm, toward the front) from the
syringe axis. The thumb pad slides in from +X, the same direction the syringe slides out of
the carriage, so the whole syringe comes off in one sideways pull.
No anti-rotation guide is needed: the plunger (held by the barrel) stops the pusher spinning.

Exported upside down for printing (top face on the bed). Nut flange goes on the top face.
"""
from pathlib import Path
import math
import cadquery as cq
from params import (THUMB_PAD_D, THUMB_PAD_THICK, PLUNGER_STEM_WIDTH, NUT_FLANGE_D,
                    NUT_BODY_D, NUT_HOLE_PCD, CLEAR, SCREW_DY, M3_CLEAR, M3_NUT_AF, M3_NUT_THICK)

WALL = 4.0
LIP = 0.0                                   # v0.3: no lip under the pad (it needed support)
TOP = 6.0                                   # over the pad: pushes the plunger in
POCKET_H = THUMB_PAD_THICK + 1.6            # loose: fits pads up to ~3.4 mm thick
H = LIP + POCKET_H + TOP
POCKET_D = THUMB_PAD_D + 2 * CLEAR + 0.4
SLOT_W = PLUNGER_STEM_WIDTH + 2 * CLEAR
R_SYR = POCKET_D / 2 + WALL
R_NUT = NUT_FLANGE_D / 2 + WALL
SY = SCREW_DY                               # screw at (0, SY)
# v1.1: M3 clearance holes + nut traps (the 2.8 mm self-tap pilots printed too small to take a screw).
# The nut lobe is DROP mm thicker on the bottom so an M3x16 passes the flange, the lobe and a full nut.
DROP = 3.0
OPEN_DIR = -1                               # v0.6: pocket opens toward -X
NUT_TRAP_AF = M3_NUT_AF + 0.3               # 5.8 mm across flats: M3 nut presses in
NUT_TRAP_D = M3_NUT_THICK + 0.2             # 2.6 mm deep, nut sits flush


def build():
    body = (cq.Workplane("XY").circle(R_SYR).extrude(H)
            .union(cq.Workplane("XY").workplane(offset=-DROP).center(0, SY).circle(R_NUT).extrude(H + DROP))
            .union(cq.Workplane("XY").center(0, SY / 2).rect(2 * R_NUT, abs(SY)).extrude(H)))
    # v0.5: round the outline BEFORE cutting holes. Filleting after the hex traps made an invalid
    # solid, and the slicer filled the holes and nut traps in (Debbie's print, 2026-11-21).
    try:
        body = body.edges("|Z").fillet(0.8)
    except Exception:
        pass
    # pad pocket + stem slot, both open to -X (v0.6, see docstring)
    body = body.cut(cq.Workplane("XY").workplane(offset=LIP).circle(POCKET_D / 2).extrude(POCKET_H)
                    .union(cq.Workplane("XY").workplane(offset=LIP).center(OPEN_DIR * R_SYR, 0)
                           .rect(2 * R_SYR, POCKET_D).extrude(POCKET_H)))
    # nut bore + 4 pilot holes
    body = body.cut(cq.Workplane("XY").workplane(offset=-DROP - 1).center(0, SY)
                    .circle(NUT_BODY_D / 2 + 0.3).extrude(H + DROP + 2))
    pts = [(NUT_HOLE_PCD / 2 * math.cos(math.radians(a)),
            SY + NUT_HOLE_PCD / 2 * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
    body = body.cut(cq.Workplane("XY").workplane(offset=-DROP - 1).pushPoints(pts)
                    .circle(M3_CLEAR / 2).extrude(H + DROP + 2))
    # hex nut traps open on the bottom face (that face is UP when printed, so no support)
    for (x, y) in pts:
        a = math.degrees(math.atan2(y - SY, x))      # flat faces the nut bore -> max wall to the bore
        body = body.cut(cq.Workplane("XY").workplane(offset=-DROP - 0.01).center(x, y)
                        .polygon(6, NUT_TRAP_AF / math.cos(math.radians(30))).extrude(NUT_TRAP_D)
                        .rotate((x, y, 0), (x, y, 1), a))
    assert body.val().isValid(), "pusher solid is invalid"
    return body


if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    part = build()
    cq.exporters.export(part, str(out / "plunger_pusher.step"))
    # Print upside down (top face on the bed): the pad pocket then only overhangs ~4 mm
    # instead of bridging ~36 mm over the pocket.
    flipped = part.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, H))
    bbz = flipped.val().BoundingBox().zmin
    flipped = flipped.translate((0, 0, -bbz))
    cq.exporters.export(flipped, str(out / "plunger_pusher.stl"), tolerance=0.02, angularTolerance=0.1)
    bb = part.val().BoundingBox()
    print(f"pusher bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}  vol {part.val().Volume()/1000:.1f} cm3")
