# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Set up

```bash
git clone https://github.com/debbieyuen/pumpkinpi-printer.git && cd pumpkinpi-printer
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q     # offline: mocked API, no key, no printer, no camera
```

The touchscreen app also runs in demo mode with no server: open `ui/index.html` in a browser.

## Rules

- **Never commit secrets.** Keys go in `.env` (git-ignored). `guests.json`, `machine.json`,
  `cards.json` and `camera_cal.json` are also git-ignored. Use made-up names in examples and tests.
- **Keep the safety rules.** Food mode never homes, never probes and never turns on heaters.
  STOP always sends `M112`. A person always presses Start. Add a test when you touch
  `pumpkinpi/printer.py`, `pumpkinpi/toolpath.py` or `pumpkinpi/allergen_check.py`.
- **Allergen logic never guesses green.** If evidence is missing or unclear, the answer is
  "check the label". Cite a source for any allergen or food-safety rule you add.
- **Perplexity APIs:** use the Agent, Search and Decisions APIs
  ([docs](https://docs.perplexity.ai)). Don't add Sonar chat completions.
- Don't commit sliced G-code; attach it to a release instead.

## Pull requests

Keep them small, describe what you tested (unit tests, dry run, real printer), and include
a photo or screen recording for UI or hardware changes.
