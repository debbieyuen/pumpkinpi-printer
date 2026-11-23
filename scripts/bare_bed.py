"""Print the card straight on the bare bed (no paper). Back to paper: python3 scripts/paper_6x9.py

Creality's filament table (https://store.creality.com/uk/blogs/basics/creality-filaments-parameter-reference-table):
Ender-PLA nozzle 200 C, bed 50 C. Normal first layer (0.2 mm, 100 % flow, no paper to soak into), fan off on
layer 1, 3 layers so the letters are stiff enough to peel off in one piece. paper_mm 0: the prime line is on the
same surface as the print. The measured paper thickness is kept in paper_measured for paper_6x9.py.
"""
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "machine.json"
if not path.exists():
    shutil.copy(ROOT / "machine.example.json", path)
data = json.loads(path.read_text())
pla = data.setdefault("pla", {})
if pla.get("paper_mm"):
    pla["paper_measured"] = pla["paper_mm"]
pla.update({"surface": "bed", "bed": 50, "nozzle": 210, "paper_mm": 0.0, "first_z": 0.2, "first_flow": 1.0,
            "first_feed": 1200, "layers": 3, "z_adjust": 0.0})
path.write_text(json.dumps(data, indent=1) + "\n")
print("machine.json pla: bare bed, bed 50 C, nozzle 210 C, 3 layers. Nothing on the bed. Back to paper: python3 scripts/paper_6x9.py")
