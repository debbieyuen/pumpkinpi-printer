from pumpkinpi import detail
from pumpkinpi.design import tidy
from pumpkinpi.shapes import strokes_for
from pumpkinpi.toolpath import Machine, piped_path, to_gcode

from test_server import PLAN, setup


def run(plan):
    s = strokes_for(plan)
    return detail.check(plan, s, piped_path(to_gcode(s, Machine()), Machine()))


def test_simple_designs_are_ok():
    for p in [dict(shape="cat", text="Sam", font="cursive"), dict(shape="heart"), dict(shape="text", text="Alex"),
              dict(shape="text", text="Happy Thanksgiving")]:
        assert run(p) == {"level": "ok", "reasons": [], "try": ""}


def test_model_flag_is_too_much_and_keeps_its_idea():
    r = run(dict(shape="heart", text="Mom", too_detailed="A family portrait needs shading.", simpler="A heart with Mom"))
    assert r["level"] == "too_much" and r["try"] == "A heart with Mom"


def test_long_message_is_cut_and_reported():
    p = tidy({"shape": "text", "text": "Happy Thanksgiving to Grandma Lily", "ingredients": []})
    assert p["text_asked"] == "Happy Thanksgiving to Grandma Lily" and p["text"] != p["text_asked"]
    r = run(p)
    assert r["level"] == "too_much" and "two short lines" in r["reasons"][0]
    assert tidy({"shape": "text", "text": "Happy Thanksgiving", "ingredients": []})["text_asked"] == ""


def test_tiny_letters_on_a_small_dish():
    r = run(dict(shape="cat", text="Alex", fit_r=18))
    assert r["level"] == "too_much" and "mm tall" in r["reasons"][0]


def test_many_strokes_and_long_time():
    s = [[(i * 0.5, 0), (i * 0.5, 1)] for i in range(70)]
    r = detail.check({"shape": "heart"}, s, {"seconds": 300})
    assert r["level"] == "too_much" and len(r["reasons"]) == 2
    r = detail.check({"shape": "heart"}, s[:45], {"seconds": 160})
    assert r["level"] == "busy"


def test_design_endpoint_returns_detail(tmp_path, monkeypatch):
    import pumpkinpi.server as srv
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, "plan_design", lambda *a, **k: {**PLAN, "too_detailed": "A whole scene is too much.", "simpler": "A smiley"})
    r = c.post("/api/design", json={"prompt": "the whole Thanksgiving table"}).json()
    assert r["detail"]["level"] == "too_much" and r["detail"]["try"] == "A smiley"
    r = c.post("/api/edit", json={"shape": "heart"}).json()   # hand edit: the model's note no longer applies
    assert r["detail"]["level"] == "ok"
