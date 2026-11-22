"""Invitation cards drawn in PLA on watercolor paper: the menu, and what's in each dish.

Every card lists the dishes, one short line each, with the allergens Perplexity found:

    Family Hot Pot
    Thu Nov 26  3 PM
    Lily
    Mushroom broth: soy, wheat
    Beef slices: none
    Sesame dip: sesame ?
    ? = ask Debbie

How each line is made (cards.json, copy cards.example.json):
  1. Every dish lists the exact products that go in it (brand + product + size).
  2. Search API finds each product's label pages; one Decider call per product answers
     "contains X?" for each term in TERMS (same gate as the pie: allergen_check.check_ingredient).
  3. A dish line names every term that came back red. Yellow (unsure) adds " ?" -> check the label.
     Nothing is ever printed as safe: a dish with no red terms says "none" plus "?" if any were unsure.

Printing (PLA, the stock hot end; the syringe stays mounted but must sit ABOVE the nozzle tip):
  prep_gcode()  heat + home with the bed EMPTY, then park at the back so you can tape the card down
  card_gcode()  the card's strokes, 1-2 thin layers, Z from the paper top you measured (pla.paper_z)
These are streamed over USB, never written to the microSD as a food file, and never run in food mode.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .shapes import FONTS, Stroke, move

ROOT = Path(__file__).resolve().parent.parent
CARDS_FILE = Path(os.environ.get("PUMPKINPI_CARDS", ROOT / "cards.json"))
MACHINE_FILE = Path(os.environ.get("PUMPKINPI_MACHINE", ROOT / "machine.json"))

# What each dish line can name. Short words, because 5 mm letters in PLA are the readable minimum.
# key = word printed on the card, value = what the Decider is asked about.
TERMS = {
    "milk": "milk",
    "egg": "eggs",
    "wheat": "wheat or gluten",
    "soy": "soy",
    "sesame": "sesame",
    "fish": "fish",
    "shellfish": "crustacean shellfish (shrimp, crab, lobster)",
    "peanut": "peanuts",
    "tree nut": "tree nuts",
    "meat": "meat, poultry or meat-derived ingredients (broth, gelatin, lard, tallow)",
    "pork": "pork or pork-derived ingredients (lard, gelatin)",
    "alcohol": "alcohol (wine, sake, mirin, alcohol-based extracts)",
}
FOUND_AT, SAFE_AT = 0.7, 0.1      # same thresholds as allergen_check


# ---------------------------------------------------------------- checks (Search + Decider)
def dish_line(dish: dict, results: dict[str, dict]) -> dict:
    """Combine each product's verdicts into one printed line for the dish."""
    terms = dish.get("terms") or list(TERMS)
    found, unsure, sources = [], [], []
    for prod in dish["products"]:
        r = results.get(prod)
        if not r:
            unsure.append(prod)
            continue
        for t in terms:
            c = r["checks"].get(TERMS[t])
            v = c["verdict"] if c else "unsure"
            if v == "found" and t not in found:
                found.append(t)
            elif v == "unsure" and t not in found and t not in unsure:
                unsure.append(t)
            if c:
                sources += [u for u in c.get("sources", [])[:2] if u not in sources]
    unsure = [u for u in unsure if u not in found]
    text = f"{dish['name']}: {', '.join(found) if found else 'none'}"
    if unsure:
        text += " ?"
    return {"name": dish["name"], "contains": found, "unsure": unsure, "text": text, "sources": sources[:6]}


def check_menu(client, cfg: dict) -> list[dict]:
    """One Search API call + one Decider call per product, then one line per dish."""
    from .allergen_check import check_ingredient
    want: dict[str, list[str]] = {}
    for dish in cfg["menu"]:
        for prod in dish["products"]:
            for t in dish.get("terms") or list(TERMS):
                if TERMS[t] not in want.setdefault(prod, []):
                    want[prod].append(TERMS[t])
    results = {}
    for prod, allergens in want.items():
            r = check_ingredient(client, prod, allergens)
            results[prod] = {"checks": {a: asdict(c) for a, c in r["checks"].items()},
                             "relevance": r.get("relevance")}
    return [dish_line(d, results) for d in cfg["menu"]]


# ---------------------------------------------------------------- layout (mm, card's front-left corner = 0,0)
def text_line(s: str, h: float, font: str = "print") -> list[Stroke]:
    """Single-stroke text, capital letters h mm tall, left edge at x=0, baseline at y=0 (descenders go below)."""
    from HersheyFonts import HersheyFonts
    if not s.strip():
        return []
    f = HersheyFonts()
    f.load_default_font(FONTS.get(font, "futural"))
    ref = [y for st in f.strokes_for_text("H") for _, y in st]
    base, k = max(ref), h / ((max(ref) - min(ref)) or 1)   # raw Hershey y points down
    st = [list(x) for x in f.strokes_for_text(s)]
    if not st:
        return []
    x0 = min(x for s_ in st for x, _ in s_)
    return [[((x - x0) * k, (base - y) * k) for x, y in s_] for s_ in st]


def width(strokes: list[Stroke]) -> float:
    xs = [x for st in strokes for x, _ in st]
    return (max(xs) - min(xs)) if xs else 0.0


def fit_line(s: str, h: float, max_w: float, font: str = "print") -> list[Stroke]:
    st = text_line(s, h, font)
    w = width(st)
    return move(st, k=max_w / w) if w > max_w else st


def layout(cfg: dict, lines: list[dict], guest: str = "") -> list[Stroke]:
    """The whole card as strokes in mm. Portrait: x across the card, y from the bottom edge up.

    Fixed line pitch (baselines), block centered top to bottom, a small pumpkin under the menu."""
    from .shapes import pumpkin
    card = cfg.get("card", {})
    W, H = card.get("w", 127.0), card.get("h", 178.0)       # 5 x 7 inch
    m = card.get("margin", 10.0)
    th = card.get("text_mm", 5.0)                             # letter height for menu lines (5 mm = readable in PLA)
    pitch = th * card.get("line_gap", 1.8)
    ev = cfg.get("event", {})
    rows = [(ev.get("title", "Thanksgiving"), 12, "cursive", True, 22)]
    if ev.get("when"):
        rows.append((ev["when"], 5, "print", True, 17))
    if guest:
        rows.append((guest, 9, "cursive", True, 18))
    rows.append(("Menu", 6, "print", True, pitch + 3))
    rows += [(ln["text"], th, "print", False, pitch) for ln in lines]
    if any(ln.get("unsure") for ln in lines):
        rows.append((ev.get("unsure_note", "? = check with host"), 4, "print", True, 10))
    art = 16.0                                                # pumpkin height
    total = sum(r[4] for r in rows[:-1]) + rows[-1][1] + 10 + art
    if total > H - 2 * m:
        raise ValueError(f"Menu doesn't fit the card: {len(lines)} lines. Use fewer dishes or a smaller text_mm.")
    y = H - (H - total) / 2 - rows[0][1]                      # first baseline
    out: list[Stroke] = []
    for i, (txt, h, font, center, step) in enumerate(rows):
        st = fit_line(txt, h, W - 2 * m, font)
        dx = (W - width(st)) / 2 if center else m
        out.extend(move(st, dx=dx, dy=y))
        if i < len(rows) - 1:
            y -= step
    out.extend(move(pumpkin(), dx=W / 2, dy=y - 10 - art / 2, k=art / 2 / 40 / 0.9))
    return out


# ---------------------------------------------------------------- PLA G-code
@dataclass
class Pla:
    nozzle: float = 205.0          # PLA nozzle temp (check your filament's range)
    bed: float = 0.0               # paper: no bed heat
    card_x: float = 15.0           # printer X/Y of the card's front-left corner (tape a corner guide there)
    card_y: float = 20.0
    paper_z: float = 0.45          # Z where the nozzle just drags a sheet of copy paper ON the card (measure!)
    layer: float = 0.25
    layers: int = 1                # 2 = raised lines you can feel
    line_w: float = 0.45
    feed: float = 900.0            # mm/min drawing
    travel: float = 6000.0
    retract: float = 0.8           # direct drive
    hop: float = 1.2
    x_min: float = 2.0
    x_max: float = 215.0
    y_min: float = 2.0
    y_max: float = 215.0
    park_x: float = 110.0          # where the head waits while you tape the card down
    park_y: float = 215.0
    park_z: float = 40.0

    @classmethod
    def load(cls, path: Path = MACHINE_FILE) -> "Pla":
        data = json.loads(path.read_text()).get("pla", {}) if path.exists() else {}
        return cls(**{k: type(getattr(cls, k))(v) for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def e_per_mm(self) -> float:
        return self.line_w * self.layer / (math.pi * (1.75 / 2) ** 2)


def prep_gcode(p: Pla) -> list[str]:
    """Bed EMPTY: heat, home, then park high at the back for taping the card down."""
    return ["M140 S0" if not p.bed else f"M140 S{p.bed:.0f}", f"M104 S{p.nozzle:.0f}", "G90", "G28",
            "M420 S1", f"G0 Z{p.park_z:.1f} F600", f"G0 X{p.park_x:.1f} Y{p.park_y:.1f} F{p.travel:.0f}",
            f"M109 S{p.nozzle:.0f}", "M117 Tape the card down"]


def card_gcode(strokes: list[Stroke], p: Pla) -> list[str]:
    out = ["G90", "M83", f"M109 S{p.nozzle:.0f}", "M106 S255"]
    for n in range(p.layers):
        z = p.paper_z + p.layer * (n + 1)
        zt = z + p.hop
        out.append(f"G0 Z{zt:.2f} F600")
        for st in strokes:
            if len(st) < 2:
                continue
            x, y = st[0]
            out += [f"G0 X{p.card_x + x:.2f} Y{p.card_y + y:.2f} F{p.travel:.0f}", f"G1 Z{z:.2f} F600",
                    f"G1 E{p.retract:.2f} F2400"]
            for (ax, ay), (bx, by) in zip(st, st[1:]):
                e = math.hypot(bx - ax, by - ay) * p.e_per_mm
                out.append(f"G1 X{p.card_x + bx:.2f} Y{p.card_y + by:.2f} E{e:.5f} F{p.feed:.0f}")
            out += [f"G1 E-{p.retract:.2f} F2400", f"G0 Z{zt:.2f} F600"]
    out += ["M104 S0", "M140 S0", "M107", f"G0 Z{p.park_z:.1f} F600",
            f"G0 X{p.park_x:.1f} Y{p.park_y:.1f} F{p.travel:.0f}", "M400", "M117 Card done"]
    check_bounds(out, p)
    return out


def check_bounds(lines: list[str], p: Pla) -> None:
    for ln in lines:
        if not ln.startswith(("G0", "G1")):
            continue
        for w in ln.split()[1:]:
            lim = {"X": (p.x_min, p.x_max), "Y": (p.y_min, p.y_max), "Z": (p.paper_z, 120.0)}.get(w[0])
            if lim and not lim[0] <= float(w[1:]) <= lim[1]:
                raise ValueError(f"{ln!r}: {w[0]} outside {lim}. Check pla.card_x/card_y/paper_z in machine.json")


def load(path: Path = CARDS_FILE) -> dict:
    p = path if path.exists() else ROOT / "cards.example.json"
    return json.loads(p.read_text())


def main() -> None:
    ap = argparse.ArgumentParser(description="Menu invitation cards in PLA.")
    ap.add_argument("--check", action="store_true", help="run Search + Decider on every product (needs the API key)")
    ap.add_argument("--guest", default="", help="name printed on the card")
    ap.add_argument("--gcode", action="store_true", help="print the card's G-code")
    args = ap.parse_args()
    cfg = load()
    if args.check:
        from .pplx import make_client
        with make_client() as c:
            lines = check_menu(c, cfg)
        Path("captures").mkdir(exist_ok=True)
        Path("captures/menu_check.json").write_text(json.dumps(lines, indent=2))
    elif Path("captures/menu_check.json").exists():
        lines = json.loads(Path("captures/menu_check.json").read_text())
    else:
        raise SystemExit("Run with --check first")
    if args.gcode:
        print("\n".join(card_gcode(layout(cfg, lines, args.guest), Pla.load())))
    else:
        for ln in lines:
            print(ln["text"], "  (check:", ", ".join(ln["unsure"]) + ")" if ln["unsure"] else "")


if __name__ == "__main__":
    main()
