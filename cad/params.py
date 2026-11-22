"""Shared dimensions for PumpkinPi printed parts (all in mm).

MEASURED = taken with calipers by Debbie on 2026-11-21 (photos in the project files).
TYPICAL  = common T8 nut / NEMA 17 values from seller listings; confirm with calipers.
ASSUMED  = placeholder until measured. Update and re-run the part scripts.
"""

# --- 60 mL Luer-lock syringe -------------------------------------------------
BARREL_OD = 31.1             # MEASURED 1.225 in
BARREL_FRONT_TO_FLANGE = 121.1  # MEASURED 4.767 in (barrel front face to finger flange)
TIP_TO_FLANGE = 139.1        # MEASURED 5.476 in (Luer tip end to finger flange)
FLANGE_WIDTH = 47.1          # MEASURED 1.855 in (long side of finger flange)
FLANGE_THICK = 1.75          # MEASURED 0.069 in
THUMB_PAD_D = 34.5           # MEASURED 1.358 in
PLUNGER_OUT_PAST_FLANGE = 113.0  # ESTIMATE from tape-measure photo (~9.3 in overall)
PLUNGER_IN_PAST_FLANGE = 14.0    # ESTIMATE from photos (plunger fully pushed in)
FLANGE_DEPTH = 36.0          # ASSUMED short side of finger flange
THUMB_PAD_THICK = 2.0        # ASSUMED
PLUNGER_STEM_WIDTH = 27.5    # ASSUMED: 60 mL plunger fins are about as wide as the barrel bore

# --- Tr8x2 brass nut (TYPICAL) ----------------------------------------------
NUT_FLANGE_D = 22.0
NUT_FLANGE_THICK = 3.5
NUT_BODY_D = 10.2
NUT_BODY_LEN = 10.0
NUT_HOLE_PCD = 16.0
NUT_HOLE_D = 3.5
LEAD_SCREW_D = 8.0

# --- Hardware ----------------------------------------------------------------
M3_CLEAR = 3.4
M3_NUT_AF = 5.5     # across flats
M3_NUT_THICK = 2.4

# --- Print fit ---------------------------------------------------------------
CLEAR = 0.4         # general sliding clearance for PETG on the Ender 3 V3 SE

# --- STEPPERONLINE NEMA 17 pancake (seller drawing, Amazon B0B93PNYCP) -------
MOTOR_W = 42.3            # max, square body
MOTOR_LEN = 23.0          # max body length
MOTOR_HOLE_SPACING = 31.0 # ±0.2, 4x M3, thread depth 3.0 min
MOTOR_BOSS_D = 22.0       # -0.05
MOTOR_BOSS_H = 2.0
MOTOR_SHAFT_D = 5.0       # -0.012, D-flat 4.5 ±0.1 across, flat length 17 ±0.25
MOTOR_SHAFT_LEN = 20.0    # ±1 from mounting face
MOTOR_SCREW_THREAD_DEPTH = 3.0  # min: plate 5 mm + M3x8 -> 3 mm engagement

# --- Layout of the syringe on the print head (nozzle-tip coordinates, see head_geometry.py)
SYR_X = 54.0        # syringe axis, right of the nozzle
SYR_Y = -6.0        # syringe axis, slightly toward the front
LUER_Z = 5.0        # end of the syringe's Luer tip, above the nozzle tip.
                    # Any dispensing tip longer than ~8 mm then hangs below the hot-end nozzle.
SCREW_DY = -47.0    # lead screw axis offset from the syringe axis (toward the front).
                    # v1.1: was -42; moved 5 mm forward so the back motor screw heads clear the web.
MOTOR_SCREW_HEAD_D = 5.5   # M3 socket head
MOTOR_SCREW_WALL_GAP = 3.0 # v1.1: min gap from a motor screw head to any wall (Debbie, 2026-11-21)
