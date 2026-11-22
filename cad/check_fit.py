"""Interference check: carriage vs the reference print head, plus dummy syringe/motor/coupler."""
import cadquery as cq
from head_geometry import toolhead_solid
import carriage as C
from params import *

part = C.build()
head = toolhead_solid()
worst = 0
for i, s in enumerate(head.solids().vals()):
    v = part.val().intersect(s).Volume()
    if v > 0.01:
        print(f"  overlaps head solid {i}: {v:.2f} mm3"); worst = max(worst, v)
print("head interference max", round(worst, 2))

def cyl(x, y, r, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)
barrel = cyl(C.SX, C.SY, BARREL_OD/2, C.BARREL_Z0, C.FLANGE_Z)
flange = C.box(C.SX-FLANGE_WIDTH/2, C.SX+FLANGE_WIDTH/2, C.SY-FLANGE_DEPTH/2, C.SY+FLANGE_DEPTH/2, C.FLANGE_Z, C.FLANGE_Z+FLANGE_THICK)
motor = C.box(C.MX-MOTOR_W/2, C.MX+MOTOR_W/2, C.MY-MOTOR_W/2, C.MY+MOTOR_W/2, C.MOTOR_PLATE_TOP-C.MOTOR_PLATE_T-MOTOR_LEN, C.MOTOR_PLATE_TOP-C.MOTOR_PLATE_T)
coupler = cyl(C.MX, C.MY, 10.0, C.MOTOR_PLATE_TOP+1, C.MOTOR_PLATE_TOP+26)
for name, d in [("barrel", barrel), ("flange", flange), ("motor", motor), ("coupler", coupler)]:
    print(name, "vs carriage", round(part.val().intersect(d.val()).Volume(), 2))
    hv = sum(d.val().intersect(s).Volume() for s in head.solids().vals())
    print(name, "vs head", round(hv, 2))
hb = head.val().BoundingBox()
print("head bbox", [round(v,1) for v in (hb.xmin,hb.xmax,hb.ymin,hb.ymax,hb.zmin,hb.zmax)])
