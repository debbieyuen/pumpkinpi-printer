import pytest

from pumpkinpi import cards


def res(**verdicts):
    return {"checks": {cards.TERMS[t]: {"verdict": v, "sources": ["https://example.com/label"]} for t, v in verdicts.items()}}


def test_dish_line_names_red_terms_and_marks_unsure():
    dish = {"name": "Dip", "products": ["A", "B"], "terms": ["soy", "sesame", "fish"]}
    line = cards.dish_line(dish, {"A": res(soy="found", sesame="safe", fish="safe"),
                                  "B": res(soy="safe", sesame="found", fish="unsure")})
    assert line["contains"] == ["soy", "sesame"]
    assert line["unsure"] == ["fish"]
    assert line["text"] == "Dip: soy, sesame ?"


def test_unchecked_product_is_never_printed_as_clean():
    line = cards.dish_line({"name": "Veg", "products": ["X"], "terms": ["soy"]}, {})
    assert line["text"].endswith("?")


def test_card_fits_and_gcode_stays_on_card():
    cfg = cards.load()
    lines = [{"text": f"Dish {i}: soy, wheat", "unsure": ["egg"]} for i in range(6)]
    st = cards.layout(cfg, lines, "Lily")
    W, H = cfg["card"]["w"], cfg["card"]["h"]
    assert all(0 <= x <= W and 0 <= y <= H for s in st for x, y in s)
    p = cards.Pla()
    g = cards.card_gcode(st, p)
    assert "G28" not in g                       # homing only in prep, with the bed empty
    assert g[-7] == "M104 S0"                   # heater off at the end
    zs = [float(w[1:]) for ln in g if ln.startswith(("G0", "G1")) for w in ln.split()[1:] if w[0] == "Z"]
    assert min(zs) >= p.paper_z + p.layer - 1e-6


def test_too_many_dishes_refused():
    with pytest.raises(ValueError):
        cards.layout(cards.load(), [{"text": "x: y", "unsure": []}] * 20)


def test_prep_homes_then_parks_high():
    g = cards.prep_gcode(cards.Pla())
    assert g.index("G28") < g.index("M109 S205")
    assert any(ln.startswith("G0 Z40") for ln in g)


def test_back_lists_exact_label_ingredients_and_fits():
    cfg = cards.load()
    texts = [r[0] for r in cards.back_rows(cfg)]
    assert any(t.startswith("Tofu: water, soybeans") for t in texts)
    assert any(t.startswith("Soy sauce: water, soybeans, wheat") for t in texts)
    assert "How to hot pot" in texts
    st = cards.layout(cfg, [], side="back")
    W, H = cfg["card"]["w"], cfg["card"]["h"]
    assert all(0 <= x <= W and 0 <= y <= H for s in st for x, y in s)


def test_every_labeled_product_has_a_source_and_reaches_the_decider(monkeypatch):
    cfg = cards.load()
    for d in cfg["menu"]:
        for p in d["products"]:
            if p.get("tag"):                       # packaged product: exact label + where it came from
                assert p["label"] and p["source"].startswith("https://")
    seen = {}

    def fake(client, prod, allergens, label=None):
        seen[prod] = label
        return {"checks": {}, "relevance": None}
    monkeypatch.setattr("pumpkinpi.allergen_check.check_ingredient", fake)
    lines = cards.check_menu(None, cfg)
    assert seen["Kikkoman Soy Sauce"]["ingredients"].startswith("Water, Soybeans, Wheat")
    assert all(ln["text"].endswith("?") for ln in lines)     # no verdicts -> never printed as clean


def test_recipe_label_is_evidence():
    from pumpkinpi.allergen_check import label_evidence
    ev = label_evidence(cards.prod_label({"item": "Tofu", "label": "Water, Soybeans", "source": "https://x"}))
    assert "Water, Soybeans" in ev[0]["text"] and ev[0]["url"] == "https://x"
