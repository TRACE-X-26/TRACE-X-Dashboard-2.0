# TRACE-X Dashboard 2.0 — operator interface

This repository is an independent copy of the TRACE-X implementation, now with a simplified Raspberry Pi touchscreen entry point.

## Main screen
- Motor or Circuit branch selection (selecting does not power either branch).
- Motor: automated read-only hardware readiness checks, status/error reason, Start Motor, Stop Motor and Emergency Stop, fixed firmware-reported PWM and at most 30-second duration.
- Real motor test measurements: voltage, current, input power and RPM as the backend provides them; no fabricated readings when idle.
- Circuit: supervised circuit power On/Off and live circuit INA219 metrics. It is **not** automatic circuit fault diagnosis.
- Pi/backend availability visible in the header.

The legacy simulator, dashboard charts, profiles and advanced diagnostics remain in the source tree but are not in the operator navigation. Backend API authorization, firmware safety checks and independent physical cutoff are unchanged. No changes were made to the STM32 firmware in this UI redesign.

## Raspberry Pi deployment

The separate repo must be cloned/build on the Pi and its systemd service must be confirmed to use the matching checkout. Avoid overwriting the original service or private configs just to preview the new frontend.

```bash
cd ~
git clone https://github.com/TRACE-X-26/TRACE-X-Dashboard-2.0.git
cd TRACE-X-Dashboard-2.0/frontend
npm ci
npm run build
```

Check service deployment before replacing the served frontend:

```bash
systemctl --user show trace-x.service -p WorkingDirectory
```

Do not infer that a GitHub update has installed or tested hardware on the Pi. The app's physical START button remains disabled until the backend confirms a commissioned matching profile and fresh successful preflight.
