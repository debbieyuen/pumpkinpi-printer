"""Ender-3 V3 SE print head geometry, read from Michael Hilton's reference STEP model.

Source: "Open source Ender 3 V3 SE Reference Models (.STEP FILES)" by Michael Hilton,
https://www.printables.com/model/672045 , licensed CC BY (Creative Commons Attribution).
The author describes it as a "somewhat accurate" model, so print cad/out/fit_test.stl first.

Coordinates used by every PumpkinPi part (mm):
  origin = nozzle tip, +X = toward the printer's right side, +Y = toward the back (gantry),
  +Z = up.
"""
from functools import lru_cache
from pathlib import Path
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

REF = Path(__file__).parent / "reference"


@lru_cache(None)
def _frame_and_offset():
    full = cq.importers.importStep(str(REF / "FullToolhead.step"))
    frame = cq.importers.importStep(str(REF / "Frame.step"))
    sol = full.solids().vals()
    nz = sol[3].BoundingBox()                       # brass nozzle
    tip = cq.Vector((nz.xmin + nz.xmax) / 2, (nz.ymin + nz.ymax) / 2, nz.zmin)
    fb, f22 = frame.val().BoundingBox(), sol[22].BoundingBox()
    off = cq.Vector(f22.xmin - fb.xmin, f22.ymin - fb.ymin, f22.zmin - fb.zmin) - tip
    return full, frame, tip, off


def toolhead_solid():
    """Whole reference toolhead moved into nozzle-tip coordinates."""
    full, _, tip, _ = _frame_and_offset()
    return full.translate(-tip)


def right_plate():
    """Outer face X of the right-hand side plate and its two M3 screw centres (y, z)."""
    _, frame, _, off = _frame_and_offset()
    holes = []
    for f in frame.faces().vals():
        a = BRepAdaptor_Surface(f.wrapped)
        if a.GetType() != GeomAbs_Cylinder:
            continue
        cy = a.Cylinder()
        d = cy.Axis().Direction()
        c = f.Center()
        if abs(cy.Radius() - 1.5) < 0.05 and abs(d.X()) > 0.99 and c.x > 60:
            holes.append((round(c.y + off.y, 2), round(c.z + off.z, 2)))
    holes = sorted(set(holes), key=lambda h: h[1])
    face_x = 62.89 + off.x                           # outer face of the 2.5 mm right plate
    return round(face_x, 2), holes


if __name__ == "__main__":
    print(right_plate())
