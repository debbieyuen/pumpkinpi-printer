import json

from fastapi.testclient import TestClient

import pumpkinpi.server as srv
from pumpkinpi.allergen_check import Check

PLAN = {"guest": "Alex", "shape": "smiley", "text": "Alex", "topping": "ganache",
        "ingredients": ["chocolate chips", "heavy cream"],
        "products": [{"ingredient": "chocolate chips", "brand": "Enjoy Life", "product": "Semi-Sweet Mini Chips", "size": "9 oz", "store": "Safeway", "upc": ""},
                     {"ingredient": "heavy cream", "brand": "Clover Sonoma", "product": "Organic Heavy Whipping Cream", "size": "1 pint", "store": "Safeway", "upc": ""}],
        "recipe": [], "piping_notes": "",
        "diet_notes": "Dad limits sugar", "caption": "Smiley", "sources": []}


LABEL = {"upc": "0853522000009", "name": "Mini Chips", "brand": "Enjoy Life", "size": "9 oz",
         "image": "https://images.openfoodfacts.org/x.jpg", "ingredients": "Cane sugar, unsweetened chocolate, cocoa butter",
         "allergens": [], "traces": [], "url": "https://world.openfoodfacts.org/product/0853522000009"}
seen_labels: list = []


class FakeRecorder:
    def __init__(self):
        self.calls = []

    def start(self, auto=False):
        self.calls.append(("start", auto))
        return True

    def stop(self):
        self.calls.append(("stop",))

    def stop_auto(self):
        self.calls.append(("stop_auto",))

    def status(self):
        return {"recording": bool(self.calls and self.calls[-1][0] == "start"), "clips": []}


def setup(tmp_path, monkeypatch, verdict="safe"):
    f = tmp_path / "guests.json"
    f.write_text(json.dumps({"event": "Test", "guests": [{"name": "Alex", "avoid": ["tree nuts"], "notes": "private"}]}))
    monkeypatch.setattr(srv, "GUESTS_FILE", f)
    monkeypatch.setattr(srv, "printer", lambda: (_ for _ in ()).throw(RuntimeError("no printer")))
    monkeypatch.setattr(srv, "make_client", lambda: __import__("contextlib").nullcontext(None))
    monkeypatch.setattr(srv, "plan_design", lambda c, p, g, diets=None, **kw: dict(PLAN))
    seen_labels.clear()
    monkeypatch.setattr(srv, "enrich", lambda ps: [{**p, "label": LABEL if p["ingredient"] == "chocolate chips" else None} for p in ps])
    monkeypatch.setattr(srv, "check_ingredient", lambda c, prod, al, label=None: seen_labels.append(label) or {
        "checks": {a: Check(prod, a, 0.02, verdict, ["https://example.com"]) for a in al},
        "search": {"queries": ["q"], "results": [{"title": "t", "url": "https://example.com"}]},
        "relevance": 0.9, "natural_flavor": 0.1})
    monkeypatch.setattr(srv, "run_job", lambda lines, dry_run=False: None)
    monkeypatch.setattr(srv, "recorder", FakeRecorder())
    srv.state.update(checks={}, ready=0.0, plan=None, strokes=None, job={"running": False}, dish=None)
    return TestClient(srv.app)


def test_status_hides_health_notes(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    s = c.get("/api/status").json()
    assert s["printer"] is False
    assert s["guests"] == [{"name": "Alex", "avoid": ["tree nuts"]}]


def test_design_hides_diet_notes_and_returns_strokes(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    r = c.post("/api/design", json={"prompt": "smiley in chocolate for Alex"}).json()
    assert r["plan"]["diet_notes"] == "" and len(r["strokes"]) > 3


def test_start_refused_without_design(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert c.post("/api/start", json={}).status_code == 409


def test_start_needs_every_ingredient_checked(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    c.post("/api/check", json={"product": "chocolate chips"})
    srv.state["ready"] = 0.99
    r = c.post("/api/start", json={})
    assert r.status_code == 409 and "heavy cream" in r.json()["detail"]


def test_start_refused_when_not_green(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch, verdict="unsure")
    c.post("/api/design", json={"prompt": "x"})
    for p in PLAN["ingredients"]:
        c.post("/api/check", json={"product": p})
    srv.state["ready"] = 0.99
    assert c.post("/api/start", json={}).status_code == 409


def test_start_ok_when_all_green_and_ready(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    for p in PLAN["ingredients"]:
        c.post("/api/check", json={"product": p})
    assert c.post("/api/start", json={}).status_code == 409   # camera not ready yet
    srv.state["ready"] = 0.95
    assert c.post("/api/start", json={}).status_code == 200


def test_dry_run_only_needs_design(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    assert c.post("/api/start", json={"dry_run": True}).json()["dry_run"] is True


def test_ui_served(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert "Perplexity Make" in c.get("/").text


def test_vegan_diet_adds_a_gating_row(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    r = c.post("/api/design", json={"prompt": "x", "diets": ["vegan", "low sugar"]}).json()
    assert r["plan"]["diets"] == ["vegan", "low sugar"]
    rows = c.post("/api/check", json={"product": "heavy cream", "diets": ["vegan", "low sugar"]}).json()["results"]
    assert [x["name"] for x in rows] == ["Alex", "Vegan"]


def test_unknown_diet_rejected(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert c.post("/api/design", json={"prompt": "x", "diets": ["keto"]}).status_code == 400


def test_design_preview_is_the_gcode_path(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    r = c.post("/api/design", json={"prompt": "x"}).json()
    assert len(r["strokes"]) == len(srv.state["strokes"]) and r["path"]["mm"] > 0
    for a, b in zip(r["strokes"], srv.state["strokes"]):
        assert len(a) == len(b) and all(abs(p[0] - q[0]) < 0.01 and abs(p[1] - q[1]) < 0.01 for p, q in zip(a, b))


def test_edit_keeps_checks_and_drops_name(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    c.post("/api/check", json={"product": "chocolate chips"})
    srv.state["ready"] = 0.95
    r = c.post("/api/edit", json={"shape": "heart", "text": ""}).json()
    assert r["plan"]["shape"] == "heart" and r["plan"]["text"] == "" and len(r["strokes"]) == 1
    assert "chocolate chips" in srv.state["checks"] and srv.state["ready"] == 0.95
    assert c.post("/api/edit", json={"shape": "dragon"}).status_code == 400


def test_revise_rechecks_only_when_ingredients_change(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    c.post("/api/check", json={"product": "chocolate chips"})
    monkeypatch.setattr(srv, "revise_design", lambda cl, plan, ch, g, diets=None, **kw: {**plan, "shape": "heart", "text": ""})
    c.post("/api/revise", json={"change": "just a heart, no name"})
    assert srv.state["plan"]["shape"] == "heart" and srv.state["checks"]
    monkeypatch.setattr(srv, "revise_design", lambda cl, plan, ch, g, diets=None, **kw: {**plan, "ingredients": ["white chocolate chips", "heavy cream"]})
    c.post("/api/revise", json={"change": "white chocolate"})
    assert srv.state["checks"] == {}


def test_start_blocked_when_a_step_names_a_nut(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    plan = dict(PLAN, recipe=["Heat the cream.", "Add 1/4 tsp almond extract."])
    monkeypatch.setattr(srv, "plan_design", lambda cl, p, g, diets=None, **kw: dict(plan))
    r = c.post("/api/design", json={"prompt": "x"}).json()
    assert r["scan"][0]["term"] == "almond extract"
    for p in PLAN["ingredients"]:
        c.post("/api/check", json={"product": p})
    srv.state["ready"] = 0.99
    r = c.post("/api/start", json={})
    assert r.status_code == 409 and "almond extract" in r.json()["detail"]


def test_guide_falls_back_to_cited_lists(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    monkeypatch.setattr(srv.allergy_guide, "research", lambda *a: (_ for _ in ()).throw(RuntimeError("offline")))
    g = c.post("/api/guide", json={}).json()
    assert g["allergens"][0]["allergen"] == "tree nuts" and g["allergens"][0]["sources"]


def test_design_adds_product_photo_and_check_uses_label(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    r = c.post("/api/design", json={"prompt": "x"}).json()
    assert r["plan"]["products"][0]["label"]["image"].startswith("https://")
    chk = c.post("/api/check", json={"product": "chocolate chips"}).json()
    assert seen_labels[-1]["brand"] == "Enjoy Life"
    assert chk["sources"][0]["url"].startswith("https://world.openfoodfacts.org/")


def test_edit_to_cat_in_cursive(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    r = c.post("/api/edit", json={"shape": "cat", "text": "Sam", "font": "cursive"}).json()
    assert r["plan"]["shape"] == "cat" and r["plan"]["font"] == "cursive" and len(r["strokes"]) > 8
    assert c.post("/api/edit", json={"font": "gothic"}).status_code == 400


def test_question_returns_answer_and_keeps_design(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    first = c.post("/api/design", json={"prompt": "x"}).json()
    q = {**PLAN, "kind": "question", "answer": "Free range means outdoor access.", "base": "none",
         "sources": [{"title": "FSIS", "url": "https://www.fsis.usda.gov/"}]}
    monkeypatch.setattr(srv, "plan_design", lambda cl, p, g, diets=None, **kw: dict(q))
    r = c.post("/api/design", json={"prompt": "what does free range mean on a turkey?"}).json()
    assert r["question"]["answer"].startswith("Free range") and "strokes" not in r
    assert srv.state["plan"]["ingredients"] == first["plan"]["ingredients"]   # design kept


def test_cookie_base_shrinks_design_and_none_has_no_path(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, "plan_design", lambda cl, p, g, diets=None, **kw: {**PLAN, "kind": "make", "base": "cookie", "shape": "heart", "text": ""})
    r = c.post("/api/design", json={"prompt": "M&M cookies with a heart"}).json()
    assert max(abs(v) for s in r["strokes"] for pt in s for v in pt[:2]) <= 45 * 0.75 + 0.5
    monkeypatch.setattr(srv, "plan_design", lambda cl, p, g, diets=None, **kw: {**PLAN, "kind": "make", "base": "none"})
    r = c.post("/api/design", json={"prompt": "roast turkey"}).json()
    assert r["strokes"] == []
    assert c.post("/api/start", json={"dry_run": True}).status_code == 409


def test_layers_keep_first_topping_and_use_its_settings(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, "plan_design", lambda cl, p, g, diets=None, **kw: {**PLAN, "base": "cookie", "shape": "heart", "text": "", "topping_type": "chocolate"})
    c.post("/api/design", json={"prompt": "chocolate heart cookie", "topping_type": "chocolate"})
    seen = {}
    def second(cl, p, g, diets=None, topping_type=None, layers=None, **kw):
        seen.update(topping_type=topping_type, layers=layers)
        return {**PLAN, "base": "pie", "shape": "text", "text": "Sam", "topping_type": "frosting"}
    monkeypatch.setattr(srv, "plan_design", second)
    r = c.post("/api/design", json={"prompt": "Sam in frosting", "topping_type": "frosting", "add_layer": True}).json()
    assert seen["topping_type"] == "frosting" and seen["layers"][0]["topping_type"] == "chocolate"
    assert r["plan"]["base"] == "cookie" and len(r["layers"]) == 1 and r["layers"][0]["strokes"]
    # a fresh design clears the layers
    monkeypatch.setattr(srv, "plan_design", lambda cl, p, g, diets=None, **kw: dict(PLAN))
    assert c.post("/api/design", json={"prompt": "new"}).json()["layers"] == []
    assert c.post("/api/design", json={"prompt": "x", "topping_type": "gravy"}).status_code == 400


def test_topping_profiles_and_drip_suggestion(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    mf = tmp_path / "machine.json"
    monkeypatch.setattr(srv.Machine.load.__func__, "__defaults__", (mf, None))
    t = c.get("/api/toppings").json()
    assert set(t) == {"frosting", "chocolate", "marshmallow"}
    assert t["marshmallow"]["settings"]["dwell"] > t["frosting"]["settings"]["dwell"]
    s = c.post("/api/drip-test/result", json={"topping_type": "chocolate", "seconds": 4.2}).json()["suggest"]
    assert s["dwell"] == 4.5 and s["retract"] > t["chocolate"]["settings"]["retract"]


def test_start_records_a_timelapse(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    c.post("/api/design", json={"prompt": "x"})
    c.post("/api/start", json={"dry_run": True})
    assert srv.recorder.calls == [("start", True)]


def test_record_button(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert c.post("/api/record", json={"on": True}).json()["recording"] is True
    assert c.post("/api/record", json={"on": False}).json()["recording"] is False
    assert srv.recorder.calls == [("start", False), ("stop",)]


def test_clip_names_are_checked(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert c.get("/api/clips/..%2F.env").status_code == 404
    assert c.get("/api/clips/20261126-153000.mp4").status_code == 404
