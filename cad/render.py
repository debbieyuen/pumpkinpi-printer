"""Shaded previews: python3 cad/render.py  -> out/assembly.png, out/parts.png"""
import sys, tempfile
from pathlib import Path
import numpy as np, trimesh, cadquery as cq
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = Path(__file__).parent; OUT = HERE / "out"


def mesh(wp):
    f = tempfile.NamedTemporaryFile(suffix=".stl", delete=False).name
    cq.exporters.export(wp, f, tolerance=0.3, angularTolerance=0.4)
    return trimesh.load(f)


def draw(ax, m, color, alpha=1.0):
    tri = m.vertices[m.faces]
    n = m.face_normals
    light = np.clip(n @ np.array([0.4, -0.6, 0.7]) / 1.0, 0.15, 1)
    c = np.array(matplotlib.colors.to_rgb(color))
    cols = np.c_[np.outer(light, c) * 0.85 + 0.15 * c, np.full(len(light), alpha)]
    ax.add_collection3d(Poly3DCollection(tri, facecolors=cols, edgecolor="none"))


def setup(ax, pts, elev, azim, title):
    lo, hi = pts.min(0), pts.max(0); c = (lo + hi) / 2; r = (hi - lo).max() / 2 * 0.62
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev, azim); ax.set_axis_off(); ax.set_title(title, fontsize=11)


def assembly():
    sys.path.insert(0, str(HERE))
    import carriage as C, plunger_pusher as P
    from head_geometry import toolhead_solid
    from params import BARREL_OD, FLANGE_WIDTH, FLANGE_DEPTH, FLANGE_THICK, MOTOR_W, MOTOR_LEN
    head = mesh(toolhead_solid())
    car = mesh(C.build())
    cyl = lambda x, y, r, z0, z1: cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)
    syr = mesh(cyl(C.SX, C.SY, BARREL_OD / 2, C.BARREL_Z0, C.FLANGE_Z)
               .union(cyl(C.SX, C.SY, 3, C.BARREL_Z0 - 18, C.BARREL_Z0))
               .union(C.box(C.SX - FLANGE_WIDTH / 2, C.SX + FLANGE_WIDTH / 2, C.SY - FLANGE_DEPTH / 2,
                            C.SY + FLANGE_DEPTH / 2, C.FLANGE_Z, C.FLANGE_Z + FLANGE_THICK)))
    zp = 200.0
    plunger = mesh(cyl(C.SX, C.SY, 12, C.FLANGE_Z, zp + 5).union(cyl(C.SX, C.SY, 17, zp + 3, zp + 5)))
    mot = mesh(C.box(C.MX - MOTOR_W / 2, C.MX + MOTOR_W / 2, C.MY - MOTOR_W / 2, C.MY + MOTOR_W / 2,
                     C.MOTOR_PLATE_TOP - C.MOTOR_PLATE_T - MOTOR_LEN, C.MOTOR_PLATE_TOP - C.MOTOR_PLATE_T))
    scr = mesh(cyl(C.MX, C.MY, 4, C.MOTOR_PLATE_TOP + 14, C.MOTOR_PLATE_TOP + 164)
               .union(cyl(C.MX, C.MY, 10, C.MOTOR_PLATE_TOP + 1, C.MOTOR_PLATE_TOP + 26)))
    push = mesh(P.build().translate((C.SX, C.SY, zp)))
    fig = plt.figure(figsize=(14, 7.5))
    for k, (el, az, t) in enumerate([(18, -60, "Front-right view"), (20, 30, "Back-right view")]):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        for m, col, a in [(head, "#9a9a9a", 1), (syr, "#cfe8ff", 0.55), (plunger, "#ffffff", 0.6),
                          (mot, "#444444", 1), (scr, "#b8b8b8", 1), (car, "#f28c28", 1), (push, "#f2b028", 1)]:
            draw(ax, m, col, a)
        setup(ax, np.vstack([head.vertices, car.vertices, scr.vertices]), el, az, t)
    fig.suptitle("PumpkinPi syringe carriage on the Ender-3 V3 SE print head (grey = reference model)", fontsize=12)
    plt.tight_layout(); fig.savefig(OUT / "assembly.png", dpi=110); print(OUT / "assembly.png")


def plate():
    plates = [("A_syringe", "Plate A: carriage + pusher (print first)"),
              ("B_accessories", "Plate B: camera, display feet, pie locator")]
    fig = plt.figure(figsize=(15, 7.5))
    for k, (tag, title) in enumerate(plates):
        m = trimesh.load(OUT / f"plate_{tag}.stl")
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        draw(ax, m, "#f28c28")
        bed = trimesh.creation.box((220, 220, 0.5)); bed.apply_translation((110, 110, -0.3))
        draw(ax, bed, "#333333", 0.25)
        setup(ax, np.vstack([m.vertices, bed.vertices]), 55, -70, title)
    fig.suptitle("Two print plates on the 220 x 220 mm bed, no supports needed", fontsize=13, y=0.98)
    plt.tight_layout(rect=(0, 0, 1, 0.93)); fig.savefig(OUT / "plate.png", dpi=110); print(OUT / "plate.png")


if __name__ == "__main__":
    assembly()
    if (OUT / "plate_A_syringe.stl").exists():
        plate()
