"""Safety gate: ask the Perplexity Decisions API whether a product contains an allergen.

Uses POST https://api.perplexity.ai/v1/decisions with mode="web_grounding", so the
model searches the web first and returns the evidence in `search_results`.
Docs: https://docs.perplexity.ai/docs/decisions/decisions#web-grounding

Two paths:
  check_ingredient()  Search API gathers label pages, then ONE Decider call judges every
                      allergen against that evidence (what the touchscreen uses).
  check_product()     Decider with mode=web_grounding, one call per allergen (CLI / fallback).

Verdicts:
  "found"  (red)    probability of allergen >= FOUND_AT  -> printer must not start
  "unsure" (yellow) in between                          -> check the label
  "safe"   (green)  probability <= SAFE_AT              -> OK, still show sources
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field

import httpx

DECISIONS_URL = "https://api.perplexity.ai/v1/decisions"
MODEL = "pplx-decider-latest"
FOUND_AT = 0.7
SAFE_AT = 0.1
RETRIES = 3


@dataclass
class Check:
    product: str
    allergen: str
    probability: float
    verdict: str
    sources: list[str] = field(default_factory=list)
    note: str = ""   # why, in a few words ("almond milk is a tree nut")


def verdict_for(p: float) -> str:
    if p >= FOUND_AT:
        return "found"
    if p <= SAFE_AT:
        return "safe"
    return "unsure"


def check_product(client: httpx.Client, product: str, allergen: str) -> Check:
    """One grounded yes/no question: does `product` contain `allergen`?"""
    body = {
        "model": MODEL,
        "mode": "web_grounding",
        # Product first: the search query is built from the question plus the start of state.
        "state": f"Product: {product}. Ingredients, allergen statements and may-contain warnings.",
        "questions": {
            "contains": {
                "type": "noul",
                "instructions": f"Does this product contain {allergen} or a {allergen}-derived ingredient?",
            }
        },
    }
    for attempt in range(RETRIES + 1):
        r = client.post(DECISIONS_URL, json=body)
        if r.status_code == 200:
            data = r.json()
            p = float(data["answers"]["contains"]["noul"])
            urls = [s["url"] for s in data.get("search_results") or [] if "url" in s]
            return Check(product, allergen, p, verdict_for(p), urls)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES:
            time.sleep(min(2**attempt, 30))
            continue
        raise RuntimeError(f"Decisions API {r.status_code}: {r.text[:200]}")
    raise RuntimeError("unreachable")


RELEVANT_AT = 0.7   # evidence must describe this exact product before anything is green
LEAN_SAFE_AT = 0.3  # found this exact product's label and the Decider leans no -> safe (cited to that label)
FLAVOR_AT = 0.5     # "natural flavor" can hide coconut and other removed tree nuts -> yellow


def search_queries(product: str, allergens: list[str]) -> list[str]:
    """Up to 5 Search API queries: the label, then one per allergen with its hidden names.

    "semi-sweet chocolate chips tree nuts almond hazelnut cross-contact" finds the brand pages and
    allergy-group pages that a generic "allergen statement" query misses.
    """
    from .allergens import key_for, search_terms

    q = [f"{product} ingredients allergen statement may contain"]
    nutty = [a for a in allergens if key_for(a)]
    for a in nutty[:3]:
        words = " ".join(search_terms(a, 3))
        q.append(f"{product} {a} {words} shared equipment cross-contact")
    other = [a for a in allergens if not key_for(a)]
    if other:
        q.append(f"is {product} {' '.join(other)}")
    return q[:5]


def tag_result(r: dict, allergens: list[str]) -> str:
    """Which allergen a source talks about (for grouping on screen), else "label"."""
    from .allergens import key_for, name_hits

    text = f"{r.get('title') or ''} {r.get('snippet') or ''}"[:4000]
    for a in allergens:
        k = key_for(a)
        if k and (a.lower() in text.lower() or name_hits(text, a)["contains"]):
            return k
    return "label"


def flag_by_name(product: str, a: str, p: float, v: str) -> tuple[float, str, str]:
    """Stricter only: the product's own name contains the allergen (red) or a check-the-label word (yellow)."""
    from .allergens import name_hits

    h = name_hits(product, a)
    if h["contains"]:
        return 1.0, "found", f"{h['contains'][0]} is {a}"
    if h["check"] and v == "safe":
        return p, "unsure", f"{h['check'][0]}: check the label for {a}"
    return p, v, ""


# Store / website boilerplate that lists every allergen for every product, e.g. Acme/Safeway:
# "Products in our stores may contain, or may have been exposed to, ... peanuts, tree nuts, sesame, ... fish".
# It says nothing about this product, so it's removed before the Decider reads the evidence.
BOILERPLATE = re.compile(
    r"[^.\n]*(?:\bour stores?\b|\bin (?:our|the) (?:store|bakery|deli|kitchen)s?\b|may have been exposed to|"
    r"actual product packaging|not intended to be a substitute|does not represent or warrant|"
    r"product information is provided by|for educational purposes only)[^.\n]*[.\n]?", re.I)


def strip_boilerplate(text: str) -> str:
    return re.sub(r"\s{2,}", " ", BOILERPLATE.sub(" ", text or "")).strip()


def label_evidence(label: dict | None) -> list[dict]:
    """A package label as one evidence item, or nothing.

    From Open Food Facts (products.py) or from the Pi camera (label_scan.py, source="camera")."""
    if not label or not (label.get("ingredients") or label.get("allergens")):
        return []
    cam = label.get("source") == "camera"
    if label.get("source") == "recipe":   # the exact label text we typed into cards.json, with its web source
        return [{"title": f"Label as written in the recipe: {label.get('name', '')}", "url": label.get("url"),
                 "text": (f"Exact ingredients on the label of {label.get('name', '')}: {label.get('ingredients')}. "
                          f"Contains: {', '.join(label.get('allergens') or []) or 'none listed'}.")}]
    missing = "none printed" if cam else "none listed (Open Food Facts often misses these)"
    text = (f"{'Photo of the package label' if cam else 'Package label'} for {label.get('brand', '')} "
            f"{label.get('name', '')} {label.get('size', '')}. "
            f"Ingredients: {label.get('ingredients') or 'not listed'}. "
            f"Contains: {', '.join(label.get('allergens') or []) or 'none listed'}. "
            f"May contain: {', '.join(label.get('traces') or []) or missing}.")
    title = "Camera photo of the label" if cam else "Open Food Facts"
    return [{"title": f"{title}: {label.get('brand', '')} {label.get('name', '')}".strip(),
             "url": label.get("url"), "text": text}]


def check_ingredient(client: httpx.Client, product: str, allergens: list[str], label: dict | None = None) -> dict:
    """Search API for evidence, then Decider answers one question per allergen on that evidence.

    `label` is the Open Food Facts entry for this exact product (photo, printed ingredients,
    contains / may-contain), added as extra evidence. It never turns a result green by itself.

    Returns {"product", "search": {"queries", "results"}, "checks": {allergen: Check}, "relevance", "natural_flavor"}.
    Each result gets "tag": "tree nuts" / "peanuts" / "fish" / "label".
    """
    from . import pplx
    from .allergens import HIDDEN, key_for

    queries = search_queries(product, allergens)
    results = pplx.search(client, queries, max_results=12)
    if not results and not label_evidence(label):  # nothing found: fall back to Decider's own grounded search
        checks = {}
        for a in allergens:
            c = check_product(client, product, a)
            c.probability, c.verdict, c.note = flag_by_name(product, a, c.probability, c.verdict)
            checks[a] = c
        return {"product": product, "search": {"queries": queries, "results": []},
                "checks": checks, "relevance": None, "natural_flavor": None}
    for r in results:
        r["tag"] = tag_result(r, allergens)

    state = {"product": product,
             "evidence": label_evidence(label) +
                         [{"title": r.get("title"), "url": r.get("url"), "text": strip_boilerplate(r.get("snippet") or "")[:2500]}
                          for r in results]}
    questions = {
        "about_product": {"type": "noul", "instructions":
                          f"Does the evidence include the ingredient list or allergen statement for this exact product: {product}?"},
        "natural_flavor": {"type": "noul", "instructions":
                           "Does the product's ingredient list include 'natural flavor', 'flavoring' or another unspecified flavor?"},
    }
    for i, a in enumerate(allergens):
        k = key_for(a)
        hidden = f" Count every form of it, including {', '.join(HIDDEN[k]['contains'][:18])}." if k else ""
        questions[f"a{i}"] = {"type": "noul", "instructions":
                              f"Based on the evidence, does {product} contain {a} or a {a}-derived ingredient, "
                              f"or carry a may-contain or shared-facility/equipment warning for {a}?{hidden} "
                              f"Only count this product's own ingredient list, Contains line or may-contain line. "
                              f"Ignore store or website notices that list many allergens for every product."}
    ans = pplx.decide(client, state, questions)["answers"]
    rel = float(ans["about_product"]["noul"])
    flav = float(ans["natural_flavor"]["noul"])
    checks = {}
    for i, a in enumerate(allergens):
        p = float(ans[f"a{i}"]["noul"])
        v = verdict_for(p)
        note = ""
        if v == "unsure" and p < LEAN_SAFE_AT and rel >= RELEVANT_AT:
            v = "safe"          # the label for this exact product was found and doesn't list it
        if v == "safe" and rel < RELEVANT_AT:
            v, note = "unsure", "no label found for this exact product"
        elif v == "safe" and flav >= FLAVOR_AT:
            v, note = "unsure", "natural flavor can hide nuts"
        p, v, why = flag_by_name(product, a, p, v)
        k = key_for(a)
        mine = [r["url"] for r in results if r.get("url") and r["tag"] in (k, "label")]
        checks[a] = Check(product, a, p, v, mine or [r["url"] for r in results if r.get("url")], why or note)
    return {"product": product, "search": {"queries": queries, "results": results},
            "checks": checks, "relevance": rel, "natural_flavor": flav}


def check_for_guests(client: httpx.Client, product: str, guests: list[dict]) -> list[tuple[str, Check]]:
    """Check one product against every allergen any guest avoids (one call per allergen)."""
    allergens = sorted({a for g in guests for a in g.get("avoid", [])})
    results = {a: check_product(client, product, a) for a in allergens}
    return [(g["name"], results[a]) for g in guests for a in g.get("avoid", [])]


def make_client() -> httpx.Client:
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        raise SystemExit("Set PERPLEXITY_API_KEY first (never hard-code it).")
    return httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=30.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check a product against guests' allergies.")
    ap.add_argument("product", help='e.g. "Barefoot Moscato wine"')
    ap.add_argument("--guests", default="guests.json")
    args = ap.parse_args()
    guests = json.load(open(args.guests))["guests"]
    blocked = False
    with make_client() as client:
        for name, c in check_for_guests(client, args.product, guests):
            icon = {"found": "RED", "unsure": "YELLOW", "safe": "GREEN"}[c.verdict]
            print(f"[{icon}] {name}: {c.allergen} p={c.probability:.2f}")
            for u in c.sources[:3]:
                print(f"    {u}")
            blocked |= c.verdict != "safe"
    print("PRINTER BLOCKED" if blocked else "OK to print")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
