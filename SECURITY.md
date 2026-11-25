# Security and safety reports

Please report security problems **privately** through GitHub:
**Security → Report a vulnerability** on this repo. Don't open a public issue.

Report privately if you find:

- a way to leak the `PERPLEXITY_API_KEY` or other secrets,
- a way for the web server (bound to `127.0.0.1:8000`) to be reached or controlled from the network,
- a way past the food-mode lockout (for example, sending `G28`, `G29`, `G30` or heater commands
  while food mode is on), or a STOP that doesn't send `M112`,
- an allergen check that shows green when the evidence shows an allergen.

Safety bugs about the printer or the allergen check matter as much as security bugs here.
