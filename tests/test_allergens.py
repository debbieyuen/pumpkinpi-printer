import json

import httpx

from pumpkinpi.allergens import name_hits, scan_blocks, scan_recipe
from pumpkinpi.allergen_check import check_ingredient, search_queries
from pumpkinpi import allergy_guide


def test_hidden_tree_nut_names():
    assert name_hits("Unsweetened Almondmilk", "tree nuts")["contains"] == ["almond milk"]
    assert name_hits("hazelnut praline paste", "tree nuts")["contains"] == ["hazelnut", "praline"]
    assert name_hits("Nutella", "tree nuts")["contains"] == ["nutella"]
    assert name_hits("coconut cream", "tree nuts") == {"contains": [], "check": ["coconut"]}


def test_not_nuts():
    for t in ["ground nutmeg", "butternut squash puree", "water chestnuts", "nut-free chocolate chips", "vanilla extract"]:
        assert name_hits(t, "tree nuts")["contains"] == [], t


def test_peanut_is_not_a_tree_nut_but_has_its_own_names():
    assert name_hits("peanut butter", "tree nuts")["contains"] == []
    assert name_hits("peanut butter", "peanuts")["contains"] == ["peanut butter"]
    assert name_hits("arachis oil", "peanuts")["contains"] == ["arachis"]
    assert name_hits("lupin flour", "peanuts")["contains"] == ["lupin"]


def test_fish_names():
    assert name_hits("Worcestershire sauce", "fish")["contains"] == ["worcestershire"]
    assert name_hits("shellfish stock", "fish")["contains"] == []   # shellfish is OK for Debbie


def test_scan_finds_nuts_in_steps():
    plan = {"topping": "ganache", "ingredients": ["chocolate chips", "heavy cream"],
            "recipe": ["Heat cream.", "Stir in a drop of almond extract."], "piping_notes": ""}
    hits = scan_recipe(plan, ["tree nuts", "peanuts"])
    assert [(h["term"], h["where"]) for h in scan_blocks(hits)] == [("almond extract", "step 2")]


def test_queries_name_hidden_nuts_and_fit_the_api():
    q = search_queries("semi-sweet chocolate chips", ["fish", "gluten", "peanuts", "tree nuts"])
    assert len(q) <= 5
    assert any("almond" in x and "tree nuts" in x for x in q)
    assert any("peanut" in x for x in q)


def _client(decider):
    def handler(request):
        if request.url.path == "/search":
            return httpx.Response(200, json={"results": [
                {"title": "Silk Almondmilk", "url": "https://silk.example/almond", "snippet": "Contains: almonds"},
                {"title": "FARE tree nut", "url": "https://foodallergy.org/tree-nut", "snippet": "tree nuts include almond"}]})
        return httpx.Response(200, json={"answers": decider})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_name_overrides_a_low_decider_score():
    r = check_ingredient(_client({"about_product": {"noul": 0.9}, "natural_flavor": {"noul": 0.0},
                                  "a0": {"noul": 0.02}}), "almond milk", ["tree nuts"])
    c = r["checks"]["tree nuts"]
    assert c.verdict == "found" and "almond milk" in c.note
    assert all(x["tag"] == "tree nuts" for x in r["search"]["results"])


def test_coconut_is_check_the_label():
    r = check_ingredient(_client({"about_product": {"noul": 0.9}, "natural_flavor": {"noul": 0.0},
                                  "a0": {"noul": 0.02}}), "coconut cream", ["tree nuts"])
    assert r["checks"]["tree nuts"].verdict == "unsure"


def test_guide_offline_has_cited_cards():
    g = [{"name": "Michael", "avoid": ["tree nuts"]}, {"name": "Debbie", "avoid": ["tree nuts", "peanuts", "fish"]}]
    out = allergy_guide.offline(g)
    cards = {c["allergen"]: c for c in out["allergens"]}
    assert cards["tree nuts"]["guests"] == ["Michael", "Debbie"] and cards["peanuts"]["guests"] == ["Debbie"]
    assert all(c["sources"] and c["names"] for c in cards.values())
    assert any("foodallergy.org" in s["url"] for s in cards["peanuts"]["sources"])
