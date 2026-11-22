"""Syringe carriage v1: head bracket + syringe clamp + flange cradle + motor mount in ONE part.

Bolts to the two M2 screws on the right side plate of the Ender-3 V3 SE print head
(positions from head_geometry.py). The syringe slides out toward +X with no tools, so you can
take it off before homing/levelling.

Coordinates: nozzle tip = origin, +X right, +Y back, +Z up (see head_geometry.py).
Print orientation: lying on the flat face that touches the print head (exported that way).
"""
from pathlib import Path
import math
import cadquery as cq
from params import (BARREL_OD, BARREL_FRONT_TO_FLANGE, TIP_TO_FLANGE, FLANGE_WIDTH, FLANGE_THICK,
                    FLANGE_DEPTH, PLUNGER_STEM_WIDTH, MOTOR_W, MOTOR_HOLE_SPACING, CLEAR,
                    SYR_X, SYR_Y, LUER_Z, SCREW_DY,
                    MOTOR_SCREW_HEAD_D, MOTOR_SCREW_WALL_GAP)
from head_geometry import right_plate

PLATE_X, HOLES = right_plate()
SPINE_T = 6.0
# v1.2: the stock head screws are M2 (Debbie, 2026-11-21), so the head-mount holes are M2.
HOLE_D = 2.5                          # M2 clearance (ISO 273 medium = 2.4) + 0.1 for print shrink
CBORE_D, CBORE_DEPTH = 4.6, 2.0       # M2 socket head is 3.8 mm -> new screw = stock screw + 4 mm
HOLE_SLOT = 1.7                       # each hole is a short slot along the line between the two holes,
                                      # so the spacing can be anywhere from 12.5 mm (caliper) to 14.2 mm (model)
SPINE_Y = (-15.0, 11.0)
FLANGE_Z = LUER_Z + TIP_TO_FLANGE     # finger-side face of the flange
BARREL_Z0 = FLANGE_Z - BARREL_FRONT_TO_FLANGE
R_BORE = BARREL_OD / 2 + CLEAR
WALL = 4.0
CLIP_Z = (55.0, 65.0)                 # lower barrel clip
SNAP_W = BARREL_OD - 1.2              # clip mouth: syringe snaps in with ~0.6 mm per side
SHELF_T, LIP_T = 10.0, 4.0
SLOT_H = FLANGE_THICK + 0.6
FL_HALF_X = FLANGE_WIDTH / 2 + 0.6    # flange long axis runs along X (slides in from +X)
FL_HALF_Y = FLANGE_DEPTH / 2 + 0.6
STEM_SLOT = PLUNGER_STEM_WIDTH + 1.5
MOTOR_PLATE_T = 5.0                   # M3x8 into the motor = 3 mm of thread (drawing: 3.0 min)
MOTOR_PLATE_TOP = 126.0               # keeps coupler below the pusher at full stroke
SX, SY = SYR_X, SYR_Y
MX, MY = SYR_X, SYR_Y + SCREW_DY      # motor / lead screw axis

X0 = PLATE_X
X1 = PLATE_X + SPINE_T
SHELF_Z0 = FLANGE_Z - SHELF_T
TOP_Z = FLANGE_Z + SLOT_H + LIP_T


def box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def teardrop(x, y, r, z0, h):
    """Vertical (Z) hole of radius r with a 45-degree point toward +X (print 'up')."""
    import math
    k = r / math.sqrt(2)
    tip = (cq.Workplane("XY").workplane(offset=z0)
           .polyline([(x + k, y + k), (x + r * math.sqrt(2), y), (x + k, y - k), (x, y)]).close()
           .extrude(h))
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(h).union(tip)


def c_slot(r, mouth, z0, z1):
    """Cylinder r at the syringe axis plus a mouth opening toward +X."""
    return (cq.Workplane("XY").workplane(offset=z0).center(SX, SY).circle(r).extrude(z1 - z0)
            .union(box(SX, SX + 60, SY - mouth / 2, SY + mouth / 2, z0, z1)))


def build():
    # Spine against the head's side plate
    body = box(X0, X1, *SPINE_Y, CLIP_Z[0], TOP_Z)

    # Lower barrel clip
    ring = (cq.Workplane("XY").workplane(offset=CLIP_Z[0]).center(SX, SY)
            .circle(R_BORE + WALL).extrude(CLIP_Z[1] - CLIP_Z[0]))
    body = body.union(ring).union(box(X0, SX, SY - R_BORE - WALL, SY + R_BORE + WALL, *CLIP_Z))

    # Flange cradle (shelf + slot + lip)
    cr_x1 = SX + FL_HALF_X + 3.0
    body = body.union(box(X0, cr_x1, SY - FL_HALF_Y - 3.0, SY + FL_HALF_Y + 3.0,
                          SHELF_Z0, TOP_Z))

    # Motor plate + web up to the cradle
    # v1.1: plate margin sized so each motor screw head is >= MOTOR_SCREW_WALL_GAP from the 3 mm front rib
    s = MOTOR_HOLE_SPACING / 2
    h = max(MOTOR_W / 2 + 2.0, s + MOTOR_SCREW_HEAD_D / 2 + MOTOR_SCREW_WALL_GAP + 3.0)
    web_y0 = SY - FL_HALF_Y - 3.0 - 4.0
    # (starts at X0 so it sits on the print bed: no floating overhang when printed lying down)
    body = body.union(box(X0, MX + h, MY - h, max(MY + h, SY - FL_HALF_Y - 1.0),
                          MOTOR_PLATE_TOP - MOTOR_PLATE_T, MOTOR_PLATE_TOP))
    body = body.union(box(X0, MX + h, SY - FL_HALF_Y - 3.0 - 4.0, SY - FL_HALF_Y - 1.0,
                          MOTOR_PLATE_TOP - MOTOR_PLATE_T, TOP_Z))
    # web from motor plate back to the spine
    body = body.union(box(X0, MX - h + 0.01, SY - FL_HALF_Y - 7.0, SPINE_Y[0] + 0.01,
                          SHELF_Z0, TOP_Z))
    # gussets under the motor plate's outer corners -> keep clear of screws: thin side ribs
    # (both ribs start at X0 so they stand on the print bed; nothing floats when printed lying down)
    body = body.union(box(X0, X0 + 3.0, MY - h, SY - FL_HALF_Y - 3.0,
                          MOTOR_PLATE_TOP, MOTOR_PLATE_TOP + 10.0))       # rib along the head side
    body = body.union(box(X0, MX + h, MY - h, MY - h + 3.0,
                          MOTOR_PLATE_TOP, MOTOR_PLATE_TOP + 10.0))       # rib along the front edge

    # v1.1 guard: every motor screw head clears every wall by the required gap
    for a in (-1, 1):
        for b in (-1, 1):
            hx, hy = MX + a * s, MY + b * s
            gaps = [hx - (X0 + 3.0), hy - (MY - h + 3.0), web_y0 - hy]
            assert min(gaps) - MOTOR_SCREW_HEAD_D / 2 >= MOTOR_SCREW_WALL_GAP - 1e-6, (hx, hy, gaps)

    # --- cuts ---
    body = body.cut(c_slot(R_BORE, SNAP_W, CLIP_Z[0] - 1, CLIP_Z[1] + 1))
    body = body.cut(c_slot(R_BORE, 2 * R_BORE, SHELF_Z0 - 1, FLANGE_Z + 0.01))
    body = body.cut(box(SX - FL_HALF_X, SX + 80, SY - FL_HALF_Y, SY + FL_HALF_Y,
                        FLANGE_Z, FLANGE_Z + SLOT_H))
    body = body.cut(c_slot(STEM_SLOT / 2, STEM_SLOT, FLANGE_Z + SLOT_H - 0.01, TOP_Z + 1))

    # Motor plate holes: centre boss / shaft + 4x M3
    # Teardrop holes: the point faces +X, which is "up" when the part is printed lying down,
    # so the hole tops print as 45-degree slopes and need no support.
    zc = MOTOR_PLATE_TOP - MOTOR_PLATE_T - 1
    body = body.cut(teardrop(MX, MY, 11.6, zc, MOTOR_PLATE_T + 12))
    s = MOTOR_HOLE_SPACING / 2
    for a in (-1, 1):
        for b in (-1, 1):
            body = body.cut(teardrop(MX + a * s, MY + b * s, 1.75, zc, MOTOR_PLATE_T + 2))

    # Head screws: M2 through slots along X + head pockets on the outer (+X) face
    return cut_head_holes(body, 40)   # long pocket, so a hex key reaches in


def cut_head_holes(body, cbore_len):
    """M2 slots + head pockets. Each slot reaches HOLE_SLOT/2 toward the other hole."""
    (y1, z1), (y2, z2) = HOLES
    L = math.hypot(y2 - y1, z2 - z1)
    ang = math.degrees(math.atan2(z2 - z1, y2 - y1))
    uy, uz = (y2 - y1) / L, (z2 - z1) / L
    for (y, z), sgn in ((HOLES[0], 1), (HOLES[1], -1)):
        cy, cz = y + sgn * uy * HOLE_SLOT / 4, z + sgn * uz * HOLE_SLOT / 4
        body = body.cut(cq.Workplane("YZ").workplane(offset=X0 - 1).center(cy, cz)
                        .slot2D(HOLE_D + HOLE_SLOT / 2, HOLE_D, ang).extrude(SPINE_T + 2))
        body = body.cut(cq.Workplane("YZ").workplane(offset=X1 - CBORE_DEPTH).center(cy, cz)
                        .slot2D(CBORE_D + HOLE_SLOT / 2, CBORE_D, ang).extrude(cbore_len))
    return body


def for_printing(part):
    """Lay it on the face that touches the print head (that face down, z = 0)."""
    p = part.rotate((0, 0, 0), (0, 1, 0), -90)
    bb = p.val().BoundingBox()
    return p.translate((-bb.xmin, -bb.ymin, -bb.zmin))


if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    part = build()
    cq.exporters.export(part, str(out / "carriage_assembled_coords.step"))
    pp = for_printing(part)
    cq.exporters.export(pp, str(out / "carriage.stl"), tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(pp, str(out / "carriage.step"))
    bb = pp.val().BoundingBox()
    print(f"carriage print bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}  vol {part.val().Volume()/1000:.1f} cm3")
    print("holes", HOLES, "plate x", PLATE_X, "flange z", FLANGE_Z, "barrel z0", BARREL_Z0, "top", TOP_Z)
