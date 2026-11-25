# SD card files

Pre-sliced G-code is not stored in the repo (it is large and only fits one slicer profile).
Download it from the repo's GitHub Releases page, or slice `../out/*.3mf` yourself
(OrcaSlicer, stock Ender-3 V3 SE 0.4 profile; settings in `../README.md`).

Copy the files to the top level of the printer's SD card (not in a folder). The Ender-3 V3 SE
only reads names of 20 characters or fewer, using letters and numbers.

1. `fitM2.gcode`: 13 min fit test for the M2 head-mount holes. Print first.
2. `plateA3.gcode`: carriage v1.2 + plunger pusher v0.5, about 4 h 3 min / 71 g PETG
3. `plateB.gcode`: camera post and holder, display feet, pie locator, about 3 h 56 min
4. `pusher5.gcode`: plunger pusher v0.5 only, about 56 min / 18 g
