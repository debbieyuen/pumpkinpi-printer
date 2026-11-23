"""Prompt -> dinner menu with exact branded products (Agent API), saved for the cards.

The Agent only picks the products. It never decides what is safe: every product still goes through
the Search API + Decider in cards.check_menu, and anything without a clear label prints as a NO.

    "hot pot with beef, lamb and shrimp; pumpkin pie"  ->  captures/menu.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import pplx

ROOT = Path(__file__).resolve().parent.parent
MENU_FILE = ROOT / "captures" / "menu.json"
LINE_CHARS = 34          # one printed card line (about 4 mm letters on a 5 x 7 inch card)

INSTRUCTIONS = """You plan a home dinner menu for a printed place card.
Turn the request into the dishes it names and, for every packaged product, pick ONE exact retail product
sold in US grocery stores (San Francisco Bay Area): brand + product name + size, e.g.
"Haidilao Mushroom Hot Pot Soup Base, 5.3 oz". Use web search to confirm the product exists.
- item: the full name exactly as printed on the package, with brand and size, e.g. "Libby's 100% Pure Pumpkin,
  15 oz" (never a made-up name like "Libby's pumpkin pie"). It must be a product that brand really sells.
- ingredients: the ingredient list copied exactly from that product's package label (from a retailer or brand
  page you found), plus its "Contains:" line if it has one. label_url: that page. "" if you could not find it.
- Every dessert product must be a branded packaged product. Desserts must never contain fish or fish
  ingredients (no fish gelatin, anchovy, fish sauce, isinglass). Pick another brand if a label mentions fish.
- Keep the user's dishes. Do not swap a dish for another one.
- Where brands differ, prefer a product whose label avoids the guests' allergens and has no
  shared-facility warning for them. Never claim a product is safe; a separate checker reads every label.
- Fresh produce and plain raw meat with no brand: brand "" and a plain name ("Bok choy").
- Dipping sauces / condiments go in part "sauce"; desserts in part "dessert"; everything else part "main".
- section: the heading printed on the card, short ("Hot Pot Menu", "Dinner", "Dessert"). Use at most 3 sections.
- tag: 1-2 lowercase words for the card ("beef", "broth", "apple pie").
- At most 14 main products, 6 dessert products and 8 sauces.
- title: 1-3 words naming the meal ("Hot pot", "Roast chicken").
- recipes: one home recipe per dish the user asked for (e.g. "Baked lamb", "Pumpkin pie"). Use the products
  you picked. ingredients: amount + ingredient ("2 lb bone-in lamb leg", "1 can Libby's pumpkin, 15 oz").
  steps: 4-8 short steps with temperatures and times. url: the recipe page you based it on (a real page
  from your web search). Keep sugar modest where you can; never claim the dish is allergen-free.
If the request is not a meal, return no products and say why in note."""

# Two real products that DO contain nuts, always added to the allergy chart (not the printed card) so the
# chart shows what a NO looks like. Labels copied from the brand / retailer pages cited below.
EXAMPLES = [
    {"item": "Nabisco Nutter Butter Peanut Butter Sandwich Cookies, 16 oz", "brand": "Nutter Butter",
     "tag": "cookies", "contains": ["peanut"],
     "label": "Unbleached enriched flour, sugar, peanut butter (roasted peanuts, corn syrup solids, hydrogenated "
              "vegetable oil, salt, peanut oil), soybean and/or canola oil, whole grain wheat flour, high fructose "
              "corn syrup, palm oil, salt, leavening, soy lecithin, artificial flavor. Contains: wheat, peanut, soy.",
     "source": "https://www.heb.com/product-detail/nutter-butter-peanut-butter-sandwich-cookies-family-size/139057"},
    {"item": "Nutella Hazelnut Spread with Cocoa, 13 oz", "brand": "Nutella", "tag": "hazelnut spread",
     "contains": ["tree nut"],
     "label": "Sugar, palm oil, hazelnuts, skim milk, cocoa, lecithin as emulsifier, vanillin: an artificial flavor.",
     "source": "https://www.nutella.com/us/en/products/spread/nutella"},
]

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "note": {"type": "string"},
        "recipes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "dish": {"type": "string"}, "serves": {"type": "string"},
                "ingredients": {"type": "array", "items": {"type": "string"}},
                "steps": {"type": "array", "items": {"type": "string"}},
                "url": {"type": "string"},
            },
            "required": ["dish", "ingredients", "steps", "url"],
        }},
        "products": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "item": {"type": "string"}, "brand": {"type": "string"}, "tag": {"type": "string"},
                "ingredients": {"type": "string"}, "label_url": {"type": "string"},
                "part": {"type": "string", "enum": ["main", "dessert", "sauce"]},
                "section": {"type": "string"},
            },
            "required": ["item", "brand", "tag", "part", "section"],
        }},
    },
    "required": ["title", "products", "recipes"],
}


SIZE_RX = re.compile(r"(,\s*|\s+)\(?\d[\d.,/ ]*\s*(fl\.? ?oz|oz|lb|lbs|g|kg|ml|l|ct|count|pack|in)\b\.?\)?\s*$", re.I)


def card_word(p: dict) -> str:
    """The exact product name, without the package size: "Libby's 100% Pure Pumpkin". Fresh food: "Bok choy"."""
    item, brand = p["item"].strip(), p.get("brand", "").strip()
    if not brand:
        return item[:1].upper() + item[1:]
    name = SIZE_RX.sub("", item).strip(" ,")
    return name if brand.lower().split()[0] in name.lower() else f"{brand} {name}"


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
    urls = plan.get("_urls")
    menu: dict[str, list[dict]] = {}
    sauces: list[dict] = []
    for p in plan.get("products", []):
        prod = {"item": p["item"].strip(), "tag": p.get("tag", "").strip() or p["item"].strip()}
        if p.get("brand", "").strip():
            prod["brand"] = p["brand"].strip()
        prod["card"] = card_word(prod)
        # The Agent's copy of the label is printed under the product and handed to the Decider as evidence.
        # It is NOT a cited source: it never makes anything safe by itself (term_status needs the Decider).
        if (p.get("ingredients") or "").strip():
            prod["ingredients"] = p["ingredients"].strip()[:400]
        u = (p.get("label_url") or "").strip().rstrip("/")
        if u.startswith("http") and (urls is None or u in urls):
            prod["label_url"] = u
        if p.get("part") == "sauce":
            sauces.append(prod)
        else:
            sec = (p.get("section") or ("Dessert" if p.get("part") == "dessert" else "Menu")).strip()
            menu.setdefault(sec, []).append(prod)
    simple = {sec: pack([card_word(x) for x in items]) for sec, items in menu.items()}
    return {"title": plan.get("title", "").strip() or "Dinner", "prompt": plan.get("prompt", ""),
            "menu": [{"name": sec, "products": items} for sec, items in menu.items()],
            "dessert": None, "more": [], "examples": [dict(x) for x in EXAMPLES], "sauces": sauces, "simple": simple, "avoid_extra": [],
            "recipes": clean_recipes(plan.get("recipes") or [], plan.get("_urls"))}


def clean_recipes(recipes: list[dict], urls: set[str] | None = None) -> list[dict]:
    """Short, tidy recipes; a link is kept only if the web search really returned it."""
    out = []
    for r in recipes[:6]:
        u = (r.get("url") or "").strip()
        if urls is not None and u.rstrip("/") not in urls:
            u = ""
        out.append({"dish": (r.get("dish") or "").strip()[:60], "serves": (r.get("serves") or "").strip()[:30],
                    "ingredients": [x.strip()[:90] for x in r.get("ingredients") or [] if x.strip()][:16],
                    "steps": [x.strip()[:220] for x in r.get("steps") or [] if x.strip()][:10],
                    "url": u if u.startswith("http") else ""})
    return [r for r in out if r["dish"] and r["steps"]]


def plan_menu(client, prompt: str, allergies: dict[str, list[str]]) -> dict:
    text, results = pplx.agent(client, instructions=INSTRUCTIONS, name="pumpkinpi_menu", schema=SCHEMA,
                               input=f"Guests' allergies: {json.dumps(allergies)}\n\nRequest: {prompt}")
    plan = json.loads(text)
    plan["prompt"] = prompt
    plan["_urls"] = {r.get("url", "").rstrip("/") for r in results if r.get("url")} or None
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
