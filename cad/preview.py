"""Line-drawing previews of a part:  python3 cad/preview.py plunger_pusher"""
import sys, importlib
from pathlib import Path
import cadquery as cq, cairosvg
from PIL import Image

def preview(module_name):
    here = Path(__file__).parent; sys.path.insert(0, str(here))
    part = importlib.import_module(module_name).build()
    ims = []
    for name, d in [("top", (1, -1.2, 0.9)), ("bottom", (1, -1.2, -0.9))]:
        svg = f"/tmp/{module_name}_{name}.svg"; png = svg.replace(".svg", ".png")
        cq.exporters.export(part, svg, opt={"width": 700, "height": 450, "projectionDir": d,
                            "showHidden": False, "strokeWidth": 0.4, "marginLeft": 40, "marginTop": 20})
        cairosvg.svg2png(url=svg, write_to=png, background_color="white", output_width=700)
        ims.append(Image.open(png).convert("RGB"))
    out = Image.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims)), "white"); x = 0
    for i in ims: out.paste(i, (x, 0)); x += i.width
    dest = here / "out" / f"{module_name}.png"; out.save(dest); print(dest)

if __name__ == "__main__":
    preview(sys.argv[1] if len(sys.argv) > 1 else "plunger_pusher")
