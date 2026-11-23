"""Print the card straight on the bare bed (no paper). Back to paper: python3 scripts/paper_6x9.py

    python3 scripts/bare_bed.py          # PETG (the orange Creality EN-PETG that's loaded)
    python3 scripts/bare_bed.py pla      # only if you load PLA

Temperatures must match the filament in the printer. PETG at PLA temperatures (210 C, bed 50 C) barely melts: it
comes out as a stiff thread that lies on the plate without bonding, and the next travel drags it away.
PETG: same as the OrcaSlicer profile the parts printed with (Generic PETG, 240 C, bed 70 C), fan low.
PLA: Creality's filament table (https://store.creality.com/uk/blogs/basics/creality-filaments-parameter-reference-table),
Ender-PLA 200-210 C, bed 50 C.
Normal first layer (0.2 mm, 100 % flow), fan off on layer 1, 3 layers so the letters peel off in one piece.
paper_mm 0: the prime line is on the same surface as the print. The measured paper thickness is kept in
paper_measured for paper_6x9.py.
"""
import json, shutil, sys
from pathlib import Path

FILAMENTS = {
    "petg": {"nozzle": 240, "bed": 70, "fan": 90},     # fan ~35 % from layer 2: PETG bonds worse when cooled hard
    "pla": {"nozzle": 210, "bed": 50, "fan": 255},
}
kind = (sys.argv[1] if len(sys.argv) > 1 else "petg").lower()
if kind not in FILAMENTS:
    sys.exit(f"Unknown filament {kind!r}: use one of {', '.join(FILAMENTS)}")

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "machine.json"
if not path.exists():
    shutil.copy(ROOT / "machine.example.json", path)
data = json.loads(path.read_text())
pla = data.setdefault("pla", {})      # "pla" is the settings block name; it holds whichever filament is loaded
if pla.get("paper_mm"):
    pla["paper_measured"] = pla["paper_mm"]
pla.update({"surface": "bed", "filament": kind, **FILAMENTS[kind], "first_fan": 0, "paper_mm": 0.0,
            "first_z": 0.2, "first_flow": 1.0, "first_feed": 1200, "layers": 3, "z_adjust": 0.0,
            # Card text is mostly strokes under 4 mm, each printing ~0.15 mm of filament. A 1.5 mm retract and a
            # slow 4 mm lift on every one starves the start of the next stroke and drags the last one off the bed.
            # Small retract, short pause so the line sets, low hop: the string breaks instead of pulling.
            "retract": 0.8, "end_pause": 0.15, "hop": 0.8, "hop_feed": 1200})
path.write_text(json.dumps(data, indent=1) + "\n")
f = FILAMENTS[kind]
print(f"machine.json: {kind.upper()} on the bare bed, nozzle {f['nozzle']} C, bed {f['bed']} C, 3 layers. "
      "Nothing on the bed. Back to paper: python3 scripts/paper_6x9.py")
