"""Talk to the Ender 3 V3 SE (Marlin) over USB serial with pyserial.

Safety rules (from the project notes):
- Never home or run auto Z offset with food on the bed.
- Frosting mode: heaters off, cold extrusion allowed (M302 P1), motors stay powered (M84 S0).
- emergency_stop() sends M112. Stay next to the machine.
"""
from __future__ import annotations

import os
import re
import time

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

    def send(self, line: str, wait_s: float = 30.0) -> list[str]:
        """Send one G-code line and wait for Marlin's 'ok'."""
        if self.food_mode and FOOD_MODE_BLOCKED.match(line.strip()):
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
