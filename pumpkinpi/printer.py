"""Talk to the Ender 3 V3 SE (Marlin) over USB serial with pyserial.

Safety rules (from the project notes):
- Never home or run auto Z offset with food on the bed.
- Frosting mode: heaters off, cold extrusion allowed (M302 P1), motors stay powered (M84 S0).
- emergency_stop() sends M112. Stay next to the machine.
"""
from __future__ import annotations

import os
import time

import serial  # pyserial

BAUD = 115200
FROSTING_SETUP = ["M104 S0", "M140 S0", "M302 P1", "M84 S0", "M220 S15", "M117 PumpkinPi ready"]


class Printer:
    def __init__(self, port: str | None = None, baud: int = BAUD, timeout: float = 2.0):
        self.ser = serial.Serial(port or os.environ.get("PRINTER_PORT", "/dev/ttyUSB0"), baud, timeout=timeout)
        time.sleep(2)  # Marlin resets on connect
        self.ser.reset_input_buffer()

    def send(self, line: str, wait_s: float = 30.0) -> list[str]:
        """Send one G-code line and wait for Marlin's 'ok'."""
        self.ser.write((line.strip() + "\n").encode())
        out, deadline = [], time.time() + wait_s
        while time.time() < deadline:
            resp = self.ser.readline().decode(errors="replace").strip()
            if not resp:
                continue
            out.append(resp)
            if resp.startswith("ok"):
                return out
        raise TimeoutError(f"No ok for {line!r}: {out}")

    def frosting_mode(self) -> None:
        for cmd in FROSTING_SETUP:
            self.send(cmd)

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
