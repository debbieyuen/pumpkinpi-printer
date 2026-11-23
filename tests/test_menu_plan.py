import json

import pytest
from fastapi.testclient import TestClient

from pumpkinpi import cards, menu_plan
from pumpkinpi.allergen_check import Check

PLAN = {"title": "Roast chicken", "products": [
    {"item": "Whole chicken", "brand": "Mary's Free Range", "tag": "chicken", "part": "main", "section": "Dinner"},
    {"item": "Garlic", "brand": "", "tag": "garlic", "part": "main", "section": "Dinner"},
    {"item": "Thai fish sauce", "brand": "Red Boat", "tag": "fish sauce", "part": "sauce", "section": "Dinner"},
    {"item": "Pumpkin pie", "brand": "Marie Callender's", "tag": "pumpkin pie", "part": "dessert", "section": "Dessert"},
]}


def test_pack_keeps_lines_short():
    out = menu_plan.pack(["Mary's Free Range chicken", "Garlic", "Yukon gold potatoes"], 34)
    assert out == ["Mary's Free Range chicken, Garlic", "Yukon gold potatoes"]
    assert all(len(x) <= 34 for x in out)


def test_to_cards_splits_sections_and_sauces():
    m = menu_plan.to_cards(PLAN)
    assert m["title"] == "Roast chicken"
    assert [d["name"] for d in m["menu"]] == ["Dinner", "Dessert"]
    assert m["sauces"] == [{"item": "Thai fish sauce", "tag": "fish sauce", "brand": "Red Boat", "card": "Red Boat Thai fish sauce"}]
    assert m["simple"]["Dinner"] == ["Mary's Free Range Whole chicken", "Garlic"]
    assert "brand" not in m["menu"][0]["products"][1]          # fresh garlic has no brand
    # the Agent never supplies a label or source, so nothing can be green without the Decider
    assert not any("label" in p or "source" in p for d in m["menu"] for p in d["products"])


def test_plan_menu_uses_agent_and_rejects_non_meals(monkeypatch):
    seen = {}

    def agent(client, **k):
        seen.update(k)
        return json.dumps(PLAN), []
    monkeypatch.setattr(menu_plan.pplx, "agent", agent)
    m = menu_plan.plan_menu(None, "roast chicken", {"Debbie": ["fish"]})
    assert m["prompt"] == "roast chicken" and "fish" in seen["input"] and seen["schema"] is menu_plan.SCHEMA
    monkeypatch.setattr(menu_plan.pplx, "agent", lambda c, **k: (json.dumps({"title": "", "products": [], "note": "Not food"}), []))
    with pytest.raises(ValueError, match="Not food"):
        menu_plan.plan_menu(None, "a bicycle", {})


def test_load_merges_saved_menu():
    base = cards.load()
    assert base.get("menu_title") == "Hot pot (saved)"
    menu_plan.save({**menu_plan.to_cards(PLAN), "prompt": "roast chicken"})
    cfg = cards.load()
    assert cfg["menu_title"] == "Roast chicken" and cfg["menu_prompt"] == "roast chicken"
    assert cfg["menu"][0]["name"] == "Dinner" and cfg["guests"] == base["guests"]
    assert cards.menu_key(cfg) != cards.menu_key(base)
    assert cards.load(use_menu=False)["menu_title"] == "Hot pot (saved)"


def test_menu_endpoint(tmp_path, monkeypatch):
    import pumpkinpi.server as srv
    from contextlib import contextmanager

    @contextmanager
    def client():
        yield None

    def check(c, product, allergens, label=None):
        bad = "fish" if "fish sauce" in product.lower() else None
        return {"checks": {a: Check(product, a, 0.9 if bad and bad in a else 0.02,
                                    "found" if bad and bad in a else "safe", ["https://example.com"]) for a in allergens},
                "relevance": 0.9}
    monkeypatch.setattr(srv, "make_client", client)
    monkeypatch.setattr(srv, "MENU_CHECK", tmp_path / "menu_check.json")
    monkeypatch.setattr(menu_plan.pplx, "agent", lambda c, **k: (json.dumps(PLAN), []))
    monkeypatch.setattr("pumpkinpi.allergen_check.check_ingredient", check)
    srv.state.pop("cards", None); srv.state.pop("cards_key", None)
    tc = TestClient(srv.app)
    assert tc.post("/api/menu", json={"prompt": "  "}).status_code == 400
    r = tc.post("/api/menu", json={"prompt": "roast chicken; pumpkin pie"})
    assert r.status_code == 200 and r.json()["title"] == "Roast chicken" and r.json()["lines"]
    info = tc.get("/api/cards").json()
    assert info["title"] == "Roast chicken" and info["prompt"] == "roast chicken; pumpkin pie"
    assert any("Red Boat" in x and "fish" in x for x in info["avoid"]["Debbie"])
    monkeypatch.setattr(menu_plan.pplx, "agent", lambda c, **k: (json.dumps({"title": "", "products": []}), []))
    assert tc.post("/api/menu", json={"prompt": "a bicycle"}).status_code == 400


def test_card_word_is_the_exact_product_without_size():
    assert menu_plan.card_word({"item": "Libby's 100% Pure Pumpkin, 15 oz", "brand": "Libby's"}) == "Libby's 100% Pure Pumpkin"
    assert menu_plan.card_word({"item": "Pie Crusts (2 ct)", "brand": "Pillsbury"}) == "Pillsbury Pie Crusts"
    assert menu_plan.card_word({"item": "bok choy"}) == "Bok choy"


def test_agent_label_is_printed_but_never_a_cited_source():
    plan = {"title": "Pie", "_urls": {"https://www.libbys.com/pure-pumpkin"}, "products": [
        {"item": "Libby's 100% Pure Pumpkin, 15 oz", "brand": "Libby's", "tag": "pumpkin", "part": "dessert",
         "section": "Dessert", "ingredients": "Pumpkin.", "label_url": "https://www.libbys.com/pure-pumpkin"},
        {"item": "Made Up Pie, 9 in", "brand": "Nobody", "tag": "pie", "part": "dessert", "section": "Dessert",
         "ingredients": "Flour, butter.", "label_url": "https://not-searched.example/pie"}]}
    a, b = menu_plan.to_cards(plan)["menu"][0]["products"]
    assert a["card"] == "Libby's 100% Pure Pumpkin" and a["ingredients"] == "Pumpkin."
    assert a["label_url"] == "https://www.libbys.com/pure-pumpkin" and "label_url" not in b   # only real search hits
    assert "source" not in a and "label" not in a
    # an agent label alone never turns anything green: no Decider verdict -> unsure
    assert set(cards.term_status(a, None).values()) == {"unsure"}


def test_desserts_never_fish_rule_in_agent_instructions():
    assert "Desserts must never contain fish" in menu_plan.INSTRUCTIONS
