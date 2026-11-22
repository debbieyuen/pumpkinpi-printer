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
from .toolpath import TOPPINGS
from .shapes import BASES, FONTS, MAX_LINE, MAX_TEXT, SHAPES, split_lines

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["make", "question"],
                 "description": "make = they want to cook/bake/decorate something; question = they only want information"},
        "answer": {"type": "string", "description": "For questions (and any question inside a make request): 3-6 short plain sentences, no URLs"},
        "makes": {"type": "string", "description": "What the recipe makes, e.g. 'M&M's cookies with a heart', 'Roast turkey'"},
        "base": {"type": "string", "enum": list(BASES), "description": "What the design is piped on; none if nothing gets piped"},
        "topping_type": {"type": "string", "enum": list(TOPPINGS),
                         "description": "What the syringe pipes: the selected one unless the request names another"},
        "guest": {"type": "string", "description": "Guest name from the list, or empty"},
        "shape": {"type": "string", "enum": list(SHAPES)},
        "text": {"type": "string", "description": f"Words to pipe: at most 2 short lines of {MAX_LINE} letters, or empty"},
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
        "recipe": {"type": "array", "items": {"type": "string"}, "description": "3-5 short steps for a topping; 7-10 if they bake/cook the food too (prefix e.g. 'Cookies:' and 'Topping:')"},
        "piping_notes": {"type": "string", "description": "Consistency and temperature for a cold syringe"},
        "diet_notes": {"type": "string", "description": "Sugar or other diet notes for guests who limit something"},
        "allergy_notes": {"type": "string", "description": "How the recipe avoids each guest allergen, one short line"},
        "design_note": {"type": "string", "description": "One short line if you simplified the design (one picture, shorter words), else empty"},
        "caption": {"type": "string", "description": "One short on-screen line, under 60 characters"},
    },
    "required": ["kind", "answer", "makes", "base", "topping_type", "guest", "shape", "text", "font", "topping", "ingredients", "products", "recipe", "piping_notes", "diet_notes", "allergy_notes", "caption"],
    "additionalProperties": False,
}

INSTRUCTIONS = f"""You are PumpkinPi, a Thanksgiving kitchen helper on a touchscreen. Guests type anything about food. It
also has a printer that pipes a topping from an unheated 60 mL syringe onto a pie, cake, cookie or cupcake.

Answer what they actually asked, never a preset:
- kind "question" when they only want information (e.g. "what does free-range mean on a turkey", "is organic
  worth it", "how long to thaw a turkey", "is this safe for Debbie"). Put the answer in answer: short, plain,
  practical, grounded in your web search. For labels, safety and nutrition use regulators and research first
  (fsis.usda.gov, ams.usda.gov, fda.gov, foodsafety.gov, fdc.nal.usda.gov, certifiedhumane.org, university
  extension, pubmed) and say what the label legally means vs what it does not guarantee. For health questions
  give general guidance only. If it is not about food or cooking, say kindly that you help with food. For a
  question, base is "none", shape "text", text "", and ingredients/products/recipe may be empty unless a recipe helps.
- kind "make" when they want to cook, bake or decorate something. makes says what it is. The recipe is for
  THAT food (cookies give a cookie recipe, a turkey gives a turkey recipe), never a pumpkin pie unless asked.
  base is what the design is piped on: "cookie" for cookies, "cupcake", "cake", "pie" (also the default when they
  only ask for a design), or "none" when nothing gets piped (e.g. a roast turkey or a side dish). Decorated
  cookies/cakes must be fully cool before piping, so say so in the recipe. If they also ask a question (e.g.
  "pasture-raised or organic?"), answer it in answer, else leave answer empty.

Design rules (when base is not none):
- Keep it simple: the syringe pipes one thick bead, so a pie gets ONE picture plus at most two short lines of
  words. shape must be one of {list(SHAPES)}. "kitty"/"kitten" is cat, "puppy" is dog. If they ask for two
  pictures (e.g. a cat and a dog), use the last one named. If the picture isn't in the list, pick the closest
  and say so in design_note.
- text: the name or words they asked for (spell guest names as in the guest list, e.g. "Debbie"), or the guest's
  name if the design is for a named guest, else empty. Whole words only, at most two lines of {MAX_LINE} letters (e.g.
  "Happy Thanksgiving" pipes as "Happy" / "Thanksgiving"). If the words are longer, shorten them and say so in design_note.
- font: "cursive" if they ask for cursive, script or handwriting, else "print".
- The syringe pipes one of three toppings (topping_type), loaded one at a time:
  "chocolate" = melted chocolate chips (an exact chip product; optionally a little neutral oil so it flows);
  "frosting" = a pipeable frosting (e.g. buttercream or cream-cheese frosting, from exact products);
  "marshmallow" = melted marshmallows (an exact marshmallow product; they contain gelatin, so not vegan).
  Use the selected topping unless the request clearly names another. The syringe is NOT heated: for
  chocolate say in piping_notes to pipe within about 10-15 minutes of melting and keep it under 120°F; for
  marshmallow say to cool it about 3 minutes and pipe right away because it sets fast and strings.
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
- If they ask to bake or make the food itself (e.g. "bake cookies with M&M's and a heart on top", "bake a
  pumpkin pie with a cat"), the ingredients cover that whole food first, each as an exact store product (for
  cookies: flour, butter, sugars, eggs, baking soda, vanilla, salt, plus the mix-ins they named), then the
  pipeable topping. The recipe steps start with the food name (e.g. "Cookies:" / "Pie:") and then "Topping:".
  Topping says e.g. "M&M's cookies + chocolate frosting". For low-sugar guests, give a reduced-sugar option in
  diet_notes. For a dish with nothing piped (turkey), topping is empty and recipe covers the dish (7-10 steps,
  with the safe internal temperature from fsis.usda.gov for meat).
- Fill products[] in the same order, with a Bay Area store that sells it and the UPC if a store page shows it.
- Never say an ingredient is safe; PumpkinPi checks each one separately. Do not put URLs in the JSON.
- If diet options are given (vegan, dairy-free, gluten-free, egg-free, low sugar), every ingredient must fit them,
  e.g. vegan ganache uses dairy-free chocolate and oat or soy cream.
- Search the web for the topping's piping consistency; prefer university extension and
  food-safety sites.
Return only a JSON object matching the schema."""


def tidy(plan: dict, old: dict | None = None) -> dict:
    """Keep the model inside what shapes.py can draw, and products[] in step with ingredients[]."""
    if plan.get("kind") not in ("make", "question"):
        plan["kind"] = "make"
    if plan.get("topping_type") not in TOPPINGS:
        plan["topping_type"] = (old or {}).get("topping_type", "chocolate")
    if plan.get("base") not in BASES:
        plan["base"] = (old or {}).get("base", "pie")
    if plan["kind"] == "question":
        plan["base"] = "none"
    plan["answer"] = (plan.get("answer") or "").strip()
    plan["makes"] = (plan.get("makes") or plan.get("topping") or "").strip()
    if plan.get("shape") not in SHAPES:
        plan["shape"] = (old or {}).get("shape", "text")
    if plan.get("font") not in FONTS:
        plan["font"] = "print"
    words = " ".join((plan.get("text") or "").split())
    plan["text"] = " ".join(split_lines(words))
    note = plan.get("design_note") or ""
    if plan["text"] != words and "short" not in note.lower():
        note = (note + f' Kept the words short enough to pipe: "{plan["text"]}".').strip()
    plan["design_note"] = note
    by_name = {p.get("ingredient", "").lower(): p for p in plan.get("products") or []}
    plan["products"] = [{"ingredient": i, "brand": "", "product": i, "size": "", "store": "", "upc": "",
                         **by_name.get(i.lower(), {}), "ingredient": i} for i in plan.get("ingredients", [])]
    return plan


LAYER = """

Adding a layer: the food and earlier toppings are already on it (listed as Layers). Plan ONLY this new
topping: ingredients, products and recipe are just for this topping, base stays the same, makes says e.g.
"Frosting layer". Pick a design that goes with the earlier layers (e.g. a name in frosting under a chocolate heart)."""


def context(roster, diets, topping_type, layers) -> str:
    s = f"Guests: {json.dumps(roster)}\nDiet options: {json.dumps(diets or [])}\nSelected topping: {topping_type or 'chocolate'}\n"
    if layers:
        s += f"Layers already piped: {json.dumps(layers)}\n"
    return s


def plan_design(client: httpx.Client, prompt: str, guests: list[dict], diets: list[str] | None = None,
                topping_type: str | None = None, layers: list[dict] | None = None) -> dict:
    roster = [{"name": g["name"], "avoid": g.get("avoid", []), "limit": g.get("limit", [])} for g in guests]
    text, results = pplx.agent(
        client, instructions=INSTRUCTIONS + (LAYER if layers else ""), name="pumpkinpi_design", schema=SCHEMA,
        input=context(roster, diets, topping_type, layers) + f"\nRequest: {prompt}",
    )
    plan = tidy(json.loads(text))
    plan["sources"] = [{"title": r.get("title"), "url": r.get("url")} for r in results if r.get("url")][:8]
    return plan


REVISE = INSTRUCTIONS + """

You are changing an existing design. Apply only the requested change and keep everything else
(topping, ingredients, recipe) the same unless the change asks for it. "No name" or "without
Michael's name" means text is empty. "Only a heart" means shape heart; drop the text unless the
change asks for words. "A cat with the name 'debbie' in cursive" means shape cat, text "Debbie",
font cursive. Words in quotes are the text to pipe. If they now ask a question instead of a change
(e.g. "is organic turkey worth it?"), return kind "question" with the answer. If they ask for a different
food ("make cookies instead"), plan that food from scratch."""


def revise_design(client: httpx.Client, plan: dict, change: str, guests: list[dict],
                  diets: list[str] | None = None, topping_type: str | None = None,
                  layers: list[dict] | None = None) -> dict:
    """Edit the current plan ("just a heart, no name") instead of starting over."""
    roster = [{"name": g["name"], "avoid": g.get("avoid", []), "limit": g.get("limit", [])} for g in guests]
    current = {k: plan.get(k) for k in SCHEMA["properties"]}
    text, results = pplx.agent(
        client, instructions=REVISE, name="pumpkinpi_revise", schema=SCHEMA,
        input=context(roster, diets, topping_type or plan.get("topping_type"), layers) +
              f"Current design: {json.dumps(current)}\n\nChange: {change}",
    )
    new = tidy(json.loads(text), plan)
    new["sources"] = plan.get("sources", [])
    if new.get("kind") == "question" or new["ingredients"] != plan.get("ingredients"):   # new research: keep only the new research
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
