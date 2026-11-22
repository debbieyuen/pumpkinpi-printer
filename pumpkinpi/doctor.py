"""Preflight check:  python -m pumpkinpi.doctor   (never prints your key, never moves the printer)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    ok = True

    def report(good, msg):
        nonlocal ok
        ok &= bool(good)
        print(("OK   " if good else "FIX  ") + msg)

    report(os.environ.get("PERPLEXITY_API_KEY"), "PERPLEXITY_API_KEY is set (value not shown)")
    try:
        g = json.loads((ROOT / "guests.json").read_text())
        report(g.get("guests"), f"guests.json has {len(g.get('guests', []))} guests")
    except Exception as e:
        report(False, f"guests.json: {e}")
    report((ROOT / "machine.json").exists(), "machine.json exists (pie position + z_surface measured)")

    from .printer import find_port
    try:
        port = find_port()
    except FileNotFoundError:
        port = None
    report(port, f"printer serial port: {port or 'none found - is USB plugged in?'}")
    if port:
        try:
            import serial
            with serial.Serial(port, 115200, timeout=3) as s:
                s.write(b"M115\n")  # firmware info only, no motion
                reply = s.read(400).decode(errors="ignore")
            report("FIRMWARE" in reply, "printer answers M115")
        except Exception as e:
            report(False, f"serial open failed: {e} (did you reboot after setup for dialout?)")

    if shutil.which("rpicam-hello"):
        r = subprocess.run(["rpicam-hello", "--list-cameras"], capture_output=True, text=True)
        out = (r.stdout + r.stderr).lower()
        found = "imx708" in out or ("available cameras" in out and "no cameras" not in out)
        report(found, "camera detected (Camera Module 3)" if found else
               "no camera found - check the ribbon cable (power off first)")
    else:
        report(False, "rpicam-hello not installed (sudo apt install rpicam-apps)")
    report(shutil.which("ffmpeg"), "ffmpeg installed (timelapse clips)" if shutil.which("ffmpeg") else
           "ffmpeg missing - timelapse keeps only photos (sudo apt install -y ffmpeg)")
    print("\nAll good." if ok else "\nFix the lines marked FIX, then run again.")


if __name__ == "__main__":
    main()
