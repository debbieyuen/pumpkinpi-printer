"""Export shapes.py art and the two Hershey fonts to ui/shapes.json.

The touchscreen uses this only when it is NOT connected to the Pi (sample mode, e.g. the published
web preview), so a typed design such as "a cat with Debbie in cursive" still draws the right pie.
On the Pi the strokes always come from shapes.py + the real G-code.

    python scripts/export_ui_shapes.py
"""
import json
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from HersheyFonts import HersheyFonts  # noqa: E402

from pumpkinpi import shapes  # noqa: E402

r2 = lambda st: [[round(x, 2), round(y, 2)] for x, y in st]  # noqa: E731


def font(name: str) -> dict:
    f = HersheyFonts()
    f.load_default_font(name)
    f.normalize_rendering(10)
    ref = [list(s) for s in f.strokes_for_text("I")]
    out = {}
    for c in string.printable[:95]:
        own = [list(s) for s in f.strokes_for_text(c)]
        both = [list(s) for s in f.strokes_for_text(c + "I")]
        adv = both[-len(ref)][0][0] - ref[0][0][0]
        out[c] = {"a": round(adv, 3), "s": [r2(s) for s in own]}
    return out


data = {"shapes": {k: [r2(s) for s in getattr(shapes, k)()] for k in shapes.SHAPES if k != "text"},
        "fonts": {k: font(v) for k, v in shapes.FONTS.items()}, "max_text": shapes.MAX_TEXT, "max_r": shapes.MAX_R}
out = Path(__file__).resolve().parent.parent / "ui" / "shapes.json"
out.write_text(json.dumps(data, separators=(",", ":")))
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
