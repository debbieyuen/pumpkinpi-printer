import json

import httpx

from pumpkinpi.allergen_check import check_for_guests, check_product, verdict_for


def client_returning(p, seen):
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "answers": {"contains": {"type": "noul", "noul": p}},
            "search_results": [{"url": "https://example.com/label"}],
        })
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_uses_web_grounding():
    seen = []
    c = check_product(client_returning(0.95, seen), "Almond wine", "tree nuts")
    assert seen[0]["mode"] == "web_grounding"
    assert seen[0]["model"] == "pplx-decider-latest"
    assert c.verdict == "found" and c.sources == ["https://example.com/label"]


def test_thresholds():
    assert verdict_for(0.05) == "safe"
    assert verdict_for(0.5) == "unsure"
    assert verdict_for(0.9) == "found"


def test_one_call_per_allergen():
    seen = []
    guests = [{"name": "Michael", "avoid": ["tree nuts"]},
              {"name": "Debbie", "avoid": ["tree nuts", "fish"]}]
    rows = check_for_guests(client_returning(0.02, seen), "Pumpkin puree", guests)
    assert len(seen) == 2 and len(rows) == 3


def test_check_ingredient_uses_search_then_one_decider_call():
    from pumpkinpi.allergen_check import check_ingredient
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path == "/search":
            return httpx.Response(200, json={"results": [{"title": "Label", "url": "https://brand.example/chips", "snippet": "Ingredients: sugar, chocolate. May contain milk."}]})
        return httpx.Response(200, json={"answers": {
            "about_product": {"noul": 0.9}, "natural_flavor": {"noul": 0.05},
            "a0": {"noul": 0.03}, "a1": {"noul": 0.85}}})

    r = check_ingredient(httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.perplexity.ai"),
                         "chocolate chips", ["peanuts", "tree nuts"])
    assert [p for p, _ in calls] == ["/search", "/v1/decisions"]
    assert "mode" not in calls[1][1]          # evidence comes from Search, not web_grounding
    assert r["checks"]["peanuts"].verdict == "safe"
    assert r["checks"]["tree nuts"].verdict == "found"


def test_safe_downgraded_when_evidence_is_not_this_product():
    from pumpkinpi.allergen_check import check_ingredient

    def handler(request):
        if request.url.path == "/search":
            return httpx.Response(200, json={"results": [{"title": "x", "url": "https://x.example", "snippet": "..."}]})
        return httpx.Response(200, json={"answers": {
            "about_product": {"noul": 0.2}, "natural_flavor": {"noul": 0.05}, "a0": {"noul": 0.02}}})

    r = check_ingredient(httpx.Client(transport=httpx.MockTransport(handler)), "chips", ["tree nuts"])
    assert r["checks"]["tree nuts"].verdict == "unsure"


def test_label_is_extra_evidence_not_a_pass():
    from pumpkinpi.allergen_check import label_evidence
    assert label_evidence(None) == []
    ev = label_evidence({"brand": "M&M's", "name": "Milk Chocolate", "size": "1.69 oz", "ingredients": "milk chocolate",
                         "allergens": ["milk", "soybeans"], "traces": [], "url": "https://world.openfoodfacts.org/product/0040000000310"})
    assert "Contains: milk, soybeans" in ev[0]["text"] and "often misses" in ev[0]["text"]


def test_design_tidy_keeps_products_in_step():
    from pumpkinpi.design import tidy
    p = tidy({"shape": "dragon", "font": "gothic", "text": "Debbie", "ingredients": ["A", "B"],
              "products": [{"ingredient": "b", "brand": "Clover Sonoma", "product": "Cream", "size": "1 pint", "store": "Safeway", "upc": ""}]})
    assert p["shape"] == "text" and p["font"] == "print"
    assert [x["ingredient"] for x in p["products"]] == ["A", "B"] and p["products"][1]["brand"] == "Clover Sonoma"
