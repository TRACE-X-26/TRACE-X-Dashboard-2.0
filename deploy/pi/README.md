# Trace-X Pi touchscreen installation

Target: Raspberry Pi 5, Debian 13 or Raspberry Pi OS based on Debian 13, Hosyond 7-inch 1024×600 capacitive touchscreen in landscape. This package has been software-tested on the development Mac; installation, touch input and reboot behavior still require acceptance on the actual Pi.

## Transfer and prerequisites

Copy `Trace-X-Pi.zip` to a USB drive, then extract it to a new directory such as `/home/amirzoom8/Trace-X` on the Pi. Do not extract over a running installation or an existing database. The package includes a consistent database backup with imported recordings and the original recording ZIP when supplied. It excludes Mac Python environments, node_modules, Git credentials/configuration and IDE workspace state.

The Pi needs a graphical desktop, Chromium, Python 3 with venv/pip, Node.js 20.19+ or 22.12+ (Vite requirement), npm and curl. Check `node --version` before installation. On Debian 13, install OS packages from its package manager:

```sh
sudo apt update
sudo apt install python3-venv python3-pip nodejs npm chromium curl
```

Initial installation requires internet for Python/npm packages. The running dashboard needs no internet. Do not copy the Mac's `.venv` or node_modules to the Pi. Set the display to its native 1024×600 landscape mode using the desktop display settings. Connect HDMI for video and USB for touch according to the screen manual.

## Install locally on the Pi

Open a terminal on the Pi desktop as `amirzoom8`, enter the extracted Trace-X directory, then run:

```sh
bash deploy/pi/install.sh
```

This creates `.venv-pi`, builds React, creates a user systemd service and a dedicated Chromium autostart entry, and starts the backend. It does not use sudo, configure firmware, open serial, enable autologin or change physical motor controls. The server binds only to localhost. React, REST and WebSockets share **http://127.0.0.1:13115/**; a Vite development server is not needed on the Pi.

Open the local URL manually first. For kiosk display:

```sh
bash deploy/pi/kiosk.sh
```

The launcher waits up to one minute for the backend before opening Chromium in full-screen with a separate kiosk browser profile. Alt+F4 exits the browser. The application remains available in a normal browser window. A keyboard may still be useful for asset-name text entry and maintenance; automatic on-screen keyboard setup depends on the installed desktop.

## Automatic display after boot

The backend is enabled as a **user** service: it starts when this desktop user logs in. Most desktop sessions honor the generated `~/.config/autostart/trace-x.desktop` entry. Reboot and confirm this on the installed desktop.

If the Pi uses **labwc** and does not honor XDG autostart, append this one line to `~/.config/labwc/autostart`, using the actual installed path:

```sh
/bin/bash /home/amirzoom8/Trace-X/deploy/pi/kiosk.sh &
```

Use one browser autostart mechanism, not both. Do not overwrite existing labwc configuration. Raspberry Pi's official kiosk guide documents the labwc autostart mechanism: https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/

To boot all the way into the dashboard without entering a password, the Pi must already have desktop autologin configured or you must explicitly enable it using that OS's login settings. The installer does not weaken login security. Display blanking/sleep and on-screen keyboard settings must be checked in the actual desktop. Debian 13 alone does not identify the compositor/session.

## Modes and live hardware

Simulation is the installation default. Physical control remains disabled. Historical recordings are labeled separately from simulation and unverified hardware monitoring. The simulation score is a rule score, not a validated motor-health percentage.

Only after reviewing the flashed sensor firmware's reset/autostart behavior with motor energy disconnected, stop other serial readers and set `ADS_LIVE_SERIAL_PORT` to the verified serial path in `~/.config/trace-x/runtime.env`. Then restart the service. Prefer `/dev/serial/by-id/…`. Grant only the necessary serial permissions through your OS; do not run the whole app as root. Opening some USB serial devices can reset their controller. Live diagnosis still abstains until channel calibration, geared-motor limits/baselines and circuit test-point mappings are verified.

```sh
systemctl --user restart trace-x.service
systemctl --user status trace-x.service
journalctl --user -u trace-x.service -n 60 --no-pager
```

Re-running install preserves the existing runtime.env but regenerates the service/autostart files. It does not overwrite the existing database. For safe database copies, stop the service or use SQLite's backup API; copying only a live main database file can miss WAL transactions. Uninstall automatic backend startup with `systemctl --user disable --now trace-x.service`; disable the chosen browser autostart entry separately. Keep the application/database to preserve history.

## Presentation acceptance

- [ ] All nine pages fit horizontally at 1024×600; navigation and touch controls are reachable.
- [ ] Touch works at all four corners; ordinary controls can be selected without a mouse.
- [ ] Readings, warnings and source labels are readable at the intended viewing distance.
- [ ] CSV recordings and graphs work with Wi-Fi disconnected; no external fonts are requested.
- [ ] Three normal reboots reach the kiosk without terminal commands after the selected login policy.
- [ ] Closing/restarting the backend produces visible offline status and recovery.
- [ ] Run for the full presentation duration without memory growth, freezing or lost history.
- [ ] Hardware unplug/reconnect and sensor failures are tested under safe conditions. The passive receiver currently requires backend restart after a serial failure.
- [ ] Reference instruments verify live values; uncalibrated readings never imply verified health.
- [ ] Presenter distinguishes implemented simulations, historical experiments and physically validated behavior.

Preparation tests do not substitute for these physical checks. Do not demonstrate automatic motor operation until the STM32's independent safety protections are physically verified.
