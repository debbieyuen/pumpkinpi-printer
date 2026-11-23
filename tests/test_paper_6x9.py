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


def test_whole_foods_ok_but_not_mixtures():
    for n in ["Diamond Crystal Kosher Salt, 3 lb box", "Vital Farms Pasture-Raised Large Eggs 12 ct", "Bone-in leg of lamb"]:
        assert set(cards.term_status({"item": n}, None).values()) == {"safe"}, n
    for n in ["garlic powder", "egg noodles", "McCormick Pumpkin Pie Spice", "salmon", "Salted caramel"]:
        assert "unsure" in cards.term_status({"item": n}, None).values(), n
    found = {"checks": {cards.TERMS["tree nut"]: {"verdict": "found"}}}
    assert cards.term_status({"item": "Almond-fed chicken"}, found)["tree nut"] == "found"
