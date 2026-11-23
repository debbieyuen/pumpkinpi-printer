import datetime as dt

import pytest

from pumpkinpi.printer import FoodModeError, Printer, SD_NAME, SDError, sd_file, sd_name


class FakeMarlin:
    """Enough of Marlin's serial replies for M20/M21/M23/M24/M27/M28/M29."""
    def __init__(self, sd=True):
        self.sd, self.files, self.writing, self.out = sd, {}, None, []

    def write(self, b):
        ln = b.decode().strip()
        if self.writing and ln != "M29":
            self.files[self.writing] += len(ln) + 2; self.out += ["ok"]; return
        cmd = ln.split()[0]
        if cmd == "M21": self.out += (["echo:SD card ok"] if self.sd else ["echo:SD init fail"]) + ["ok"]
        elif cmd == "M28":
            if self.sd:
                self.writing = ln.split()[1]; self.files[self.writing] = 0
                self.out += [f"Writing to file: {self.writing}", "ok"]
            else: self.out += ["echo:open failed", "ok"]
        elif cmd == "M29": self.writing = None; self.out += ["Done saving file.", "ok"]
        elif cmd == "M20": self.out += ["Begin file list", *[f"{k} {v}" for k, v in self.files.items()], "End file list", "ok"]
        elif cmd == "M23": self.out += ["File opened: x Size: 1", "File selected", "ok"]
        else: self.out += ["ok"]

    def readline(self):
        return (self.out.pop(0) + "\n").encode() if self.out else b""

    def flush(self): pass


def printer(fake):
    p = Printer.__new__(Printer); p.ser, p.food_mode, p.port = fake, True, "/dev/null"
    return p


def test_names_are_8_3_and_count_up():
    d = dt.date(2026, 11, 26)
    assert sd_name(False, [], d) == "PP112601.GCO"
    assert sd_name(False, ["pp112601.gco", "PP112602.GCO"], d) == "PP112603.GCO"
    assert sd_name(True, [], d) == "DR112601.GCO"
    for n in ["PP112601.GCO", "DR112699.GCO"]:
        assert SD_NAME.match(n) and len(n.split(".")[0]) <= 8
    assert not SD_NAME.match("pumpkin pie.gcode")


def test_file_has_safe_header_and_no_homing():
    data = sd_file(["G90", "G0 Z40 ; up", "", "G1 X10 E0.1"], "PP112601.GCO")
    assert data[:3] == ["M104 S0", "M140 S0", "M302 P1"] and "G0 Z40" in data and "" not in data
    with pytest.raises(FoodModeError):
        sd_file(["G28"], "PP112601.GCO")
    with pytest.raises(FoodModeError):
        sd_file(["M104 S200"], "PP112601.GCO")


def test_upload_verifies_size_and_starts():
    f = FakeMarlin(); p = printer(f)
    data = sd_file(["G90", "G1 X10 Y10"], "PP112601.GCO")
    p.sd_upload("PP112601.GCO", data)
    assert "PP112601.GCO" in p.sd_list()
    p.sd_start("PP112601.GCO")


def test_no_card_raises_so_server_can_fall_back():
    p = printer(FakeMarlin(sd=False))
    with pytest.raises(SDError):
        p.sd_upload("PP112601.GCO", ["G90"])


def test_card_file_homes_on_card_but_never_probes_bed():
    import datetime as _dt
    from pumpkinpi.printer import card_file
    d = _dt.date(2026, 11, 22)
    assert sd_name(False, ["CD112201.GCO"], d, prefix="CD") == "CD112202.GCO"
    from pumpkinpi.printer import card_label
    assert card_label(["card_11_22_print01.gcode"], d) == "card_11_22_print02"
    out = card_file(["G90", "M109 S205", "G1 X10 Y10 E0.1 ; draw"], "card_11_22_print01.gcode")
    assert out[2] == "M117 card_11_22_print01" and out[0].startswith("; card_11_22_print01")
    assert out[1] == "M302 P0" and "M109 S205" in out and "G1 X10 Y10 E0.1" in out
    assert "G28" in card_file(["G28", "M420 S1"], "CD112201.GCO")
    for bad in ("G29", "M302 P1", "M851 Z-1", "M500"):
        with pytest.raises(FoodModeError):
            card_file([bad], "CD112201.GCO")
