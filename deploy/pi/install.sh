#!/usr/bin/env bash
# Run as the desktop user on the Pi, never with sudo.
set -euo pipefail
if [[ $(uname -s) != Linux || $(id -u) == 0 ]]; then
  echo 'Run as your normal desktop user on the Raspberry Pi (not sudo).' >&2
  exit 1
fi
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"
for dependency in python3 npm curl systemctl systemd-analyze journalctl; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  echo 'Install Chromium before continuing.' >&2
  exit 1
fi
python3 -m venv .venv-pi
.venv-pi/bin/python -m pip install -r requirements-backend.txt
(cd frontend && npm ci && npm run build)
config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
export TRACE_X_PROJECT_ROOT="$project_root" TRACE_X_CONFIG_ROOT="$config_root"
python3 deploy/pi/configure.py
systemd-analyze --user verify "$config_root/systemd/user/trace-x.service"
systemctl --user daemon-reload
systemctl --user enable trace-x.service
systemctl --user restart trace-x.service
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:13115/api/health >/dev/null; then break; fi
  if [[ $attempt == 30 ]]; then
    journalctl --user -u trace-x.service -n 40 --no-pager
    exit 1
  fi
  sleep 1
done
echo 'Backend installed at http://127.0.0.1:13115/'
echo 'Logs: journalctl --user -u trace-x.service -f'
echo 'Serial access: inspect ls -l /dev/serial/by-id/ and group membership; do not run the app as root.'
echo 'Launch the touchscreen with: bash deploy/pi/kiosk.sh'
echo 'See deploy/pi/README.md to enable browser autostart for your desktop.'
