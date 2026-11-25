"""Labelled parts sheet: python3 cad/render_parts.py -> renders/syringe_parts.png

Carriage v1.2 and plunger pusher v0.6 (VTK views with callouts), the v0.6 pocket direction
seen from above, and the plateA3 bed layout (needs out/plate_A_syringe.stl from plate.py).
Headless Linux needs an EGL or OSMesa library (sudo apt install libegl1 libosmesa6).
"""
import math, sys
from pathlib import Path
import numpy as np
import cadquery as cq
import vtk
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle, Polygon

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import carriage as C, plunger_pusher as P
from params import M3_NUT_AF, NUT_HOLE_PCD, NUT_FLANGE_D, NUT_FLANGE_THICK, NUT_BODY_D
from render_vtk import actor, cyl

ORANGE = (0.95, 0.47, 0.10)
BG = (1.0, 1.0, 1.0)
BOX = dict(boxstyle="round,pad=0.35", fc="white", ec="0.6", lw=0.8)
ARROW = dict(arrowstyle="-|>", color="0.25", lw=0.9, shrinkA=0, shrinkB=2)


def shot(parts, direction, points, size=(1100, 900), zoom=1.0, pad=30):
    """Render parts seen from `direction`; return the cropped image and the 2D pixel spots of `points`."""
    ren = vtk.vtkRenderer(); ren.SetBackground(*BG)
    for wp, col, op in parts:
        ren.AddActor(actor(wp, col, op))
    win = vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetMultiSamples(0)
    win.AddRenderer(ren); win.SetSize(*size)
    ren.ResetCamera()
    cam = ren.GetActiveCamera(); fp = cam.GetFocalPoint(); d = cam.GetDistance()
    n = np.array(direction, float); n /= np.linalg.norm(n)
    cam.SetPosition(*(np.array(fp) + n * d))
    cam.SetViewUp(0, 0, 1 if abs(n[2]) < 0.95 else 0); cam.OrthogonalizeViewUp()
    ren.ResetCamera(); cam.Zoom(zoom)
    kit = vtk.vtkLightKit(); kit.SetKeyLightIntensity(0.85); kit.AddLightsToRenderer(ren)
    ren.SetUseFXAA(1); win.Render()
    grab = vtk.vtkWindowToImageFilter(); grab.SetInput(win); grab.ReadFrontBufferOff(); grab.Update()
    img = grab.GetOutput(); w, h, _ = img.GetDimensions()
    from vtk.util.numpy_support import vtk_to_numpy
    arr = vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w, -1)[::-1, :, :3]
    pts = []
    for p in points:
        c = vtk.vtkCoordinate(); c.SetCoordinateSystemToWorld(); c.SetValue(*p)
        x, y = c.GetComputedDoubleDisplayValue(ren); pts.append((x, h - y))
    mask = np.any(arr < 250, axis=2); ys, xs = np.where(mask)
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, w); y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, h)
    return arr[y0:y1, x0:x1], [(x - x0, y - y0) for x, y in pts]


def show(ax, img, title):
    ax.imshow(img); ax.set_title(title, fontsize=12, fontweight="bold", pad=22); ax.axis("off")


def note(ax, xy, text, at, ha="left"):
    ax.annotate(text, xy=xy, xytext=at, textcoords="axes fraction", fontsize=8.5, ha=ha, va="center",
                bbox=BOX, arrowprops=ARROW)


def hexnut(x, y, z0, z1, ang):
    r = (M3_NUT_AF / 2) / math.cos(math.radians(30))
    return (cq.Workplane("XY").workplane(offset=z0).center(x, y).polygon(6, 2 * r)
            .circle(1.6).extrude(z1 - z0).rotate((x, y, 0), (x, y, 1), ang))


def section(stl, z):
    """Outer outlines and holes of a mesh cut at height z, in the mesh's own X/Y."""
    import trimesh
    m = trimesh.load(stl); s = m.section(plane_origin=(0, 0, z), plane_normal=(0, 0, 1))
    polys = s.to_2D(to_2D=np.eye(4))[0].polygons_full
    return [np.asarray(p.exterior.coords) for p in polys], [np.asarray(i.coords) for p in polys for i in p.interiors]


def main(path=HERE / "renders" / "syringe_parts.png"):
    fig, axs = plt.subplots(2, 3, figsize=(18, 11.5), gridspec_kw=dict(hspace=0.12, wspace=0.05))
    fig.suptitle("PumpkinPi syringe parts: carriage v1.2 + plunger pusher v0.6 (plateA3.gcode)", fontsize=16)

    # 1. carriage, front-right
    car = C.build()
    (hy1, hz1), (hy2, hz2) = C.HOLES
    img, p = shot([(car, ORANGE, 1)], (1, -0.9, 0.55),
                  [(C.SX + 18, C.SY, C.FLANGE_Z + 2), (C.SX + C.R_BORE + 2, C.SY, 60),
                   (C.MX + 12, C.MY - 12, C.MOTOR_PLATE_TOP), (C.SX, C.SY - 8, C.TOP_Z)])
    ax = axs[0, 0]; show(ax, img, "Carriage v1.2")
    note(ax, p[0], "Flange slot: the syringe\nflange slides in from the side", (0.58, 0.99))
    note(ax, p[1], "Barrel clip: snaps around\nthe barrel", (0.72, 0.30))
    note(ax, p[2], "Motor plate: 4x M3x8,\nscrew heads clear walls by 3 mm", (0.02, 0.12))
    note(ax, p[3], "Stem slot for\nthe plunger", (0.02, 0.92))

    # 2. carriage, head side
    img, p = shot([(car, ORANGE, 1)], (-1, -0.35, 0.15),
                  [(C.X0, hy1, hz1), (C.X0, hy2, hz2)])
    ax = axs[0, 1]; show(ax, img, "Carriage from the print-head side")
    for q in p:
        note(ax, q, "M2 slot, 2.5 mm, 4.6 mm head pocket.\nSlots fit hole spacing 12.5 to 14.2 mm",
             (0.60, 0.42))
    ax.text(0.5, -0.02, "Bolts to the head's side plate with 2x M2 (stock screws + 4 mm)",
            transform=ax.transAxes, ha="center", fontsize=9)

    # 3. pusher v0.6 top, with the brass nut lifted
    pus = P.build(); sy = P.SY
    nut = (cyl(0, sy, NUT_FLANGE_D / 2, P.H + 8, P.H + 8 + NUT_FLANGE_THICK)
           .union(cyl(0, sy, NUT_BODY_D / 2, P.H + 8 + NUT_FLANGE_THICK, P.H + 20))
           .cut(cyl(0, sy, 4.2, P.H, P.H + 30)))
    hole = (NUT_HOLE_PCD / 2 * math.cos(math.radians(315)), sy + NUT_HOLE_PCD / 2 * math.sin(math.radians(315)))
    img, p = shot([(pus, ORANGE, 1), (nut, (0.80, 0.62, 0.25), 1)], (-0.7, -1, 0.9),
                  [(-P.R_SYR + 2, 0, P.LIP + 1), (0, sy, P.H + 14), (hole[0], hole[1], P.H)])
    ax = axs[1, 0]; show(ax, img, "Pusher v0.6: top")
    note(ax, p[0], "Thumb-pad pocket underneath,\nopen toward the print head (-X)", (0.02, 0.92))
    note(ax, p[1], "Tr8x2 brass nut sits on top\n(shown lifted)", (0.62, 0.95))
    note(ax, p[2], "4x 3.4 mm M3\nclearance holes", (0.02, 0.12))

    # 4. pusher v0.6 bottom, nuts lifted
    pts = [(NUT_HOLE_PCD / 2 * math.cos(math.radians(a)), sy + NUT_HOLE_PCD / 2 * math.sin(math.radians(a)))
           for a in (45, 135, 225, 315)]
    nuts = None
    for x, y in pts:
        n = hexnut(x, y, -P.DROP - 9, -P.DROP - 6.6, math.degrees(math.atan2(y - sy, x)))
        nuts = n if nuts is None else nuts.union(n)
    img, p = shot([(pus, ORANGE, 1), (nuts, (0.18, 0.18, 0.2), 1)], (-1, -0.55, -1.1),
                  [(pts[0][0], pts[0][1], -P.DROP - 9), (0, sy + P.R_NUT, -P.DROP), (0, 0, 0)])
    ax = axs[1, 1]; show(ax, img, "Pusher v0.6: bottom (flipped over)")
    note(ax, p[0], "Hex nut traps: M3 nuts press in\n(shown lifted)", (0.60, 0.92))
    note(ax, p[1], "Nut lobe 3 mm thicker underneath,\nso an M3x16 reaches a full nut", (0.55, 0.10))
    note(ax, p[2], "Printed this side up:\nno supports", (0.02, 0.80))

    # 5. top-down: why v0.6 opens to -X
    ax = axs[0, 2]
    ax.set_title("Why v0.6 opens toward the head", fontsize=12, fontweight="bold")
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False).name
    cq.exporters.export(pus, tmp, tolerance=0.05, angularTolerance=0.1)
    outers, holes = section(tmp, P.LIP + 0.5)
    for o in outers:
        ax.add_patch(Polygon(o[:, :2], closed=True, fc=(1.0, 0.72, 0.45), ec=ORANGE, lw=1.5))
    for i in holes:
        ax.add_patch(Polygon(i[:, :2], closed=True, fc="white", ec=ORANGE, lw=1))
    ax.add_patch(plt.Circle((0, 0), P.POCKET_D / 2 - 1.5, fc="0.93", ec="0.5", lw=1, ls="--"))
    ax.text(0, 0, "thumb\npad", ha="center", va="center", fontsize=9, color="0.35")
    ax.plot(0, sy, "o", color="0.3", ms=4)
    r = 22
    ax.add_patch(FancyArrowPatch((r * math.cos(math.radians(35)), sy + r * math.sin(math.radians(35))),
                                 (r * math.cos(math.radians(145)), sy + r * math.sin(math.radians(145))),
                                 connectionstyle="arc3,rad=0.45",
                                 arrowstyle="-|>", mutation_scale=16, color="0.2", lw=1.4))
    ax.text(0, sy - 25, "Driving the nut down drags\nthe pusher counterclockwise", ha="center", fontsize=9)
    ax.add_patch(FancyArrowPatch((-28, 10), (-48, 10), arrowstyle="-|>", mutation_scale=16, color=(0.2, 0.4, 0.8), lw=1.6))
    ax.text(-38, 15, "print head\n(-X)", ha="center", fontsize=9, color=(0.2, 0.4, 0.8))
    ax.text(30, 0, "closed wall\ncatches the pad", ha="left", va="center", fontsize=9)
    ax.text(0, 34, "seen from above, carriage coordinates", ha="center", fontsize=8.5, color="0.4")
    ax.set_xlim(-60, 60); ax.set_ylim(-80, 40); ax.set_aspect("equal"); ax.axis("off")

    # 6. plateA3 layout
    ax = axs[1, 2]
    ax.set_title("plateA3.gcode: both parts, one print\nabout 4 h 3 min | 71 g PETG | no supports", fontsize=12, fontweight="bold")
    stl = HERE / "out" / "plate_A_syringe.stl"
    if stl.exists():
        outers, holes = section(stl, 0.2)
        for o in outers:
            ax.add_patch(Polygon(o[:, :2], closed=True, fc=(1.0, 0.72, 0.45), ec=ORANGE, lw=1))
        for i in holes:
            ax.add_patch(Polygon(i[:, :2], closed=True, fc="white", ec=ORANGE, lw=0.8))
    ax.add_patch(Rectangle((0, 0), 220, 220, fc="none", ec="0.2", lw=1.2))
    ax.set_xlim(-5, 225); ax.set_ylim(-5, 225); ax.set_aspect("equal")
    ax.set_xticks([0, 110, 220]); ax.set_yticks([0, 110, 220]); ax.tick_params(labelsize=8)
    ax.set_xlabel("first layer on the 220 x 220 mm bed (mm)", fontsize=9)

    fig.text(0.5, 0.03, "Hardware: 2x M2 socket head (stock length + 4 mm) to the print head  |  4x M3x8 for the motor  |  "
             "4x M3x16 + 4x M3 nuts for the brass nut", ha="center", fontsize=10)
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white"); print(path)


if __name__ == "__main__":
    main()
