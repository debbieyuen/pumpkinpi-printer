# PumpkinPi CAD

Parametric CadQuery scripts for the printed syringe-extruder parts. All dimensions live in `params.py`.
Edit a number there, re-run the part script, and the STL/STEP files rebuild.

```bash
pip install -r cad/requirements.txt
python3 cad/plunger_pusher.py        # -> cad/out/plunger_pusher.step / .stl
python3 cad/preview.py plunger_pusher  # -> cad/out/plunger_pusher.png
```

STEP files open in Fusion 360 / SolidWorks / FreeCAD. STL goes into Creality Print or OrcaSlicer.

## Parts

| Part | Status |
|---|---|
| `plunger_pusher.py` | v0.1 — first test print |
| syringe clamp | next |
| motor mount / frame (with guide channel for the pusher key) | after clamp |
| head bracket | needs print-head photos + screw spacing |

## Plunger pusher v0.1

- Lead screw runs parallel to the syringe, 31.6 mm off its axis, so it clears the 47.1 mm finger flange.
- The thumb pad slides in from the side into a pocket, so the pusher can push (dispense) and pull (retract).
- The T8 brass nut sits on top: its body drops into the center bore, and 4× M3×12 screws thread into 2.8 mm pilot holes.
- The +X key rides in a channel in the frame (not designed yet) so the pusher can't spin with the screw.
- Size about 74 × 44 × 10.5 mm.

### Print settings (PETG, Ender 3 V3 SE)
Lay it flat, with the top face (nut side) up. 0.2 mm layers, 4 walls, 40% gyroid infill, no supports. The pocket roof is a 36 mm bridge, so slow bridging to about 25 mm/s with fan 100% for bridges.
Nozzle and bed temperatures: follow the filament label (the Creality manual lists 230 °C / 70 °C for CR-PETG).

### Values to confirm with calipers (in `params.py`)
- `THUMB_PAD_THICK` (assumed 2.0)
- `PLUNGER_STEM_WIDTH`: width of the cross-shaped stem just under the thumb pad (assumed 22)
- T8 brass nut: flange Ø, body Ø, hole spacing (typical 22 / 10.2 / 16 PCD)
