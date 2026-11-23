from pathlib import Path
from pumpkinpi import cards

ROOT = Path(__file__).resolve().parents[1]


def test_6x9_card_draws_inside_bed():
    cfg = cards.load(ROOT / "cards.example.json", use_menu=False)
    cfg["card"].update({"w": 152.4, "h": 228.6, "margin": 15})
    g = cards.card_gcode(cards.layout(cfg, [], "Debbie", "front"), cards.Pla(nozzle=190, card_x=34, card_y=-4))
    assert "M140 S0" in g and "M106 S255" in g and "M109 S190" in g
    ys = [float(l.split()[2][1:]) for l in g if l.startswith("G1 X")]
    assert ys and 2 <= min(ys) and max(ys) <= 215


def test_end_pause_comes_after_retract_and_before_lift():
    st = [[(10, 10), (12, 10)]]
    g = cards.card_gcode(st, cards.Pla(bed=50, retract=0.8, end_pause=0.15, hop=0.8, layers=1))
    i = g.index("G4 P150")
    assert g[i - 1] == "G1 E-0.80 F2700" and g[i + 1].startswith("G0 Z")
    assert all("G4" not in ln for ln in cards.card_gcode(st, cards.Pla(layers=1)))   # paper default unchanged


def test_whole_foods_ok_but_not_mixtures():
    for n in ["Diamond Crystal Kosher Salt, 3 lb box", "Vital Farms Pasture-Raised Large Eggs 12 ct", "Bone-in leg of lamb"]:
        assert set(cards.term_status({"item": n}, None).values()) == {"safe"}, n
    for n in ["garlic powder", "egg noodles", "McCormick Pumpkin Pie Spice", "salmon", "Salted caramel"]:
        assert "unsure" in cards.term_status({"item": n}, None).values(), n
    found = {"checks": {cards.TERMS["tree nut"]: {"verdict": "found"}}}
    assert cards.term_status({"item": "Almond-fed chicken"}, found)["tree nut"] == "found"


def test_nut_examples_are_red_and_cited():
    from pumpkinpi import menu_plan
    lines = cards.item_lines([("Example", p) for p in menu_plan.EXAMPLES], {})
    assert lines[0]["terms"]["peanut"] == "found" and lines[1]["terms"]["tree nut"] == "found"
    assert all(p["source"].startswith("https://") for p in menu_plan.EXAMPLES)


def test_wipe_moves_back_along_the_stroke_after_retract():
    st = [[(10, 10), (20, 10)]]
    g = cards.card_gcode(st, cards.Pla(retract=1.2, retract_feed=2400, wipe=1.5, layers=1, card_x=0, card_y=0))
    i = g.index("G1 E-1.20 F2400")
    assert g[i + 1].startswith("G1 X18.50 Y10.00")          # 1.5 mm back from the end, no extrusion
    assert cards.wipe_point([(0, 0), (1, 0)], 5) == (0, 0)  # short stroke: wipe to its start, never past it
