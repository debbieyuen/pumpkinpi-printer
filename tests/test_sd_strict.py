"""End-to-end: G-code file -> USB upload -> what the printer would actually run from its microSD.

StrictMarlin follows Marlin's queue.cpp rules that broke the first real card prints:
  * a blank or comment-only line gets no reply at all
  * while saving (M28) every line needs "N<n> ...*<checksum>" in sequence, else Error + Resend, nothing saved
  * the numbered line is saved as-is; lines of 96+ chars are cut off
  * M20 lists names without sizes (like the V3 SE); M23 reports the size
"""
import re

import pytest

from pumpkinpi import cards
from pumpkinpi.printer import Printer, SDError, card_file, sd_file

MAX_CMD = 96


class StrictMarlin:
    def __init__(self, strip=False):
        self.strip = strip          # some builds save the line without "N.. " and "*cs"
        self.files, self.saving, self.last_n, self.out, self.rx = {}, None, 0, [], []

    def _cs(self, body):
        c = 0
        for ch in body.encode():
            c ^= ch
        return c

    def write(self, b):
        ln = b.decode()[:MAX_CMD - 1].split(";", 1)[0].strip()
        self.rx.append(ln)
        if not ln:
            return
        m = re.fullmatch(r"N(\d+) (.*)\*(\d+)", ln)
        if m:
            n, cmd = int(m[1]), m[2]
            if int(m[3]) != self._cs(ln.rsplit("*", 1)[0]):
                self.out += ["Error:checksum mismatch", f"Resend: {self.last_n + 1}", "ok"]; return
            if cmd.startswith("M110"):
                self.last_n = int(cmd.split("N")[1]); self.out += ["ok"]; return
            if n != self.last_n + 1:
                self.out += ["Error:Line Number is not Last Line Number+1", f"Resend: {self.last_n + 1}", "ok"]; return
            self.last_n = n
        elif self.saving and ln != "M29":
            self.out += ["Error:No Checksum with line number, Last Line: 0", f"Resend: {self.last_n + 1}", "ok"]; return
        else:
            cmd = ln
        if self.saving:
            if cmd == "M29":
                self.saving = None; self.out += ["Done saving file.", "ok"]
            else:
                self.files[self.saving].append(cmd if self.strip else ln); self.out += ["ok"]
            return
        word = cmd.split()[0]
        if word == "M28":
            self.saving = cmd.split()[1]; self.files[self.saving] = []
            self.out += [f"Writing to file: {self.saving}", "ok"]
        elif word == "M20":
            self.out += ["Begin file list", *self.files, "End file list", "ok"]
        elif word == "M23":
            f = cmd.split()[1]
            if f in self.files:
                self.out += [f"File opened: {f} Size: {self.size(f)}", "File selected", "ok"]
            else:
                self.out += ["open failed", "ok"]
        elif word == "M30":
            self.files.pop(cmd.split()[1], None); self.out += ["ok"]
        else:
            self.out += ["ok"]

    def size(self, f):
        return sum(len(x) + 2 for x in self.files[f])

    def runs(self, f):
        """What the printer executes when you press Print: N and *checksum are skipped."""
        return [re.sub(r"^N\d+ ", "", x).rsplit("*", 1)[0] for x in self.files[f]]

    def readline(self):
        return (self.out.pop(0) + "\n").encode() if self.out else b""

    def flush(self):
        pass


def strict(strip=False):
    f = StrictMarlin(strip)
    p = Printer.__new__(Printer); p.ser, p.food_mode, p.port = f, False, "/dev/null"
    return f, p


def card_lines():
    st = cards.layout(cards.load(), [{"text": "Pumpkin pie: may have tree nut", "unsure": []}], "Debbie")
    return card_file(cards.card_gcode(st, cards.Pla(card_x=34, card_y=-4)), "card_11_22_print01.gcode")


def test_card_on_sd_runs_every_command_in_order(monkeypatch):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)   # no real waiting on timeouts
    f, p = strict()
    data = card_lines()
    p.sd_upload("CD112201.GCO", data, card=True)
    want = [c for c in (x.split(";", 1)[0].strip() for x in data) if c]
    assert f.runs("CD112201.GCO") == want                          # nothing dropped, nothing extra
    assert want[:4] == ["M302 P0", "M117 card_11_22_print01", "M140 S0", "M104 S150"]


def test_food_file_on_sd_runs_every_command(monkeypatch):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)
    f, p = strict()
    data = sd_file(["G90", "G1 X100 Y100 E0.1 F600"], "PP112601.GCO")
    p.sd_upload("PP112601.GCO", data)
    assert f.runs("PP112601.GCO") == data


def test_no_blank_or_comment_line_is_ever_sent(monkeypatch):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)
    f, p = strict()
    p.sd_upload("CD112201.GCO", ["; header", "", "M104 S190", "G1 X50 Y50 ; go"], card=True)
    assert all(x for x in f.rx)
    assert f.runs("CD112201.GCO") == ["M104 S190", "G1 X50 Y50"]


def test_failed_upload_leaves_no_file(monkeypatch):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)
    f, p = strict()
    real = f.write
    def flaky(b):                                   # printer rejects line 3 forever
        if b.decode().startswith("N3 "):
            f.out += ["Error:checksum mismatch", "Resend: 3", "ok"]; return
        real(b)
    f.write = flaky
    with pytest.raises(SDError):
        p.sd_upload("CD112201.GCO", ["M104 S190", "G90", "G1 X1 Y1", "G1 X2 Y2"], card=True)
    assert "CD112201.GCO" not in f.files


def test_server_print_card_puts_full_file_on_printer(monkeypatch, tmp_path):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)
    from pumpkinpi import server
    f, p = strict()
    p._long = False
    monkeypatch.setattr(server, "_printer", p)
    monkeypatch.setattr(server, "GCODE_DIR", tmp_path)
    monkeypatch.setattr("pumpkinpi.printer.sd_mounts", lambda: [])
    st = cards.layout(cards.load(), [{"text": "Pie: none", "unsure": []}], "Debbie")
    lines = cards.card_gcode(st, cards.Pla(card_x=34, card_y=-4))
    server.state["job"] = {"running": True}
    server.run_card(lines)
    job = server.state["job"]
    assert job.get("error") is None and job["where"] == "printer", job
    assert job["file"] == job["sd_file"] and job["uploaded"]      # same name on the Pi and the printer
    name = job["sd_file"] + ".GCO"
    assert f.runs(name)[3] == "M104 S150" and "G28" in f.runs(name) and f.runs(name)[-1] == "M117 Card done"


def test_build_that_saves_plain_lines_also_passes(monkeypatch):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)
    f, p = strict(strip=True)
    data = card_lines()
    p.sd_upload("CD112201.GCO", data, card=True)
    assert f.runs("CD112201.GCO")[3] == "M104 S150"


def test_empty_files_from_old_uploads_are_cleared(monkeypatch, tmp_path):
    monkeypatch.setattr("time.time", iter(range(10**7)).__next__)
    from pumpkinpi import server
    f, p = strict()
    p._long = False
    f.files = {"CD112201.GCO": [], "fittest.GCO": ["G90"]}
    monkeypatch.setattr(server, "_printer", p)
    monkeypatch.setattr(server, "GCODE_DIR", tmp_path)
    monkeypatch.setattr("pumpkinpi.printer.sd_mounts", lambda: [])
    server.state["job"] = {"running": True}
    server.run_card(["M104 S190", "G1 X50 Y50"])
    assert "CD112201.GCO" not in f.files                             # empty leftover deleted
    assert f.files[server.state["job"]["sd_file"] + ".GCO"]          # new file is full
    assert "fittest.GCO" in f.files
