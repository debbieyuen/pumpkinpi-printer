# PumpkinPi

[![tests](https://github.com/debbieyuen/pumpkinpi-food-printer/actions/workflows/tests.yml/badge.svg)](https://github.com/debbieyuen/pumpkinpi-food-printer/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)

A Thanksgiving food printer built from a Raspberry Pi 5 and a Creality Ender-3 V3 SE. Type what you want on the
touchscreen ("a smiley face in chocolate for Alex"). [Perplexity](https://docs.perplexity.ai) plans the design and
checks every ingredient against each guest's allergies. The camera confirms the pie is in place, and then a 60 mL
syringe extruder pipes the design onto a mini pumpkin pie. With the stock hot end, it can also print allergen
menu cards for each guest in PLA on watercolor paper.

The machine won't make your food until it has checked that it's safe for you.

![60 mL syringe in the orange carriage on the Ender-3 V3 SE print head, front and back views](cad/out/assembly.png)

> [!WARNING]
> **The allergen check is an aid, not a guarantee.** It reads web pages and labels that can be wrong, out of date
> or about a different version of the product. Always read the label on the package in your hand, and ask guests
> about their allergies yourself. This project is not medical advice.
>
> **Food printing is at your own risk.** Only food-safe parts (the syringe and tips) should touch food. The printed
> PETG carriage and pusher are not food contact parts. Keep food off the bed whenever the printer homes, probes or
> heats.

## How it works

1. **Prompt**: type on the touchscreen (built-in on-screen keyboard).
2. **Plan**: the Perplexity **Agent API** (`/v1/agent`, web search tool, JSON schema output) picks a shape (smiley,
   heart, star, text), the guest's name, topping, ingredient list and recipe that avoids every guest's allergens.
3. **Check ingredients**: for each ingredient, the **Search API** (`/search`) finds label pages. Then one
   **Decisions API** call (`/v1/decisions`) scores "is this evidence about this product", "natural flavor listed"
   and "contains / may contain" for each allergen. It's green only when the evidence is relevant and every
   allergen is unlikely. Otherwise it's yellow ("check the label") or red.
4. **Pie ready**: the camera photo goes to the Decisions API. Start stays locked below 0.90.
5. **Toolpath**: single-stroke Hershey fonts plus shapes, kept inside a 45 mm radius, with bounds-checked G-code.
6. **You press Start**: dry run first (15 mm above the pie, no plunger). Heaters off, `M302 P1`, no homing in food
   mode. **STOP sends `M112` at any step.**

## Hardware

| Part | Notes |
|---|---|
| [Creality Ender-3 V3 SE](https://www.creality.com/products/creality-ender-3-v3-se) | Stock Marlin firmware, CR Touch, 220 x 220 mm bed |
| [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/) (8 GB used) | Raspberry Pi OS with desktop |
| [Raspberry Pi Touch Display 2](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html) | Kiosk UI |
| [Raspberry Pi Camera Module 3](https://www.raspberrypi.com/documentation/accessories/camera.html) | Fixed above the bed, not on the head |
| NEMA 17 pancake stepper + Tr8x2 lead screw (150 mm) | Drives the plunger from the printer's E axis |
| 60 mL Luer-lock syringe + tapered tips | Food contact parts |
| Printed parts (PETG) | `cad/`: carriage, plunger pusher, camera post, display feet, pie locator |
| M2/M3 screws and M3 nuts | See `cad/README.md` |

The Pi talks to the printer over USB serial (115200 baud) with pyserial. No Klipper or OctoPrint needed.

## Try it without a Pi

The touchscreen app has a demo mode with sample data. Open `ui/index.html` in a browser, or run the server on any
computer:

```bash
git clone https://github.com/debbieyuen/pumpkinpi-food-printer.git && cd pumpkinpi-food-printer
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q             # offline: mocked API, no key, no printer
cp .env.example .env                       # add PERPLEXITY_API_KEY to use the real APIs
.venv/bin/python -m pumpkinpi.server       # http://127.0.0.1:8000
```

You need a [Perplexity API key](https://docs.perplexity.ai) for live planning and allergen checks.

## Setup on the Pi

```bash
ssh <user>@pumpkinpi.local
git clone https://github.com/debbieyuen/pumpkinpi-food-printer.git && cd pumpkinpi-food-printer
bash scripts/setup_pi.sh
nano .env            # PERPLEXITY_API_KEY=...   (never commit it or show it on camera)
nano guests.json     # names + allergies
sudo reboot
```

After reboot, the server starts on its own and the touchscreen opens the app full screen. To rotate Touch Display 2
to landscape, go to **Preferences → Control Centre → Screens → DSI-1 → Orientation**.

```bash
cd ~/pumpkinpi-food-printer && .venv/bin/python -m pumpkinpi.doctor   # preflight: key, guests, serial, camera
sudo systemctl status pumpkinpi     # server logs: journalctl -u pumpkinpi -f
```

### Config files

All of these are git-ignored. `setup_pi.sh` creates them from the `*.example.json` files in `examples/`.

| File | What |
|---|---|
| `.env` | `PERPLEXITY_API_KEY`, optional `PRINTER_PORT`, `PUMPKINPI_SHOW_HEALTH` |
| `guests.json` | Guest names, allergens to `avoid`, things to `limit`, private `notes` |
| `machine.json` | Pie position, syringe and topping settings, PLA card settings |
| `cards.json` | Menu, exact branded products and card layout (falls back to `examples/cards.example.json`) |
| `camera_cal.json` | Written by "Save as center" |

## Code layout

| Path | What it is |
|---|---|
| `pumpkinpi/server.py` | Local web server + API for the touchscreen (127.0.0.1:8000) |
| `pumpkinpi/pplx.py` | Perplexity Agent, Search and Decisions API client (key from env) |
| `pumpkinpi/design.py` | Prompt → design plan (Agent API, structured output) |
| `pumpkinpi/allergen_check.py` | Safety gate: Search API evidence + Decisions API per allergen |
| `pumpkinpi/allergens.py`, `allergy_guide.py` | Allergen names, hidden sources and guest guide |
| `pumpkinpi/label_scan.py` | Read an ingredient label from a camera photo |
| `pumpkinpi/menu_plan.py`, `menu_science.py`, `products.py` | Menu planning, food science notes, product photos |
| `pumpkinpi/pie_ready.py`, `vision.py` | "Pie in place" check and dish/crust detection (OpenCV) |
| `pumpkinpi/shapes.py`, `toolpath.py`, `detail.py` | Shapes and fonts → G-code, bounds check, dry run, "too much detail" rules |
| `pumpkinpi/cards.py` | PLA menu cards on paper |
| `pumpkinpi/printer.py` | USB serial control, food-mode lockout (blocks G28/G29/G30/heaters), M112 stop, SD upload |
| `pumpkinpi/camera.py`, `timelapse.py` | Camera stills and timelapse clips |
| `pumpkinpi/doctor.py` | Preflight check |
| `ui/` | Touchscreen app (HTML/JS/CSS); demo mode when opened without the server |
| `cad/` | Parametric CadQuery models for the syringe add-on ([cad/README.md](cad/README.md)); `render_vtk.py` draws the picture above, `render_parts.py` the labelled parts sheet |
| `scripts/` | Pi setup, kiosk and card print presets |
| `docs/` | [Food mode](docs/food-mode.md), [menu cards](docs/menu-cards.md), [hot pot sauces](docs/hot-pot-sauces.md) |
| `examples/` | Example `guests`, `machine` and `cards` config files |
| `tests/` | Offline pytest suite |

## Too much detail

A cold syringe lays a bead a few mm wide, so the Design screen says "That's too much detail to pipe" when:
- the request is a photo, portrait, scene, shading or several pictures (the Agent API flags it in `too_detailed`),
- the words need more than two short lines (it shows what it kept),
- letters would be under 6 mm tall (small dish or wide crust),
- there are more than 60 separate lines, or piping would take over 4 minutes.

It offers a simpler idea ("Try that" sends it as a change) or "Keep mine". It never blocks Send. Rules: `pumpkinpi/detail.py`.

## Camera extras

- **Scan label**: hold a package's ingredient list up to the camera and tap Scan label. The Agent API reads the
  photo ([image input](https://docs.perplexity.ai/docs/agent-api/image-attachments)), then the normal Search API +
  Decider check runs with the photo as label evidence. Printed allergens or a may-contain line for a guest allergen
  turn it red; "natural flavor" or a cut-off label is never green. If the brand matches a recipe ingredient, the
  result counts for that ingredient.
- **Timelapse**: recording starts by itself when piping or a dry run starts, and the Record button starts it by hand.
  Clips land in `captures/timelapse/` as a 4:3 MP4 and a 9:16 `-vertical.mp4` for the video. Copy them to a laptop:

  ```
  scp <user>@pumpkinpi.local:~/pumpkinpi-food-printer/captures/timelapse/*.mp4 .
  ```

- **Dish and crust**: Check pie takes one photo. Decider says if it's ready, the Agent API says what it is (pumpkin pie,
  cookie, cupcake...), and OpenCV on the Pi finds the outer edge and where the filling meets the crust
  ([Hough circles](https://docs.opencv.org/4.x/da/d53/tutorial_py_houghcircles.html) plus a color walk from the
  center). The design shrinks to fit inside the filling (never grows), and new designs are planned for the dish
  (a cookie gets a shape or a short name). The camera must be fixed above the bed, not on the moving head.
- **Save as center** (once, optional): put the pie exactly where you measured `pie_x`/`pie_y`, tap Check pie, then
  Save as center. That writes `camera_cal.json` (git-ignored) and gives real mm sizes plus an off-center warning
  with a target on screen. Set `pie_mm` in `machine.json` to that pie's outer diameter (default 152 = 6 inch).
  Vision never moves the printer or homes; it only resizes the design and warns.

## Calibrate (empty bed, syringe off)

1. Home normally with **no food on the bed and the syringe removed**.
2. Jog the syringe tip over where the pie center will sit, send `M114`, put X/Y into `machine.json` as `pie_x` / `pie_y`.
3. Lower to paper-touch on an empty pie pan top, put Z into `z_surface`.
4. Plunger rate: `.venv/bin/python -m pumpkinpi.toolpath --calibrate` and adjust `e_per_mm`.
5. Then only cold, no-homing runs with food: always **Dry run** first.

## Toppings, pause and drip test

Three syringes: **melted chocolate** (melted chips), **frosting** and **melted marshmallow**. Pick one with the chips on the Recipe screen. Each has its own starting settings in `pumpkinpi/toolpath.py` (`TOPPINGS`), and your measured values are saved per topping under `"toppings"` in `machine.json`:

| Topping | feed | e_per_mm | prime | pull-back | pause | gap | lift speed |
|---|---|---|---|---|---|---|---|
| frosting | 600 | 0.02 | 0.3 | 0.6 | 0.5 s | 1.5 | 300 |
| chocolate | 720 | 0.015 | 0.2 | 0.8 | 1.0 s | 1.0 | 300 |
| marshmallow | 420 | 0.03 | 0.4 | 1.0 | 1.5 s | 2.0 | 120 |

These are estimates; tune them with the drip test.

- **Pause** (`dwell`): after each line the plunger pulls back, then waits `G4` this long before lifting, so the ooze lands on the line instead of trailing.
- **Drip test** (Camera tab): put a plate with parchment where the food goes, tap Drip test. It pipes one 4 cm line, pulls back with no pause and lifts 3 mm. Tap "Drip stopped" when the tip stops oozing; it suggests a pause (ooze time + 0.3 s, max 8 s, plus more pull-back if over 3 s). Tap Save.
- **Layers**: after a topping is piped, tap "Add another topping" (e.g. frosting after chocolate). Swap the syringe, tap Loaded. Earlier layers stay on the preview, and Send stays locked until the right syringe is loaded.
- **tip_offset**: if a nozzle is longer or shorter than the one you set `z_surface` with, measure the difference with an empty bed and save it as that topping's `tip_offset` (mm; positive = longer tip, so the carriage stays higher; negative = shorter tip).

## Menu cards (filament on paper or the bare bed)

`pumpkinpi/cards.py` turns the menu in `cards.json` into a card for each guest. Each card lists every dish, with
the allergens Perplexity found in its exact branded products. A `?` means "check the label". Nothing is ever printed
as safe. Cards use the stock hot end with PLA or PETG (set the temperatures for the filament that is loaded), and the syringe must sit above the nozzle tip.

```bash
.venv/bin/python -m pumpkinpi.cards --check            # run the allergen check for the menu (uses the API)
.venv/bin/python -m pumpkinpi.cards --guest Alex --gcode > card.gcode
```

Presets for `machine.json`:

- `python3 scripts/paper_6x9.py`: 6 x 9 in, 140 lb watercolor paper (bed off, cool nozzle, fan 100 %, tape all edges).
- `python3 scripts/measure_paper.py`: measures paper thickness with the CR Touch so the prime line reaches the bed.
  Stop the server first (`sudo systemctl stop pumpkinpi`). Only paper on the bed.
- `python3 scripts/bare_bed.py`: prints straight on the bare bed instead of paper. PETG by default (235 C nozzle, 75 C bed); `python3 scripts/bare_bed.py pla` if PLA is loaded.

The Ender-3 V3 SE reads files from the top folder of its SD card. The server saves cards there and checks file names.

## Safety

- Never home or run auto Z offset with food on the bed. Food mode blocks `G28`, `G29`, `G30` and heater commands.
- Frosting mode: heaters off, `M302 P1`, slow speed. STOP sends `M112`.
- A person presses Start. The allergen check is an aid, not a guarantee. Always read the label.
- Guests' diet and health notes stay hidden on screen unless `PUMPKINPI_SHOW_HEALTH=1`. Get consent first.

## Tests

```bash
.venv/bin/python -m pytest -q      # offline (mocked API, no key, no printer)
```

GitHub Actions runs the same tests on every push and pull request.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md), [CODE_OF_CONDUCT.md](.github/CODE_OF_CONDUCT.md) and [SECURITY.md](.github/SECURITY.md).

## License

The code, CAD scripts and docs are under the [MIT License](LICENSE). Bundled third-party files (three.js, the Inter
font, Open Food Facts photos and the Perplexity logos) keep their own licenses. See
[licenses/README.md](licenses/README.md).
