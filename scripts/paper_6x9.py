"""Card settings for 6 x 9 in, 140 lb (300 g/m2) watercolor paper, from Callum Coles' paper-printing video
(https://www.youtube.com/watch?v=9UiPPWbeScY): bed off, nozzle as cool as possible (190 C), fan 100 %,
masking tape on all four edges, leave a border. 9 in (228.6 mm) is longer than the 220 mm bed, so the card
hangs ~4 mm off the front and back; the drawing stays inside the bed. Run from the repo: python3 scripts/paper_6x9.py
"""
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def update(name: str, key: str, values: dict) -> None:
    path = ROOT / name
    if not path.exists():
        shutil.copy(ROOT / name.replace(".json", ".example.json"), path)
    data = json.loads(path.read_text())
    data.setdefault(key, {}).update(values)
    path.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{name} {key}: {values}")


update("cards.json", "card", {"w": 152.4, "h": 228.6, "margin": 15})
update("machine.json", "pla", {"nozzle": 190, "bed": 0, "fan": 255, "card_x": 34, "card_y": -4, "layer": 0.2, "layers": 2, "z_adjust": 0.0})
print("Now: tape all 4 edges, front-left corner at X34 Y-4 (4 mm in front of the bed edge). The printer finds the paper itself when it homes.")
