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
