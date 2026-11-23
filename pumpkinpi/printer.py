"""Talk to the Ender 3 V3 SE (Marlin) over USB serial with pyserial.

Safety rules (from the project notes):
- Never home or run auto Z offset with food on the bed.
- Frosting mode: heaters off, cold extrusion allowed (M302 P1), motors stay powered (M84 S0).
- emergency_stop() sends M112. Stay next to the machine.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time
from collections.abc import Callable

import serial  # pyserial
from serial.tools import list_ports

BAUD = 115200
FROSTING_SETUP = ["M104 S0", "M140 S0", "M302 P1", "M84 S0", "M220 S15", "M117 PumpkinPi ready"]

# Commands that home, probe or heat. The V3 SE heats the nozzle and taps the bed during
# calibration, and the syringe tip hangs below the nozzle, so none of these may run once
# food mode is on. Reconnect (power-cycle) with the bed empty and the syringe off to use them.
FOOD_MODE_BLOCKED = re.compile(r"^(G28|G29|G30|G34|G35|M48|M104|M109|M140|M190|M303|M851)\b", re.I)


class FoodModeError(RuntimeError):
    pass


class SDError(RuntimeError):
    """The printer's microSD couldn't be written or read (no card, or firmware without SD writes)."""


# ---- microSD file names ----
# Marlin selects files (M23) by their DOS 8.3 short name, and M20 lists 8.3 names, so we only ever
# write 8.3-safe names: 1 letter + up to 7 letters/digits, no spaces/underscores, ".GCO" (Marlin lists
# .gcode, .gco and .g). https://marlinfw.org/docs/gcode/M020.html
#   PPMMDDNN.GCO  piping job   e.g. PP112601.GCO = first pie on Nov 26
#   DRMMDDNN.GCO  dry run (path 15 mm above the pie, no topping)
#   CDMMDDNN.GCO  PLA menu card (heats the nozzle; run only after Heat & home)
SD_NAME = re.compile(r"^[A-Z][A-Z0-9]{0,7}\.GCO$")
# Spelled-out names (card_11_22_print01.gcode) only when the firmware reports LONG_FILENAME_WRITE in M115;
# it is off in stock Marlin. https://marlinfw.org/docs/settings/lcd.html
LONG_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}\.gcode$")


def card_label(existing: list[str], today: dt.date | None = None) -> str:
    """card_MM_DD_printNN: the spelled-out name shown in the app, on the printer screen and in gcode/."""
    today = today or dt.date.today()
    stem = f"card_{today:%m_%d}_print"
    taken = {n.lower().rsplit(".", 1)[0] for n in existing}
    for i in range(1, 100):
        if f"{stem}{i:02d}" not in taken:
            return f"{stem}{i:02d}"
    raise SDError(f"99 cards named {stem}NN today already")


def sd_name(dry_run: bool, existing: list[str], today: dt.date | None = None, prefix: str | None = None) -> str:
    today = today or dt.date.today()
    stem = f"{prefix or ('DR' if dry_run else 'PP')}{today:%m%d}"
    taken = {n.upper() for n in existing}
    for i in range(1, 100):
        name = f"{stem}{i:02d}.GCO"
        if name not in taken:
            return name
    raise SDError(f"99 files named {stem}NN.GCO already; delete some from the card")


# A file on the card can be started later from the printer's own screen, so it must be safe on its
# own: heaters off and cold extrusion first, and never a homing/probing/heating command.
HEATER_OFF = re.compile(r"^(M104|M140) S0$", re.I)


def file_safe(lines: list[str]) -> None:
    for ln in lines:
        ln = ln.split(";")[0].strip()
        if ln and FOOD_MODE_BLOCKED.match(ln) and not HEATER_OFF.match(ln):
            raise FoodModeError(f"{ln!r} may not go in a food file (homing/probing/heating)")


# PLA card files are started from the printer's screen, so they heat and home themselves. G28 taps the
# CR Touch once on the paper card (bed center) to find its top; no bed probing/mesh rebuild, no PID,
# no Z-offset change, and cold extrusion stays blocked. Paper only on the bed: never food.
CARD_BLOCKED = re.compile(r"^(G29|G30|G34|G35|M48|M303|M851|M500|M302 P1)\b", re.I)


def card_file_safe(lines: list[str]) -> None:
    for ln in lines:
        ln = ln.split(";")[0].strip()
        if ln and CARD_BLOCKED.match(ln):
            raise FoodModeError(f"{ln!r} may not go in a card file (no bed probing or settings changes; cold extrusion stays off)")


def card_file(lines: list[str], name: str) -> list[str]:
    """The exact lines written to the card for a PLA menu card: cold-extrusion guard on, then the drawing."""
    body = [ln.split(";")[0].strip() for ln in lines]
    stem = name.rsplit('.', 1)[0][:30]
    out = [f"; {stem}: PLA on paper. Paper card taped down, nothing else on the bed.", "M302 P0", f"M117 {stem}",
           *[b for b in body if b]]
    card_file_safe(out)
    return out


def sd_file(lines: list[str], name: str) -> list[str]:
    """The exact lines written to the card: food-safe header, the toolpath, no comments or blanks."""
    body = [ln.split(";")[0].strip() for ln in lines]
    out = [*FROSTING_SETUP[:-1], f"M117 PumpkinPi {name[:-4]}", *[b for b in body if b]]
    file_safe(out)
    return out


def sd_mounts() -> list[str]:
    """microSD cards plugged into the Pi (USB card reader), e.g. /media/debbiepumpkinpi/3D PRINTER.
    PUMPKINPI_SD_DIR overrides (any folder)."""
    if os.environ.get("PUMPKINPI_SD_DIR"):
        return [os.environ["PUMPKINPI_SD_DIR"]]
    out = []
    try:
        with open("/proc/mounts") as f:
            for ln in f:
                dev, mnt, fs = ln.split()[:3]
                mnt = mnt.replace("\\040", " ")
                if fs in ("vfat", "exfat", "msdos") and mnt.startswith(("/media/", "/run/media/", "/mnt/")):
                    out.append(mnt)
    except OSError:
        pass
    return out


def find_port() -> str:
    """PRINTER_PORT if set, else the first USB serial device (the V3 SE shows up as ttyUSB* or ttyACM*)."""
    if os.environ.get("PRINTER_PORT"):
        return os.environ["PRINTER_PORT"]
    for p in list_ports.comports():
        if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM")):
            return p.device
    raise FileNotFoundError("No USB serial device found. Is the printer on and plugged into the Pi?")


class Printer:
    def __init__(self, port: str | None = None, baud: int = BAUD, timeout: float = 2.0):
        self.port = port or find_port()
        self.food_mode = False
        self.ser = serial.Serial(self.port, baud, timeout=timeout)
        time.sleep(2)  # Marlin resets on connect
        self.ser.reset_input_buffer()

    def send(self, line: str, wait_s: float = 30.0, check: bool = True) -> list[str]:
        """Send one G-code line and wait for Marlin's 'ok'. check=False only for lines being saved to SD."""
        if check and self.food_mode and FOOD_MODE_BLOCKED.match(line.strip()):
            raise FoodModeError(f"{line.strip()!r} is blocked in food mode (homing/probing/heating)")
        self.ser.write((line.strip() + "\n").encode())
        out, deadline = [], time.time() + wait_s
        while time.time() < deadline:
            resp = self.ser.readline().decode(errors="replace").strip()
            if not resp:
                continue
            out.append(resp)
            if resp.startswith("ok"):
                return out
            if resp.startswith("Error") and "Printer halted" in resp:
                raise RuntimeError(f"Printer halted: {out}")
        raise TimeoutError(f"No ok for {line!r}: {out}")

    def frosting_mode(self) -> None:
        """Heaters off, cold extrusion on, slow speed. After this, homing/probing/heating is refused."""
        for cmd in FROSTING_SETUP:
            self.send(cmd)
        self.food_mode = True

    def pla_mode(self) -> None:
        """Plain PLA printing (invitation cards): heaters and homing allowed again, cold-extrusion guard back on.

        Only after the person at the printer confirms the bed has no food and the syringe tip sits above the
        nozzle tip (server.py asks). M302 P0 turns Marlin's cold-extrusion protection back on."""
        self.food_mode = False
        self.send("M302 P0")

    def long_names(self) -> bool:
        """True if the firmware can write long file names to the SD card (M115 Cap:LONG_FILENAME_WRITE:1)."""
        if not hasattr(self, "_long"):
            self._long = any(re.search(r"Cap:LONG_FILENAME_WRITE:1", x) for x in self.send("M115", wait_s=10))
        return self._long

    # ---- microSD: upload over USB (M28/M29), then print from the card (M23/M24) ----
    def sd_list(self) -> dict[str, int]:
        """{8.3 NAME: size in bytes} from M20."""
        files, inside = {}, False
        for ln in self.send("M20", wait_s=20):
            if ln.startswith("Begin file list"):
                inside = True
            elif ln.startswith("End file list"):
                inside = False
            elif inside and ln:
                parts = ln.split()
                name = parts[0].split("/")[-1].upper()
                files[name] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else -1
        return files

    def sd_upload(self, name: str, lines: list[str], progress: Callable[[int, int], None] | None = None,
                  stop: Callable[[], bool] | None = None, card: bool = False) -> None:
        """Write `lines` to the card as `name`, then check the file size from M20.

        card=True: a PLA menu card file (may heat, never homes); otherwise a food file (no heat, no homing)."""
        if not (SD_NAME.match(name) or (card and LONG_NAME.match(name))):
            raise SDError(f"{name!r} is not an 8.3 name like PP112601.GCO")
        (card_file_safe if card else file_safe)(lines)
        # Marlin sends no "ok" for a comment-only or blank line, so never send one: strip comments first.
        lines = [c for c in (ln.split(";", 1)[0].strip() for ln in lines) if c]
        out = self.send("M21", wait_s=10)
        if any("init fail" in x.lower() or "no sd" in x.lower() for x in out):
            raise SDError("No microSD card in the printer (M21 failed)")
        out = self.send(f"M28 {name}", wait_s=10)
        if not any("writing to file" in x.lower() for x in out):
            raise SDError(f"Printer would not open {name} for writing: {' '.join(out)[:120]}")
        try:
            for i, ln in enumerate(lines, 1):
                if stop and stop():
                    raise SDError("Stopped during upload")
                self.send(ln, wait_s=10, check=False)   # saved to the card, not run
                if progress:
                    progress(i, len(lines))
        finally:
            self.send("M29", wait_s=10)
        size = self.sd_list().get(name)
        want = sum(len(x) for x in lines)
        if size is None:
            raise SDError(f"{name} not on the card after upload")
        if size != -1 and not want <= size <= want + 2 * len(lines):  # Marlin ends lines with \n or \r\n
            raise SDError(f"{name} is {size} bytes, expected about {want}; upload was corrupted")

    def sd_start(self, name: str) -> None:
        out = self.send(f"M23 {name}", wait_s=10)
        if not any("file opened" in x.lower() or "file selected" in x.lower() for x in out):
            raise SDError(f"Could not open {name}: {' '.join(out)[:120]}")
        self.send("M24", wait_s=10)

    def sd_progress(self) -> tuple[int, int] | None:
        """(byte, total) while printing from SD, None when not."""
        for ln in self.send("M27", wait_s=10):
            m = re.search(r"SD printing byte (\d+)/(\d+)", ln)
            if m:
                return int(m[1]), int(m[2])
        return None

    def emergency_stop(self) -> None:
        self.ser.write(b"M112\n")
        self.ser.flush()

    def close(self) -> None:
        self.ser.close()


if __name__ == "__main__":
    p = Printer()
    for cmd in ["M115", "M105", "M117 Hello from Perplexity"]:
        print(cmd, "->", p.send(cmd))
    p.close()
