# PumpkinPi

A Thanksgiving food printer: a Raspberry Pi 5 checks every ingredient against each guest's allergies with the Perplexity Decisions API, then a syringe extruder on a Creality Ender 3 V3 SE pipes each guest's name onto a mini pumpkin pie.

The machine won't make your food until it has checked that it's safe for you.

## Layout

| Path | What it is |
|---|---|
| `pumpkinpi/allergen_check.py` | Safety gate: grounded yes/no allergen check with sources (Decisions API, `mode: web_grounding`) |
| `pumpkinpi/printer.py` | USB serial control of the printer (Marlin G-code, frosting mode, M112 stop) |
| `tests/` | Offline tests (mocked API, no key or network needed) |
| `docs/PROJECT_SUMMARY.md` | Full project plan, hardware, video plan |
| `guests.example.json` | Example guest list. Copy to `guests.json` (git-ignored) for real data |

## Setup on the Pi

```bash
ssh <user>@pumpkinpi.local
git clone https://github.com/debbieyuen/pumpkinpi-printer.git && cd pumpkinpi-printer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo usermod -aG dialout $USER   # then log out and back in
export PERPLEXITY_API_KEY=...    # never commit or show on camera
cp guests.example.json guests.json
```

## Try it

```bash
pytest -q                                          # offline tests
python -m pumpkinpi.printer                        # M115 / M105 / "Hello from Perplexity"
python -m pumpkinpi.allergen_check "Barefoot Moscato wine"   # exit code 1 = printer blocked
```

## Safety

- Never home or run auto Z offset with food on the bed.
- Frosting mode: heaters off, `M302 P1`, slow speed. STOP sends `M112`.
- The allergen check is an aid, not a guarantee. Always read the label.
