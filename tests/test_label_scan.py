import json

import pumpkinpi.server as srv
from pumpkinpi import label_scan, timelapse
from pumpkinpi.allergen_check import Check

from test_server import PLAN, setup

READ = {"readable": True, "complete": True, "brand": "Enjoy Life", "product": "Semi-Sweet Mini Chips", "size": "9 oz",
        "ingredients": "Cane sugar, unsweetened chocolate, cocoa butter", "contains": [], "may_contain": "", "problem": ""}


def scan(tmp_path, monkeypatch, read, verdict="safe"):
    c = setup(tmp_path, monkeypatch, verdict=verdict)
    photo = tmp_path / "label.jpg"
    photo.write_bytes(b"\xff\xd8fake\xff\xd9")
    monkeypatch.setattr(srv, "take_photo", lambda path=None: photo)
    monkeypatch.setattr(label_scan, "read_label", lambda client, jpeg: dict(read))
    c.post("/api/design", json={"prompt": "x"})
    return c, c.post("/api/label", json={})


def test_label_counts_for_matching_ingredient(tmp_path, monkeypatch):
    c, r = scan(tmp_path, monkeypatch, READ)
    body = r.json()
    assert r.status_code == 200 and body["ingredient"] == "chocolate chips"
    assert srv.state["checks"]["chocolate chips"] == ["safe"]
    assert body["label"]["source"] == "camera" and body["product"] == "chocolate chips"


def test_other_brand_is_just_a_check(tmp_path, monkeypatch):
    c, r = scan(tmp_path, monkeypatch, {**READ, "brand": "Nestle Toll House", "product": "Semi-Sweet Morsels"})
    assert r.json()["ingredient"] is None and "chocolate chips" not in srv.state["checks"]


def test_printed_almonds_turn_red(tmp_path, monkeypatch):
    c, r = scan(tmp_path, monkeypatch, {**READ, "ingredients": "Sugar, chocolate, almonds, cocoa butter"})
    row = r.json()["results"][0]
    assert row["verdict"] == "found" and "almond" in row["note"]
    assert srv.state["checks"]["chocolate chips"] == ["found"]


def test_may_contain_tree_nuts_turns_red(tmp_path, monkeypatch):
    c, r = scan(tmp_path, monkeypatch, {**READ, "may_contain": "Made on shared equipment with tree nuts and milk."})
    assert r.json()["results"][0]["verdict"] == "found"


def test_cut_off_label_is_never_green(tmp_path, monkeypatch):
    c, r = scan(tmp_path, monkeypatch, {**READ, "complete": False, "problem": "glare"})
    row = r.json()["results"][0]
    assert row["verdict"] == "unsure" and "glare" in row["note"]


def test_unreadable_label_is_refused(tmp_path, monkeypatch):
    c, r = scan(tmp_path, monkeypatch, {**READ, "readable": False, "ingredients": "", "problem": "blurry"})
    assert r.status_code == 422 and "blurry" in r.json()["detail"]


def test_scan_never_makes_red_greener():
    ch = {"tree nuts": Check("x", "tree nuts", 0.9, "found")}
    label_scan.apply_printed(ch, READ)
    assert ch["tree nuts"].verdict == "found"


def test_read_label_parses_agent_json(monkeypatch):
    monkeypatch.setattr(label_scan.pplx, "agent_image", lambda c, **k: "Here: " + json.dumps(READ))
    assert label_scan.read_label(None, b"x")["brand"] == "Enjoy Life"


class FakeCam:
    error = None

    def __init__(self):
        self.seq = 0

    def keep_alive(self):
        pass

    def latest(self):
        self.seq += 1
        return self.seq, b"\xff\xd8frame\xff\xd9"


def test_timelapse_saves_frames_without_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(timelapse, "DIR", tmp_path / "tl")
    monkeypatch.setattr(timelapse, "INTERVAL_S", 0.01)
    monkeypatch.setattr(timelapse.shutil, "which", lambda n: None)
    rec = timelapse.Recorder(FakeCam())
    assert rec.start(auto=True) and not rec.start()
    import time
    time.sleep(0.15)
    rec.stop(wait=True)
    assert rec.frames >= 3 and "ffmpeg" in rec.error
    assert len(list((tmp_path / "tl").glob("*/*.jpg"))) == rec.frames
