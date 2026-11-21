"""Small PumpkinPi parts: fit test tab, pie locator, camera stand + holder, display feet.

All exported in print orientation (flat face down).
"""
from pathlib import Path
import math
import cadquery as cq
import carriage as C

OUT = Path(__file__).parent / "out"


def box(x0, x1, y0, y1, z0, z1):
    return C.box(x0, x1, y0, y1, z0, z1)


def fit_test():
    """Just the bracket's head-mounting area. Print first (~10 min) and bolt it on."""
    zs = [z for _, z in C.HOLES]
    p = box(C.X0, C.X1, *C.SPINE_Y, min(zs) - 9, max(zs) + 9)
    for (y, z) in C.HOLES:
        p = p.cut(cq.Workplane("YZ").workplane(offset=C.X0 - 1).center(y, z)
                  .circle(C.HOLE_D / 2).extrude(C.SPINE_T + 2))
        p = p.cut(cq.Workplane("YZ").workplane(offset=C.X1 - C.CBORE_DEPTH).center(y, z)
                  .circle(C.CBORE_D / 2).extrude(5))
    return C.for_printing(p)


def pie_locator(pan_d=152.4, wall=4.0, h=12.0):
    """90-degree V stop for 6-inch pie pans. Tape it to the bed; push the pan into the V.
    Pan centre sits on the V's centre line, pan_radius * sqrt(2) from the inside corner."""
    arm = pan_d / 2 + 20
    pts_in = [(0, 0), (arm * math.cos(math.radians(45)), arm * math.sin(math.radians(45)))]
    def arm_solid(sign):
        a = math.radians(90 - 45 * sign) if False else math.radians(45 if sign > 0 else 135)
        return (cq.Workplane("XY").rect(arm, wall, centered=(False, True)).extrude(h)
                .union(cq.Workplane("XY").rect(arm, wall + 14, centered=(False, False))
                       .extrude(2).translate((0, -wall / 2 - 14 if sign > 0 else wall / 2, 0)))
                .rotate((0, 0, 0), (0, 0, 1), math.degrees(a)))
    v = arm_solid(1).union(arm_solid(-1))
    v = v.union(cq.Workplane("XY").circle(wall * 1.2).extrude(h))
    # centre-line notch on top of each arm end so the camera/eye can line it up
    return v


def camera_post(h=110.0):
    base = box(-30, 30, -22, 30, 0, 4)
    post = box(-8, 8, 12, 24, 0, h)
    fork = box(-8, -3, 12, 24, h, h + 14).union(box(3, 8, 12, 24, h, h + 14))
    p = base.union(post).union(fork)
    # teardrop pivot hole (point up) so it prints without support
    k = 1.7 / math.sqrt(2)
    hole = (cq.Workplane("YZ").workplane(offset=-10).center(18, h + 8).circle(1.7).extrude(20)
            .union(cq.Workplane("YZ").workplane(offset=-10)
                   .polyline([(18 + k, h + 8 + k), (18, h + 8 + 1.7 * math.sqrt(2)),
                              (18 - k, h + 8 + k), (18, h + 8)]).close().extrude(20)))
    p = p.cut(hole)
    return p


def camera_holder():
    """Camera Module 3 (25 x 23.86 mm PCB) slides in from the bottom; ribbon exits the bottom.
    Tab bolts into the post's fork with an M3x20 + nut; loosen to tilt."""
    w_in, back_t, side_w, depth = 23.0, 2.0, 3.0, 6.5
    groove_z, groove_w, groove_d = back_t + 3.0, 1.4, 1.3
    L = 30.0
    p = box(-(w_in / 2 + side_w), w_in / 2 + side_w, 0, L, 0, back_t)
    for s in (-1, 1):
        x0 = s * w_in / 2 if s > 0 else -(w_in / 2 + side_w)
        p = p.union(box(x0, x0 + side_w, 0, L, 0, depth))
    p = p.union(box(-(w_in / 2 + side_w), w_in / 2 + side_w, L - 2, L, 0, depth))   # top stop
    # grooves for the PCB edges
    p = p.cut(box(-(w_in / 2 + groove_d), w_in / 2 + groove_d, -1, L - 2,
                  groove_z, groove_z + groove_w))
    # pivot tab (fits the 6 mm fork gap)
    tab = box(-2.8, 2.8, L - 10, L + 12, 0, back_t + 2)
    tab = tab.cut(cq.Workplane("XY").center(0, L + 6).circle(1.7).extrude(10))
    return p.union(tab)


def display_foot():
    """Two of these hold Touch Display 2 (5 in, 143.5 x 91.5 x 16 mm) by its short ends,
    leaning back 15 degrees. The Pi on the back sits between the feet."""
    base = box(0, 22, -25, 35, 0, 4)
    block = box(0, 22, -10, 22, 0, 32)
    slot = (cq.Workplane("XY").box(30, 18.0, 60).translate((11, 0, 34))
            .rotate((11, 0, 4), (1, 0, 0), -15))
    return base.union(block).cut(slot)


def export(name, part):
    cq.exporters.export(part, str(OUT / f"{name}.stl"), tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(part, str(OUT / f"{name}.step"))
    bb = part.val().BoundingBox()
    print(f"{name}: {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}  vol {part.val().Volume()/1000:.1f} cm3")
    return part


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    export("fit_test", fit_test())
    export("pie_locator", pie_locator())
    export("camera_post", camera_post())
    export("camera_holder", camera_holder())
    export("display_foot", display_foot())
