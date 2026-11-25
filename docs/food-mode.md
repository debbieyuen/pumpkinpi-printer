# Food mode

Everything about piping onto food: calibrating, toppings, the drip test and the camera. Read the safety notes in
the [README](../README.md) first.

## Calibrate (empty bed, syringe off)

Do this once, with nothing on the bed.

1. Take the syringe off and home the printer normally.
2. Jog the syringe tip over where the center of the pie will sit, send `M114`, and put the X and Y into
   `machine.json` as `pie_x` and `pie_y`.
3. Lower it until it just touches a sheet of paper on top of an empty pie pan. Put that Z into `z_surface`.
4. Check the plunger rate with `.venv/bin/python -m pumpkinpi.toolpath --calibrate` and adjust `e_per_mm`.

From here on, food runs are cold and never home. Do a dry run first every time.

## Toppings

There are three syringes: melted chocolate (melted chips), frosting and melted marshmallow. You pick one on the
Recipe screen. Each one starts with its own settings from `TOPPINGS` in `pumpkinpi/toolpath.py`, and anything you
tune gets saved under `"toppings"` in `machine.json`.

| Topping | feed | e_per_mm | prime | pull-back | pause | gap | lift speed |
|---|---|---|---|---|---|---|---|
| frosting | 600 | 0.02 | 0.3 | 0.6 | 0.5 s | 1.5 | 300 |
| chocolate | 720 | 0.015 | 0.2 | 0.8 | 1.0 s | 1.0 | 300 |
| marshmallow | 420 | 0.03 | 0.4 | 1.0 | 1.5 s | 2.0 | 120 |

These are my starting guesses. Tune them with the drip test.

After each line, the plunger pulls back and then waits (`dwell`, sent as `G4`) before lifting. That way the
last bit of ooze lands on the line instead of trailing across the pie.

### Drip test

On the Camera tab, put a plate with parchment where the pie goes and tap Drip test. It pipes one 4 cm line, pulls
back, and lifts 3 mm without pausing. Tap "Drip stopped" when the tip stops oozing. It suggests a pause (the ooze
time plus 0.3 s, up to 8 s, with more pull-back if it took over 3 s). Tap Save to keep it.

### Layers

After one topping is done, tap "Add another topping" (say, frosting on top of chocolate). Swap the syringe and tap
Loaded. The earlier layers stay on the preview, and Send stays locked until the right syringe is in.

### Different tips

If a tip is longer or shorter than the one you calibrated `z_surface` with, measure the difference on an empty bed
and save it as that topping's `tip_offset` in mm. Positive means a longer tip, so the head stays higher.

## Too much detail

A cold syringe lays down a bead a few mm wide, so some ideas just won't pipe. The Design screen warns you when:

- you ask for a photo, portrait, scene, shading or several pictures,
- the words need more than two short lines (it shows what it kept),
- letters would come out under 6 mm tall,
- there are more than 60 separate lines, or it would take over 4 minutes.

It suggests something simpler. You can try that or keep yours, and it never blocks Send. The rules are in
`pumpkinpi/detail.py`.

## Camera

The camera has to be mounted above the bed, not on the moving head.

**Check pie** takes one photo. The Decisions API says whether the pie is ready, the Agent API says what it is
(pie, cookie, cupcake...), and OpenCV finds the outer edge and where the filling meets the crust
([Hough circles](https://docs.opencv.org/4.x/da/d53/tutorial_py_houghcircles.html) plus a color walk out from
the center). The design shrinks to fit inside the filling, but never grows. Start stays locked until the ready
score is at least 0.90.

**Save as center** is optional and only needed once. Put a pie exactly at `pie_x`/`pie_y`, tap Check pie, then
Save as center. That writes `camera_cal.json`, so you get real mm sizes and a warning with a target if the pie is
off center. Set `pie_mm` in `machine.json` to the pie's outer diameter (default 152 mm, a 6 inch pie). The camera
never moves the printer. It only resizes the design and warns you.

**Scan label**: hold an ingredient list up to the camera and tap Scan label. The Agent API reads the photo
([image input](https://docs.perplexity.ai/docs/agent-api/image-attachments)), and then the usual allergen check
runs with the photo as evidence. A listed allergen or a "may contain" line for a guest's allergen turns it red.
"Natural flavor" or a cut-off label is never green. If the brand matches an ingredient in the recipe, the result
counts for that ingredient.

**Timelapse** starts on its own when piping or a dry run starts, or you can tap Record. Clips go to
`captures/timelapse/` as a 4:3 MP4 plus a 9:16 `-vertical.mp4`. To copy them to your laptop:

```bash
scp <user>@pumpkinpi.local:~/pumpkinpi-food-printer/captures/timelapse/*.mp4 .
```
