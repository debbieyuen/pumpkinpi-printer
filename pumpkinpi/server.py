"""Touchscreen server for the Pi: serves ui/ and a small JSON API.

Run on the Pi:
    export PERPLEXITY_API_KEY=...        # never commit it
    python -m pumpkinpi.server           # then open http://localhost:8000 in kiosk mode

Endpoints
    GET  /api/status   event, guests (names + allergens only), printer connected?
    POST /api/design   {"prompt": "...", "diets": ["vegan"]} -> Agent API recipe + design plan + piping preview
    POST /api/check    {"product": "...", "diets": [...]} -> Search API sources + Decider verdict per guest
                       allergen and per chosen diet (vegan, dairy-free, gluten-free, egg-free)
    POST /api/ready    photo -> Decider: is the pie ready?  {"probability": 0.97}
    POST /api/start    {"dry_run": bool} -> refuses until every ingredient is green and readiness >= 0.9,
                       then writes the G-code to the printer's microSD (PPMMDDNN.GCO) and prints from it
    GET  /api/photo    latest camera photo
    GET  /api/camera.mjpg  live camera preview (MJPEG)
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
from . import allergy_guide
from .allergens import scan_blocks, scan_recipe
from .camera import camera
from .design import plan_design, revise_design
from .pie_ready import PHOTO, pie_ready, take_photo
from .pplx import make_client
from .shapes import MAX_TEXT, SHAPES, strokes_for
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


class CheckReq(BaseModel):
    product: str
    diets: list[str] = []


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


def exact(plan: dict) -> tuple[list, dict]:
    """Strokes plus the path read back from the real G-code, so Design shows exactly what will pipe."""
    try:
        strokes = strokes_for(plan)
        m = Machine.load()
        path = piped_path(to_gcode(strokes, m), m)
    except ValueError as e:   # off the pie or outside the printer's safe box
        raise HTTPException(422, str(e))
    return strokes, path


def publish(plan: dict, keep_checks: bool) -> dict:
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
            "scan": scan}


@app.post("/api/design")
def design(req: DesignReq):
    if not req.prompt.strip():
        raise HTTPException(400, "Type what you'd like on the pie")
    diets = clean_diets(req.diets)
    with make_client() as client:
        plan = plan_design(client, req.prompt, guests()["guests"], diets=diets)
    plan["diets"] = diets
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
        plan = revise_design(client, old, req.change, guests()["guests"], diets=diets)
    plan["diets"] = diets
    plan["diet_notes"] = plan.get("diet_notes") or old.get("diet_notes", "")
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
    return publish(plan, keep_checks=True)


@app.post("/api/check")
def check(req: CheckReq):
    g = guests()["guests"]
    diets = [d for d in clean_diets(req.diets) if d in DIET_CHECKS]
    terms = allergens() + [DIET_CHECKS[d] for d in diets if DIET_CHECKS[d] not in allergens()]
    with make_client() as client:
        res = check_ingredient(client, req.product, terms)
    rows = [{"name": x["name"], **asdict(res["checks"][a])} for x in g for a in x.get("avoid", [])]
    rows += [{"name": d.capitalize(), "diet": d, **asdict(res["checks"][DIET_CHECKS[d]])} for d in diets]
    state["checks"][req.product.lower()] = [r["verdict"] for r in rows]
    return {"product": req.product, "results": rows, "relevance": res["relevance"],
            "natural_flavor": res["natural_flavor"], "queries": res["search"]["queries"],
            "sources": [{"title": r.get("title"), "url": r.get("url"), "tag": r.get("tag", "label")}
                        for r in res["search"]["results"]][:8]}


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
    with make_client() as client:
        p = pie_ready(client, take_photo())
    state["ready"] = p
    return {"probability": p}


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


@app.post("/api/start")
def start(req: StartReq):
    gate(req.dry_run)
    lines = to_gcode(state["strokes"], Machine.load(), dry_run=req.dry_run)
    _stop.clear()
    state["job"] = {"running": True, "done": 0, "total": len(lines), "pct": 0, "phase": "start", "file": None,
                    "error": None, "dry_run": req.dry_run}
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
