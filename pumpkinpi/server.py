"""Touchscreen server for the Pi: serves ui/ and a small JSON API.

Run on the Pi:
    export PERPLEXITY_API_KEY=...        # never commit it
    python -m pumpkinpi.server           # then open http://localhost:8000 in kiosk mode

Endpoints
    GET  /api/status   event, guests (names + allergens only), printer connected?
    POST /api/design   {"prompt": "..."} -> Agent API design plan + piping preview
    POST /api/check    {"product": "..."} -> Search API sources + Decider verdict per guest allergen
    POST /api/ready    photo -> Decider: is the pie ready?  {"probability": 0.97}
    POST /api/start    {"dry_run": bool} -> refuses until every ingredient is green and readiness >= 0.9
    GET  /api/job      piping progress
    POST /api/stop     sends M112 immediately
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .allergen_check import check_ingredient
from .design import plan_design
from .pie_ready import pie_ready, take_photo
from .pplx import make_client
from .shapes import strokes_for
from .toolpath import Machine, to_gcode

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


class DesignReq(BaseModel):
    prompt: str


class CheckReq(BaseModel):
    product: str


class StartReq(BaseModel):
    dry_run: bool = False


@app.get("/api/status")
def status():
    g = guests()
    try:
        printer()
        connected = True
    except Exception:
        connected = False
    # Only names and allergens go to the screen; health notes stay off camera.
    return {"event": g.get("event"), "printer": connected,
            "guests": [{"name": x["name"], "avoid": x.get("avoid", [])} for x in g["guests"]]}


@app.post("/api/design")
def design(req: DesignReq):
    if not req.prompt.strip():
        raise HTTPException(400, "Type what you'd like on the pie")
    with make_client() as client:
        plan = plan_design(client, req.prompt, guests()["guests"])
    try:
        strokes = strokes_for(plan)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not SHOW_HEALTH:
        plan["diet_notes"] = ""
    state.update(plan=plan, strokes=strokes, checks={}, ready=0.0)
    return {"plan": plan, "strokes": strokes}


@app.post("/api/check")
def check(req: CheckReq):
    g = guests()["guests"]
    with make_client() as client:
        res = check_ingredient(client, req.product, allergens())
    rows = [{"name": x["name"], **asdict(res["checks"][a])} for x in g for a in x.get("avoid", [])]
    state["checks"][req.product.lower()] = [r["verdict"] for r in rows]
    return {"product": req.product, "results": rows, "relevance": res["relevance"],
            "natural_flavor": res["natural_flavor"], "queries": res["search"]["queries"],
            "sources": [{"title": r.get("title"), "url": r.get("url")} for r in res["search"]["results"]][:6]}


@app.post("/api/ready")
def ready():
    with make_client() as client:
        p = pie_ready(client, take_photo())
    state["ready"] = p
    return {"probability": p}


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
    if state["ready"] < READY_AT:
        raise HTTPException(409, "Pie readiness below 0.9; re-run the camera check")


def run_job(lines: list[str]) -> None:
    job = state["job"]
    try:
        p = printer()
        p.frosting_mode()
        for ln in lines:
            if _stop.is_set():
                break
            p.send(ln, wait_s=120)
            job["done"] += 1
    except Exception as e:  # noqa: BLE001 - surface any printer error on screen
        job["error"] = str(e)
    finally:
        job["running"] = False


@app.post("/api/start")
def start(req: StartReq):
    gate(req.dry_run)
    lines = to_gcode(state["strokes"], Machine.load(), dry_run=req.dry_run)
    _stop.clear()
    state["job"] = {"running": True, "done": 0, "total": len(lines), "error": None, "dry_run": req.dry_run}
    threading.Thread(target=run_job, args=(lines,), daemon=True).start()
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
