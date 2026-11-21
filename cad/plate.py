"""Lay every part on one 220 x 220 mm Ender-3 V3 SE bed and check nothing overlaps.

python3 cad/plate.py  -> out/plate_all.stl, out/plate_all.3mf, layout printed to the console.
(fit_test.stl is NOT on this plate: print it on its own first.)
"""
from pathlib import Path
import numpy as np, trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union

OUT = Path(__file__).parent / "out"
BED = 220.0
MARGIN = 5.0
GAP = 3.0

# name, file, rotate-about-Z degrees, (x, y) of the bounding-box min corner
LAYOUT = [
    ("pie_locator",   "pie_locator.stl",   0,  (30, 5)),
    ("plunger_pusher", "plunger_pusher.stl", 90, (71, 56)),
    ("carriage",      "carriage.stl",      0,  (5, 103)),
    ("camera_post",   "camera_post.stl",   0,  (110, 103)),
    ("display_foot_1", "display_foot.stl", 90, (140, 162)),
    ("display_foot_2", "display_foot.stl", 90, (140, 189)),
    ("camera_holder", "camera_holder.stl", 0,  (104, 162)),
]


def footprint(m):
    tris = m.vertices[m.faces][:, :, :2]
    polys = [Polygon(t) for t in tris if Polygon(t).area > 1e-6]
    return unary_union(polys).buffer(0)


def main():
    placed, prints = [], []
    for name, fn, rot, (x, y) in LAYOUT:
        m = trimesh.load(OUT / fn)
        if rot:
            m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(rot), (0, 0, 1)))
        lo = m.bounds[0]
        m.apply_translation((x - lo[0], y - lo[1], -lo[2]))
        fp = footprint(m)
        placed.append((name, m, fp))
        b = m.bounds
        prints.append(f"{name:15s} x {b[0][0]:6.1f}-{b[1][0]:6.1f}  y {b[0][1]:6.1f}-{b[1][1]:6.1f}  h {b[1][2]:5.1f}")
    ok = True
    for i in range(len(placed)):
        n, m, fp = placed[i]
        b = m.bounds
        if b[0][0] < MARGIN or b[0][1] < MARGIN or b[1][0] > BED - MARGIN or b[1][1] > BED - MARGIN:
            print("OFF BED:", n); ok = False
        for j in range(i + 1, len(placed)):
            if fp.buffer(GAP / 2).intersects(placed[j][2].buffer(GAP / 2)):
                print("TOO CLOSE:", n, placed[j][0]); ok = False
    print("\n".join(prints))
    print("layout OK" if ok else "layout PROBLEM")
    scene = trimesh.Scene()
    for n, m, _ in placed:
        scene.add_geometry(m, node_name=n, geom_name=n)
    scene.export(OUT / "plate_all.3mf")
    trimesh.util.concatenate([m for _, m, _ in placed]).export(OUT / "plate_all.stl")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
