# PumpkinPi

A Thanksgiving food printer: type what you want on the Raspberry Pi touchscreen ("a smiley face in chocolate for Michael"), Perplexity plans the design, checks every ingredient against each guest's allergies, confirms the pie is in place, and then a syringe extruder on a Creality Ender 3 V3 SE pipes it onto a mini pumpkin pie.

The machine won't make your food until it has checked that it's safe for you.

## How it works

1. **Prompt** – type on the touchscreen (built-in on-screen keyboard).
2. **Plan** – Perplexity **Agent API** (`/v1/agent`, web search tool, JSON schema output) picks a shape (smiley, heart, star, text), the guest's name, topping, ingredient list and recipe that avoids every guest's allergens.
3. **Check ingredients** – for each ingredient, the **Search API** (`/search`) finds label pages, then one **Decisions API** call (`/v1/decisions`) scores "is this evidence about this product", "natural flavor listed" and "contains / may contain" for each allergen. Green only when the evidence is relevant and every allergen is unlikely; otherwise yellow ("check the label") or red.
4. **Pie ready** – the camera photo goes to the Decisions API; Start stays locked below 0.90.
5. **Toolpath** – single-stroke Hershey font + shapes, kept inside a 45 mm radius, bounds-checked G-code.
6. **You press Start** – dry run first (15 mm above the pie, no plunger). Heaters off, `M302 P1`, no homing in food mode. **STOP sends `M112` at any step.**

## Layout

| Path | What it is |
|---|---|
| `pumpkinpi/server.py` | Local web server + API for the touchscreen (127.0.0.1:8000) |
| `pumpkinpi/pplx.py` | Perplexity Agent, Search and Decisions API client (key from env) |
| `pumpkinpi/design.py` | Prompt → design plan (Agent API, structured output) |
| `pumpkinpi/allergen_check.py` | Safety gate: Search API evidence + Decider per allergen |
| `pumpkinpi/pie_ready.py` | Camera "pie in place" check |
| `pumpkinpi/shapes.py` | Smiley / heart / star / name strokes |
| `pumpkinpi/toolpath.py` | Strokes → G-code, bounds check, dry run, calibration |
| `pumpkinpi/printer.py` | USB serial control, food-mode lockout (blocks G28/G29/heaters), M112 stop |
| `pumpkinpi/doctor.py` | Preflight check (key, guests, serial, camera) |
| `ui/` | Touchscreen app (HTML/JS/CSS); demo mode when opened without the server |
| `scripts/setup_pi.sh` | One-time Pi setup: venv, service, kiosk |
| `machine.example.json` | Pie position and syringe settings. Copy to `machine.json` |
| `guests.example.json` | Example guest list. Copy to `guests.json` (git-ignored) |

## Setup on the Pi

```bash
ssh <user>@pumpkinpi.local
git clone https://github.com/debbieyuen/pumpkinpi-printer.git && cd pumpkinpi-printer
bash scripts/setup_pi.sh
nano .env            # PERPLEXITY_API_KEY=...   (never commit or show on camera)
nano guests.json     # names + allergies
sudo reboot
```

After reboot the server starts on its own and the touchscreen opens the app full screen. Rotate Touch Display 2 to landscape in **Preferences → Control Centre → Screens → DSI-1 → Orientation**.

```bash
cd ~/pumpkinpi-printer && .venv/bin/python -m pumpkinpi.doctor
sudo systemctl status pumpkinpi     # server logs: journalctl -u pumpkinpi -f
```

## Calibrate (empty bed, syringe off)

1. Home normally with **no food on the bed and the syringe removed**.
2. Jog the syringe tip over where the pie center will sit, send `M114`, put X/Y into `machine.json` as `pie_x` / `pie_y`.
3. Lower to paper-touch on an empty pie pan top, put Z into `z_surface`.
4. Plunger rate: `.venv/bin/python -m pumpkinpi.toolpath --calibrate` and adjust `e_per_mm`.
5. Then only cold, no-homing runs with food: always **Dry run** first.

## Tests

```bash
.venv/bin/python -m pytest -q      # offline (mocked API, no key, no printer)
```

## Safety

- Never home or run auto Z offset with food on the bed (food mode blocks `G28`, `G29`, `G30`, heater commands).
- Frosting mode: heaters off, `M302 P1`, slow speed. STOP sends `M112`.
- A person presses Start. The allergen check is an aid, not a guarantee. Always read the label.
- Guests' diet/health notes are hidden on screen unless `PUMPKINPI_SHOW_HEALTH=1` (get consent first).
