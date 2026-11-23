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
  card_gcode()  one standalone file: bed off, 190 C, home ON the taped card (CR Touch at the bed center,
                so Z0 = paper top), prime off the card, 2 thin layers, fan 100 %. Saved to the microSD and
                started from the printer's own screen. Paper only on the bed: never food.
"""
from __future__ import annotations

import re
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
    if not isinstance(p, dict) or not (p.get("label") or p.get("ingredients")):
        return None
    return {"source": "recipe", "name": p["item"], "ingredients": p.get("label") or p["ingredients"],
            "allergens": p.get("contains") or [], "url": p.get("source") or p.get("label_url")}


# What every card line answers, guest by guest. key = TERMS key, value = word printed on the card.
WATCH = {"peanut": "peanut", "tree nut": "tree nut", "sesame": "sesame", "fish": "fish"}
SESAME_RX = r"sesame|tahini|芝麻|참깨|참기름|ごま|胡麻"


# Single-ingredient whole foods. None of them is (or contains) a peanut, tree nut, fish or sesame, which are
# FDA major food allergens named on their own: https://www.fda.gov/food/buy-store-serve-safe-food/food-allergies-what-you-need-know
WHOLE_SRC = "https://www.fda.gov/food/buy-store-serve-safe-food/food-allergies-what-you-need-know"
WHOLE = {"salt", "egg", "eggs", "garlic", "onion", "onions", "shallot", "shallots", "lamb", "beef", "pork", "chicken",
         "turkey", "potato", "potatoes", "carrot", "carrots", "celery", "lemon", "lemons", "lime", "limes", "apple",
         "apples", "squash", "ginger", "scallion", "scallions", "thyme", "rosemary", "sage", "parsley", "water",
         "milk", "cream", "sugar"}


def is_whole(p) -> bool:
    """True for one plain food, named last ("Diamond Crystal Kosher Salt", "Vital Farms Large Eggs",
    "Bone-in leg of lamb"). Not "garlic powder", "egg noodles", "salted caramel" or anything with a multi-part label."""
    import re
    name = prod_name(p).lower()
    label = p.get("label", "") if isinstance(p, dict) else ""
    words = re.findall(r"[a-z]+", re.split(r",| - | – ", re.sub(r"\(.*?\)", " ", name))[0])
    while words and words[-1] in {"ct", "count", "oz", "lb", "lbs", "g", "kg", "dozen", "pack", "box", "bag",
                                  "jar", "carton", "fl", "large", "medium", "small", "whole", "fresh"}:
        words.pop()          # "Large Eggs 12 ct", "Kosher Salt 3 lb box"
    return bool(words) and words[-1] in WHOLE and "," not in label


def term_status(p, r: dict | None) -> dict[str, str]:
    """{"peanut": "found"|"safe"|"unsure", ...} for one product.

    found: the Decider found it, OR the exact label we wrote down lists it (contains / label words).
    safe: not found, and the Decider said safe or the label has a cited source (https) naming none.
    unsure: no source, or a "check" word (natural flavor, coconut, may contain) on the label."""
    import re
    from .allergens import name_hits
    d = p if isinstance(p, dict) else {}
    # "No addition of peanut" / "no added peanuts" is not a hit
    label = re.sub(r"\bno (addition of|added)\s+\w+", " ", d.get("label") or d.get("ingredients") or "", flags=re.I)
    cited = str(d.get("source") or "").startswith("https://")
    listed = set(d.get("contains") or [])
    checks = (r or {}).get("checks", {})
    whole = is_whole(p)
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
        elif whole and not name_hits(prod_name(p), {"peanut": "peanuts", "tree nut": "tree nuts",
                                                    "fish": "fish"}.get(t, t))["contains"]:
            out[t] = "safe"                         # plain salt, eggs, lamb...: not a nut, peanut, fish or sesame (FDA)
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
        src = [p[k] for k in ("source", "label_url") if isinstance(p, dict) and p.get(k)]   # shown, not "cited"
        for c in ((results.get(prod_name(p)) or {}).get("checks") or {}).values():   # Search API links per allergen
            src += [u for u in (c.get("sources") or []) if u and u not in src]
        src = ([WHOLE_SRC] if is_whole(p) else []) + src[:4]
        if isinstance(p, dict) and p.get("brand"):
            out.append({"name": p.get("card") or f"{p.get('tag') or dish} ({p['brand']})", "item": p["item"], "brand": p["brand"], "terms": st,
                        "sources": src})
        else:
            fresh.append((prod_name(p), st, src))
    if fresh:
        rank = {"found": 2, "unsure": 1, "safe": 0}
        st = {t: max((f[1][t] for f in fresh), key=rank.get) for t in WATCH}
        out.append({"name": "Fresh veg + spices", "item": ", ".join(f[0] for f in fresh), "terms": st,
                    "sources": sorted({u for f in fresh for u in f[2]}),
                    "each": [{"name": f[0][:1].upper() + f[0][1:], "terms": f[1]} for f in fresh]})
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
    dessert = [cfg["dessert"]] if cfg.get("dessert") else []
    more = [{"name": "More", "products": cfg.get("more", []) + cfg.get("examples", [])}]
    for dish in cfg["menu"] + dessert + more + [{"name": "Sauce", "products": cfg.get("sauces", [])}]:
        for p in dish["products"]:
            prod = prod_name(p)
            labels[prod] = prod_label(p)
            for t in list(WATCH):
                if TERMS[t] not in want.setdefault(prod, []):
                    want[prod].append(TERMS[t])
    from concurrent.futures import ThreadPoolExecutor

    def one(prod: str) -> dict:
        r = check_ingredient(client, prod, want[prod], label=labels[prod])
        return {"checks": {a: asdict(c) for a, c in r["checks"].items()}, "relevance": r.get("relevance")}
    with ThreadPoolExecutor(4) as ex:            # 4 products at a time: Search + Decider each
        results = dict(zip(want, ex.map(one, want)))
    menu = item_lines([(d["name"], p) for d in cfg["menu"] for p in d["products"]], results)
    sauces = item_lines([("Sauce", p) for p in cfg.get("sauces", [])], results)
    sweet = item_lines([(d["name"], p) for d in dessert for p in d["products"]], results)
    extra = item_lines([("More", p) for p in cfg.get("more", [])], results)
    examples = item_lines([("Example", p) for p in cfg.get("examples", [])], results)   # chart only, never printed
    return ([{**ln, "part": "menu"} for ln in menu] + [{**ln, "part": "dessert"} for ln in sweet]
            + [{**ln, "part": "more"} for ln in extra]
            + [{**ln, "part": "example"} for ln in examples]
            + [{**ln, "part": "sauce"} for ln in sauces])


# ---------------------------------------------------------------- layout (mm, card's front-left corner = 0,0)
def text_line(s: str, h: float, font: str = "print") -> list[Stroke]:
    """Single-stroke text, capital letters h mm tall, left edge at x=0, baseline at y=0 (descenders go below)."""
    from HersheyFonts import HersheyFonts
    import unicodedata
    # The Hershey fonts have no accented letters and silently drop them ("Nestlé" -> "Nestl"): print the plain
    # letter instead (é -> e, ñ -> n).
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
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
    """Every sauce by exact brand, YES/NO for this guest."""
    card = cfg.get("card", {})
    sh = card.get("sauce_mm", 3.6)
    pitch = sh * card.get("back_gap", 1.5)
    rows = [("Sauces: can I eat it?", 5.5, "print", True, pitch + 3)]
    rows += [(ln["text"], sh, "print", False, pitch) for ln in
             guest_lines(cfg, [x for x in lines if x.get("part") == "sauce"], guest)]
    rows[-1] = rows[-1][:4] + (pitch + 1,)
    rows.append((legend(cfg, guest), 3.2, "print", True, pitch))
    return rows


def back_rows(cfg: dict) -> list[tuple]:
    """The ingredients insert: exactly what's in each dish, from the labels (a second card)."""
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    bh = card.get("back_mm", 3.6)
    pitch = bh * card.get("back_gap", 1.6)
    rows = [("Ingredients", 5.5, "print", True, pitch + 3)]
    fresh = []
    for d in cfg["menu"]:
        # one line per labeled product ("Tofu (House Foods): water, soybeans, calcium sulfate");
        # unbranded fresh foods (water, ginger, napa...) share one "Fresh" line at the end
        for p in d["products"]:
            short = (p.get("short") or p["item"]) if isinstance(p, dict) else p
            if isinstance(p, dict) and p.get("tag"):
                brand = f" ({p['brand']})" if p.get("brand") else ""
                rows += [(x, bh, "print", False, pitch) for x in wrap(f"{p['tag']}{brand}: {short}", bh, W - 2 * m)]
            elif short not in fresh:
                fresh.append(short)
    if fresh:
        rows += [(x, bh, "print", False, pitch) for x in wrap(f"Fresh: {', '.join(fresh)}", bh, W - 2 * m)]
    if cfg.get("dessert") and card.get("back_dessert", False):
        # pie: multi-ingredient labels get their own line, one-ingredient items share a line
        rows[-1] = rows[-1][:4] + (pitch + 2,)
        rows.append((cfg["dessert"]["name"], 4.5, "print", True, pitch + 1.5))
        single = []
        for p in cfg["dessert"]["products"]:
            short = p.get("short") or p["item"]
            if "," in short:
                rows += [(x, bh, "print", False, pitch) for x in wrap(f"{p['tag']}: {short}", bh, W - 2 * m)]
            else:
                single.append(f"{p['tag']}: {short}")
        if single:
            rows += [(x, bh, "print", False, pitch) for x in wrap("; ".join(single), bh, W - 2 * m)]
    return rows


TOP = 35.0     # mm from the card's top edge to the first line on top-aligned cards


def draw_rows(rows: list[tuple], W: float, H: float, m: float, extra: float = 0.0,
              top: bool = False) -> tuple[list[Stroke], float]:
    """Rows of (text, height, font, centered, step to next baseline), block centered top to bottom
    (or starting right under the top margin with top=True)."""
    total = sum(r[4] for r in rows[:-1]) + rows[-1][1] + extra
    if total > H - 2 * m:
        raise ValueError(f"Doesn't fit the card ({total:.0f} mm of {H - 2 * m:.0f}). Use fewer dishes or smaller text.")
    # top=True starts TOP mm under the card's top edge. Not closer: that edge sits at the back of the bed, far
    # from the probe point at the bed center, and the first test card's strokes curled up in the air there.
    y = H - (max(m, TOP) if top else (H - total) / 2) - rows[0][1]
    if top and total > H - m - max(m, TOP):
        raise ValueError(f"Doesn't fit the card ({total:.0f} mm). Use fewer dishes or smaller text.")
    out: list[Stroke] = []
    for i, (txt, h, font, center, step) in enumerate(rows):
        st = fit_line(txt, h, W - 2 * m, font)
        dx = (W - width(st)) / 2 if center else m + (4 if txt.startswith(" ") else 0)
        out.extend(move(st, dx=dx, dy=y))
        if i < len(rows) - 1:
            y -= step
    return out, y


def entry_rows(cfg: dict, dishes: list[dict], lines: list[dict], guest: str) -> list[tuple]:
    """One entry per item: "Tofu (House Foods): YES" and its label ingredients right under it.

    Menu YES/NO and the ingredient list used to be printed twice (front and back); now they're merged."""
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    th = card.get("text_mm", 3.6)
    pitch = th * card.get("line_gap", 1.4)
    dh = card.get("detail_mm", 3.2)
    dp = dh * card.get("detail_gap", 1.35)
    glines = guest_lines(cfg, lines, guest)
    names = {ln["name"]: ln for ln in glines if "name" in ln}
    rows, fresh, used = [], [], set()
    for d in dishes:
        for p in d["products"]:
            short = (p.get("short") or p["item"]) if isinstance(p, dict) else p
            if isinstance(p, dict) and p.get("brand"):
                ln = names.get(f"{p.get('tag') or d['name']} ({p['brand']})")
                if ln:
                    used.add(ln["name"])
                    rows += _entry(ln["text"], short, th, pitch, dh, dp, W, m)
            elif short not in fresh:
                fresh.append(short)
    ln = names.get("Fresh veg + spices")
    if fresh and ln:
        used.add(ln["name"])
        rows += _entry(ln["text"], ", ".join(fresh), th, pitch, dh, dp, W, m)
    rows += [(ln["text"], th, "print", False, pitch) for ln in glines if ln.get("name") not in used]
    return rows


def _entry(head: str, short: str, th, pitch, dh, dp, W, m) -> list[tuple]:
    key = head.split(" (")[0].split(":")[0].lower()
    if short.lower() in (key, key.rstrip("s"), key + "s"):     # "Eggs: eggs" adds nothing
        return [(head, th, "print", False, pitch)]
    body = wrap(short, dh, W - 2 * m - 4)
    rows = [(head, th, "print", False, dh + 2.2)]
    rows += [("  " + x.strip(), dh, "print", False, dp) for x in body]
    rows[-1] = rows[-1][:4] + (pitch,)
    return rows


def section(title: str, h: float = 5.5, step: float = 8.0) -> tuple:
    return (title, h, "print", True, step)


def avoid_lines(cfg: dict, lines: list[dict], guest: str) -> list[str]:
    """Everything this guest should NOT eat: each NO (with what's in it) and each "check label".

    Unsure always counts as NO here, so nothing unchecked hides under the "Everything else is okay" line.
    A guest with no allergy list gets nothing here (their back says so instead)."""
    if not (cfg.get("allergies") or {}).get(guest):
        return []
    products = {p.get("item"): p for d in cfg.get("menu", []) + [cfg.get("dessert") or {"products": []}]
                for p in d.get("products", [])}
    products.update({p.get("item"): p for p in cfg.get("more", []) + cfg.get("sauces", [])})
    out = []
    for ln in guest_lines(cfg, lines, guest):
        t = ln.get("text", "")
        name, _, verdict = t.rpartition(": ")
        if verdict.startswith("NO"):
            out.append(f"{name}: {verdict[2:].strip() or 'no'}")
        elif verdict == "check label" or (ln.get("unsure") and not verdict.startswith("YES")):
            why = (products.get(ln.get("item")) or {}).get("why", {})   # e.g. {"tree nut": "coconut"}
            uns = ln.get("unsure") or ["?"]
            rest = [u for u in uns if u not in why]
            out.append(f"{name}: " + ", ".join([why[u] for u in uns if u in why]
                                               + ([f"may have {', '.join(rest)}"] if rest else [])))
    mine = set((cfg.get("allergies") or {}).get(guest) or [])
    for x in cfg.get("avoid_extra", []):              # e.g. "Peanut topping on pie" for peanut-allergic guests
        if mine & set(x.get("terms", [])):
            out.append(x["text"])
    return out


def short_back_rows(cfg: dict, lines: list[dict], guest: str) -> list[tuple]:
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    h = card.get("avoid_mm", 5.0)
    pitch = h * card.get("avoid_gap", 1.5)
    who = guest or "Guest"
    bad = avoid_lines(cfg, lines, guest)
    rows = [(f"{who}: don't eat", 7, "cursive" if guest else "print", True, pitch + 5)]
    if not (cfg.get("allergies") or {}).get(guest):
        rows = [(f"{who}", 7, "cursive" if guest else "print", True, pitch + 5),
                ("No food allergies on file", h, "print", True, pitch + 5)]
        rows += [(x, h * 0.85, "print", True, h * 0.85 * 1.5)
                 for x in wrap("Not sure? Check the label.", h * 0.85, W - 2 * m)]
        return rows
    if bad:
        for b in bad:
            rows += [(x, h, "print", False, pitch) for x in wrap(b, h, W - 2 * m)]
    else:
        rows.append(("Nothing on the menu", h, "print", True, pitch))
    rows[-1] = rows[-1][:4] + (pitch + 5,)
    rows += [(x, h * 0.85, "print", True, h * 0.85 * 1.5)
             for t in OK_LINES for x in wrap(t, h * 0.85, W - 2 * m)]
    return rows


def dessert_verdict(cfg: dict, lines: list[dict], guest: str) -> str:
    """One word for the whole pie: NO if any ingredient is NO, "check label" if any is unsure, else YES."""
    if not (cfg.get("allergies") or {}).get(guest):
        return ""
    v = [ln["text"].rpartition(": ")[2] for ln in guest_lines(cfg, [x for x in lines if x.get("part") == "dessert"], guest)]
    if not v:
        return "check label"
    if any(x.startswith("NO") for x in v):
        return "NO"
    if any(x == "check label" for x in v):
        return "check label"
    return "YES"


def product_name(ln: dict) -> str:
    """The real product for the chart ("Libby's 100% Pure Pumpkin", "McCormick Pumpkin Pie Spice"), not the dish."""
    item = re.split(r",| - | – ", ln.get("item") or "")[0].strip()
    item = re.sub(r"\s+\d+(\.\d+)?\s*(oz|fl oz|lb|lbs|g|kg|ct|count|ml|l)\b.*$", "", item, flags=re.I).strip()
    brand = (ln.get("brand") or "").strip()
    if not item or ln.get("each"):
        return ln["name"]
    return item if not brand or brand.lower() in item.lower() else f"{brand} {item}"


def chart(cfg: dict, lines: list[dict]) -> dict:
    """Ingredient x guest chart: "ok" (YES), "no" (has it) or "maybe" (MAY CONTAIN: unclear label) per cell."""
    guests = [g for g, a in (cfg.get("allergies") or {}).items() if a]
    rows = []
    for ln in lines:
        for it in ln.get("each") or [{"name": product_name(ln), "terms": ln.get("terms", {})}]:
            cells = {}
            for g in guests:
                mine = cfg["allergies"][g]
                found = [t for t in mine if it["terms"].get(t) == "found"]
                maybe = [t for t in mine if it["terms"].get(t) == "unsure"]
                cells[g] = {"v": "no" if found else "maybe" if maybe else "ok",
                            "why": ", ".join(found or maybe)}
            mt = re.match(r"(.+?) \((.+?)\)$", it["name"])        # "broth (Haidilao)" -> "Haidilao broth"
            rows.append({"name": f"{mt[2]} {mt[1]}" if mt else it["name"], "part": ln.get("part", ""), "cells": cells})
    return {"guests": guests, "rows": rows}


def simple_avoid(cfg: dict, lines: list[dict], guest: str) -> list[str]:
    """ "Lee Kum Kee Satay: peanut, sesame" (brand first, like a handwritten note), then unchecked items."""
    out = []
    for b in avoid_lines(cfg, lines, guest):
        mt = re.match(r"(.+?) \((.+?)\): (.+)", b)
        out.append(f"{mt[2]} {mt[1]}: {mt[3]}" if mt else b)
    return out


# Smallest letters that print cleanly in PLA with a 0.4 mm nozzle. Below this the strokes are ~1-3 mm long,
# the 0.45 mm line fills the letters in, and short strokes don't stick to the bed or the paper.
LINE_PITCH = 1.75                # baseline to baseline, in letter heights (see simple_rows)
SIMPLE_MIN_MM = 5.0              # product names and section titles
SIMPLE_AVOID_MIN_MM = 4.5        # "Allergens:" lines
INGREDIENT_MIN_MM = 4.0          # label ingredients under a product


def simple_rows(cfg: dict, lines: list[dict], guest: str, ingredients: bool = True,
                menu: bool = True, short: bool = False) -> list[tuple]:
    """Plain list card: name, then each section ("Hot Pot Menu:", "Dessert:", "Allergens:") left-aligned.
    When the card is too full, layout() cuts the least important text first, never the letter size:
    ingredients=False leaves out the label lines under each product (they are on the back),
    short=True prints "brand + tag" instead of the full product name (so they share lines),
    menu=False replaces the menu list with one line. The guest name and allergen lines are never cut."""
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    h = max(card.get("simple_mm", 5.5), SIMPLE_MIN_MM)
    ah = max(card.get("simple_avoid_mm", 5.0), SIMPLE_AVOID_MIN_MM)
    # Line pitch: this font rises 1.05 h above the baseline and descends 0.33 h (g, p, y), so 1.75 h leaves a
    # clear ~0.37 h gap between a line's descenders and the next line's capitals. 1.4 h made them touch.
    p, ap = h * LINE_PITCH, ah * LINE_PITCH
    rows = []
    if guest:
        rows.append((guest, 8, "cursive", True, 12))
    ih = max(h * 0.8, INGREDIENT_MIN_MM)   # label ingredients under each product, a bit smaller
    max_w = W - 2 * m

    def packed(names: list[str]) -> list[str]:
        """Plain items share lines ("Ginger, Garlic, Scallions") so big letters still fit; never split a name."""
        out: list[str] = []
        for n in names:
            if out and width(text_line(f"{out[-1]}, {n}", h)) <= max_w:
                out[-1] += f", {n}"
            else:
                out.append(n)
        return out

    if not menu:
        rows.append(("Full menu on the back.", h, "print", False, p + 3))
    for title, items in (simple_items(cfg, short) if menu else {}).items():
        rows.append((f"{title}:", h + 0.6, "print", False, p))
        plain: list[str] = []
        for i, (t, ing) in enumerate(items):
            if not (ing and ingredients):
                plain.append(t)
                nxt = items[i + 1] if i + 1 < len(items) else None
                if nxt and not (nxt[1] and ingredients):
                    continue                      # keep collecting plain items
                rows += [(x, h, "print", False, p) for ln in packed(plain) for x in wrap(ln, h, max_w)]
                plain = []
                continue
            rows += [(x, h, "print", False, p) for x in wrap(t, h, max_w)]
            rows[-1] = rows[-1][:4] + (h * 0.33 + ih * 1.05 + 0.4 * ih,)
            rows += [(x, ih, "print", False, ih * LINE_PITCH) for x in wrap(" " + ing, ih, max_w)]
            rows[-1] = rows[-1][:4] + (p + 1,)
        rows[-1] = rows[-1][:4] + (p + 2,)
    rows.append(("Allergens:", h + 0.6, "print", False, p))
    if not (cfg.get("allergies") or {}).get(guest):
        rows.append(("No food allergies on file", ah, "print", False, ap))
    else:
        for b in simple_avoid(cfg, lines, guest) or ["None on the menu"]:
            rows += [(x, ah, "print", False, ap) for x in wrap(b, ah, W - 2 * m)]
        rows[-1] = rows[-1][:4] + (ap + 2,)
        rows += [(x, ah, "print", False, ap) for t in OK_LINES for x in wrap(t, ah, W - 2 * m)]
    return rows


OK_LINES = ("Everything else is okay.", "But double check labels.")


# Words that describe packaging or marketing, not what the product is. Dropped from names on a full card.
FILLER = {"premade", "refrigerated", "premium", "pure", "100%", "cane", "granulated", "large", "grade", "a",
          "white", "brown", "organic", "extra", "original", "classic", "natural", "all", "fresh", "count",
          "deep", "dish", "easy", "family", "size", "value", "pack", "the", "and", "of", "with"}


def short_name(full: str, brand: str = "", tag: str = "") -> str:
    """A shorter but still true product name for a full card ("C&H sugar", "Libby's Pumpkin").

    The planner's tag is used only when its words are in the product name: a tag can name the dish instead
    ("pumpkin pie" on evaporated milk), and the card must never name the wrong product."""
    if not brand:
        return full                  # plain produce ("Fresh ginger") is already short
    low = full.lower()
    if tag and all(w.rstrip("s") in low for w in tag.lower().split()):
        return f"{brand} {tag}"
    words = [w for w in re.sub(r",.*$", "", full).split() if w.lower() not in FILLER]
    return " ".join(words) or full


def simple_items(cfg: dict, short: bool = False) -> dict[str, list[tuple[str, str]]]:
    """{section: [(exact product name, label ingredients or "")]}. Menus planned from a prompt carry the
    exact name ("card") and label per product; older configs only have the packed "simple" lines."""
    menu = [d for d in cfg.get("menu") or [] if any(isinstance(x, dict) and x.get("card") for x in d["products"])]
    if not menu:
        # old saved menus pack several items per line ("Sky Ranch beef, Little Sheep lamb"): one item each,
        # so simple_rows can re-pack them for the current letter size without splitting a name
        return {k: [(x.strip(), "") for t in v for x in t.split(", ") if x.strip()]
                for k, v in (cfg.get("simple") or {}).items()}
    def name(x: dict) -> str:
        full = x.get("card") or x["item"]
        return short_name(full, x.get("brand", ""), x.get("tag", "")) if short else full
    return {d["name"]: [(name(x), x.get("ingredients", "")) for x in d["products"]] for d in menu}


def one_page_rows(cfg: dict, lines: list[dict], guest: str) -> list[tuple]:
    """Everything on one side: date, name, menu overview, then this guest's don't-eat list."""
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    oh = card.get("one_menu_mm", 4.6)
    ah = card.get("one_avoid_mm", 4.2)
    op, ap = oh * 1.5, ah * 1.5
    ev = cfg.get("event", {})
    rows = []
    if ev.get("when"):
        rows.append((ev["when"], 4.6, "print", True, 10))
    if guest:
        rows.append((guest, 8, "cursive", True, 13))
    rows.append(section("Menu", 5.5, op + 2))
    pie = (cfg.get("dessert") or {}).get("name")
    for t in cfg.get("overview_one") or cfg.get("overview", []):
        if t == pie:
            v = dessert_verdict(cfg, lines, guest)
            t = f"{t}: {v}" if v else t
        rows += [(x, oh, "print", True, op) for x in wrap(t, oh, W - 2 * m)]
    rows[-1] = rows[-1][:4] + (op + 5,)
    if not (cfg.get("allergies") or {}).get(guest):
        rows.append(("No food allergies on file", ah, "print", True, ap))
    else:
        rows.append((f"Don't eat", 6.5, "cursive", True, ap + 4))
        for b in avoid_lines(cfg, lines, guest) or ["Nothing on the menu"]:
            rows += [(x, ah, "print", False, ap) for x in wrap(b, ah, W - 2 * m)]
        rows[-1] = rows[-1][:4] + (ap + 3,)
        rows += [(x, 3.8, "print", True, 6.5) for t in OK_LINES for x in wrap(t, 3.8, W - 2 * m)]
    return rows


def short_front_rows(cfg: dict, guest: str, lines: list[dict] | None = None) -> list[tuple]:
    card = cfg.get("card", {})
    W, m = card.get("w", 127.0), card.get("margin", 10.0)
    h = card.get("overview_mm", 5.5)
    pitch = h * card.get("overview_gap", 1.55)
    ev = cfg.get("event", {})
    rows = []
    if card.get("show_title", True):
        rows.append((ev.get("title", "Thanksgiving"), 11, "cursive", True, 17))
    if ev.get("when"):
        rows.append((ev["when"], 5, "print", True, 12))
    if guest:
        rows.append((guest, 9, "cursive", True, 16))
    rows.append(section("Menu", 6.5, pitch + 3))
    pie = (cfg.get("dessert") or {}).get("name")
    for t in cfg.get("overview", []):
        if t == pie and lines is not None:
            v = dessert_verdict(cfg, lines, guest)
            t = f"{t}: {v}" if v else t
        rows += [(x, h, "print", True, pitch) for x in wrap(t, h, W - 2 * m)]
    return rows


def layout_back(cfg: dict, lines: list[dict] | None = None, guest: str = "", side: str = "back") -> list[Stroke]:
    """Back: short style = this guest's "don't eat" list; full style = pie + sauces YES/NO."""
    card = cfg.get("card", {})
    lines = lines or []
    if card.get("style", "short") in ("one", "simple"):
        return []                                              # one-page card: nothing on the back
    if card.get("style", "short") == "short":
        st, _ = draw_rows(short_back_rows(cfg, lines, guest), card.get("w", 127.0), card.get("h", 178.0),
                          card.get("margin", 10.0))
        return st
    rows = []
    if cfg.get("dessert"):
        rows.append(section(f"Dessert: {cfg['dessert']['name'].lower()}"))
        rows += entry_rows(cfg, [cfg["dessert"]], [x for x in lines if x.get("part") == "dessert"], guest)
        rows[-1] = rows[-1][:4] + (rows[-1][4] + 4,)
    rows += sauce_rows(cfg, lines, guest)
    st, _ = draw_rows(rows, card.get("w", 127.0), card.get("h", 178.0), card.get("margin", 10.0))
    return st


def layout(cfg: dict, lines: list[dict], guest: str = "", side: str = "front") -> list[Stroke]:
    """Front: date, guest, then the hot pot menu: each item YES/NO with its label ingredients under it."""
    from .shapes import pumpkin
    if side == "back":
        return layout_back(cfg, lines, guest, side)
    card = cfg.get("card", {})
    W, H = card.get("w", 127.0), card.get("h", 178.0)       # 5 x 7 inch
    m = card.get("margin", 10.0)
    ev = cfg.get("event", {})
    rows = []
    if card.get("show_title", True):
        rows.append((ev.get("title", "Thanksgiving"), 11, "cursive", True, 17))
    if ev.get("when"):
        rows.append((ev["when"], 5, "print", True, 11))
    if guest:
        rows.append((guest, 8, "cursive", True, 12))
    if card.get("style", "short") == "simple":
        # A longer menu: smaller letters until it fits, never below the SIMPLE_*_MIN_MM sizes (simple_rows clamps).
        # Cut order (least important first): ingredient lines, then full product names become "brand + tag",
        # then the menu list. Never the allergen lines.
        tries = ([(k, True, False, True) for k in (1, .92, .85, .78, .72, .66, .6)]
                 + [(k, False, False, True) for k in (1, .9)] + [(k, False, True, True) for k in (1, .9)]
                 + [(k, False, False, False) for k in (1, .9)])
        for i, (k, ing, sh, mn) in enumerate(tries):
            c = {**cfg, "card": {**card, "simple_mm": card.get("simple_mm", 5.5) * k,
                                 "simple_avoid_mm": card.get("simple_avoid_mm", 5.0) * k}}
            try:                                  # start right under the top margin: room for labels + allergens
                return draw_rows(simple_rows(c, lines, guest, ingredients=ing, menu=mn, short=sh),
                                 W, H, m, top=True)[0]
            except ValueError as e:
                if i == len(tries) - 1:
                    raise ValueError(f"Allergen list too long for one card at readable letter sizes "
                                     f"({SIMPLE_AVOID_MIN_MM} mm): use a bigger card. ({e})") from e
    if card.get("style", "short") == "one":
        return draw_rows(one_page_rows(cfg, lines, guest), W, H, m)[0]
    if card.get("style", "short") == "short":
        rows = short_front_rows(cfg, guest, lines)
        menu = []
    else:
        menu = [x for x in lines if x.get("part", "menu") == "menu"]
        rows.append(section("Menu", 6))
        rows += entry_rows(cfg, cfg["menu"], menu, guest)
    if menu:
        rows[-1] = rows[-1][:4] + (rows[-1][4] + 2,)
        rows.append((legend(cfg, guest), 3.4, "print", True, 10))
    art = 16.0                                                # pumpkin height
    try:
        out, y = draw_rows(rows, W, H, m, extra=10 + art)
    except ValueError:                                        # long menu: drop the pumpkin, keep the words
        return draw_rows(rows, W, H, m)[0]
    out.extend(move(pumpkin(), dx=W / 2, dy=y - 10 - art / 2, k=art / 2 / 40 / 0.9))
    return out


# ---------------------------------------------------------------- PLA G-code
# Paper settings follow Callum Coles' "3D Printing on Paper" (https://www.youtube.com/watch?v=9UiPPWbeScY):
# heated bed off, hot end as cool as PLA allows (190 C) and part fan 100 % so the paper doesn't warp,
# card taped down on every edge. The V3 SE homes Z with the CR Touch at the bed center, which is under the
# card, so G28 measures the paper's top: Z0 = paper surface, and each layer is laid on top of it.
@dataclass
class Pla:
    nozzle: float = 215.0          # PLA. Video uses 190 C; hotter flows into watercolor paper better. Ender-PLA: 190-230 C
    bed: float = 0.0               # paper: bed heater off
    fan: int = 255                 # part fan 100 % (layer 2+)
    first_fan: int = 0             # layer 1: fan off. 50 % cooled the PLA before it grabbed the paper (it curled up)
    card_x: float = 15.0           # printer X/Y of the card's front-left corner (6x9: run scripts/paper_6x9.py)
    card_y: float = 20.0
    z_adjust: float = 0.0          # extra Z above the paper the probe found (+0.05 if it scrapes, -0.05 if it won't stick)
    layer: float = 0.2             # thin lines: 2 layers of 0.2 mm = 0.4 mm raised text
    first_z: float = 0.1           # nozzle height for layer 1 above the probed paper: squishes PLA into the paper texture
    first_feed: float = 480.0      # mm/min on layer 1 (8 mm/s): slower = more time to soak into the paper
    first_flow: float = 1.3        # layer 1 lays 30 % more PLA so it presses into the paper's texture
    layers: int = 2
    line_w: float = 0.45
    feed: float = 900.0            # mm/min drawing (15 mm/s: clean letters on textured paper)
    travel: float = 6000.0
    retract: float = 1.5           # direct drive; pulls the string back before a lift
    hop: float = 4.0               # lift high so strings (dot of an i) snap off
    hop_feed: float = 1200.0       # mm/min for the lift (the firmware caps Z speed anyway)
    retract_feed: float = 2700.0   # mm/min pulling back (OrcaSlicer PETG: 2400)
    unretract_feed: float = 2700.0 # mm/min pushing back before a stroke (OrcaSlicer PETG: 1800)
    wipe: float = 0.0              # mm to move back along the stroke after the retract, nozzle still down: the
                                   # tip wipes its ooze onto the line instead of pulling a string to the next one
    end_pause: float = 0.0         # seconds to hold still after the retract, before lifting: the line sets
                                   # and the ooze stops, so the lift doesn't pull a short stroke off the bed
    prime_x: float = 5.0           # prime blob off the card, on bare bed
    prime_y: float = 5.0
    x_min: float = 2.0
    x_max: float = 215.0
    y_min: float = 2.0
    y_max: float = 215.0
    park_x: float = 110.0
    park_y: float = 215.0          # bed forward at the end so you can peel the card
    park_z: float = 40.0
    surface: str = "paper"         # "paper" (taped card) or "bed" (straight on the bare bed: scripts/bare_bed.py)
    paper_mm: float = 0.0          # paper thickness measured by scripts/measure_paper.py (CR Touch, paper vs bare bed)
    paper_z: float = 0.0           # old setting (Z of the paper over a bare-bed home); no longer used

    @classmethod
    def load(cls, path: Path = MACHINE_FILE) -> "Pla":
        data = json.loads(path.read_text()).get("pla", {}) if path.exists() else {}
        return cls(**{k: type(getattr(cls, k))(v) for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def e_per_mm(self) -> float:
        return self.line_w * self.layer / (math.pi * (1.75 / 2) ** 2)


def paper(p: "Pla") -> float:
    return max(0.0, min(p.paper_mm, 0.6))      # never dig more than 0.6 mm below the paper top


def prime_lines(p: "Pla") -> list[str]:
    z = 0.05 + p.z_adjust - paper(p)
    line = [f"G1 Z{z:.2f} F600", f"G1 Y{p.prime_y + 70:.1f} E12 F400", f"G1 E-{p.retract:.2f} F2700",
            f"G0 Z{p.hop + 1:.1f} F1200"]
    return ["M211 S0", *line, "M211 S1"] if z < 0.05 else line


def wipe_point(st: Stroke, dist: float) -> tuple[float, float]:
    """The point dist mm back along the stroke from its end (or its start, if the stroke is shorter)."""
    left = dist
    for (bx, by), (ax, ay) in zip(st[::-1], st[-2::-1]):     # walk from the end towards the start
        seg = math.hypot(bx - ax, by - ay)
        if seg >= left and seg > 0:
            t = left / seg
            return bx + (ax - bx) * t, by + (ay - by) * t
        left -= seg
    return st[0]


def card_gcode(strokes: list[Stroke], p: Pla) -> list[str]:
    """One file the printer runs on its own from the microSD: heat, home ON the card, prime off it, draw."""
    out = [f"M140 S{p.bed:.0f}", f"M104 S{p.nozzle:.0f}", "M107", "G90", "M83",
           *([f"M190 S{p.bed:.0f}"] if p.bed > 0 else []),     # bare bed: wait until it's warm before homing
           "G28",                                     # CR Touch taps the card at the bed center: Z0 = paper top
           "M420 S1",                                 # saved bed mesh
           f"G0 Z10 F600", f"G0 X{p.prime_x:.1f} Y{p.prime_y:.1f} F{p.travel:.0f}",
           f"M109 S{p.nozzle:.0f}",
           # prime line on the bare bed left of the card (card starts at X34). Z0 is the paper top, so the bed
           # here is one paper-thickness lower. With a measured paper_mm, drop by it (below Z0, so the software
           # Z-min stop is off just for this line), else Z0.05 and a thick line.
           *prime_lines(p)]
    for n in range(p.layers):
        # layer 1 fan off so the PLA grabs the paper (tape loops under the card keep it flat); full fan after
        out.append(f"M106 S{p.first_fan if n == 0 else p.fan}" if n or p.first_fan else "M107")
        z = p.z_adjust + p.first_z + p.layer * n
        feed = p.first_feed if n == 0 else p.feed
        flow = p.first_flow if n == 0 else 1.0
        zt = z + p.hop
        out.append(f"G0 Z{zt:.2f} F1200")
        for st in strokes:
            if len(st) < 2:
                continue
            x, y = st[0]
            out += [f"G0 X{p.card_x + x:.2f} Y{p.card_y + y:.2f} F{p.travel:.0f}", f"G1 Z{z:.2f} F600",
                    f"G1 E{p.retract:.2f} F{p.unretract_feed:.0f}"]
            for (ax, ay), (bx, by) in zip(st, st[1:]):
                e = math.hypot(bx - ax, by - ay) * p.e_per_mm * flow
                out.append(f"G1 X{p.card_x + bx:.2f} Y{p.card_y + by:.2f} E{e:.5f} F{feed:.0f}")
            out.append(f"G1 E-{p.retract:.2f} F{p.retract_feed:.0f}")
            if p.wipe > 0:
                wx, wy = wipe_point(st, p.wipe)
                out.append(f"G1 X{p.card_x + wx:.2f} Y{p.card_y + wy:.2f} F{p.travel / 2:.0f}")
            if p.end_pause > 0:
                out.append(f"G4 P{round(p.end_pause * 1000)}")
            out.append(f"G0 Z{zt:.2f} F{p.hop_feed:.0f}")
    out += ["M104 S0", "M140 S0", "M107", f"G0 Z{p.park_z:.1f} F600",
            f"G0 X{p.park_x:.1f} Y{p.park_y:.1f} F{p.travel:.0f}", "M400", "M84", "M117 Card done"]
    check_bounds(out, p)
    return out


def minutes(lines: list[str], p: Pla) -> float:
    """Rough print time: drawing + travel + ~3 min to heat and home."""
    import re as _re
    t, x, y = 0.0, None, None
    for ln in lines:
        m = _re.match(r"G[01] X([-\d.]+) Y([-\d.]+)(?:.* F(\d+))?", ln)
        if m:
            nx, ny = float(m[1]), float(m[2])
            if x is not None:
                t += math.hypot(nx - x, ny - y) / (float(m[3]) if m[3] else p.travel)
            x, y = nx, ny
    return round(t + 3, 0)


def check_bounds(lines: list[str], p: Pla) -> None:
    for ln in lines:
        if not ln.startswith(("G0", "G1")):
            continue
        for w in ln.split()[1:]:
            lim = {"X": (p.x_min, p.x_max), "Y": (p.y_min, p.y_max), "Z": (min(0.05, round(0.05 + p.z_adjust - paper(p), 2)) - 1e-6, 120.0)}.get(w[0])
            if lim and not lim[0] <= float(w[1:]) <= lim[1]:
                raise ValueError(f"{ln!r}: {w[0]} outside {lim}. Check pla.card_x/card_y/z_adjust in machine.json")


def load(path: Path = CARDS_FILE, use_menu: bool = True) -> dict:
    """Guests, allergies and card settings from cards.json; the menu from the last prompt if there is one."""
    from . import menu_plan
    p = path if path.exists() else ROOT / "cards.example.json"
    cfg = json.loads(p.read_text())
    m = menu_plan.saved() if use_menu else None
    if m:
        cfg.update({k: v for k, v in m.items() if k not in ("title", "prompt")})
        cfg["menu_title"], cfg["menu_prompt"] = m.get("title", "Dinner"), m.get("prompt", "")
        cfg.setdefault("examples", [dict(x) for x in menu_plan.EXAMPLES])
    return cfg


def menu_key(cfg: dict) -> str:
    """Fingerprint of the menu, so a saved check from an older menu is never reused."""
    import hashlib
    keep = {k: cfg.get(k) for k in ("menu", "dessert", "more", "sauces", "allergies")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser(description="Menu invitation cards in PLA.")
    ap.add_argument("--check", action="store_true", help="run Search + Decider on every product (needs the API key)")
    ap.add_argument("--guest", default="", help="name printed on the card")
    ap.add_argument("--gcode", action="store_true", help="print the card's G-code")
    ap.add_argument("--side", default="front", choices=["front", "back"],
                    help="front: menu YES/NO + how to hot pot; back: exact ingredients + sauces YES/NO")
    args = ap.parse_args()
    cfg = load()
    if args.check:
        from .pplx import make_client
        with make_client() as c:
            lines = check_menu(c, cfg)
        Path("captures").mkdir(exist_ok=True)
        Path("captures/menu_check.json").write_text(json.dumps({"key": menu_key(cfg), "lines": lines}, indent=2))
    else:
        f = Path("captures/menu_check.json")
        saved = json.loads(f.read_text()) if f.exists() else None
        if not (isinstance(saved, dict) and saved.get("key") == menu_key(cfg)):
            raise SystemExit("Menu changed (or never checked): run with --check first")
        lines = saved["lines"]
    if args.gcode:
        print("\n".join(card_gcode(layout(cfg, lines, args.guest, args.side), Pla.load())))
    else:
        for ln in lines:
            print(ln["text"], "  (check:", ", ".join(ln["unsure"]) + ")" if ln["unsure"] else "")


if __name__ == "__main__":
    main()
