"""Safety gate: ask the Perplexity Decisions API whether a product contains an allergen.

Uses POST https://api.perplexity.ai/v1/decisions with mode="web_grounding", so the
model searches the web first and returns the evidence in `search_results`.
Docs: https://docs.perplexity.ai/docs/decisions/decisions#web-grounding

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
