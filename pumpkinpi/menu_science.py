"""The science behind tonight's menu, from verified sources only (CDC, FDA, NIH/PubMed, USDA, ...).

One deep-research Agent API run (effort="high", web search limited to government health agencies,
peer-reviewed research and allergy/health organizations). It explains the allergy facts for the
guests' allergens and any label words in the menu (organic, natural flavor, ...), each with a link.

This is background reading for the Sources card. It never changes a label verdict: the per-product
Search API + Decider check is still the only gate.
"""
from __future__ import annotations

import json

import httpx

from . import pplx

DOMAINS = ["cdc.gov", "fda.gov", "nih.gov", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "usda.gov",
           "foodsafety.gov", "cochranelibrary.com", "who.int", "foodallergy.org", "aaaai.org", "acaai.org",
           "diabetes.org", "heart.org", "arthritis.org", "ucanr.edu", "extension.psu.edu"]

SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "2-4 words, e.g. 'Peanut vs tree nut'"},
            "fact": {"type": "string", "description": "One plain sentence, under 140 characters"},
            "source": {"type": "string", "description": "Publisher, e.g. FDA, CDC, NIH (PubMed study)"},
            "url": {"type": "string", "description": "The exact page you read this on"},
        },
        "required": ["topic", "fact", "source", "url"], "additionalProperties": False}}},
    "required": ["facts"], "additionalProperties": False,
}

INSTRUCTIONS = """You research the food science behind one family dinner, using only government health
agencies (CDC, FDA, NIH, USDA), peer-reviewed research (PubMed, Cochrane) and major allergy and health
organizations. Give 5 to 7 facts, each from a page you actually read, covering:
- each allergen listed: how it is labeled in the US (FDA allergen rules), cross-contact and
  "may contain" statements, and how common or serious it is
- peanuts vs tree nuts, and fish vs shellfish, when those allergens are listed
- any label words in the menu (organic, natural flavor, gluten-free, ...): what the rule really means
  and what research says (for organic: USDA rules and what studies found on nutrition and residues)
- low added sugar, if a guest limits sugar: one guideline from a health authority
Rules: plain words, one sentence per fact, no medical advice, never say a specific product is safe.
Put the exact URL of the page each fact came from. Return only JSON matching the schema."""


def research(client: httpx.Client, menu: dict, guest_list: list[dict]) -> dict:
    allergens = sorted({a for g in guest_list for a in g.get("avoid", [])})
    limits = sorted({x for g in guest_list for x in g.get("limit", [])})
    items = [p.get("item") if isinstance(p, dict) else str(p)
             for d in menu.get("menu", []) for p in d.get("products", [])] + [
             p.get("item") if isinstance(p, dict) else str(p) for p in menu.get("sauces", [])]
    text, results = pplx.agent(
        client, instructions=INSTRUCTIONS, name="pumpkinpi_menu_science", schema=SCHEMA, domains=DOMAINS,
        effort="high",
        input=f"Menu: {menu.get('menu_title') or menu.get('title')}\nItems: {json.dumps(items)}\n"
              f"Allergens to avoid: {json.dumps(allergens)}\nLimits: {json.dumps(limits)}")
    return clean(json.loads(text).get("facts", []), results)


def clean(facts: list[dict], results: list[dict]) -> dict:
    """Keep only facts whose link is on a verified domain and was really returned by the search."""
    seen = {r.get("url", "").rstrip("/") for r in results if r.get("url")}
    titles = {r.get("url", "").rstrip("/"): r.get("title") for r in results if r.get("url")}
    out = []
    for f in facts:
        u = (f.get("url") or "").strip()
        host = u.split("/")[2].lower() if u.count("/") >= 2 else ""
        if not any(host == d or host.endswith("." + d) for d in DOMAINS):
            continue
        if seen and u.rstrip("/") not in seen:
            continue
        out.append({"topic": f["topic"][:40], "fact": f["fact"][:200], "source": f["source"][:40], "url": u,
                    "title": titles.get(u.rstrip("/")) or f["source"]})
    return {"facts": out[:7]}
