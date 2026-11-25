"""Hero render of the syringe add-on on the print head: python3 cad/render_vtk.py -> out/assembly.png

Uses VTK (installed with CadQuery) so parts hide each other properly and the barrel is see-through.
Needs the reference STEP files in cad/reference/ (see cad/reference/README.md). Headless machines
need an EGL or OSMesa library (Debian/Ubuntu: sudo apt install libegl1 libosmesa6).
"""
import sys, tempfile
from pathlib import Path
import cadquery as cq
import vtk

HERE = Path(__file__).parent; OUT = HERE / "out"
sys.path.insert(0, str(HERE))

BG = (0.965, 0.965, 0.955)  # light warm grey, so white parts still show
FILL = 50.0          # how far the stopper sits above the barrel bottom (mm), i.e. about half full


def cyl(x, y, r, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def cone(x, y, r0, r1, z0, z1):
    return cq.Workplane("XY").add(cq.Solid.makeCone(r0, r1, z1 - z0, cq.Vector(x, y, z0)))


def parts():
    import carriage as C, plunger_pusher as P
    from head_geometry import toolhead_solid
    from params import (BARREL_OD, FLANGE_WIDTH, FLANGE_DEPTH, FLANGE_THICK, MOTOR_W, MOTOR_LEN,
                        THUMB_PAD_D, THUMB_PAD_THICK, PLUNGER_STEM_WIDTH, PLUNGER_IN_PAST_FLANGE, LUER_Z,
                        NUT_FLANGE_D, NUT_FLANGE_THICK, NUT_BODY_D)
    sx, sy, bore = C.SX, C.SY, BARREL_OD / 2 - 1.2
    stop_z = C.BARREL_Z0 + FILL                                  # bottom of the rubber stopper
    pad_z = C.FLANGE_Z + PLUNGER_IN_PAST_FLANGE + FILL           # bottom of the thumb pad
    zp = pad_z + THUMB_PAD_THICK - P.POCKET_H                    # pusher sits on the pad
    w, t = PLUNGER_STEM_WIDTH / 2, 1.0
    fins = (C.box(sx - w, sx + w, sy - t, sy + t, stop_z + 8, pad_z)
            .union(C.box(sx - t, sx + t, sy - w, sy + w, stop_z + 8, pad_z)))
    flange = C.box(sx - FLANGE_WIDTH / 2, sx + FLANGE_WIDTH / 2, sy - FLANGE_DEPTH / 2, sy + FLANGE_DEPTH / 2,
                   C.FLANGE_Z, C.FLANGE_Z + FLANGE_THICK).edges("|Z").fillet(8)
    barrel = (cyl(sx, sy, BARREL_OD / 2, C.BARREL_Z0, C.FLANGE_Z).cut(cyl(sx, sy, bore, C.BARREL_Z0 + 1.5, C.FLANGE_Z + 1))
              .union(flange.cut(cyl(sx, sy, bore, C.FLANGE_Z - 1, C.FLANGE_Z + 5)))
              .union(cone(sx, sy, 2.2, 4.5, LUER_Z, C.BARREL_Z0 + 0.5)))
    mz0 = C.MOTOR_PLATE_TOP - C.MOTOR_PLATE_T
    return [
        ("head", toolhead_solid(), (0.62, 0.63, 0.65), 1.0),
        ("carriage", C.build(), (0.95, 0.47, 0.10), 1.0),
        ("pusher", P.build().translate((sx, sy, zp)), (0.95, 0.47, 0.10), 1.0),
        ("nut", cyl(C.MX, C.MY, NUT_FLANGE_D / 2, zp + P.H, zp + P.H + NUT_FLANGE_THICK)
                .union(cyl(C.MX, C.MY, NUT_BODY_D / 2, zp + P.H, zp + P.H + 12))
                .cut(cyl(C.MX, C.MY, 4.2, zp, zp + P.H + 20)), (0.80, 0.62, 0.25), 1.0),
        ("motor", C.box(C.MX - MOTOR_W / 2, C.MX + MOTOR_W / 2, C.MY - MOTOR_W / 2, C.MY + MOTOR_W / 2,
                        mz0 - MOTOR_LEN, mz0).edges("|Z").fillet(3), (0.12, 0.12, 0.13), 1.0),
        ("coupler", cyl(C.MX, C.MY, 10, C.MOTOR_PLATE_TOP + 1, C.MOTOR_PLATE_TOP + 26), (0.78, 0.79, 0.82), 1.0),
        ("screw", cyl(C.MX, C.MY, 4, C.MOTOR_PLATE_TOP + 14, C.MOTOR_PLATE_TOP + 164), (0.70, 0.71, 0.74), 1.0),
        ("plunger", fins.union(cyl(sx, sy, THUMB_PAD_D / 2, pad_z, pad_z + THUMB_PAD_THICK)), (0.93, 0.93, 0.90), 1.0),
        ("stopper", cyl(sx, sy, bore - 0.2, stop_z, stop_z + 8), (0.15, 0.15, 0.16), 1.0),
        ("filling", cyl(sx, sy, bore - 0.3, C.BARREL_Z0 + 1.5, stop_z), (0.24, 0.12, 0.06), 1.0),
        ("tip", cone(sx, sy, 0.9, 3.8, LUER_Z - 30, LUER_Z + 4), (0.30, 0.55, 0.90), 1.0),
        ("barrel", barrel, (0.86, 0.93, 1.0), 0.2),
    ]


def actor(wp, color, opacity):
    f = tempfile.NamedTemporaryFile(suffix=".stl", delete=False).name
    cq.exporters.export(wp, f, tolerance=0.05, angularTolerance=0.1)
    rd = vtk.vtkSTLReader(); rd.SetFileName(f)
    nm = vtk.vtkPolyDataNormals(); nm.SetInputConnection(rd.GetOutputPort()); nm.SetFeatureAngle(35)
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(nm.GetOutputPort())
    a = vtk.vtkActor(); a.SetMapper(m)
    p = a.GetProperty(); p.SetColor(*color); p.SetOpacity(opacity)
    p.SetAmbient(0.35); p.SetDiffuse(0.8); p.SetSpecular(0.25 if opacity == 1 else 0.6); p.SetSpecularPower(30)
    return a


def render(path, size=(1400, 1600), azim=35, elev=12, zoom=1.0):
    ren = vtk.vtkRenderer(); ren.SetBackground(*BG)
    ren.SetUseDepthPeeling(1); ren.SetMaximumNumberOfPeels(12); ren.SetOcclusionRatio(0.0)
    for _, wp, col, op in parts():
        ren.AddActor(actor(wp, col, op))
    win = vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetAlphaBitPlanes(1); win.SetMultiSamples(0)
    win.AddRenderer(ren); win.SetSize(*size)
    ren.ResetCamera()
    cam = ren.GetActiveCamera(); cam.SetViewUp(0, 0, 1)
    fp = cam.GetFocalPoint(); d = cam.GetDistance()
    cam.SetPosition(fp[0], fp[1] - d, fp[2]); cam.Azimuth(azim); cam.Elevation(elev); cam.OrthogonalizeViewUp()
    ren.ResetCamera(); cam.Zoom(zoom)
    kit = vtk.vtkLightKit(); kit.SetKeyLightIntensity(0.8); kit.SetKeyToFillRatio(2.0); kit.AddLightsToRenderer(ren)
    fxaa = 1
    ren.SetUseFXAA(fxaa)
    win.Render()
    grab = vtk.vtkWindowToImageFilter(); grab.SetInput(win); grab.SetScale(1); grab.ReadFrontBufferOff(); grab.Update()
    w = vtk.vtkPNGWriter(); w.SetFileName(str(path)); w.SetInputConnection(grab.GetOutputPort()); w.Write()
    crop(path)


def crop(path, pad=40):
    """Trim the white border so the parts fill the picture."""
    from PIL import Image, ImageChops
    im = Image.open(path).convert("RGB")
    box = ImageChops.difference(im, Image.new("RGB", im.size, tuple(round(c * 255) for c in BG))).getbbox()
    if box:
        x0, y0, x1, y1 = box
        im = im.crop((max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, im.width), min(y1 + pad, im.height)))
    im.save(path)


def views(path=OUT / "assembly.png"):
    """Front-right and back-right views side by side."""
    from PIL import Image
    shots = []
    for k, az in enumerate((35, 150)):
        f = OUT / f"_view{k}.png"; render(f, azim=az); shots.append(Image.open(f).convert("RGB"))
    h = max(s.height for s in shots); gap = 60
    out = Image.new("RGB", (sum(s.width for s in shots) + gap, h), tuple(round(c * 255) for c in BG))
    x = 0
    for s in shots:
        out.paste(s, (x, h - s.height)); x += s.width + gap
    out.save(path)
    for k in range(len(shots)):
        (OUT / f"_view{k}.png").unlink()
    print(path)


if __name__ == "__main__":
    views()
