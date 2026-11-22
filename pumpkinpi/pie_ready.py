"""Camera readiness check: is the pie centered, chilled-looking and ready to decorate?

Takes a photo with the Pi Camera Module 3 (rpicam-still) and asks the Decisions API
with an image part in `state` (PNG/JPEG/WebP data URL; http URLs are rejected).
Docs: https://docs.perplexity.ai/docs/decisions/decisions
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import httpx

from .allergen_check import DECISIONS_URL, MODEL

PHOTO = Path("captures/pie.jpg")


def take_photo(path: Path = PHOTO) -> Path:
    from .camera import camera
    if camera.snapshot(path):  # live preview owns the camera: use its newest frame
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rpicam-still", "-n", "-t", "800", "--width", "1280", "--height", "960", "-o", str(path)], check=True)
    return path


def pie_ready(client: httpx.Client, photo: Path) -> float:
    data = base64.b64encode(photo.read_bytes()).decode()
    body = {
        "model": MODEL,
        "state": [
            "Overhead photo of a 3D printer bed before piping a topping onto a food item (pie, tart, cookie, cupcake or cake).",
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
        ],
        "questions": {
            "ready": {
                "type": "noul",
                "instructions": "Is there exactly one whole food item (pie, tart, cookie, cupcake or cake), roughly centered on the bed, with a smooth unbroken top and nothing (hands, tools, utensils) in the way?",
            }
        },
    }
    r = client.post(DECISIONS_URL, json=body)
    r.raise_for_status()
    return float(r.json()["answers"]["ready"]["noul"])
