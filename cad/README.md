# PumpkinPi CAD: syringe carriage and accessories (v1)

Parametric CadQuery models for the 60 mL syringe add-on for the Creality Ender-3 V3 SE,
plus the camera, display and pie-locator parts. All of them fit on one 220 x 220 mm plate.

## Print it tonight

| File | What | Time / PETG |
|---|---|---|
| `out/fit_test_PETG.gcode` | Fit test: the screw holes and spine face. Print this first. | 13 min / 4 g |
| `out/pumpkinpi_plate_PETG.gcode` | All 7 parts on one plate | 7 h 50 min / 144 g |
| `out/plate_all.3mf` | The same plate, for opening in a slicer | |

Slicer settings: OrcaSlicer 2.5.1 with the stock Ender-3 V3 SE 0.4 profile. Generic PETG at 240 °C
(the strings-free temp from Debbie's notes), bed at 70 °C, 0.20 mm layers, 4 walls, 5 top/bottom layers,
40% gyroid infill, 3 mm brim, no supports. Every part prints flat in the orientation the model gives it.

## Parts

| Part | Notes |
|---|---|
| `carriage` | A one-piece bracket. It bolts to the head's right side plate with the 2 stock screws. It has a lower snap clip for the barrel, a cradle for the flange and a plate for the motor. It prints lying on the face that goes against the head. |
| `plunger_pusher` | A brass T8 nut goes into the screw hole. The thumb pad slides into the pocket from +X. |
| `pie_locator` | A 90° V for 6-inch pans. Tape it to the bed. |
| `camera_post` + `camera_holder` | Holds the Camera Module 3 in grooves. The pivot uses an M3x20 bolt and nut. |
| `display_foot` x2 | 18 mm slots with a 15° lean, for the 5" Touch Display 2. |

## Hardware

- 2x M3 screws, each 4 mm longer than the stock side-plate screws. The spine is 6 mm thick with a 2 mm counterbore.
- 4x M3x8 to mount the motor. The motor drawing says the threads are at least 3 mm deep.
- 4x M3x12 to fix the brass T8 nut flange into the pusher.
- 1x M3x20 + nut for the camera pivot.

## Use it safely

1. Print `fit_test` and bolt it onto the head. Check that the holes line up before you trust the overnight plate.
2. **Remove the syringe before homing.** Never home or run auto Z offset with food on the bed.
3. Home with the syringe off, put the syringe on, then pipe **without re-homing**. Use cold extrusion (`M302 P1`) with the heaters off.
4. The syringe axis is offset from the nozzle by X +54, Y -6 mm. The Luer tip sits 5 mm above the nozzle tip,
   so the dispensing tip hangs below the nozzle.
5. Soft limits: keep the nozzle at X <= ~150, because the syringe hangs off the right. Keep Z low, because the
   stack reaches ~290 mm above the nozzle tip. Jog slowly once to check clearance before loading food.
6. Pie locator: the pan center is R x sqrt(2) from the V corner. Calibrate it once, then tape the locator down.

## Assumptions (check with calipers if anything binds)

- These values are assumed: FLANGE_DEPTH 36, THUMB_PAD_THICK 2.0 and PLUNGER_STEM_WIDTH 27.5. The T8 nut sizes are typical values.
- The head geometry comes from Michael Hilton's Ender-3 V3 SE model, which he describes as "somewhat accurate".
  The model puts the 2 right-side M3 holes 14.2 mm apart, center to center.
- `check_fit.py` reports zero interference with the head, a dummy barrel, the flange, the motor and the coupler.

## Rebuild

```bash
pip install -r requirements.txt
python3 carriage.py && python3 plunger_pusher.py && python3 small_parts.py
python3 check_fit.py && python3 plate.py && python3 render.py
```

## Credits and sources

- Print head and frame reference: Michael Hilton, "Creality Ender 3 V3 SE", CC BY.
  https://www.printables.com/model/672045 (files in `reference/`)
- Design ideas: Allstruder, a 60 mL syringe extruder. https://shiwarskilab.com/allstruder/index.html
- Touch Display 2 dimensions: https://www.raspberrypi.com/documentation/accessories/touch-display-2.html
- Camera Module 3: https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf
- Motor: the seller's drawing for Amazon B0B93PNYCP (see `params.py`).
