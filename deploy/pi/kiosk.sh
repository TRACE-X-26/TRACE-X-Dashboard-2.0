#!/usr/bin/env bash
set -euo pipefail
url='http://127.0.0.1:13115/'
for attempt in {1..60}; do
  if curl --silent --fail "${url}api/health" >/dev/null && curl --silent --fail "$url" >/dev/null; then
    break
  fi
  sleep 1
done
browser=$(command -v chromium || command -v chromium-browser || true)
if [[ -z "$browser" ]]; then
  echo 'Chromium is missing. Install it using the Pi package manager.' >&2
  exit 1
fi
profile="${XDG_CONFIG_HOME:-$HOME/.config}/trace-x/chromium"
exec "$browser" --user-data-dir="$profile" --kiosk --no-first-run --noerrdialogs "$url"
