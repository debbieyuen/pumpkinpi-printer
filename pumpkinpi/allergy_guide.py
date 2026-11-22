"""Allergy watch for one recipe: where peanuts, tree nuts and fish hide in THESE ingredients.

Two parts, shown together on the Recipe screen:
  1. allergens.HIDDEN: fixed, cited hidden-name lists (FARE, FDA, ACAAI, AAAAI). Always shown.
  2. research(): one Agent API run, web search limited to allergy authorities, that says which of
     this recipe's ingredients commonly hide each allergen (e.g. "chocolate chips: often made on
     lines shared with tree nuts and peanuts", "vegan cream: some brands are cashew-based").

The research never makes an ingredient green. It only adds things to watch for; the per-ingredient
Search API + Decider check is still the gate, and allergens.scan_recipe() can still block.
"""
from __future__ import annotations

import json

import httpx

from . import pplx
from .allergens import HIDDEN, key_for

DOMAINS = ["foodallergy.org", "fda.gov", "acaai.org", "aaaai.org", "niaid.nih.gov", "pubmed.ncbi.nlm.nih.gov",
           "foodsafety.gov", "allergicliving.com", "kidswithfoodallergies.org", "fsis.usda.gov"]

SCHEMA = {
    "type": "object",
    "properties": {
        "allergens": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "allergen": {"type": "string"},
                "watch": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"ingredient": {"type": "string"},
                                   "risk": {"type": "string", "description": "Under 90 characters"}},
                    "required": ["ingredient", "risk"], "additionalProperties": False}},
                "tip": {"type": "string", "description": "One short line, under 90 characters"},
            },
            "required": ["allergen", "watch", "tip"], "additionalProperties": False}},
    },
    "required": ["allergens"],
    "additionalProperties": False,
}

INSTRUCTIONS = """You research hidden food allergens for a home cook making one topping.
For each allergen, look at each ingredient in the recipe and search for whether that KIND of product
commonly contains the allergen or is made on shared lines with it. Examples of what to look for:
- chocolate chips and candy: often made on lines shared with tree nuts or peanuts
- dairy-free / vegan creams, butters and chocolate: some are made from cashew, almond or coconut
- extracts and flavors: almond extract is a tree nut; "natural flavor" can hide nut flavors
- seed butters and granola: often share equipment with peanuts and tree nuts
- peanuts vs tree nuts: different plants, but often processed together; many people allergic to one react to the other
Rules:
- Only list real, searched risks for the ingredients given. Skip an ingredient with no known risk.
- Never say an ingredient is safe. Say "check the label" when it depends on the brand.
- Keep each risk under 90 characters, plain words. No URLs in the JSON.
Return only JSON matching the schema."""


def research(client: httpx.Client, plan: dict, guests: list[dict]) -> dict:
    allergens = sorted({a for g in guests for a in g.get("avoid", [])})
    text, results = pplx.agent(
        client, instructions=INSTRUCTIONS, name="pumpkinpi_allergy_watch", schema=SCHEMA, domains=DOMAINS,
        input=f"Allergens: {json.dumps(allergens)}\nTopping: {plan.get('topping')}\n"
              f"Ingredients: {json.dumps(plan.get('ingredients', []))}\nSteps: {json.dumps(plan.get('recipe', []))}",
    )
    found = {a["allergen"].lower(): a for a in json.loads(text).get("allergens", [])}
    srcs = [{"title": r.get("title"), "url": r.get("url")} for r in results if r.get("url")]
    return build(allergens, guests, found, srcs)


def build(allergens: list[str], guests: list[dict], found: dict, srcs: list[dict]) -> dict:
    """Merge the fixed cited facts with the per-recipe research into one card per allergen."""
    cards = []
    for a in allergens:
        k = key_for(a)
        fixed = HIDDEN.get(k, {})
        r = found.get(a.lower()) or found.get(k or "") or {}
        mine = [s for s in srcs if k and _about(s, k)] or srcs[:2]
        seen, sources = set(), []
        for s in [*fixed.get("sources", []), *mine]:
            if s["url"] not in seen:
                seen.add(s["url"]); sources.append(s)
        cards.append({
            "allergen": a,
            "guests": [g["name"] for g in guests if a in g.get("avoid", [])],
            "names": fixed.get("show", []),
            "more": max(0, len(fixed.get("contains", [])) - len(fixed.get("show", []))),
            "facts": fixed.get("facts", []),
            "watch": r.get("watch", [])[:4],
            "tip": r.get("tip", ""),
            "sources": sources[:5],
        })
    return {"allergens": cards}


def _about(s: dict, k: str) -> bool:
    t = f"{s.get('title') or ''} {s.get('url') or ''}".lower()
    words = {"tree nuts": ("tree nut", "tree-nut", "almond", "cashew", "hazelnut", "walnut", "coconut"), "peanuts": ("peanut",), "fish": ("fish",)}[k]
    return any(w in t for w in words)


def offline(guests: list[dict]) -> dict:
    """Fixed cited facts only (no API key, or the research failed)."""
    allergens = sorted({a for g in guests for a in g.get("avoid", [])})
    return build(allergens, guests, {}, [])
