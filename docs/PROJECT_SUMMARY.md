# PumpkinPi: A Thanksgiving Food Printer Powered by Perplexity

*Project summary from planning chats, Nov 18–21, 2026*

---

## 1. The assignment

**From:** Jeff Grimes, Perplexity (Physical Maker role)

> Build an awesome physical creation powered by Perplexity, using the equipment you have. Send a video (private YouTube link) showing how you made it and the final creation. The video should feel like something Perplexity could actually post on social media.

- Perplexity will provide credits. **Ask for API credits specifically**, since a Pro/Max subscription does not cover API usage.
- Target: send the video **next week**.

---

## 2. The concept

**One-liner:** *A machine that won't make your food until it has checked that it's safe for you, and then decorates each person's own pie.*

**The story:**
Thanksgiving is coming, and I'm short on time. My family does **hot pot** for Thanksgiving, I have several **Friendsgivings**, and my **boyfriend has never had a Thanksgiving** (he wasn't born here). Everyone has different allergies and dietary needs. I want every guest to feel remembered and valued.

**The pipeline:**
1. **Perplexity finds or creates the recipe.** It accounts for everyone's allergies, diets, and cultures (e.g., a fusion pie like black sesame pumpkin or mochi-crust pumpkin), with sources.
2. **Design.** Perplexity suggests a message or design for each guest. The Pi turns each **name** into a printer path using a **single-line font**, so the frosting draws one clean line per letter.
3. **I bake** (6-inch mini pumpkin pies).
4. **The Ender 3 V3 SE pipes each guest's name** in 3D frosting or ganache.

**Safety gate:** products and ingredients are checked first. Example: scan a bottle of wine → Perplexity finds it contains **almond** → the screen shows "Michael is allergic" with a source → the printer won't start.

---

## 3. Perplexity's role (APIs)

| API | Use in this project |
|---|---|
| **Agent API** (`/v1/agent`) | Recipe generation, guest messages, food science explanations. Can use models from OpenAI, Anthropic, Google, xAI plus Perplexity search |
| **Search API** | Ranked web results and the **source links** shown on screen |
| **Decider / Decisions API** (`/v1/decisions`, launched Nov 12, 2026) | Yes/no and multiple-choice decisions that return **probabilities**. Supports `web_grounding` (searches first) and **image input** |
| ~~Sonar chat completions~~ | Being retired; docs said migrate by Sept 27, 2026. Don't build on it |

**Decider uses:**
- "Does this product contain tree nuts?" (with web grounding) → 🟢 safe / 🟡 unsure, check the label / 🔴 allergen found
- "Is the pie centered and ready to decorate?" (camera photo) → above 0.9 → **the printer starts by itself**
- Optional: pick a design per guest; rate how readable the finished name is (1–5)

**Approximate costs:** Decider ~$0.01–0.02 per 1M input tokens (output free), plus ~$0.001 per web search. Expect **under $5–10 total** for the project. Check current pricing.

**Framing for the video (accurate, not overclaiming):**
- ❌ "Only Perplexity can check facts."
- ✅ "I built this on Perplexity because checking facts with sources is what it's built for."

**Strongest "needs live search" moments:**
1. Hidden allergen in a **specific product** (almond wine; fish sauce in hot pot sauces)
2. **Recent recalls** on actual ingredients
3. Safe substitutes **sold at nearby stores** / stores open on Thanksgiving
4. Decider's probability **starting the printer**

---

## 4. Research topics for Perplexity

**Food science:**
- Why does pumpkin pie set? (egg proteins coagulate around 80°C / 175°F)
- Why evaporated milk instead of regular milk? (less water → firmer custard)
- Egg-free swaps (aquafaba: chickpea water)
- Why does pumpkin pie crack? (overbaking)
- Why chill before decorating?
- Why does frosting pipe well? (shear-thinning)
- Why does ganache temperature matter? (sets printer settings)
- Low-sugar pie options (allulose, monk fruit, erythritol) and how they affect texture; crust carbohydrates matter too

**Labels and sourcing:**
- Organic vs. conventional (pesticide residue, nutrition, baking chemistry)
- Egg labels: cage-free, free-range, pasture-raised
- Is coconut considered a tree nut? (labeling rules have changed)
- Hidden fish ingredients (fish sauce, anchovies in some dressings and Worcestershire sauce)

**Culture:**
- Thanksgiving history and traditions, explained for someone experiencing it for the first time
- Comparison with a holiday from my boyfriend's home country
- Why some Asian American families have hot pot for Thanksgiving
- "Happy first Thanksgiving" / "thank you" in a guest's language

**Building the printer:**
- Is PETG food-safe? Are these syringes food-safe?

---

## 5. Guests and dietary needs

*(Get consent before showing health details on camera; keep the screen general, e.g., "low-sugar for Dad ✅".)*

**Thanksgiving with family** (hot pot):
- Dad: diabetes, heart condition. Limit sugar
- Mom: RA. Limit sugar
- Kathy: likes vegetables, meatballs, tofu
- Michael: likes Korean hot pot meat. **Allergic to all nuts except peanuts**
- Me: **allergic to all nuts and fish** (shellfish is OK)
- Aunts and cousins: TBD

**Other events:** Friendsgiving at Alice's, Black Friday shopping, Friendsgiving at my place. Guest names TBD.

⚠️ **Check the event dates:** Thanksgiving 2026 is **Thursday, Nov 26**. The notes doc listed Nov 18–21, which looks off by a week.

---

## 6. Hardware

### Printer and extruder
- **Creality Ender 3 V3 SE** (220 × 220 mm bed, bed slides front/back, CR Touch, Marlin-based firmware)
- **Creality EN-PETG, orange**, 1.75 mm (print temp 230–250°C)
- **STEPPERONLINE NEMA 17 pancake stepper**, 42×23 mm, 1A, 17 Ncm
- **Tr8x2 lead screw**, 150 mm, 2 mm lead, 1 start, with brass nut (2 mm lead = more force, finer control, doesn't slip back)
- **5 mm → 8 mm flexible plum coupler**
- **60 mL Luer-lock syringes** (10-pack, individually wrapped). Check for BPA-free / latex-free; wash before use
- **Tapered plastic Luer-lock dispensing tips** (14/18/20/22 gauge). Tips screw directly onto the syringe; **no M6 adapter or metal nozzle needed**
- **M3 stainless socket screw kit** (max 30 mm)
- **Digital calipers**, **silicone baking mats**

### Raspberry Pi station
- **Raspberry Pi 5 (8 GB)** + **Active Cooler**
- **Raspberry Pi Camera Module 3** (standard, autofocus, **not NoIR**)
- **CSI camera cable, 500 mm, 22-pin → 15-pin** (Pi 5)
- **Raspberry Pi Touch Display 2 (5")**
- **CanaKit 45W USB-C power supply with PiSwitch** (Pi 5 needs 5V/5A; Apple/Lenovo laptop chargers only give 5V/3A)
- **SanDisk Ultra 200 GB A1** microSD (in use)
- **USB-A → USB-C data cable** (Pi → printer)

### Still to buy or decide
- Precision screwdriver set (PH0/PH00, hex 1.5/2/2.5 mm), flush cutters, zip ties
- Stepper extension cable, **only if** the motor's cable doesn't fit the printer's extruder connector
- Optional: SG90 servo for a physical "safety gauge" needle, jumper wires, arcade STOP button
- Groceries after Perplexity generates the allergy-safe recipe
- Possible returns: SanDisk Extreme PLUS 64 GB (unused). Amazon printer price dropped to $169 (paid $216); ask about the difference

---

## 7. Setup progress (as of Nov 21)

- ✅ Raspberry Pi OS (64-bit, Debian Trixie) flashed with hostname, Wi-Fi, user, SSH, and Raspberry Pi Connect
- ✅ Touch Display 2 working (Pi mounted on its back)
- ✅ Printer assembled, PETG loaded, auto Z offset completed
- ✅ Pi connected to the printer by USB
- ⬜ SSH from Mac (`ssh user@pumpkinpi.local`) and `sudo apt update && sudo apt full-upgrade -y`
- ⬜ Install the Active Cooler
- ⬜ Camera connected to the free CAM/DISP port; test with `rpicam-hello --list-cameras` (expect imx708)
- ⬜ Printer serial test: `ls /dev/ttyUSB* /dev/ttyACM*`, add user to `dialout`, `picocom -b 115200 --echo /dev/ttyUSB0`, send `M115`, `M105`, `M117 Hello from Perplexity`
- ⬜ Slicer on Mac (Creality Print or OrcaSlicer), PETG test print
- ⬜ Perplexity API key (store in an environment variable; never in code or on camera)

---

## 8. Design decisions and technical notes

- **Syringe only.** Pipe **frosting or ganache**, not melted chocolate (melted chocolate needs a heated syringe)
- **No Klipper or OctoPrint.** A custom Python script talks to the printer over USB serial (115200 baud) with `pyserial`
- **The syringe mounts beside the print head.** The nozzle stays installed and **turned off**. The syringe tip hangs **15–20 mm below** everything else so the head clears the pie crust
- **Wiring change:** the printer's extruder motor cable is unplugged from the stock extruder and plugged into the pancake motor
- **Firmware settings for frosting:** `M302 P1` (allow cold extrusion), heaters off, `M84 S0` (keep motors powered), slow speed (10–20%)
- **One 6-inch mini pumpkin pie at a time**, centered by a printed ring. Chill the pie so the surface is firm
- **Height:** measure the pie surface with the paper test at about 5 points; the code interpolates between them. Lift the tip over the crust rim between lines
- **Never run auto Z offset or homing with food on the bed.** The V3 SE heats the nozzle and taps the bed during calibration
- **The camera is fixed to the frame**, so the code moves the bed to a "photo position" before each picture
- **Safety:** big STOP button on the touchscreen (sends `M112`); only start when Decider is confident; stay nearby
- **Pi 5 has no headphone jack.** Use a Bluetooth speaker for voice alerts (optional)

### PETG parts to print (designs pending measurements)
Syringe clamp · head bracket · motor mount · plunger pusher · pie centering ring · camera mount · Pi + display stand (optional)

**Measurements needed:**
- Syringe: barrel outside diameter, flange width and thickness, barrel length, plunger length
- Print head: front and side photos, distance between two usable screw holes
- Pie pan: outside diameter

---

## 9. Video plan (~60 seconds)

| Time | Shot | Perplexity moment |
|---|---|---|
| 0–5s | "Three Friendsgivings, one family hot pot, and my boyfriend has never had Thanksgiving" | — |
| 5–12s | Guests' allergy answers coming in; boyfriend asks "Why pumpkin pie?" | Research with sources |
| 12–20s | Perplexity builds a safe recipe on the Pi screen | Recipe + citations |
| 20–28s | Scan the wine → 🔴 "Almonds, Michael is allergic" + source | **The big catch** |
| 28–35s | Pie on the bed → "Decider: ready ✅ 97%" → the printer starts by itself | Search drives the machine |
| 35–48s | Overhead timelapse: names piped in 3D frosting | Perplexity wrote each message |
| 48–60s | Guests' reactions; family hot pot table with pies | "Every pie, checked by Perplexity" |

**Filming tips:** vertical 9:16; iPhone Cinematic mode for close-ups; window light; overhead tripod for piping; CapCut for captions. Keep research moments short and physical moments long. Show real catches, not scripted ones.

**Differentiation:** current "AI 3D printers" (e.g., Creality mBox, launched Nov 9, 2026) use AI to **turn drawings into shapes**. This project uses AI to **check real-world facts before making food**.

---

## 10. Plan B and stretch goals

- If the syringe isn't working by Monday, consider asking Jeff for a few extra days
- Stretch: side camera to find the pie surface height automatically; line laser height scanning; Klipper pressure advance for cleaner frosting lines

---

## 11. Reference links

- Perplexity API docs: https://docs.perplexity.ai/docs/getting-started/overview.md
- Perplexity Decider blog: https://www.perplexity.ai/hub/blog/perplexity-decider
- Decisions API quickstart: https://docs.perplexity.ai/docs/decisions/quickstart
- Structured outputs: https://docs.perplexity.ai/docs/grounded-llm/output-control/structured-outputs
- How To Cook That DIY paste extruder: https://www.howtocookthat.net/public_html/diy-3d-paste-extruder-chocolate-printer/
- Raspberry Pi Touch Display 2 docs: https://www.raspberrypi.com/documentation/accessories/touch-display-2.html
- Chocolate 3D Printing on an Ender-3 V2 (My Tech Fun): https://www.youtube.com/watch?v=qRFqR--aaFs
- Creality mBox coverage: https://all3dp.com/4/can-kids-young-really-3d-print-without-supervision-a-look-at-the-new-creality-mbox/
