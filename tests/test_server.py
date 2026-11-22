import json

from fastapi.testclient import TestClient

import pumpkinpi.server as srv
from pumpkinpi.allergen_check import Check

PLAN = {"guest": "Michael", "shape": "smiley", "text": "Michael", "topping": "ganache",
        "ingredients": ["chocolate chips", "heavy cream"], "recipe": [], "piping_notes": "",
        "diet_notes": "Dad limits sugar", "caption": "Smiley", "sources": []}


def setup(tmp_path, monkeypatch, verdict="safe"):
    f = tmp_path / "guests.json"
    f.write_text(json.dumps({"event": "Test", "guests": [{"name": "Michael", "avoid": ["tree nuts"], "notes": "private"}]}))
    monkeypatch.setattr(srv, "GUESTS_FILE", f)
    monkeypatch.setattr(srv, "printer", lambda: (_ for _ in ()).throw(RuntimeError("no printer")))
    monkeypatch.setattr(srv, "make_client", lambda: __import__("contextlib").nullcontext(None))
    monkeypatch.setattr(srv, "plan_design", lambda c, p, g: dict(PLAN))
    monkeypatch.setattr(srv, "check_ingredient", lambda c, prod, al: {
        "checks": {a: Check(prod, a, 0.02, verdict, ["https://example.com"]) for a in al},
        "search": {"queries": ["q"], "results": [{"title": "t", "url": "https://example.com"}]},
        "relevance": 0.9, "natural_flavor": 0.1})
    monkeypatch.setattr(srv, "run_job", lambda lines: None)
    srv.state.update(checks={}, ready=0.0, plan=None, strokes=None, job={"running": False})
    return TestClient(srv.app)


def test_status_hides_health_notes(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    s = c.get("/api/status").json()
    assert s["printer"] is False
    assert s["guests"] == [{"name": "Michael", "avoid": ["tree nuts"]}]


def test_design_hides_diet_notes_and_returns_strokes(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    r = c.post("/api/design", json={"prompt": "smiley in chocolate for Michael"}).json()
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
    assert "PumpkinPi" in c.get("/").text
