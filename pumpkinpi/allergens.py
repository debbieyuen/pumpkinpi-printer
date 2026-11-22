"""Hidden names for each guest allergen, and a recipe scan that catches them by name.

Lists come from (check these before editing):
  FARE, Tips for Avoiding Your Allergen      https://www.foodallergy.org/media/1706/download
  FARE, Your Food Allergy Field Guide         https://www.foodallergy.org/media/287/download
  FDA, Food Allergen Labeling FAQ (coconut and 11 other nuts removed from the tree-nut list, Jan 2025)
      https://www.fda.gov/food/food-allergensgluten-free-guidance-documents-regulatory-information/frequently-asked-questions-food-allergen-labeling-guidance-industry
  ACAAI, Tree nut allergy (25-40% of peanut-allergic people react to a tree nut; shared lines)
      https://acaai.org/allergies/allergic-conditions/food/tree-nut/
  AAAAI, Tree nut allergy (cashew-pistachio, pecan-walnut are closely related)
      https://www.aaaai.org/tools-for-the-public/conditions-library/allergies/everything-you-need-to-know-about-tree-nut-allergy

The name scan only ever makes things stricter: a hit turns an ingredient red ("contains")
or yellow ("check the label"). No hit never makes anything green; the Decider still decides.
"""
from __future__ import annotations

import re

FARE_TIPS = {"title": "FARE: Tips for avoiding your allergen", "url": "https://www.foodallergy.org/media/1706/download"}
FARE_GUIDE = {"title": "FARE: Food allergy field guide", "url": "https://www.foodallergy.org/media/287/download"}
FDA_FAQ = {"title": "FDA: Food allergen labeling FAQ (tree nut list, coconut)",
           "url": "https://www.fda.gov/food/food-allergensgluten-free-guidance-documents-regulatory-information/frequently-asked-questions-food-allergen-labeling-guidance-industry"}
ACAAI_NUT = {"title": "ACAAI: Tree nut allergy and peanuts", "url": "https://acaai.org/allergies/allergic-conditions/food/tree-nut/"}
AAAAI_NUT = {"title": "AAAAI: Everything you need to know about tree nut allergy",
             "url": "https://www.aaaai.org/tools-for-the-public/conditions-library/allergies/everything-you-need-to-know-about-tree-nut-allergy"}

# contains: the name itself means the allergen is in it -> red.
# check: often or sometimes made with it, or not declared in "Contains" -> yellow, read the label.
HIDDEN: dict[str, dict] = {
    "tree nuts": {
        "contains": [
            "almond", "almond milk", "almond flour", "almond extract", "almond paste", "amaretto", "brazil nut",
            "cashew", "cashew milk", "cashew cream", "filbert", "hazelnut", "gianduja", "nutella", "heartnut",
            "macadamia", "pecan", "pine nut", "pignoli", "pinon", "pistachio", "walnut", "black walnut",
            "marzipan", "praline", "frangipane", "nut milk", "nut butter", "nut meal", "nut paste", "nut oil",
            "mixed nuts", "artificial nuts", "pesto", "nut extract", "chestnut", "hickory nut", "beechnut",
            "ginkgo nut", "lychee nut", "litchi nut", "pili nut", "shea", "nangai",
        ],
        "check": [
            "coconut", "natural flavor", "natural flavoring", "nougat", "mortadella", "sunflower butter",
            "seed butter", "granola", "plant-based cream", "vegan butter", "dairy-free chocolate",
        ],
        "show": ["almond milk", "cashew cream", "praline", "marzipan", "gianduja", "nut extract", "pesto", "nut oils"],
        "facts": [
            "Nut milks, nut butters, marzipan, praline, gianduja and pesto all count as tree nuts.",
            "Coconut left FDA's tree-nut list in 2025, so it won't show in \"Contains\": read the ingredients.",
            "\"May contain\" warnings are voluntary; no warning doesn't mean no shared line.",
            "Chocolate and candy are common unexpected sources.",
        ],
        "sources": [FARE_TIPS, FDA_FAQ, AAAAI_NUT],
    },
    "peanuts": {
        "contains": [
            "peanut", "peanut butter", "peanut flour", "peanut oil", "arachis", "groundnut", "ground nut",
            "goober", "beer nut", "monkey nut", "mandelona", "mixed nuts", "artificial nuts", "nut pieces",
            "lupin", "lupine",
        ],
        "check": [
            "nougat", "marzipan", "chocolate candy", "sunflower seed", "sunflower butter", "seed butter",
            "soy nut butter", "granola", "mole", "natural flavor",
        ],
        "show": ["arachis oil", "groundnut", "peanut flour", "lupin", "nougat", "mixed nuts"],
        "facts": [
            "Arachis oil and groundnut are peanut; cold-pressed peanut oil keeps peanut protein.",
            "Lupin flour can cross-react with peanut.",
            "Tree nuts, seed butters and chocolate are often made on lines shared with peanuts.",
            "25-40% of people with a peanut allergy also react to a tree nut.",
        ],
        "sources": [FARE_GUIDE, ACAAI_NUT],
    },
    "fish": {
        "contains": [
            "fish", "anchovy", "anchovies", "fish sauce", "fish gelatin", "fish oil", "omega-3 from fish",
            "worcestershire", "caesar", "surimi", "bonito", "dashi", "cod", "salmon", "tuna",
        ],
        "check": ["gelatin", "omega-3", "natural flavor"],
        "show": ["anchovy", "Worcestershire", "fish sauce", "Caesar dressing", "fish gelatin"],
        "facts": [
            "Worcestershire sauce, Caesar dressing and fish sauce often contain anchovy.",
            "Gelatin and omega-3 additives can come from fish: read the label.",
        ],
        "sources": [FARE_TIPS],
    },
}

# Words that look like a hit but aren't the allergen (FARE: nutmeg, butternut squash, water chestnut).
NOT_A_HIT = re.compile(r"nutmeg|butternut squash|water chestnuts?|(tree[\s-]*)?(pea)?nut[\s-]*free", re.I)


def _rx(term: str) -> re.Pattern:
    return re.compile(r"(?<![a-z])" + re.escape(term).replace(r"\ ", r"[\s-]*") + r"(e?s)?(?![a-z])", re.I)


_RX = {a: {k: [(t, _rx(t)) for t in v[k]] for k in ("contains", "check")} for a, v in HIDDEN.items()}


def key_for(allergen: str) -> str | None:
    """Map a guest's word ("tree nut", "nuts", "Peanut") to a HIDDEN key."""
    a = allergen.lower().strip()
    if "peanut" in a:
        return "peanuts"
    if "nut" in a:
        return "tree nuts"
    if "fish" in a and "shell" not in a:
        return "fish"
    return None


def name_hits(text: str, allergen: str) -> dict:
    """{"contains": [...terms], "check": [...terms]} found in text by name."""
    k = key_for(allergen)
    if not k:
        return {"contains": [], "check": []}
    clean = NOT_A_HIT.sub(" ", text)
    out = {}
    for kind in ("contains", "check"):
        out[kind] = [t for t, rx in _RX[k][kind] if rx.search(clean)]
    # "almond milk" also matches "almond": keep the longest names only
    for kind in out:
        out[kind] = [t for t in out[kind] if not any(t != u and t in u for u in out[kind])]
    out["check"] = [t for t in out["check"] if t not in out["contains"]]
    return out


def recipe_text(plan: dict) -> list[tuple[str, str]]:
    """(where, text) pairs for every part of a plan that names food."""
    parts = [("topping", plan.get("topping") or "")]
    parts += [("ingredient", i) for i in plan.get("ingredients") or []]
    parts += [(f"step {n + 1}", s) for n, s in enumerate(plan.get("recipe") or [])]
    parts += [("piping notes", plan.get("piping_notes") or "")]
    return parts


def scan_recipe(plan: dict, allergens: list[str]) -> list[dict]:
    """Every hidden-name hit in the topping, ingredients, steps and notes.

    Catches what the ingredient checks can't: "add a drop of almond extract" in a step, or a
    vegan swap like "cashew cream" in the notes that never made it into the ingredient list.
    """
    hits = []
    for a in allergens:
        for where, text in recipe_text(plan):
            h = name_hits(text, a)
            for kind in ("contains", "check"):
                for t in h[kind]:
                    hits.append({"allergen": a, "term": t, "kind": kind, "where": where, "text": text})
    return hits


def scan_blocks(hits: list[dict]) -> list[dict]:
    """Hits that must stop the printer: the recipe names the allergen itself."""
    return [h for h in hits if h["kind"] == "contains"]


def search_terms(allergen: str, n: int = 6) -> list[str]:
    k = key_for(allergen)
    return HIDDEN[k]["contains"][:n] if k else []
