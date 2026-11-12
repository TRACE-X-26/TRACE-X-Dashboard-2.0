# Trace-X integration publication

Target repository: https://github.com/TRACE-X-26/Dashboard

Development branch: `trace-x-integration-2026-10-30`

Commit message: `Trace-X: STM32 safety, sensor integration, Pi and dashboard updates`

The target had no Git refs during the pre-push inspection. The development branch
retains the three original local commits; no main-branch merge, history rewrite
or force push is required. The previous repository remote is preserved as
`previous-origin`; `origin` points to TRACE-X-26/Dashboard.

## Raspberry Pi retrieval

From the intended parent directory on the Pi, use a new destination directory:

```sh
git clone --branch trace-x-integration-2026-10-30 --single-branch https://github.com/TRACE-X-26/Dashboard.git Trace-X
```

Do not clone over an existing installation or experiment directory. If the
repository is private, use your authorized GitHub credentials without embedding
credentials in the URL. After retrieval, follow `deploy/pi/README.md` for setup.
Cloning does not install dependencies, open serial, flash firmware or activate
hardware. Simulation is the default and all physical motor commands stay locked.

## Source included

- React/TypeScript dashboard, touchscreen layout and live/history consumers.
- FastAPI backend, storage, historical import, simulation and diagnostics.
- Existing ADS CubeIDE project, HAL/CMSIS dependencies, linker/startup files,
  ADS v1 protocol, motor relay configuration and STM32-local watchdog.
- Raspberry Pi measurement collector and exclusive CSV recorder.
- Automated Python/C tests, HAL test double, dependency requirements and lockfile.
- Pi deployment scripts, setup guides and motor-relay bench procedure.

The GitHub branch's file tree is the authoritative uploaded-file list. Only the
named development branch is pushed; Codex checkpoint refs, local application
bundles and ignored files are not part of the publication.

## Intentionally local

Ignore rules exclude actual `.env` configurations, credentials, virtual
environments, caches, logs, IDE workspace state, generated build output,
firmware binaries, application/transfer bundles, SQLite databases and journals,
raw CSV/TSV recordings, experiment directories and archives. The detailed
`docs/TRACE_X_DATA_INVENTORY.json` and `docs/TRACE_X_RECORDING_AUDIT.md` are also
excluded because they contain private experiment-derived information. They are
preserved locally. `.env.example` contains safe sample settings and is included.

A fresh clone contains source and tests, not the Mac's populated database or
private recordings. Historical data must be transferred/imported separately
under explicit approval; source publication does not approve data publication.

## Verification scope

Run `.venv/bin/python -m unittest discover -s tests -q` from the source root
(after creating the virtual environment and installing backend requirements).
The current suite contains 85 tests, including startup/reset defaults, relay
polarity gates, PWM shutdown, communication timeout, malformed frames, tick
wraparound, fault recovery, collector persistence and dashboard interfaces.
Host tests do not establish physical relay operation or motor supply isolation.
No flash, powered motor test or motor-control unlock is part of publication.
