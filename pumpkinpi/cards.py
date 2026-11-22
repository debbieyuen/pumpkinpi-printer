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
def prod_name(p) -> str:
    """A product is either a plain name or {item, short, label, contains, source} with the exact label text."""
    return p["item"] if isinstance(p, dict) else p


def prod_label(p) -> dict | None:
    """The exact label we wrote down, handed to the Decider as evidence (never makes anything green alone)."""
    if not isinstance(p, dict) or not p.get("label"):
        return None
    return {"source": "recipe", "name": p["item"], "ingredients": p["label"],
            "allergens": p.get("contains") or [], "url": p.get("source")}


# What every card line answers, guest by guest. key = TERMS key, value = word printed on the card.
WATCH = {"peanut": "peanut", "tree nut": "tree nut", "sesame": "sesame", "fish": "fish"}
SESAME_RX = r"sesame|tahini|芝麻|참깨|참기름|ごま|胡麻"


def term_status(p, r: dict | None) -> dict[str, str]:
    """{"peanut": "found"|"safe"|"unsure", ...} for one product.

    found: the Decider found it, OR the exact label we wrote down lists it (contains / label words).
    safe: not found, and the Decider said safe or the label has a cited source (https) naming none.
    unsure: no source, or a "check" word (natural flavor, coconut, may contain) on the label."""
    import re
    from .allergens import name_hits
    d = p if isinstance(p, dict) else {}
    # "No addition of peanut" / "no added peanuts" is not a hit
    label = re.sub(r"\bno (addition of|added)\s+\w+", " ", d.get("label", ""), flags=re.I)
    cited = str(d.get("source") or "").startswith("https://")
    listed = set(d.get("contains") or [])
    checks = (r or {}).get("checks", {})
    out = {}
    for t in WATCH:
        v = (checks.get(TERMS[t]) or {}).get("verdict", "unsure")
        if t == "sesame":
            hit, check = bool(re.search(SESAME_RX, label, re.I)), False
        else:
            h = name_hits(label, {"peanut": "peanuts", "tree nut": "tree nuts", "fish": "fish"}[t])
            hit, check = bool(h["contains"]), bool(h["check"])
        if v == "found" or t in listed or hit:
            out[t] = "found"
        elif check and t != "peanut" and "may contain" in label.lower():
            out[t] = "found"                       # "may contain fish" counts as a NO for an allergy
        elif check or not (cited or v == "safe"):
            out[t] = "unsure"
        else:
            out[t] = "safe"
    return out


def item_lines(products: list[tuple[str, object]], results: dict[str, dict]) -> list[dict]:
    """One entry per branded product; unbranded fresh foods share one "Fresh veg + spices" entry."""
    out, fresh = [], []
    for dish, p in products:
        st = term_status(p, results.get(prod_name(p)))
        src = [p["source"]] if isinstance(p, dict) and p.get("source") else []
        if isinstance(p, dict) and p.get("brand"):
            out.append({"name": f"{p.get('tag') or dish} ({p['brand']})", "item": p["item"], "terms": st,
                        "sources": src})
        else:
            fresh.append((prod_name(p), st, src))
    if fresh:
        rank = {"found": 2, "unsure": 1, "safe": 0}
        st = {t: max((f[1][t] for f in fresh), key=rank.get) for t in WATCH}
        out.append({"name": "Fresh veg + spices", "item": ", ".join(f[0] for f in fresh), "terms": st,
                    "sources": sorted({u for f in fresh for u in f[2]})})
    for ln in out:
        ln["text"] = line_text(ln, None)
        ln["unsure"] = [WATCH[t] for t, v in ln["terms"].items() if v == "unsure"]
    return out


def line_text(ln: dict, allergies: list[str] | None) -> str:
    """"Satay (Lee Kum Kee): NO peanut, sesame"  /  "Hoisin (Lee Kum Kee): YES, sesame"  /  "Tofu (House Foods): YES".

    Without a guest's allergy list it just names what's in it ("none" if nothing)."""
    st = ln["terms"]
    has = list(dict.fromkeys(WATCH[t] for t in WATCH if st.get(t) == "found"))
    if allergies is None:
        words = ", ".join(has) or "none"
        return f"{ln['name']}: {words}" + (" (check label)" if any(v == "unsure" for v in st.values()) else "")
    if any(st.get(t) == "found" for t in allergies):
        return f"{ln['name']}: NO {', '.join(has)}"
    if any(st.get(t) == "unsure" for t in allergies):
        return f"{ln['name']}: check label"
    return f"{ln['name']}: YES" + (f", {', '.join(has)}" if has else "")


def guest_lines(cfg: dict, lines: list[dict], guest: str) -> list[dict]:
    allergies = (cfg.get("allergies") or {}).get(guest)
    return [{**ln, "text": line_text(ln, allergies)} if "terms" in ln else ln for ln in lines]


def dish_line(dish: dict, results: dict[str, dict]) -> dict:
    """Combine each product's verdicts into one printed line for the dish."""
    terms = dish.get("terms") or list(TERMS)
    found, unsure, sources = [], [], []
    for prod in map(prod_name, dish["products"]):
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
    labels: dict[str, dict | None] = {}
    for dish in cfg["menu"] + [{"name": "Sauce", "products": cfg.get("sauces", [])}]:
        for p in dish["products"]:
            prod = prod_name(p)
            labels[prod] = prod_label(p)
            for t in list(WATCH):
                if TERMS[t] not in want.setdefault(prod, []):
                    want[prod].append(TERMS[t])
    results = {}
    for prod, allergens in want.items():
            r = check_ingredient(client, prod, allergens, label=labels[prod])
            results[prod] = {"checks": {a: asdict(c) for a, c in r["checks"].items()},
                             "relevance": r.get("relevance")}
    menu = item_lines([(d["name"], p) for d in cfg["menu"] for p in d["products"]], results)
    sauces = item_lines([("Sauce", p) for p in cfg.get("sauces", [])], results)
    return [{**ln, "part": "menu"} for ln in menu] + [{**ln, "part": "sauce"} for ln in sauces]


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


def wrap(s: str, h: float, max_w: float, font: str = "print", indent: str = " ") -> list[str]:
    """Greedy word wrap so long ingredient lists keep their letter height instead of shrinking."""
    out, cur = [], ""
    for w in s.split():
        nxt = f"{cur} {w}" if cur else w
        if cur and width(text_line(nxt, h, font)) + (4 if nxt.startswith(" ") else 0) > max_w:
            out.append(cur)
            cur = indent + w
        else:
            cur = nxt
    return out + ([cur] if cur else [])


def legend(cfg: dict, guest: str) -> str:
    al = (cfg.get("allergies") or {}).get(guest)
    if not al:
        return "Lists any peanut, tree nut, sesame or fish"
    words = list(dict.fromkeys(WATCH[t] for t in al if t in WATCH))
    words = ", ".join(words[:-1]) + " or " + words[-1] if len(words) > 1 else words[0]
    return f"YES = no {words} on the label"


def sauce_rows(cfg: dict, lines: list[dict], guest: str) -> list[tuple]:
    """Back of the card: every sauce by exact brand, YES/NO for this guest, then how to hot pot."""
    card = cfg.get("card", {})
    bh = card.get("back_mm", 3.8)
    th = card.get("text_mm", 4.5)
    pitch = th * card.get("line_gap", 1.6)
    rows = [("Sauces: can I eat it?", 6, "print", True, pitch + 3)]
    sh = card.get("sauce_mm", 4.0)                            # brand names are long: one size for every sauce line
    rows += [(ln["text"], sh, "print", False, pitch) for ln in
             guest_lines(cfg, [x for x in lines if x.get("part") == "sauce"], guest)]
    if cfg.get("steps"):
        rows[-1] = rows[-1][:4] + (pitch + 5,)
        rows.append(("How to hot pot", 6, "print", True, pitch + 2))
        rows += [(t, th, "print", False, pitch) for t in cfg["steps"]]
    rows[-1] = rows[-1][:4] + (pitch + 1,)
    rows.append((legend(cfg, guest), bh, "print", True, pitch))
    return rows


def back_rows(cfg: dict) -> list[tuple]:
    """The ingredients insert: exactly what's in each dish, from the labels (a second card)."""
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    bh = card.get("back_mm", 3.6)
    pitch = bh * card.get("back_gap", 1.6)
    rows = [("Ingredients", 6, "print", True, pitch + 4)]
    for d in cfg["menu"]:
        # one line per labeled product ("Tofu: water, soybeans, calcium sulfate"); whole foods share the dish line
        whole, own = [], []
        for p in d["products"]:
            short = (p.get("short") or p["item"]) if isinstance(p, dict) else p
            if isinstance(p, dict) and p.get("tag"):
                brand = f" ({p['brand']})" if p.get("brand") else ""
                own.append(f"{p['tag']}{brand}: {short}")
            else:
                whole.append(short)
        if whole and own:
            own.append(f"Plus: {', '.join(whole)}")
        elif whole:
            own = [f"{d['name']}: {', '.join(whole)}"]
        for t in own:
            rows += [(x, bh, "print", False, pitch) for x in wrap(t, bh, W - 2 * m)]
    return rows


def draw_rows(rows: list[tuple], W: float, H: float, m: float, extra: float = 0.0) -> tuple[list[Stroke], float]:
    """Rows of (text, height, font, centered, step to next baseline), block centered top to bottom."""
    total = sum(r[4] for r in rows[:-1]) + rows[-1][1] + extra
    if total > H - 2 * m:
        raise ValueError(f"Doesn't fit the card ({total:.0f} mm of {H - 2 * m:.0f}). Use fewer dishes or smaller text.")
    y = H - (H - total) / 2 - rows[0][1]
    out: list[Stroke] = []
    for i, (txt, h, font, center, step) in enumerate(rows):
        st = fit_line(txt, h, W - 2 * m, font)
        dx = (W - width(st)) / 2 if center else m + (4 if txt.startswith(" ") else 0)
        out.extend(move(st, dx=dx, dy=y))
        if i < len(rows) - 1:
            y -= step
    return out, y


def layout_back(cfg: dict, lines: list[dict] | None = None, guest: str = "", side: str = "back") -> list[Stroke]:
    card = cfg.get("card", {})
    rows = back_rows(cfg) if side == "ingredients" else sauce_rows(cfg, lines or [], guest)
    st, _ = draw_rows(rows, card.get("w", 127.0), card.get("h", 178.0), card.get("margin", 10.0))
    return st


def layout(cfg: dict, lines: list[dict], guest: str = "", side: str = "front") -> list[Stroke]:
    """The whole card as strokes in mm. Portrait: x across the card, y from the bottom edge up.

    Fixed line pitch (baselines), block centered top to bottom, a small pumpkin under the menu."""
    from .shapes import pumpkin
    if side in ("back", "ingredients"):
        return layout_back(cfg, lines, guest, side)
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
    rows.append(("Menu", 6, "print", True, pitch + 2))
    menu = guest_lines(cfg, [x for x in lines if x.get("part", "menu") == "menu"], guest)
    rows += [(ln["text"], th, "print", False, pitch) for ln in menu]
    if menu:
        rows.append((legend(cfg, guest), 4, "print", True, 10))
    art = 16.0                                                # pumpkin height
    try:
        out, y = draw_rows(rows, W, H, m, extra=10 + art)
    except ValueError:                                        # long menu: drop the pumpkin, keep the words
        return draw_rows(rows, W, H, m)[0]
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
    ap.add_argument("--side", default="front", choices=["front", "back", "ingredients"],
                    help="front: menu YES/NO; back: sauces YES/NO + how to hot pot; ingredients: exact labels")
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
        print("\n".join(card_gcode(layout(cfg, lines, args.guest, args.side), Pla.load())))
    else:
        for ln in lines:
            print(ln["text"], "  (check:", ", ".join(ln["unsure"]) + ")" if ln["unsure"] else "")


if __name__ == "__main__":
    main()
