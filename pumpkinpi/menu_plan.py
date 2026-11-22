"""Prompt -> dinner menu with exact branded products (Agent API), saved for the cards.

The Agent only picks the products. It never decides what is safe: every product still goes through
the Search API + Decider in cards.check_menu, and anything without a clear label prints as a NO.

    "hot pot with beef, lamb and shrimp; pumpkin pie"  ->  captures/menu.json
"""
from __future__ import annotations

import json
from pathlib import Path

from . import pplx

ROOT = Path(__file__).resolve().parent.parent
MENU_FILE = ROOT / "captures" / "menu.json"
LINE_CHARS = 34          # one printed card line (about 4 mm letters on a 5 x 7 inch card)

INSTRUCTIONS = """You plan a home dinner menu for a printed place card.
Turn the request into the dishes it names and, for every packaged product, pick ONE exact retail product
sold in US grocery stores (San Francisco Bay Area): brand + product name + size, e.g.
"Haidilao Mushroom Hot Pot Soup Base, 5.3 oz". Use web search to confirm the product exists.
- Keep the user's dishes. Do not swap a dish for another one.
- Where brands differ, prefer a product whose label avoids the guests' allergens and has no
  shared-facility warning for them. Never claim a product is safe; a separate checker reads every label.
- Fresh produce and plain raw meat with no brand: brand "" and a plain name ("Bok choy").
- Dipping sauces / condiments go in part "sauce"; desserts in part "dessert"; everything else part "main".
- section: the heading printed on the card, short ("Hot Pot Menu", "Dinner", "Dessert"). Use at most 3 sections.
- tag: 1-2 lowercase words for the card ("beef", "broth", "apple pie").
- At most 14 main products, 6 dessert products and 8 sauces.
- title: 1-3 words naming the meal ("Hot pot", "Roast chicken").
If the request is not a meal, return no products and say why in note."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "note": {"type": "string"},
        "products": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "item": {"type": "string"}, "brand": {"type": "string"}, "tag": {"type": "string"},
                "part": {"type": "string", "enum": ["main", "dessert", "sauce"]},
                "section": {"type": "string"},
            },
            "required": ["item", "brand", "tag", "part", "section"],
        }},
    },
    "required": ["title", "products"],
}


def card_word(p: dict) -> str:
    """'Sky Ranch beef' for branded products, 'Bok choy' for fresh ones."""
    tag = (p.get("tag") or p["item"]).strip()
    return f"{p['brand'].strip()} {tag}" if p.get("brand", "").strip() else tag[:1].upper() + tag[1:]


def pack(words: list[str], n: int = LINE_CHARS) -> list[str]:
    """Join words with ', ' into card lines no longer than n characters (a long word gets its own line)."""
    out: list[str] = []
    for w in words:
        if out and len(out[-1]) + 2 + len(w) <= n:
            out[-1] += ", " + w
        else:
            out.append(w)
    return out


def to_cards(plan: dict) -> dict:
    """Agent plan -> the keys cards.py reads (menu, sauces, simple), replacing the saved example menu."""
    menu: dict[str, list[dict]] = {}
    sauces: list[dict] = []
    for p in plan.get("products", []):
        prod = {"item": p["item"].strip(), "tag": p.get("tag", "").strip() or p["item"].strip()}
        if p.get("brand", "").strip():
            prod["brand"] = p["brand"].strip()
        if p.get("part") == "sauce":
            sauces.append(prod)
        else:
            sec = (p.get("section") or ("Dessert" if p.get("part") == "dessert" else "Menu")).strip()
            menu.setdefault(sec, []).append(prod)
    simple = {sec: pack([card_word(x) for x in items]) for sec, items in menu.items()}
    return {"title": plan.get("title", "").strip() or "Dinner", "prompt": plan.get("prompt", ""),
            "menu": [{"name": sec, "products": items} for sec, items in menu.items()],
            "dessert": None, "more": [], "sauces": sauces, "simple": simple, "avoid_extra": []}


def plan_menu(client, prompt: str, allergies: dict[str, list[str]]) -> dict:
    text, _ = pplx.agent(client, instructions=INSTRUCTIONS, name="pumpkinpi_menu", schema=SCHEMA,
                         input=f"Guests' allergies: {json.dumps(allergies)}\n\nRequest: {prompt}")
    plan = json.loads(text)
    plan["prompt"] = prompt
    if not plan.get("products"):
        raise ValueError(plan.get("note") or "That doesn't look like a meal. Try: hot pot with beef and shrimp.")
    return to_cards(plan)


def save(menu: dict, path: Path | None = None) -> None:
    path = path or MENU_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(menu, indent=1, ensure_ascii=False))


def saved(path: Path | None = None) -> dict | None:
    path = path or MENU_FILE
    return json.loads(path.read_text()) if path.exists() else None
