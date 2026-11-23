"""Measure the card's thickness with the CR Touch so the prime line on the bare bed sticks.

Z0 is the paper top (the printer homes on the card), so the bare bed left of the card is one paper-thickness
lower. This taps the paper just inside its left edge and the bare bed just left of it (same Y, 30 mm apart, so
bed tilt doesn't matter), saves the difference as pla.paper_mm in machine.json. G30 only measures; it does not
save anything to the printer. Tape the card first, nothing else on the bed.
Run: sudo systemctl stop pumpkinpi && python3 scripts/measure_paper.py && sudo systemctl start pumpkinpi
"""
import json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pumpkinpi.printer import Printer  # noqa: E402

PAPER = (45, 110)   # probe point on the card (card left edge is X34)
BARE = (15, 110)    # probe point on the bare bed


def tap(p: Printer, x: float, y: float) -> float:
    out = p.send(f"G30 X{x} Y{y}", wait_s=60)
    for ln in out:
        m = re.search(r"Bed X:.*Z:\s*(-?[\d.]+)", ln)
        if m:
            return float(m.group(1))
    sys.exit(f"No reading at X{x} Y{y}. The printer said: {out}\nProbe offset: {p.send('M851')}")


p = Printer()
p.pla_mode()
for cmd in ("M104 S0", "M140 S0", "G90", "G28"):
    p.send(cmd, wait_s=180)
print("probe offset:", p.send("M851"))
on = [tap(p, *PAPER) for _ in range(2)]
off = [tap(p, *BARE) for _ in range(2)]
p.send("G0 Z10 F600")
mm = round(sum(on) / 2 - sum(off) / 2, 2)
print(f"paper {on}  bare bed {off}  ->  paper is {mm} mm thick")
if not 0.05 <= mm <= 0.6:
    sys.exit("That doesn't look like paper (0.05-0.6 mm). Check the card is taped flat at the left edge. Not saved.")
path = ROOT / "machine.json"
if not path.exists():
    shutil.copy(ROOT / "machine.example.json", path)
data = json.loads(path.read_text())
data.setdefault("pla", {}).update(paper_mm=mm, paper_measured=mm)
path.write_text(json.dumps(data, indent=1) + "\n")
print(f"Saved pla.paper_mm = {mm}. The prime line now goes {mm} mm lower, onto the bare bed.")
