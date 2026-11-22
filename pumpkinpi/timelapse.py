"""Timelapse recording from the Pi camera, for the video.

Saves one frame from the live camera stream every INTERVAL_S seconds (the stream already owns the
camera, so nothing else has to open it), then ffmpeg joins them into two MP4s:

    captures/timelapse/20261126-153000.mp4          4:3, like the Camera screen
    captures/timelapse/20261126-153000-vertical.mp4  9:16 center crop, ready for a vertical video

Recording starts by itself when piping (or a dry run) starts and stops a few seconds after it ends.
The Record button on the Camera screen starts and stops it by hand. Recording never talks to the printer.
Docs: https://www.raspberrypi.com/documentation/computers/camera_software.html#rpicam-vid
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

DIR = Path("captures/timelapse")
INTERVAL_S = float(os.environ.get("PUMPKINPI_TIMELAPSE_S", "0.5"))   # 0.5 s per frame at 15 fps = 7.5x speed
FPS_OUT = 15
MAX_S = 30 * 60          # a forgotten recording stops itself after 30 min
NAME = re.compile(r"^\d{8}-\d{6}(-vertical)?\.mp4$")


class Recorder:
    def __init__(self, camera) -> None:
        self.cam = camera
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._halt = threading.Event()
        self.stamp: str | None = None
        self.auto = False
        self.frames = 0
        self.t0 = 0.0
        self.saving = False
        self.error: str | None = None
        self.last: dict | None = None

    @property
    def recording(self) -> bool:
        return bool(self._thread and self._thread.is_alive()) and not self.saving

    def start(self, auto: bool = False) -> bool:
        """False if already recording (a manual recording is never taken over by an automatic one)."""
        with self._lock:
            if self._thread and self._thread.is_alive():   # recording or still saving the last clip
                return False
            self.stamp = time.strftime("%Y%m%d-%H%M%S")
            self.auto, self.frames, self.t0, self.error = auto, 0, time.monotonic(), None
            self._halt.clear()
            self._thread = threading.Thread(target=self._run, args=(DIR / self.stamp,), daemon=True)
            self._thread.start()
            return True

    def _run(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        seq = -1
        while not self._halt.is_set() and time.monotonic() - self.t0 < MAX_S:
            self.cam.keep_alive()
            if self.cam.error:
                self.error = self.cam.error
                break
            s, frame = self.cam.latest()
            if frame is not None and s != seq:
                seq = s
                self.frames += 1
                (folder / f"{self.frames:05d}.jpg").write_bytes(frame)
            self._halt.wait(INTERVAL_S)
        self._finish(folder)

    def stop(self, wait: bool = False) -> None:
        self._halt.set()
        t = self._thread
        if wait and t:
            t.join(timeout=120)

    def stop_auto(self, tail_s: float = 3.0) -> None:
        """End an automatic recording a moment after piping finishes. Leaves manual recordings alone."""
        if self.recording and self.auto:
            threading.Timer(tail_s, self.stop).start()

    def _finish(self, folder: Path) -> None:
        self.saving = True
        try:
            if self.frames < 2:
                self.error = self.error or "Not enough frames to make a clip"
                shutil.rmtree(folder, ignore_errors=True)
                return
            if not shutil.which("ffmpeg"):
                self.error = "ffmpeg not installed: frames kept in " + str(folder) + " (sudo apt install ffmpeg)"
                return
            out = DIR / f"{folder.name}.mp4"
            vert = DIR / f"{folder.name}-vertical.mp4"
            base = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS_OUT), "-i", str(folder / "%05d.jpg"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            subprocess.run(base + ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", str(out)], check=True, timeout=600)
            subprocess.run(base + ["-vf", "crop=trunc(ih*9/32)*2:trunc(ih/2)*2", str(vert)], check=True, timeout=600)
            shutil.rmtree(folder, ignore_errors=True)
            self.last = {"name": out.name, "vertical": vert.name, "frames": self.frames,
                         "seconds": round(self.frames / FPS_OUT, 1)}
        except (subprocess.SubprocessError, OSError) as e:
            self.error = f"Couldn't make the clip: {e}"[:200]
        finally:
            self.saving = False

    def status(self) -> dict:
        return {"recording": self.recording, "auto": self.auto, "saving": self.saving, "frames": self.frames,
                "seconds": round(time.monotonic() - self.t0) if self.recording else 0,
                "error": self.error, "last": self.last, "clips": clips()}


def clips(n: int = 6) -> list[str]:
    if not DIR.exists():
        return []
    return sorted((p.name for p in DIR.glob("*.mp4") if NAME.match(p.name)), reverse=True)[:n]


def clip_path(name: str) -> Path | None:
    p = DIR / name
    return p if NAME.match(name) and p.exists() else None
