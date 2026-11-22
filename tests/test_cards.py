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
        cfg = cards.load()
        cfg["card"]["style"] = "full"
        cards.layout(cfg, [{"text": "x: y", "unsure": []}] * 40)


def test_prep_homes_then_parks_high():
    g = cards.prep_gcode(cards.Pla())
    assert g.index("G28") < g.index("M109 S205")
    assert any(ln.startswith("G0 Z40") for ln in g)


def test_back_lists_exact_label_ingredients_and_fits():
    cfg = cards.load()
    texts = [r[0] for r in cards.back_rows(cfg)]
    assert any(t.startswith("Tofu (House Foods): water") for t in texts)
    assert any(t.startswith("Soy sauce (Kikkoman): water,") for t in texts)
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
    by = {ln["name"]: ln for ln in cards.guest_lines(cfg, lines, "Debbie")}
    assert by["Satay (Lee Kum Kee)"]["text"] == "Satay (Lee Kum Kee): NO peanut, sesame"
    assert by["Sha cha (Bull Head)"]["text"] == "Sha cha (Bull Head): NO sesame, fish"   # "No addition of peanut"
    assert by["Hoisin (Lee Kum Kee)"]["text"] == "Hoisin (Lee Kum Kee): YES, sesame"
    assert by["Soup base (Little Sheep)"]["text"].startswith("Soup base (Little Sheep): NO")  # may contain fish
    assert by["Tofu (House Foods)"]["text"] == "Tofu (House Foods): YES"


def test_no_source_never_says_yes():
    ln = cards.item_lines([("Dip", {"item": "Mystery sauce", "brand": "Acme", "label": "water, spices"})], {})[0]
    assert cards.line_text(ln, ["peanut", "tree nut", "fish"]).endswith("check label")


def test_decider_found_beats_clean_label():
    p = {"item": "X", "brand": "B", "label": "water", "source": "https://x"}
    r = {"checks": {"peanuts": {"verdict": "found"}}}
    assert cards.term_status(p, r)["peanut"] == "found"


def test_back_has_sauces_and_steps():
    import pumpkinpi.allergen_check as ac
    cfg = cards.load()
    texts = [r[0] for r in cards.sauce_rows(cfg, [], "Debbie")]
    assert texts[0] == "Sauces: can I eat it?" and texts[-1].startswith("YES = no peanut, tree nut or fish")


def test_two_sides_only_and_both_fit():
    import pumpkinpi.allergen_check as ac
    cfg = cards.load()
    orig = ac.check_ingredient
    ac.check_ingredient = lambda c, p, a, label=None: {"checks": {}, "relevance": None}
    try:
        lines = cards.check_menu(None, cfg)
    finally:
        ac.check_ingredient = orig
    W, H = cfg["card"]["w"], cfg["card"]["h"]
    cfg["card"]["style"] = "short"
    for side in ("front", "back"):
        st = cards.layout(cfg, lines, "Debbie", side)
        assert st and all(0 <= x <= W and 0 <= y <= H for s in st for x, y in s)


def test_recipe_label_is_evidence():
    from pumpkinpi.allergen_check import label_evidence
    ev = label_evidence(cards.prod_label({"item": "Tofu", "label": "Water, Soybeans", "source": "https://x"}))
    assert "Water, Soybeans" in ev[0]["text"] and ev[0]["url"] == "https://x"


def test_dessert_lines_on_front_with_brands():
    import pumpkinpi.allergen_check as ac
    cfg = cards.load()
    orig = ac.check_ingredient
    ac.check_ingredient = lambda c, p, a, label=None: {"checks": {}, "relevance": None}
    try:
        lines = cards.check_menu(None, cfg)
    finally:
        ac.check_ingredient = orig
    sweet = [ln for ln in lines if ln["part"] == "dessert"]
    assert len(sweet) == len(cfg["dessert"]["products"])
    assert all("(" in ln["name"] for ln in sweet)
    assert all(p.get("source", "").startswith("https://") for p in cfg["dessert"]["products"])


def test_each_item_printed_once_with_its_ingredients():
    import pumpkinpi.allergen_check as ac
    cfg = cards.load()
    orig = ac.check_ingredient
    ac.check_ingredient = lambda c, p, a, label=None: {"checks": {}, "relevance": None}
    try:
        lines = cards.check_menu(None, cfg)
    finally:
        ac.check_ingredient = orig
    front = [r[0] for r in cards.entry_rows(cfg, cfg["menu"], [x for x in lines if x["part"] == "menu"], "Debbie")]
    back = [r[0] for r in cards.entry_rows(cfg, [cfg["dessert"]], [x for x in lines if x["part"] == "dessert"], "Debbie")]
    heads = [t.split(":")[0] for t in front + back if not t.startswith(" ")]
    assert len(heads) == len(set(heads))
    i = front.index("Tofu (House Foods): YES")
    assert "calcium sulfate" in front[i + 1]


def _lines(cfg):
    import pumpkinpi.allergen_check as ac
    orig = ac.check_ingredient
    ac.check_ingredient = lambda c, p, a, label=None: {"checks": {}, "relevance": None}
    try:
        return cards.check_menu(None, cfg)
    finally:
        ac.check_ingredient = orig


def test_short_card_back_lists_only_nos_for_debbie():
    cfg = cards.load()
    bad = cards.avoid_lines(cfg, _lines(cfg), "Debbie")
    assert "Satay (Lee Kum Kee): peanut, sesame" in bad
    assert "Ponzu (Kikkoman): fish" in bad
    assert not any("YES" in b or "Tofu" in b or "Crust" in b for b in bad)
    texts = [r[0] for r in cards.short_back_rows(cfg, _lines(cfg), "Debbie")]
    assert texts[0] == "Debbie: don't eat" and "Not on the card? Check the label." in texts


def test_unsure_counts_as_dont_eat():
    cfg = cards.load()
    ln = {"name": "Mystery (Brand)", "terms": {t: "unsure" for t in cards.WATCH}, "unsure": ["peanut"]}
    assert "Mystery (Brand): may have peanut" in cards.avoid_lines(cfg, [ln], "Debbie")


def test_michael_unsure_sauces_are_a_no_with_reason():
    cfg = cards.load()
    t = [r[0] for r in cards.simple_rows(cfg, _lines(cfg), "Michael")]
    assert "Lee Kum Kee Satay: coconut" in t and "Bull Head Sha cha: unnamed spices" in t
    assert not any("check label" in x.lower() for x in t)


def test_no_allergy_guest_gets_no_avoid_list():
    cfg = cards.load()
    assert cards.avoid_lines(cfg, _lines(cfg), "Dad") == []
    texts = [r[0] for r in cards.short_back_rows(cfg, [], "Dad")]
    assert "No food allergies on file" in texts


def test_short_card_both_sides_fit_for_every_guest():
    cfg = cards.load()
    L = _lines(cfg)
    for g in cfg["guests"]:
        g = g if isinstance(g, str) else g.get("name", "")
        cfg["card"]["style"] = "short"
        for side in ("front", "back"):
            assert cards.layout(cfg, L, g, side)
        cfg["card"]["style"] = "one"
        assert cards.layout(cfg, L, g, "front") and cards.layout(cfg, L, g, "back") == []


def test_pie_one_line_yes_and_peanut_topping_warning():
    cfg = cards.load()
    L = _lines(cfg)
    assert cards.dessert_verdict(cfg, L, "Debbie") == "YES"
    front = [r[0] for r in cards.short_front_rows(cfg, "Debbie", L)]
    assert "Pumpkin pie: YES" in front
    assert "Peanut topping on pie" in cards.avoid_lines(cfg, L, "Debbie")
    assert "Peanut topping on pie" not in cards.avoid_lines(cfg, L, "Michael")   # peanuts are OK for him


def test_pie_verdict_no_if_any_ingredient_no():
    cfg = cards.load()
    bad = {"name": "Crust (X)", "part": "dessert", "terms": {**{t: "safe" for t in cards.WATCH}, "peanut": "found"},
           "unsure": []}
    assert cards.dessert_verdict(cfg, [bad], "Debbie") == "NO"


def test_broth_is_haidilao_mushroom_with_label():
    cfg = cards.load()
    b = [p for p in cfg["menu"][0]["products"] if isinstance(p, dict) and p.get("tag") == "Broth"][0]
    assert b["brand"] == "Haidilao" and "Mushroom" in b["item"]
    assert b["source"].startswith("https://yihaius.com/")
    assert "Mushroom broth (Haidilao)" in cfg["overview"]


def test_one_page_has_menu_and_dont_eat():
    cfg = cards.load()
    cfg["card"]["style"] = "one"
    L = _lines(cfg)
    t = [r[0] for r in cards.one_page_rows(cfg, L, "Debbie")]
    assert "Pumpkin pie: YES" in t and "Don't eat" in t
    assert "Satay (Lee Kum Kee): peanut, sesame" in t and "Peanut topping on pie" in t
    assert "No food allergies on file" in [r[0] for r in cards.one_page_rows(cfg, L, "Dad")]


def test_simple_card_like_the_note():
    cfg = cards.load()
    assert cfg["card"]["style"] == "simple"
    L = _lines(cfg)
    t = [r[0] for r in cards.simple_rows(cfg, L, "Debbie")]
    assert t[0] == "Debbie" and "Hot Pot Menu:" in t and "Dessert:" in t and "Allergens:" in t
    assert "Lee Kum Kee Satay: peanut, sesame" in t
    assert not any("check label" in x.lower() for x in t)         # every item decided YES/NO
    assert "Everything else: YES" in t and any("Little Sheep lamb" in x for x in t)
    assert any("Mrs. Smith" in x for x in t) and any("Straus" in x for x in t)
    assert cards.layout(cfg, L, "Debbie", "front") and cards.layout(cfg, L, "Debbie", "back") == []


def test_saved_check_from_old_menu_is_ignored(tmp_path, monkeypatch):
    import json
    from pumpkinpi import server, cards
    f = tmp_path / "menu_check.json"
    monkeypatch.setattr(server, "MENU_CHECK", f)
    server.state.pop("cards", None); server.state.pop("cards_key", None)
    f.write_text(json.dumps([{"text": "Beef slices: meat ?"}]))          # old list format
    assert server.card_lines() == []
    cfg = cards.load()
    f.write_text(json.dumps({"key": cards.menu_key(cfg), "lines": [{"text": "ok"}]}))
    server.state.pop("cards_key")
    assert server.card_lines() == [{"text": "ok"}]
    f.write_text(json.dumps({"key": "other", "lines": [{"text": "old"}]}))
    server.state.pop("cards_key")
    assert server.card_lines() == []
