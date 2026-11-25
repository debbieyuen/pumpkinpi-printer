"""Previews: python3 cad/render.py -> out/assembly.png (via render_vtk.py) and out/plate.png"""
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
    """The hero image now comes from render_vtk.py (proper depth sorting, see-through barrel)."""
    sys.path.insert(0, str(HERE))
    import render_vtk
    render_vtk.views()


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
