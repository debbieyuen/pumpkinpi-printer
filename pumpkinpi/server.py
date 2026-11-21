"""Touchscreen server for the Pi: serves ui/ and a small JSON API.

Run on the Pi:
    export PERPLEXITY_API_KEY=...        # never commit it
    python -m pumpkinpi.server           # then open http://localhost:8000 in kiosk mode

Endpoints
    GET  /api/status   event, guests (names + allergens only), printer connected?
    POST /api/check    {"product": "..."} -> per-guest allergen verdicts with sources
    POST /api/ready    take a photo, ask Decider if the pie is ready -> {"probability": 0.97}
    POST /api/start    {"name": "..."} -> refuses until all checks are green and readiness >= 0.9
    POST /api/stop     sends M112 immediately
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .allergen_check import check_for_guests, make_client
from .pie_ready import pie_ready, take_photo

ROOT = Path(__file__).resolve().parent.parent
GUESTS_FILE = Path(os.environ.get("PUMPKINPI_GUESTS", ROOT / "guests.json"))
READY_AT = 0.9

app = FastAPI(title="PumpkinPi")
state = {"checks": {}, "ready": 0.0}
_printer = None


def guests() -> dict:
    return json.loads(GUESTS_FILE.read_text())


def printer():
    """Connect lazily so the UI still works when the printer is off."""
    global _printer
    if _printer is None:
        from .printer import Printer
        _printer = Printer()
    return _printer


class CheckReq(BaseModel):
    product: str


class StartReq(BaseModel):
    name: str


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


@app.post("/api/check")
def check(req: CheckReq):
    with make_client() as client:
        rows = check_for_guests(client, req.product, guests()["guests"])
    out = [{"name": n, **asdict(c)} for n, c in rows]
    state["checks"][req.product] = [r["verdict"] for r in out]
    return {"product": req.product, "results": out}


@app.post("/api/ready")
def ready():
    with make_client() as client:
        p = pie_ready(client, take_photo())
    state["ready"] = p
    return {"probability": p}


@app.post("/api/start")
def start(req: StartReq):
    checks = state["checks"]
    if not checks or any(v != "safe" for vs in checks.values() for v in vs):
        raise HTTPException(409, "Not every checked ingredient is green")
    if state["ready"] < READY_AT:
        raise HTTPException(409, "Pie readiness below 0.9; re-run the camera check")
    printer().frosting_mode()
    # TODO: generate the single-line-font path for req.name and stream it (see docs/PROJECT_SUMMARY.md section 8).
    raise HTTPException(501, f"Frosting mode set. Name path generation for '{req.name}' is not built yet")


@app.post("/api/stop")
def stop():
    state["ready"] = 0.0
    printer().emergency_stop()
    return {"stopped": True}


app.mount("/", StaticFiles(directory=ROOT / "ui", html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
