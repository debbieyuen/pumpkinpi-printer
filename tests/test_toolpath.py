import math

import pytest

from pumpkinpi.shapes import MAX_R, SHAPES, strokes_for
from pumpkinpi.toolpath import Machine, OutOfBounds, to_gcode


@pytest.mark.parametrize("shape", SHAPES)
def test_every_shape_fits_the_pie(shape):
    for words in ["", "Michael", "WWWWWWWWWWWW"]:
        for font in ["print", "cursive"]:
            for st in strokes_for({"shape": shape, "text": words, "font": font}):
                assert all(math.hypot(x, y) <= MAX_R + 0.01 for x, y in st)


def test_cursive_differs_from_print():
    a = strokes_for({"shape": "text", "text": "Debbie", "font": "print"})
    b = strokes_for({"shape": "text", "text": "Debbie", "font": "cursive"})
    assert a != b


def test_gcode_never_homes_or_heats_and_stays_in_bounds():
    g = to_gcode(strokes_for({"shape": "smiley", "text": "Mom"}), Machine())
    assert not any(ln.split()[0] in {"G28", "G29", "M104", "M109", "M140", "M190"} for ln in g)
    assert "M83" in g


def test_dry_run_has_no_extrusion_and_is_higher():
    m = Machine()
    g = to_gcode(strokes_for({"shape": "heart"}), m, dry_run=True)
    assert not any(" E" in ln for ln in g)
    zs = [float(w[1:]) for ln in g for w in ln.split()[1:] if w[0] == "Z"]
    assert min(zs) >= m.z_surface + 15


def test_pie_too_far_right_is_refused():
    with pytest.raises(OutOfBounds):
        to_gcode(strokes_for({"shape": "star"}), Machine(pie_x=140))


def test_food_mode_blocks_homing():
    from pumpkinpi.printer import FOOD_MODE_BLOCKED
    for cmd in ["G28", "g29", "M104 S200", "M140 S60", "G30"]:
        assert FOOD_MODE_BLOCKED.match(cmd)
    for cmd in ["G1 X10 E0.1", "M302 P1", "M112", "M114"]:
        assert not FOOD_MODE_BLOCKED.match(cmd)


def test_long_words_wrap_to_two_lines_whole_words_only():
    from pumpkinpi.shapes import split_lines
    assert split_lines("happy thanksgiving") == ["happy", "thanksgiving"]
    assert split_lines("Happy Thanksgiving Debbie") == ["Happy", "Thanksgiving"]   # drops a word, never cuts one
    assert split_lines("Debbie") == ["Debbie"]
    assert split_lines("") == []


def test_every_shape_and_text_fits_the_pie():
    from pumpkinpi.shapes import MAX_R, SHAPES, strokes_for
    for shape in SHAPES:
        for words in ("", "Debbie", "Happy Thanksgiving"):
            for font in ("print", "cursive"):
                pts = [p for st in strokes_for({"shape": shape, "text": words, "font": font}) for p in st]
                assert pts and max((x * x + y * y) ** 0.5 for x, y in pts) <= MAX_R + 0.01


def test_pause_after_each_line_and_topping_settings(tmp_path):
    from pumpkinpi.toolpath import Machine, drip_test_gcode, save_topping, to_gcode
    mf = tmp_path / "machine.json"
    save_topping("marshmallow", {"dwell": 2.5}, mf)
    m = Machine.load(mf, topping="marshmallow")
    assert m.dwell == 2.5 and m.retract == 1.0 and m.lift_feed == 120
    g = to_gcode([[(0, 0), (10, 0)], [(0, 5), (10, 5)]], m)
    assert g.count("G4 P2500") == 2
    i = next(i for i, ln in enumerate(g) if ln.startswith("G1 E-"))
    assert g[i + 1] == "G4 P2500" and g[i + 2].startswith("G1 Z")   # pull back, pause, then lift
    assert "G4" not in "\n".join(to_gcode([[(0, 0), (10, 0)]], m, dry_run=True))
    d = drip_test_gcode(m)
    assert "G4" not in "\n".join(d) and d[-1] == "M400" and any(ln.startswith("G1 E-") for ln in d)
