# Pi touchscreen preparation results

October 30, 2026. Target: Pi 5, Debian 13 desktop, 7-inch Hosyond 1024×600 capacitive touchscreen, landscape.

## Completed on the development Mac

- Retained all nine dashboard pages, simulation controls, histories and imported recordings.
- Added 1024×600 layout with 44-pixel minimum touch controls/navigation, compact sidebar, larger readings and visible source labels.
- Browser-checked all nine pages at an exact 1024×600 viewport. No page-level horizontal overflow was observed. Overview's readiness and recent tests fit in the viewport. Longer forms/history tables remain vertically scrollable.
- Removed external Google Fonts dependency; system fonts support offline rendering.
- Replaced hardcoded overview readiness with backend/receiver state and labeled the legacy score as a simulation rule score.
- Added browser live-stream reconnection after backend interruption; physical serial reconnect still requires service restart.
- Added production static hosting after API/WebSocket routes, allowing one localhost URL without Vite.
- Prepared per-user systemd backend service, opt-in serial environment file, Chromium kiosk launcher, desktop/labwc startup instructions, and rollback/acceptance checklist.
- Prepared portable ZIP generation with a consistent SQLite backup and original recording archive. Mac virtual environments, node_modules, IDE workspace state, environment secrets and Git internals are excluded.

Validation: 75 Python tests pass; frontend build and lint pass; shell syntax and `git diff --check` pass. A full production-app integration check served the built index, health API and live WebSocket together using a temporary database and disabled serial. A WAL-mode database packaging test confirmed backup contents. Vite reports a bundle-size advisory above 500 kB.

## Still required on the Pi

The package has not been installed on the Pi. Physical touch accuracy, viewing-distance readability, compositor-specific autostart, desktop login policy, display blanking, three-reboot recovery and presentation-duration endurance must pass the checklist in `deploy/pi/README.md`.

No firmware was changed or flashed and no motor was activated. Physical sensor acquisition, calibrated motor health and live circuit diagnosis are not validated by this preparation. UI presentation readiness must not be reported as verified diagnostic accuracy. Source changes are currently uncommitted; the transferable ZIP is a snapshot, not a replacement for repository version history.
