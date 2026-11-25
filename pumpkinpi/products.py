"""Exact store products: photo + printed label from Open Food Facts.

The Agent API names each ingredient as a real product ("Enjoy Life Semi-Sweet Mini Chips, 9 oz")
and, when it can find one, its UPC barcode. This module looks that product up on Open Food Facts
(https://openfoodfacts.github.io/openfoodfacts-server/api/) to get:

  image        front-of-pack photo, shown on the Recipe screen
  ingredients  the ingredient list as printed
  allergens    "Contains" allergens, e.g. ["milk", "soybeans"]
  traces       "May contain" allergens, e.g. ["peanuts"]

Open Food Facts is crowd-sourced and often misses may-contain lines (its M&M's Milk Chocolate
entry has no traces, but the bag says "May contain peanuts"). So this label is only one piece of
evidence for the Decider, never a green light on its own. No API key; nothing secret is sent.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

OFF = "https://world.openfoodfacts.org"
OFF_SEARCH = "https://search.openfoodfacts.org/search"
UA = "PumpkinPi/1.0 (github.com/debbieyuen/pumpkinpi-food-printer)"
FIELDS = "code,product_name,brands,quantity,image_front_url,ingredients_text,allergens_tags,traces_tags"


def _tags(xs) -> list[str]:
    return [x.split(":", 1)[-1].replace("-", " ") for x in xs or []]


def _label(p: dict) -> dict:
    code = p.get("code", "")
    return {"upc": code, "name": p.get("product_name") or "", "brand": ", ".join(p["brands"]) if isinstance(p.get("brands"), list) else p.get("brands") or "",
            "size": p.get("quantity") or "", "image": p.get("image_front_url") or "",
            "ingredients": p.get("ingredients_text") or "", "allergens": _tags(p.get("allergens_tags")),
            "traces": _tags(p.get("traces_tags")), "url": f"{OFF}/product/{code}" if code else ""}


def lookup(product: dict, client: httpx.Client | None = None) -> dict | None:
    """product: {"ingredient", "brand", "product", "upc"} from the design plan. None if not found."""
    own = client is None
    c = client or httpx.Client(headers={"User-Agent": UA}, timeout=8.0)
    try:
        upc = "".join(ch for ch in str(product.get("upc") or "") if ch.isdigit())
        if len(upc) >= 8:
            r = c.get(f"{OFF}/api/v2/product/{upc}.json", params={"fields": FIELDS})
            if r.status_code == 200 and r.json().get("status") == 1:
                return _label(r.json()["product"])
        brand = (product.get("brand") or "").strip()
        name = (product.get("product") or product.get("ingredient") or "").strip()
        if not name:
            return None
        hits = []
        for q in ([f'brands:"{brand}" {name}'] if brand else []) + [f"{brand} {name}".strip()]:
            r = c.get(OFF_SEARCH, params={"q": q, "page_size": 8, "fields": FIELDS})
            if r.status_code == 200:
                hits += r.json().get("hits") or []
        # Only accept a hit from the same brand; a lookalike product's label is worse than none.
        b = brand.lower().replace("’", "'")
        for h in hits:
            hb = " ".join(h.get("brands") or []) if isinstance(h.get("brands"), list) else str(h.get("brands") or "")
            words = f"{hb} {h.get('product_name') or ''}".lower().replace("’", "'")
            if b and b in words and h.get("image_front_url"):
                return _label(h)
        return None
    except (httpx.HTTPError, ValueError):
        return None   # offline or Open Food Facts down: the check still runs on Search API evidence
    finally:
        if own:
            c.close()


def enrich(products: list[dict]) -> list[dict]:
    """Add a "label" (or None) to every product, looked up in parallel."""
    with httpx.Client(headers={"User-Agent": UA}, timeout=8.0) as c, ThreadPoolExecutor(4) as ex:
        labels = list(ex.map(lambda p: lookup(p, c), products))
    return [{**p, "label": lab} for p, lab in zip(products, labels)]
