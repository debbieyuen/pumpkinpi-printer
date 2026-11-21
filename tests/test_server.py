import json

from fastapi.testclient import TestClient

import pumpkinpi.server as srv


def setup(tmp_path, monkeypatch):
    f = tmp_path / "guests.json"
    f.write_text(json.dumps({"event": "Test", "guests": [{"name": "Michael", "avoid": ["tree nuts"], "notes": "private"}]}))
    monkeypatch.setattr(srv, "GUESTS_FILE", f)
    monkeypatch.setattr(srv, "printer", lambda: (_ for _ in ()).throw(RuntimeError("no printer")))
    srv.state.update(checks={}, ready=0.0)
    return TestClient(srv.app)


def test_status_hides_health_notes(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    s = c.get("/api/status").json()
    assert s["printer"] is False
    assert s["guests"] == [{"name": "Michael", "avoid": ["tree nuts"]}]


def test_start_refused_without_checks(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert c.post("/api/start", json={"name": "Michael"}).status_code == 409


def test_start_refused_when_red(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    srv.state.update(checks={"wine": ["found"]}, ready=0.99)
    assert c.post("/api/start", json={"name": "Michael"}).status_code == 409


def test_ui_served(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    assert "PumpkinPi" in c.get("/").text
