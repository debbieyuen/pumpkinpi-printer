#!/usr/bin/env bash
# Opens the PumpkinPi UI full-screen once the local server answers. Started from ~/.config/labwc/autostart.
URL="http://127.0.0.1:8000"
for i in $(seq 1 60); do curl -fs "$URL/api/status" >/dev/null && break; sleep 1; done
BROWSER="$(command -v chromium || command -v chromium-browser)"
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --no-first-run \
  --ozone-platform=wayland --enable-features=OverlayScrollbar --start-maximized \
  --disable-pinch --overscroll-history-navigation=0 "$URL"
