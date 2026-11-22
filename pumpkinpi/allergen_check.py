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
FLAVOR_AT = 0.5     # "natural flavor" can hide coconut and other removed tree nuts -> yellow


def search_queries(product: str, allergens: list[str]) -> list[str]:
    return [f"{product} ingredients allergen statement",
            f"{product} may contain {' '.join(allergens)} shared facility"]


def check_ingredient(client: httpx.Client, product: str, allergens: list[str]) -> dict:
    """Search API for evidence, then Decider answers one question per allergen on that evidence.

    Returns {"product", "search": {"queries", "results"}, "checks": {allergen: Check}, "relevance", "natural_flavor"}.
    """
    from . import pplx

    queries = search_queries(product, allergens)
    results = pplx.search(client, queries, max_results=6)
    if not results:  # nothing found: fall back to Decider's own grounded search
        checks = {a: check_product(client, product, a) for a in allergens}
        return {"product": product, "search": {"queries": queries, "results": []},
                "checks": checks, "relevance": None, "natural_flavor": None}

    state = {"product": product,
             "evidence": [{"title": r.get("title"), "url": r.get("url"), "text": (r.get("snippet") or "")[:2500]}
                          for r in results]}
    questions = {
        "about_product": {"type": "noul", "instructions":
                          f"Does the evidence include the ingredient list or allergen statement for this exact product: {product}?"},
        "natural_flavor": {"type": "noul", "instructions":
                           "Does the product's ingredient list include 'natural flavor', 'flavoring' or another unspecified flavor?"},
    }
    for i, a in enumerate(allergens):
        questions[f"a{i}"] = {"type": "noul", "instructions":
                              f"Based on the evidence, does {product} contain {a} or a {a}-derived ingredient, "
                              f"or carry a may-contain or shared-facility warning for {a}?"}
    ans = pplx.decide(client, state, questions)["answers"]
    rel = float(ans["about_product"]["noul"])
    flav = float(ans["natural_flavor"]["noul"])
    urls = [r["url"] for r in results if r.get("url")]
    checks = {}
    for i, a in enumerate(allergens):
        p = float(ans[f"a{i}"]["noul"])
        v = verdict_for(p)
        if v == "safe" and (rel < RELEVANT_AT or flav >= FLAVOR_AT):
            v = "unsure"  # no label for this exact product, or a hidden-flavor risk: check the label
        checks[a] = Check(product, a, p, v, urls)
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
