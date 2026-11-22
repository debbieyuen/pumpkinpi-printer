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
