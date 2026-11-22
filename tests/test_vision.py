import cv2
import numpy as np

import pumpkinpi.server as srv
from pumpkinpi import vision
from pumpkinpi.shapes import extent, strokes_for

from test_server import setup


def photo(crust=True, r=300, cx=640, cy=480, shadow=True):
    img = np.full((960, 1280, 3), (40, 38, 36), np.uint8)              # dark bed
    if shadow:
        cv2.circle(img, (cx + 14, cy + 14), r, (18, 18, 18), -1)
    cv2.circle(img, (cx, cy), r, (90, 150, 205) if crust else (60, 120, 180), -1)   # BGR tan crust / cookie
    if crust:
        cv2.circle(img, (cx, cy), int(r * 0.8), (40, 125, 215), -1)  # orange filling
    return cv2.imencode(".jpg", img)[1].tobytes()


def test_finds_pie_edge_and_filling():
    e = vision.find_edges(photo())
    assert abs(e["cx"] - 640) < 8 and abs(e["cy"] - 480) < 8
    assert abs(e["r"] - 300) < 15 and abs(e["r_in"] - 240) < 15 and e["ring"]


def test_cookie_has_no_ring():
    e = vision.find_edges(photo(crust=False, r=200))
    assert abs(e["r"] - 200) < 12 and not e["ring"]


def test_empty_bed():
    img = np.full((960, 1280, 3), (40, 38, 36), np.uint8)
    assert vision.find_edges(cv2.imencode(".jpg", img)[1].tobytes()) is None


def test_sizes_before_and_after_calibration(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "CAL_FILE", tmp_path / "cal.json")
    e = vision.find_edges(photo())
    s = vision.sizes(e, "pumpkin pie", 152, None)
    assert 55 < s["fit_r"] + vision.MARGIN_MM < 66 and s["off_mm"] is None    # 80 % of a 76 mm radius
    cal = vision.save_cal(e, 152)
    moved = vision.find_edges(photo(cx=640 + 79))                              # ~20 mm at 3.95 px/mm
    s2 = vision.sizes(moved, "pumpkin pie", 152, cal)
    assert 15 < s2["off_mm"] < 25 and s2["diameter_mm"] == 152
    assert any("off center" in w for w in vision.warnings({**s2, "dish": "pumpkin pie", "edges": moved}))


def test_design_shrinks_to_fit_never_grows():
    plan = {"shape": "smiley", "text": "Debbie"}
    full = extent(strokes_for(plan))
    assert abs(extent(strokes_for({**plan, "fit_r": 20})) - 20) < 0.01
    assert abs(extent(strokes_for({**plan, "fit_r": 80})) - full) < 0.01


def test_check_pie_resizes_the_design_for_a_cookie(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(vision, "CAL_FILE", tmp_path / "cal.json")
    f = tmp_path / "pie.jpg"
    f.write_bytes(photo(crust=False, r=200))
    monkeypatch.setattr(srv, "take_photo", lambda path=None: f)
    monkeypatch.setattr(srv, "pie_ready", lambda client, p: 0.95)
    monkeypatch.setattr(vision, "identify", lambda client, jpeg: {"dish": "cookie", "count": 1, "round": True,
                                                                   "surface": "flat", "confidence": 0.9})
    c.post("/api/design", json={"prompt": "x"})
    r = c.post("/api/ready", json={}).json()
    assert r["probability"] == 0.95 and r["dish"]["dish"] == "cookie"
    assert r["design"]["fit"]["fit_r"] == 75 / 2 - vision.MARGIN_MM and r["design"]["fit"]["scale"] < 1
    assert srv.state["ready"] == 0.95
    assert c.post("/api/dish/center", json={}).status_code == 409     # calibrate with the pie, not a cookie
    f.write_bytes(photo())
    monkeypatch.setattr(vision, "identify", lambda client, jpeg: {"dish": "pumpkin pie", "count": 1, "round": True,
                                                                   "surface": "smooth", "confidence": 0.9})
    c.post("/api/ready", json={})
    r2 = c.post("/api/dish/center", json={}).json()
    assert r2["dish"]["calibrated"] and r2["dish"]["off_mm"] == 0.0 and r2["dish"]["diameter_mm"] == 152
