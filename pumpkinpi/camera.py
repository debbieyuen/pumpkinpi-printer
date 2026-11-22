"""Live camera preview for the touchscreen (Camera Module 3).

One `rpicam-vid --codec mjpeg -o -` process writes JPEG frames to stdout; we keep the latest frame
and serve it as an MJPEG stream (`multipart/x-mixed-replace`), which <img> shows natively.
Only one process can own the camera, so the pie check grabs a frame from the running stream
instead of starting rpicam-still. The stream stops a few seconds after the last viewer leaves.
Docs: https://www.raspberrypi.com/documentation/computers/camera_software.html#rpicam-vid
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

WIDTH, HEIGHT, FPS = 1280, 960, 10
IDLE_STOP_S = 5.0
SOI, EOI = b"\xff\xd8", b"\xff\xd9"


class LiveCamera:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._seq = 0
        self._proc: subprocess.Popen | None = None
        self._last_seen = 0.0
        self.error: str | None = None

    # ---- process ----
    def _start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self.error = None
        try:
            self._proc = subprocess.Popen(
                ["rpicam-vid", "-n", "-t", "0", "--codec", "mjpeg", "--width", str(WIDTH), "--height", str(HEIGHT),
                 "--framerate", str(FPS), "-o", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        except FileNotFoundError:
            self.error = "rpicam-vid not found (run on the Pi)"
            self._proc = None
            return
        threading.Thread(target=self._read, args=(self._proc,), daemon=True).start()

    def _read(self, proc: subprocess.Popen) -> None:
        buf = b""
        while proc.poll() is None:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                a = buf.find(SOI)
                b = buf.find(EOI, a + 2) if a >= 0 else -1
                if a < 0 or b < 0:
                    break
                with self._lock:
                    self._frame, self._seq = buf[a:b + 2], self._seq + 1
                buf = buf[b + 2:]
            if len(buf) > 8_000_000:
                buf = b""
            if time.monotonic() - self._last_seen > IDLE_STOP_S:
                proc.terminate()
        if self._proc is proc:
            self._proc = None

    def stop(self) -> None:
        p = self._proc
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        self._proc = None

    @property
    def running(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    # ---- frames ----
    def frames(self):
        """Generator of multipart MJPEG chunks for StreamingResponse."""
        seq = -1
        while True:
            self._last_seen = time.monotonic()
            self._start()
            if self.error:
                return
            with self._lock:
                frame, s = self._frame, self._seq
            if frame is not None and s != seq:
                seq = s
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode()
                       + b"\r\n\r\n" + frame + b"\r\n")
            time.sleep(1 / (FPS * 2))

    def snapshot(self, path: Path, timeout: float = 4.0) -> Path | None:
        """Save the newest frame if the stream is running; None if it isn't."""
        if not self.running:
            return None
        self._last_seen = time.monotonic()
        with self._lock:
            start = self._seq
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:   # wait for a fresh frame
            with self._lock:
                if self._seq > start and self._frame:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(self._frame)
                    return path
            time.sleep(0.05)
        return None


camera = LiveCamera()
