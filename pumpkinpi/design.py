"""Prompt -> design plan, with the Perplexity Agent API (web search + JSON output).

"a cat with Debbie's name in cursive" becomes:
  {"guest": "Debbie", "shape": "cat", "text": "Debbie", "font": "cursive", "topping": "dark chocolate ganache",
   "ingredients": ["Enjoy Life Semi-Sweet Mini Chips, 9 oz", "Clover Sonoma Organic Heavy Whipping Cream, 1 pint"],
   "products": [{"ingredient": ..., "brand": "Enjoy Life", "product": "Semi-Sweet Mini Chips", "size": "9 oz",
                 "store": "Safeway", "upc": "853522000009"}, ...], ...}

Ingredients are exact store products (brand + product + size), not "chocolate chips", because
allergens and may-contain warnings differ by brand. products.py adds each one's photo and label.

The model picks the shape from a fixed list; shapes.py draws it, so the path always fits the pie.
Every ingredient then goes through the allergen gate (Search API + Decider) before Start unlocks.
"""
from __future__ import annotations

import argparse
import json

import httpx

from . import pplx
from .shapes import FONTS, MAX_TEXT, SHAPES

SCHEMA = {
    "type": "object",
    "properties": {
        "guest": {"type": "string", "description": "Guest name from the list, or empty"},
        "shape": {"type": "string", "enum": list(SHAPES)},
        "text": {"type": "string", "description": f"Words to pipe, at most {MAX_TEXT} letters, or empty"},
        "font": {"type": "string", "enum": list(FONTS), "description": "cursive if they ask for cursive/script/handwriting"},
        "topping": {"type": "string", "description": "The pipeable topping, e.g. chocolate ganache"},
        "ingredients": {"type": "array", "items": {"type": "string"},
                        "description": "Each exact store product: 'Brand Product, size', e.g. 'Enjoy Life Semi-Sweet Mini Chips, 9 oz'"},
        "products": {"type": "array", "description": "One entry per ingredient, same order", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ingredient", "brand", "product", "size", "store", "upc"],
            "properties": {
                "ingredient": {"type": "string", "description": "Exactly the matching ingredients[] string"},
                "brand": {"type": "string"}, "product": {"type": "string"}, "size": {"type": "string"},
                "store": {"type": "string", "description": "A San Francisco Bay Area store that sells it, e.g. Safeway, Whole Foods, Target"},
                "upc": {"type": "string", "description": "UPC barcode digits if you found them, else empty"}}}},
        "recipe": {"type": "array", "items": {"type": "string"}, "description": "3-5 short steps; 7-10 if the guest asks to bake the pie too (prefix 'Pie:' and 'Topping:')"},
        "piping_notes": {"type": "string", "description": "Consistency and temperature for a cold syringe"},
        "diet_notes": {"type": "string", "description": "Sugar or other diet notes for guests who limit something"},
        "allergy_notes": {"type": "string", "description": "How the recipe avoids each guest allergen, one short line"},
        "caption": {"type": "string", "description": "One short on-screen line, under 60 characters"},
    },
    "required": ["guest", "shape", "text", "font", "topping", "ingredients", "products", "recipe", "piping_notes", "diet_notes", "allergy_notes", "caption"],
    "additionalProperties": False,
}

INSTRUCTIONS = f"""You plan decorations for PumpkinPi, a printer that pipes toppings onto a 6-inch pumpkin pie
from an unheated 60 mL syringe with a narrow tip.

Rules:
- shape must be one of {list(SHAPES)}. "kitty"/"kitten" is cat. If the request is a different picture, pick the
  closest one and say so in caption.
- text: the name or words they asked for (spell guest names as in the guest list, e.g. "Debbie"), or the guest's
  name if the design is for a named guest, else empty. Max {MAX_TEXT} letters.
- font: "cursive" if they ask for cursive, script or handwriting, else "print".
- The syringe is NOT heated, so melted chocolate will set in the tip. Turn "chocolate" into a pipeable
  chocolate ganache or chocolate frosting that stays soft at room temperature.
- The topping must avoid every allergen any guest avoids. Prefer 2-3 simple, widely sold ingredients.
- Watch for hidden nuts and fish: no almond/cashew/other nut milks, creams, flours, butters, oils or
  extracts, praline, marzipan, gianduja, nougat or pesto when a guest avoids tree nuts or peanuts;
  no anchovy or Worcestershire when a guest avoids fish. Peanuts and tree nuts are different: if
  only some guests avoid peanuts, still avoid them, because the pie is shared.
- Use vanilla, not almond extract. Avoid coconut when a guest avoids tree nuts (FDA no longer lists
  it as a tree nut, so labels may not warn); for vegan cream pick oat or soy cream.
- Every food named in the steps must also be in ingredients (salt, vanilla, sweetener too), so
  each one gets checked.
- Every ingredient is an EXACT product from a grocery store shelf: brand + product name + size, e.g.
  "Enjoy Life Semi-Sweet Mini Chips, 9 oz" or "Clover Sonoma Organic Heavy Whipping Cream, 1 pint", never just
  "chocolate chips". If the guest names a brand (Hershey's, M&M's), use that exact product.
- Search the web for each product's current label. Prefer products whose label lists no guest allergen and no
  may-contain or shared-equipment warning for one (e.g. brands made in a dedicated nut-free facility). If a
  requested brand carries a warning for a guest allergen, still list it and explain in allergy_notes, and name a
  safer brand there.
- If the guest asks to bake or make the pie itself (e.g. "bake a pumpkin pie with a cat on it"), the
  ingredients cover the whole pie first, each as an exact store product (crust, canned pumpkin, evaporated
  milk or cream, eggs, sweetener, spice, salt), then the pipeable topping. The recipe bakes the pie, cools it
  fully (about 2 hours), then makes and pipes the topping. Topping says e.g. "Pumpkin pie + dark chocolate
  ganache". For low-sugar guests, give a reduced-sugar option in diet_notes.
- Fill products[] in the same order, with a Bay Area store that sells it and the UPC if a store page shows it.
- If a dish on the bed is given, design for it: a cookie or cupcake is small, so use a shape alone or a name of at
  most 6 letters; a pie has a crust ring, so keep the design inside the filling.
- Never say an ingredient is safe; PumpkinPi checks each one separately. Do not put URLs in the JSON.
- If diet options are given (vegan, dairy-free, gluten-free, egg-free, low sugar), every ingredient must fit them,
  e.g. vegan ganache uses dairy-free chocolate and oat or soy cream.
- Search the web for a ganache/frosting ratio and piping consistency; prefer university extension and
  food-safety sites.
Return only a JSON object matching the schema."""


def tidy(plan: dict, old: dict | None = None) -> dict:
    """Keep the model inside what shapes.py can draw, and products[] in step with ingredients[]."""
    if plan.get("shape") not in SHAPES:
        plan["shape"] = (old or {}).get("shape", "text")
    if plan.get("font") not in FONTS:
        plan["font"] = "print"
    plan["text"] = (plan.get("text") or "")[:MAX_TEXT]
    by_name = {p.get("ingredient", "").lower(): p for p in plan.get("products") or []}
    plan["products"] = [{"ingredient": i, "brand": "", "product": i, "size": "", "store": "", "upc": "",
                         **by_name.get(i.lower(), {}), "ingredient": i} for i in plan.get("ingredients", [])]
    return plan


def dish_line(dish: dict | None) -> str:
    if not dish or dish.get("dish") in (None, "nothing", "other"):
        return ""
    room = f", room for a design about {2 * dish['fit_r']:.0f} mm across" if dish.get("fit_r") else ""
    return f"\nDish on the bed (from the camera): {dish['dish']}{room}"


def plan_design(client: httpx.Client, prompt: str, guests: list[dict], diets: list[str] | None = None,
                dish: dict | None = None) -> dict:
    roster = [{"name": g["name"], "avoid": g.get("avoid", []), "limit": g.get("limit", [])} for g in guests]
    text, results = pplx.agent(
        client, instructions=INSTRUCTIONS, name="pumpkinpi_design", schema=SCHEMA,
        input=f"Guests: {json.dumps(roster)}\nDiet options: {json.dumps(diets or [])}{dish_line(dish)}\n\nRequest: {prompt}",
    )
    plan = tidy(json.loads(text))
    plan["sources"] = [{"title": r.get("title"), "url": r.get("url")} for r in results if r.get("url")][:8]
    return plan


REVISE = INSTRUCTIONS + """

You are changing an existing design. Apply only the requested change and keep everything else
(topping, ingredients, recipe) the same unless the change asks for it. "No name" or "without
Michael's name" means text is empty. "Only a heart" means shape heart; drop the text unless the
change asks for words. "A cat with the name 'debbie' in cursive" means shape cat, text "Debbie",
font cursive. Words in quotes are the text to pipe."""


def revise_design(client: httpx.Client, plan: dict, change: str, guests: list[dict],
                  diets: list[str] | None = None, dish: dict | None = None) -> dict:
    """Edit the current plan ("just a heart, no name") instead of starting over."""
    roster = [{"name": g["name"], "avoid": g.get("avoid", []), "limit": g.get("limit", [])} for g in guests]
    current = {k: plan.get(k) for k in SCHEMA["properties"]}
    text, results = pplx.agent(
        client, instructions=REVISE, name="pumpkinpi_revise", schema=SCHEMA,
        input=f"Guests: {json.dumps(roster)}\nDiet options: {json.dumps(diets or [])}{dish_line(dish)}\n"
              f"Current design: {json.dumps(current)}\n\nChange: {change}",
    )
    new = tidy(json.loads(text), plan)
    new["sources"] = plan.get("sources", [])
    if new["ingredients"] != plan.get("ingredients"):   # new topping: keep only the new research
        new["sources"] = [{"title": r.get("title"), "url": r.get("url")} for r in results if r.get("url")][:8]
    return new


def main() -> None:
    ap = argparse.ArgumentParser(description="Turn a prompt into a PumpkinPi design plan.")
    ap.add_argument("prompt", help='e.g. "a smiley face in chocolate for Michael"')
    ap.add_argument("--guests", default="guests.json")
    args = ap.parse_args()
    guests = json.load(open(args.guests))["guests"]
    with pplx.make_client() as c:
        print(json.dumps(plan_design(c, args.prompt, guests), indent=2))


if __name__ == "__main__":
    main()
