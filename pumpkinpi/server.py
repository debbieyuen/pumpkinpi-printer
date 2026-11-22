"""Touchscreen server for the Pi: serves ui/ and a small JSON API.

Run on the Pi:
    export PERPLEXITY_API_KEY=...        # never commit it
    python -m pumpkinpi.server           # then open http://localhost:8000 in kiosk mode

Endpoints
    GET  /api/status   event, guests (names + allergens only), printer connected?
    POST /api/design   {"prompt": "...", "diets": ["vegan"]} -> Agent API recipe + design plan + piping preview
    POST /api/check    {"product": "...", "diets": [...]} -> Open Food Facts label + Search API sources + Decider verdict per guest
                       allergen and per chosen diet (vegan, dairy-free, gluten-free, egg-free)
    POST /api/ready    photo -> Decider: is the pie ready? + vision: which dish, where the crust is; the design
                       shrinks to fit inside the filling  {"probability": 0.97, "dish": {...}, "design": {...}}
    POST /api/dish/center  one-time: the dish now sits where pie_x/pie_y was measured (camera_cal.json)
    POST /api/start    {"dry_run": bool} -> refuses until every ingredient is green and readiness >= 0.9,
                       then writes the G-code to the printer's microSD (PPMMDDNN.GCO) and prints from it
    GET  /api/photo    latest camera photo
    GET  /api/camera.mjpg  live camera preview (MJPEG)
    POST /api/label    camera photo of a package label -> Agent API reads it -> same check as /api/check
    GET  /api/label/photo  the last label photo
    GET  /api/record   timelapse status + saved clips;  POST /api/record {"on": true|false}
    GET  /api/clips/{name}  a saved timelapse MP4
    GET  /api/job      piping progress
    POST /api/stop     sends M112 immediately
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .allergen_check import check_ingredient
from . import allergy_guide, label_scan, vision
from .allergens import scan_blocks, scan_recipe
from .camera import camera
from .design import plan_design, revise_design
from .pie_ready import PHOTO, pie_ready, take_photo
from .pplx import make_client
from .products import enrich
from .timelapse import Recorder, clip_path
from .shapes import FONTS, MAX_TEXT, SHAPES, extent, strokes_for
from .toolpath import Machine, piped_path, to_gcode

ROOT = Path(__file__).resolve().parent.parent
GUESTS_FILE = Path(os.environ.get("PUMPKINPI_GUESTS", ROOT / "guests.json"))
SHOW_HEALTH = os.environ.get("PUMPKINPI_SHOW_HEALTH") == "1"   # only with the guests' consent
READY_AT = 0.9

app = FastAPI(title="PumpkinPi")
state: dict = {"checks": {}, "ready": 0.0, "plan": None, "strokes": None,
               "job": {"running": False, "done": 0, "total": 0, "error": None}}
_printer = None
_stop = threading.Event()
recorder = Recorder(camera)
LABEL_PHOTO = Path("captures/label.jpg")


def guests() -> dict:
    return json.loads(GUESTS_FILE.read_text())


def allergens() -> list[str]:
    return sorted({a for g in guests()["guests"] for a in g.get("avoid", [])})


def printer():
    """Connect lazily so the UI still works when the printer is off."""
    global _printer
    if _printer is None:
        from .printer import Printer
        _printer = Printer()
    return _printer


# Diet chips on the Recipe screen. Each one the Decider can check becomes an extra "avoid" term,
# so a red/yellow diet result locks Send just like an allergen. "low sugar" only changes the recipe.
DIET_CHECKS = {
    "vegan": "animal-derived ingredients (milk, butter, cream, eggs, honey, gelatin)",
    "dairy-free": "milk or milk-derived ingredients",
    "gluten-free": "gluten (wheat, barley or rye)",
    "egg-free": "eggs",
}
DIETS = [*DIET_CHECKS, "low sugar"]


def clean_diets(diets: list[str]) -> list[str]:
    bad = [d for d in diets if d not in DIETS]
    if bad:
        raise HTTPException(400, f"Unknown diet: {', '.join(bad)}")
    return list(dict.fromkeys(diets))


class DesignReq(BaseModel):
    prompt: str
    diets: list[str] = []


class ReviseReq(BaseModel):
    change: str
    diets: list[str] = []


class EditReq(BaseModel):
    shape: str | None = None
    text: str | None = None
    font: str | None = None


class CheckReq(BaseModel):
    product: str
    diets: list[str] = []


class LabelReq(BaseModel):
    diets: list[str] = []


class RecordReq(BaseModel):
    on: bool


class StartReq(BaseModel):
    dry_run: bool = False


def printer_connected() -> bool:
    """True if the printer is on USB. Forgets a printer that was unplugged so it can reconnect."""
    global _printer
    if _printer is not None and not os.path.exists(_printer.port):
        try:
            _printer.ser.close()
        except Exception:  # noqa: BLE001
            pass
        _printer = None
    try:
        printer()
        return True
    except Exception:  # noqa: BLE001 - no port, permission, or printer off
        return False


@app.get("/api/status")
def status():
    g = guests()
    connected = printer_connected()
    # Only names and allergens go to the screen; health notes stay off camera.
    return {"event": g.get("event"), "printer": connected, "diets": DIETS,
            "guests": [{"name": x["name"], "avoid": x.get("avoid", [])} for x in g["guests"]]}


def fit_info(plan: dict, strokes: list) -> dict:
    """How the camera changed the design's size, for the screen."""
    d = state.get("dish") or {}
    full = extent(strokes_for({**plan, "fit_r": None}))
    now = extent(strokes)
    k = now / full if full else 1.0
    letters = 10 if plan.get("shape") != "text" else 24   # letter height in mm before scaling (shapes.py)
    return {"dish": d.get("dish"), "fit_r": plan.get("fit_r"), "scale": round(k, 2),
            "small_text": bool(plan.get("text")) and letters * k < 6}


def exact(plan: dict) -> tuple[list, dict]:
    """Strokes plus the path read back from the real G-code, so Design shows exactly what will pipe."""
    try:
        strokes = strokes_for(plan)
        m = Machine.load()
        path = piped_path(to_gcode(strokes, m), m)
    except ValueError as e:   # off the pie or outside the printer's safe box
        raise HTTPException(422, str(e))
    return strokes, path


def add_labels(plan: dict, old: dict | None = None) -> dict:
    """Photo + printed label for each exact product (Open Food Facts). Reuses labels already looked up."""
    known = {p["ingredient"].lower(): p.get("label") for p in (old or {}).get("products", []) if "label" in p}
    todo = [p for p in plan.get("products", []) if p["ingredient"].lower() not in known]
    found = {p["ingredient"].lower(): p["label"] for p in enrich(todo)} if todo else {}
    plan["products"] = [{**p, "label": known.get(p["ingredient"].lower(), found.get(p["ingredient"].lower()))}
                        for p in plan.get("products", [])]
    return plan


def label_for(product: str) -> dict | None:
    for p in (state["plan"] or {}).get("products", []):
        if p["ingredient"].lower() == product.lower():
            return p.get("label")
    return None


def publish(plan: dict, keep_checks: bool) -> dict:
    d = state.get("dish") or {}
    if d.get("fit_r"):
        plan["fit_r"], plan["dish"] = d["fit_r"], d.get("dish")
    else:
        plan.pop("fit_r", None)
    strokes, path = exact(plan)
    if not SHOW_HEALTH:
        plan["diet_notes"] = ""
    checks = state["checks"] if keep_checks else {}
    # Name scan of the whole recipe (steps and notes too): "a drop of almond extract" in step 3 blocks Send.
    scan = scan_recipe(plan, allergens())
    state.update(plan=plan, strokes=strokes, checks=checks, scan=scan)
    if not keep_checks:
        state["ready"] = 0.0
        state.pop("guide", None)
    return {"plan": plan, "strokes": path["strokes"], "path": {k: path[k] for k in ("mm", "seconds")},
            "scan": scan, "fit": fit_info(plan, strokes)}


@app.post("/api/design")
def design(req: DesignReq):
    if not req.prompt.strip():
        raise HTTPException(400, "Type what you'd like on the pie")
    diets = clean_diets(req.diets)
    with make_client() as client:
        plan = plan_design(client, req.prompt, guests()["guests"], diets=diets, dish=state.get("dish"))
    plan["diets"] = diets
    add_labels(plan)
    return publish(plan, keep_checks=False)


def same_ingredients(a: dict, b: dict) -> bool:
    return [i.lower() for i in a.get("ingredients", [])] == [i.lower() for i in b.get("ingredients", [])]


@app.post("/api/revise")
def revise(req: ReviseReq):
    """Change the current design in words ("just a heart, no name"). Keeps checks if the topping is the same."""
    if not state["plan"]:
        raise HTTPException(409, "Make a design first")
    if not req.change.strip():
        raise HTTPException(400, "Say what to change")
    diets = clean_diets(req.diets)
    old = state["plan"]
    with make_client() as client:
        plan = revise_design(client, old, req.change, guests()["guests"], diets=diets, dish=state.get("dish"))
    plan["diets"] = diets
    plan["diet_notes"] = plan.get("diet_notes") or old.get("diet_notes", "")
    add_labels(plan, old)
    return publish(plan, keep_checks=same_ingredients(old, plan))


@app.post("/api/edit")
def edit(req: EditReq):
    """Instant shape / name change from the Design screen. Same topping, so checks stay."""
    if not state["plan"]:
        raise HTTPException(409, "Make a design first")
    plan = dict(state["plan"])
    if req.shape is not None:
        if req.shape not in SHAPES:
            raise HTTPException(400, f"Shape must be one of {', '.join(SHAPES)}")
        plan["shape"] = req.shape
    if req.text is not None:
        plan["text"] = req.text.strip()[:MAX_TEXT]
    if req.font is not None:
        if req.font not in FONTS:
            raise HTTPException(400, f"Font must be one of {', '.join(FONTS)}")
        plan["font"] = req.font
    return publish(plan, keep_checks=True)


def run_check(product: str, diets: list[str], label: dict | None, adjust=None) -> dict:
    """Search API + Decider for one product, one row per guest allergen and chosen diet.
    adjust(checks) may make verdicts stricter before rows are built (label scan)."""
    g = guests()["guests"]
    diets = [d for d in clean_diets(diets) if d in DIET_CHECKS]
    terms = allergens() + [DIET_CHECKS[d] for d in diets if DIET_CHECKS[d] not in allergens()]
    with make_client() as client:
        res = check_ingredient(client, product, terms, label=label)
    if adjust:
        adjust(res["checks"])
    rows = [{"name": x["name"], **asdict(res["checks"][a])} for x in g for a in x.get("avoid", [])]
    rows += [{"name": d.capitalize(), "diet": d, **asdict(res["checks"][DIET_CHECKS[d]])} for d in diets]
    off = [{"title": f"Open Food Facts: {label.get('brand', '')} {label.get('name', '')}".strip(), "url": label["url"]}] \
        if label and label.get("url") else []
    return {"product": product, "results": rows, "relevance": res["relevance"], "label": label,
            "natural_flavor": res["natural_flavor"], "queries": res["search"]["queries"],
            "sources": off + [{"title": r.get("title"), "url": r.get("url"), "tag": r.get("tag", "label")}
                               for r in res["search"]["results"]][:8]}


@app.post("/api/check")
def check(req: CheckReq):
    out = run_check(req.product, req.diets, label_for(req.product))
    state["checks"][req.product.lower()] = [r["verdict"] for r in out["results"]]
    return out


@app.post("/api/label")
def label(req: LabelReq):
    """Scan a package label held up to the camera. Counts for the matching recipe ingredient, if any."""
    try:
        photo = take_photo(LABEL_PHOTO)
    except Exception as e:   # noqa: BLE001 - no camera / rpicam-still failed
        raise HTTPException(503, f"Camera not available: {e}"[:200])
    with make_client() as client:
        read = label_scan.read_label(client, photo.read_bytes())
    if not read["readable"]:
        raise HTTPException(422, "Couldn't read the ingredients. Hold the label flat, closer and out of glare."
                            + (f" ({read['problem']})" if read.get("problem") else ""))
    ingredient = label_scan.match_ingredient(read, state["plan"])
    # Ask about the recipe's exact product when it matched, so a different bag can't turn it green.
    product = ingredient or label_scan.title(read) or "this product"
    lab = label_scan.as_label(read, image=f"/api/label/photo?t={int(time.time())}")
    out = run_check(product, req.diets, lab, adjust=lambda checks: label_scan.apply_printed(checks, read))
    if ingredient:
        state["checks"][ingredient.lower()] = [r["verdict"] for r in out["results"]]
    out["sources"] = [{"title": "Camera photo of the label", "url": lab["image"], "tag": "label"}] + out["sources"]
    return {**out, "read": read, "ingredient": ingredient, "title": label_scan.title(read)}


@app.get("/api/label/photo")
def label_photo():
    if not LABEL_PHOTO.exists():
        raise HTTPException(404, "No label photo yet")
    return FileResponse(LABEL_PHOTO, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/record")
def record_status():
    return recorder.status()


@app.post("/api/record")
def record(req: RecordReq):
    if req.on:
        recorder.start(auto=False)
    else:
        recorder.stop()
    return recorder.status()


@app.get("/api/clips/{name}")
def clip(name: str):
    p = clip_path(name)
    if not p:
        raise HTTPException(404, "No such clip")
    return FileResponse(p, media_type="video/mp4")


@app.post("/api/guide")
def guide():
    """Allergy watch for the current recipe: cited hidden names + where these ingredients hide nuts."""
    if not state["plan"]:
        raise HTTPException(409, "Make a design first")
    if state.get("guide"):
        return state["guide"]
    g = guests()["guests"]
    try:
        with make_client() as client:
            out = allergy_guide.research(client, state["plan"], g)
    except Exception as e:   # research is extra; the fixed cited lists still show
        out = {**allergy_guide.offline(g), "error": str(e)[:200]}
    out["scan"] = state.get("scan", [])
    state["guide"] = out
    return out


@app.post("/api/ready")
def ready():
    """One photo: Decider says if it's ready; vision says what it is and where the crust is."""
    from concurrent.futures import ThreadPoolExecutor
    photo = take_photo()
    jpeg = photo.read_bytes()
    pie_mm = Machine.load().pie_mm
    with make_client() as client, ThreadPoolExecutor(2) as ex:
        p_job = ex.submit(pie_ready, client, photo)
        v_job = ex.submit(vision.inspect, client, jpeg, pie_mm)
        p, v = p_job.result(), v_job.result()
    state["dish"] = v
    design = publish(dict(state["plan"]), keep_checks=True) if state["plan"] else None
    state["ready"] = p
    return {"probability": p, "dish": v, "design": design}


@app.post("/api/dish/center")
def dish_center():
    """Calibrate once: the pie sits where pie_x/pie_y was measured. Saves the target and the mm scale."""
    v = state.get("dish")
    if not v or not v.get("edges"):
        raise HTTPException(409, "Check the pie first so the camera can find its edge")
    if v["dish"] in vision.TYPICAL_MM:
        raise HTTPException(409, f"Save the center with the pie on the bed, not a {v['dish']}")
    m = Machine.load()
    vision.save_cal(v["edges"], m.pie_mm)
    v = {**v, "calibrated": True, **vision.sizes(v["edges"], v["dish"], m.pie_mm, vision.load_cal())}
    cal = vision.load_cal()
    v["target"] = {"cx": cal["cx"] * v["edges"]["w"], "cy": cal["cy"] * v["edges"]["h"]}
    v["warnings"] = vision.warnings(v)
    state["dish"] = v
    design = publish(dict(state["plan"]), keep_checks=True) if state["plan"] else None
    return {"dish": v, "design": design}


@app.get("/api/photo")
def photo():
    """Latest camera photo from the pie check, for the Camera screen."""
    if not PHOTO.exists():
        raise HTTPException(404, "No photo yet")
    return FileResponse(PHOTO, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/camera.mjpg")
def camera_stream():
    """Live preview for the Camera screen. Stops on its own a few seconds after the screen closes."""
    gen = camera.frames()
    first = next(gen, None)
    if first is None:
        raise HTTPException(503, camera.error or "Camera not available")

    def body():
        yield first
        yield from gen
    return StreamingResponse(body(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


def gate(dry_run: bool) -> None:
    if not state["strokes"]:
        raise HTTPException(409, "Ask Perplexity for a design first")
    if state["job"]["running"]:
        raise HTTPException(409, "Already piping")
    if dry_run:
        return  # no food comes out; still never homes
    need = [i.lower() for i in state["plan"]["ingredients"]]
    missing = [i for i in need if i not in state["checks"]]
    if missing:
        raise HTTPException(409, f"Not checked yet: {', '.join(missing)}")
    if any(v != "safe" for i in need for v in state["checks"][i]):
        raise HTTPException(409, "Not every ingredient is green")
    blocks = scan_blocks(scan_recipe(state["plan"], allergens()))
    if blocks:
        b = blocks[0]
        raise HTTPException(409, f"The recipe names {b['term']} ({b['allergen']}) in the {b['where']}")
    if state["ready"] < READY_AT:
        raise HTTPException(409, "Pie readiness below 0.9; re-run the camera check")


GCODE_DIR = ROOT / "gcode"   # a copy of every file sent, named like the one on the card


def run_job(lines: list[str], dry_run: bool = False) -> None:
    """Upload to the printer's microSD and print from the card; stream over USB if SD writes fail."""
    from .printer import SDError, sd_file, sd_name
    job = state["job"]

    def prog(i: int, n: int) -> None:
        job["pct"] = round(40 * i / n)        # upload = first 40 % of the bar

    try:
        p = printer()
        p.frosting_mode()
        try:
            name = sd_name(dry_run, list(p.sd_list()))
            data = sd_file(lines, name)
            GCODE_DIR.mkdir(exist_ok=True)
            (GCODE_DIR / name).write_text("\n".join(data) + "\n")
            job.update(phase="upload", file=name)
            p.sd_upload(name, data, progress=prog, stop=_stop.is_set)
            if _stop.is_set():
                return
            p.sd_start(name)
            job["phase"] = "printing"
            seen, t0 = False, time.time()
            while not _stop.is_set():
                time.sleep(1.0)
                pr = p.sd_progress()
                if pr:
                    seen = True
                    job["pct"] = 40 + round(60 * pr[0] / max(1, pr[1]))
                elif seen or time.time() - t0 > 15:
                    break   # finished, or stopped from the printer's screen
            job["pct"] = 100
        except SDError as e:  # no card / firmware without M28: fall back to streaming
            if _stop.is_set():
                return
            job.update(phase="streaming", note=f"SD upload failed ({e}); streaming over USB")
            for i, ln in enumerate(lines, 1):
                if _stop.is_set():
                    break
                p.send(ln, wait_s=120)
                job["done"] = i
                job["pct"] = round(100 * i / len(lines))
    except Exception as e:  # noqa: BLE001 - surface any printer error on screen
        job["error"] = str(e)
    finally:
        job["running"] = False
        recorder.stop_auto()


@app.post("/api/start")
def start(req: StartReq):
    gate(req.dry_run)
    lines = to_gcode(state["strokes"], Machine.load(), dry_run=req.dry_run)
    _stop.clear()
    state["job"] = {"running": True, "done": 0, "total": len(lines), "pct": 0, "phase": "start", "file": None,
                    "error": None, "dry_run": req.dry_run}
    recorder.start(auto=True)   # timelapse for the video; never touches the printer
    threading.Thread(target=run_job, args=(lines, req.dry_run), daemon=True).start()
    return {"started": True, "lines": len(lines), "dry_run": req.dry_run}


@app.get("/api/job")
def job():
    return state["job"]


@app.post("/api/stop")
def stop():
    _stop.set()
    state["ready"] = 0.0
    printer().emergency_stop()
    return {"stopped": True}


app.mount("/", StaticFiles(directory=ROOT / "ui", html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
