# Menu cards

Besides pies, PumpkinPi can print a little menu card for each guest with the stock hot end. Each card lists the
dishes and the allergens Perplexity found in the exact products that go into them. A `?` means "check the label."
Nothing ever gets printed as safe.

The menu, the products and the card layout live in `cards.json`. If you don't have one yet, it uses
`examples/cards.example.json`.

The syringe stays mounted while cards print, so make sure its tip sits above the nozzle. Only paper or the bare bed
goes on the printer here, never food.

## Print a card

You'd normally do this from the touchscreen. From the command line:

```bash
.venv/bin/python -m pumpkinpi.cards --check                    # look up every product (uses the API)
.venv/bin/python -m pumpkinpi.cards --guest Alex --gcode > card.gcode
```

The touchscreen saves the file to the printer's microSD card, and you start it from the printer's own screen. The
Ender-3 V3 SE only sees files in the top folder of the card, and it's picky about names, so the server handles that.

## Paper or bare bed

Set the temperatures for whatever filament is loaded. PETG at PLA temperatures barely melts and won't stick.

- `python3 scripts/paper_6x9.py`: 6 x 9 in, 140 lb watercolor paper. Bed off, cool nozzle, fan at 100 %, and tape
  down all four edges.
- `python3 scripts/measure_paper.py`: uses the CR Touch to measure how thick the paper is, so the prime line next to
  it still reaches the bed. Stop the server first (`sudo systemctl stop pumpkinpi`) and only have the taped card on
  the bed.
- `python3 scripts/bare_bed.py`: prints right on the bed with no paper. PETG by default (235 °C nozzle, 75 °C bed).
  Use `python3 scripts/bare_bed.py pla` if you've got PLA loaded.

Each script just rewrites your settings (`machine.json`, and the card size in `cards.json` for paper), so you can switch back and forth.
