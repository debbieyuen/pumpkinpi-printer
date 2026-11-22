"""Prompt -> design plan, with the Perplexity Agent API (web search + JSON output).

"a smiley face in chocolate for Michael" becomes:
  {"guest": "Michael", "shape": "smiley", "text": "Michael", "topping": "dark chocolate ganache",
   "ingredients": ["semi-sweet chocolate chips", "heavy cream"], ...}

The model picks the shape from a fixed list; shapes.py draws it, so the path always fits the pie.
Every ingredient then goes through the allergen gate (Search API + Decider) before Start unlocks.
"""
from __future__ import annotations

import argparse
import json

import httpx

from . import pplx
from .shapes import MAX_TEXT, SHAPES

SCHEMA = {
    "type": "object",
    "properties": {
        "guest": {"type": "string", "description": "Guest name from the list, or empty"},
        "shape": {"type": "string", "enum": list(SHAPES)},
        "text": {"type": "string", "description": f"Words to pipe, at most {MAX_TEXT} letters, or empty"},
        "topping": {"type": "string", "description": "The pipeable topping, e.g. chocolate ganache"},
        "ingredients": {"type": "array", "items": {"type": "string"},
                        "description": "Each store-bought product needed, as you'd find it on a shelf"},
        "recipe": {"type": "array", "items": {"type": "string"}, "description": "3-5 short steps"},
        "piping_notes": {"type": "string", "description": "Consistency and temperature for a cold syringe"},
        "diet_notes": {"type": "string", "description": "Sugar or other diet notes for guests who limit something"},
        "allergy_notes": {"type": "string", "description": "How the recipe avoids each guest allergen, one short line"},
        "caption": {"type": "string", "description": "One short on-screen line, under 60 characters"},
    },
    "required": ["guest", "shape", "text", "topping", "ingredients", "recipe", "piping_notes", "diet_notes", "allergy_notes", "caption"],
    "additionalProperties": False,
}

INSTRUCTIONS = f"""You plan decorations for PumpkinPi, a printer that pipes toppings onto a 6-inch pumpkin pie
from an unheated 60 mL syringe with a narrow tip.

Rules:
- shape must be one of {list(SHAPES)}. If the request is a different picture, pick the closest one and say so in caption.
- text: the guest's name if they asked for one or if the design is for a named guest, else empty. Max {MAX_TEXT} letters.
- The syringe is NOT heated, so melted chocolate will set in the tip. Turn "chocolate" into a pipeable
  chocolate ganache or chocolate frosting that stays soft at room temperature.
- The topping must avoid every allergen any guest avoids. Prefer 2-3 simple, widely sold ingredients.
- List each ingredient as a product you'd buy (e.g. "semi-sweet chocolate chips"), not a brand claim of safety.
- Never say an ingredient is safe; PumpkinPi checks each one separately. Do not put URLs in the JSON.
- If diet options are given (vegan, dairy-free, gluten-free, egg-free, low sugar), every ingredient must fit them,
  e.g. vegan ganache uses dairy-free chocolate and full-fat coconut cream or another plant cream.
- Search the web for a ganache/frosting ratio and piping consistency; prefer university extension and
  food-safety sites.
Return only a JSON object matching the schema."""


def plan_design(client: httpx.Client, prompt: str, guests: list[dict], diets: list[str] | None = None) -> dict:
    roster = [{"name": g["name"], "avoid": g.get("avoid", []), "limit": g.get("limit", [])} for g in guests]
    text, results = pplx.agent(
        client, instructions=INSTRUCTIONS, name="pumpkinpi_design", schema=SCHEMA,
        input=f"Guests: {json.dumps(roster)}\nDiet options: {json.dumps(diets or [])}\n\nRequest: {prompt}",
    )
    plan = json.loads(text)
    if plan.get("shape") not in SHAPES:
        plan["shape"] = "text"
    plan["text"] = (plan.get("text") or "")[:MAX_TEXT]
    plan["sources"] = [{"title": r.get("title"), "url": r.get("url")} for r in results if r.get("url")][:8]
    return plan


REVISE = INSTRUCTIONS + """

You are changing an existing design. Apply only the requested change and keep everything else
(topping, ingredients, recipe) the same unless the change asks for it. "No name" or "without
Michael's name" means text is empty. "Only a heart" means shape heart; drop the text unless the
change asks for words."""


def revise_design(client: httpx.Client, plan: dict, change: str, guests: list[dict],
                  diets: list[str] | None = None) -> dict:
    """Edit the current plan ("just a heart, no name") instead of starting over."""
    roster = [{"name": g["name"], "avoid": g.get("avoid", []), "limit": g.get("limit", [])} for g in guests]
    current = {k: plan.get(k) for k in SCHEMA["properties"]}
    text, results = pplx.agent(
        client, instructions=REVISE, name="pumpkinpi_revise", schema=SCHEMA,
        input=f"Guests: {json.dumps(roster)}\nDiet options: {json.dumps(diets or [])}\n"
              f"Current design: {json.dumps(current)}\n\nChange: {change}",
    )
    new = json.loads(text)
    if new.get("shape") not in SHAPES:
        new["shape"] = plan.get("shape", "text")
    new["text"] = (new.get("text") or "")[:MAX_TEXT]
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
