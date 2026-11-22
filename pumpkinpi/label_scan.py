"""Scan a package label with the Pi camera.

Hold the bag or box up to the camera and tap Scan label:

  1. The live camera frame goes to the Agent API as an image, which reads the label word for word
     (brand, product, ingredients, "Contains", "May contain" / shared-equipment lines).
     https://docs.perplexity.ai/docs/agent-api/image-attachments
  2. The reading becomes label evidence for the normal ingredient check (Search API + Decider),
     so a photo of the real bag counts alongside the web pages.
  3. A local name scan of the printed text (allergens.py) can only make the result stricter:
     "almonds" in the ingredients is red, "natural flavor" or "coconut" is check-the-label,
     and an allergen named in a may-contain line is red. A cut-off or blurry label is never green.

If the product matches an ingredient in the current recipe, the result counts for that ingredient.
"""
from __future__ import annotations

import json
import re

from . import pplx
from .allergens import key_for, name_hits

SCHEMA = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean", "description": "True only if the ingredient list can be read"},
        "complete": {"type": "boolean", "description": "True only if the whole ingredient list and allergen statement are in the photo and sharp"},
        "brand": {"type": "string"},
        "product": {"type": "string"},
        "size": {"type": "string"},
        "ingredients": {"type": "string", "description": "The ingredient list exactly as printed"},
        "contains": {"type": "array", "items": {"type": "string"}, "description": "Allergens in the 'Contains' statement, as printed"},
        "may_contain": {"type": "string", "description": "Any may-contain, shared-equipment or facility line, exactly as printed; empty if none"},
        "problem": {"type": "string", "description": "What stops a full reading (glare, cut off, blurry); empty if none"},
    },
    "required": ["readable", "complete", "brand", "product", "size", "ingredients", "contains", "may_contain", "problem"],
}

INSTRUCTIONS = """You read food package labels for an allergy check. Copy text exactly as printed; never guess,
never fill in words you cannot see, and never add ingredients from memory of the product. If any part of
the ingredient list or allergen statement is cut off, blurry or covered, set complete=false and say why
in problem. If there is no readable ingredient list, set readable=false."""


def _json(text: str) -> dict:
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("The label reading came back empty")
        return json.loads(m.group(0))


def read_label(client, jpeg: bytes) -> dict:
    raw = _json(pplx.agent_image(client, instructions=INSTRUCTIONS, jpeg=jpeg, schema=SCHEMA, name="label",
                                 text="Read this package label."))
    out = {k: raw.get(k, "" if SCHEMA["properties"][k]["type"] == "string" else None) for k in SCHEMA["properties"]}
    out["contains"] = [str(x) for x in raw.get("contains") or []]
    out["readable"] = bool(raw.get("readable")) and bool((out["ingredients"] or "").strip())
    out["complete"] = bool(raw.get("complete")) and out["readable"]
    return out


def title(read: dict) -> str:
    return " ".join(x for x in (read.get("brand"), read.get("product"), read.get("size")) if x).strip()


def as_label(read: dict, image: str = "") -> dict:
    """Same shape as an Open Food Facts label (products.py), so the ingredient check can use it."""
    return {"source": "camera", "upc": "", "name": read.get("product") or "", "brand": read.get("brand") or "",
            "size": read.get("size") or "", "image": image, "ingredients": read.get("ingredients") or "",
            "allergens": read.get("contains") or [], "traces": [read["may_contain"]] if read.get("may_contain") else [],
            "url": ""}


_WORDS = re.compile(r"[a-z0-9]+")
_SKIP = {"oz", "fl", "lb", "g", "ml", "the", "and", "of", "with", "organic", "pint", "quart", "can", "pack"}


def _words(s: str) -> set[str]:
    return {w for w in _WORDS.findall((s or "").lower().replace("’", "'")) if w not in _SKIP and not w.isdigit()}


def match_ingredient(read: dict, plan: dict | None) -> str | None:
    """Which recipe ingredient this bag is, or None. The brand must match when the recipe names one."""
    if not plan:
        return None
    seen = _words(title(read))
    best, score = None, 0.0
    for p in plan.get("products") or []:
        brand = _words(p.get("brand", ""))
        if brand and not brand <= seen:
            continue
        want = _words(f"{p.get('product', '')} {p.get('ingredient', '')}") - brand
        if not want:
            continue
        s = len(want & seen) / len(want)
        if s > score:
            best, score = p["ingredient"], s
    return best if score >= 0.5 else None


def printed_hits(read: dict, allergen: str) -> dict:
    """Name scan of what is printed. may_contain = the allergen (or a name for it) is in the may-contain line."""
    body = " ".join([read.get("ingredients") or "", " ".join(read.get("contains") or [])])
    h = name_hits(body, allergen)
    warn = read.get("may_contain") or ""
    k = key_for(allergen)
    may = bool(warn) and (allergen.lower() in warn.lower() or bool(name_hits(warn, allergen)["contains"])
                          or (k == "tree nuts" and re.search(r"\btree\s*nuts?\b", warn, re.I) is not None)
                          or (k == "peanuts" and re.search(r"\bpeanuts?\b", warn, re.I) is not None))
    return {**h, "may_contain": may}


def apply_printed(checks: dict, read: dict) -> None:
    """Make each Check stricter from the printed text. Never turns anything greener."""
    for a, c in checks.items():
        h = printed_hits(read, a)
        if h["contains"]:
            c.probability, c.verdict, c.note = 1.0, "found", f"label lists {h['contains'][0]}"
        elif h["may_contain"]:
            c.probability, c.verdict, c.note = max(c.probability, 0.9), "found", f"label: {read['may_contain'][:80]}"
        elif c.verdict == "safe" and h["check"]:
            c.verdict, c.note = "unsure", f"label lists {h['check'][0]}: check with the maker"
        elif c.verdict == "safe" and not read.get("complete"):
            c.verdict, c.note = "unsure", f"part of the label wasn't readable{': ' + read['problem'] if read.get('problem') else ''}"
