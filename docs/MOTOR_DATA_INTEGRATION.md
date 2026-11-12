# Motor data integration and temperature removal

Temperature is excluded from motor diagnostic rules, baseline fitting/scoring features, automated-run health requirements, charts, metric cards, profile controls and multimeter channels. Original files and legacy database fields remain readable for provenance. The physical operator profile already disables temperature. No firmware output configuration was changed.

## Archive audit

The supplied trace_x_motor_data.zip and earlier motor_test_results.zip contain 134 CSV entries, representing 74 unique byte contents and 60 exact duplicate copies. All entries are accounted for. Tests 2–13 contain measurements; Test 1 has a software-only result. Separate repeated recordings remain separate. Filename load labels remain unverified labels in grams. Friction condition, motor identity and calibration are not inferred from filenames. The workbook is a secondary human-readable view with six sheets; its claimed source inventory differs from the CSV-only inventory and is not used to override original recordings.

The supplied motor_data_collector.py is a passive logger. It does not execute motor commands. Its MEAS branch has device ticks and shunt microvolts, while its generic nested JSON handling cannot establish validity of ADS measurement objects. It is not substituted for the exclusive CRC-protected backend owner.

Run the repeatable audit/import from the checkout:

```sh
python3 -m diagnostic_platform.experimental_data /path/to/trace_x_motor_data.zip /path/to/motor_test_results.zip --output data/motor_audit --database diagnostics.db
```

Outputs include canonical.json with parsed rows, quality flags, provenance and per-run statistics; run_features.csv; archive_replay.json for the existing CSV recordings screen; summary.json when stdout is redirected; and originals/ containing exact source CSV bytes under their SHA-256. Re-import uses existing database content hashes. Canonical data and original CSV bytes are delivered in the separate audit package. Summarized replay, coverage and baseline readiness are now committed in reference_data/, so a fresh clone displays historical results. The replay endpoint prefers local audited data when present; ADS_MOTOR_DATA_DIR can override its directory.

Mean, median, minimum, maximum, population standard deviation and median absolute deviation are calculated per run and per channel, separately for all recorded observations and logged running phases. Adjacent serial lines are not converted into instantaneous power. Serial-reported power stays reported. Host event markers do not establish STM32 acquisition phase. Each run remains historical reference only. There are no approved baselines or validated ML predictions in this archive. Statistical prediction intervals cannot be justified from unknown operating conditions.

## Supervised execution

The current upstream engine already supports bounded fixed-duty execution with single serial ownership, authorization, cancellation, STOP acknowledgment, heartbeat loss handling, local deadlines and durable samples/events. This change preserves the operator-approved 50% PWM, 30-second maximum, 1.5 A cutoff and 11–13 V window. The serial identity still needs completion on the Pi. No hardware was flashed or energized. Historical catalog names have been corrected; catalog membership does not authorize other procedures.

## Update the Pi

Use the Pi desktop account and preserve local edits before pulling. The existing installation is /home/amirzoom8/Trace-X.

```sh
cd /home/amirzoom8/Trace-X
systemctl --user stop trace-x.service
# Before pulling, use the installed Python to back up the configured database.
.venv-pi/bin/python - <<'PYBACKUP'
import os, sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import dotenv_values
settings=dotenv_values(Path.home()/".config/trace-x/runtime.env")
database=Path(os.getenv("ADS_DATABASE_PATH", settings.get("ADS_DATABASE_PATH") or "diagnostics.db")).resolve()
if not database.is_file():
    raise SystemExit("Configured database missing; verify its path before updating")
destination=database.with_name(database.stem+".backup-"+datetime.now().strftime("%Y%m%d-%H%M%S%f")+".db")
source=sqlite3.connect(database.as_uri()+"?mode=ro", uri=True)
target=sqlite3.connect(destination)
source.backup(target)
target.close()
source.close()
print(destination)
PYBACKUP
git pull --ff-only origin trace-x-integration-2026-10-30
.venv-pi/bin/python -m pip install -r requirements-backend.txt
(cd frontend && npm ci && npm run build)
.venv-pi/bin/python -m diagnostic_platform.experimental_data ~/Downloads/trace_x_motor_data.zip ~/Downloads/motor_test_results.zip --output data/motor_audit --database diagnostics.db
.venv-pi/bin/python -c 'from pathlib import Path; from diagnostic_platform.automated_engine import load_hardware_profile; p=load_hardware_profile(Path.home()/".config/trace-x/motor-hardware.json"); print(p["operating_mode"],p["limits"])'
systemctl --user restart trace-x.service
curl --fail http://127.0.0.1:13115/api/health
journalctl --user -u trace-x.service -n 40 --no-pager
```

The summarized historical results are available immediately after pulling and building. Import the original ZIPs when raw observations and canonical exports are needed in the local database. Review the live profile against the flashed firmware and retain per-run supervision. These commands update application software and data only.

## Reference approval and model validation

The baseline package builder consumes a manifest containing five or more full exported physical run reports in `runs`. Set each run's `known_good` only after independent confirmation. Runs need distinct identities, matching operating conditions, calibrated electrical/encoder data, valid acquisition timestamps, a completed capture and a confirmed stop. The manifest must provide positive `tolerances` and `max_std` entries for voltage, current, rpm and power in native units, chosen from repeatability evidence and requirements.

```sh
.venv-pi/bin/python -m diagnostic_platform.baseline_package verified-runs.json --output candidate-baseline.json
```

Without an `approval` object containing reviewer, evidence_id and approved_at, the output stays CANDIDATE_REQUIRES_APPROVAL. A reviewed package can be placed under `baselines[package.test_id]` in the existing hardware profile. The baseline must match the new run's full operating context exactly. This process adds assessment evidence; it does not authorize motor output or expand procedure limits. Physical results have measured comparisons and classifications; a numerical health index remains withheld pending model validation.

The optional experimental training manifest contains run_id, source, label, label_verified, label_evidence_id, measurements_verified, recording_session_id, full operating_context and numeric voltage/current/rpm/power feature values. All runs must use the same operating context and each label needs at least three recording sessions. Entire sessions are held out; scaling is fit within each training fold. Centroid validation exports confusion counts, precision, recall, F1 and false-positive/false-negative rates. Production predictions remain disabled. There are no physical model metrics for the current unlabeled archive.

```sh
.venv-pi/bin/python -m diagnostic_platform.model_training verified-labels.json --output model-validation.json
```

## Supported procedures and commissioning

The API `/api/automated/catalog` maps Tests 1–13 to procedure IDs, equipment, commands, completion checks, features, setup and limitations. Simulation covers the six original idle/fixed-PWM procedures and five additional fixed-duty observation procedures. Automated simulation series exclude procedures requiring operator setup. Physical supervised sequences are restricted to one procedure per fresh authorization.

Steady-State RPM, Voltage Stability, Power Consumption, Weight / Load Testing and Excessive Friction use the fixed 50% duty path, with a minimum five-second capture and a three-second settling window defined using STM32 acquisition timestamps. Their IDs are steady_state, voltage_stability, power_consumption, load_response and friction_response. Each stays unavailable on hardware until that individual procedure is commissioned and its ID is listed in `additional_procedures_approved` in the existing operator profile. No such approval was added by this agent. Load and friction are applied by the operator. The software records load ID, condition and optional mass in grams; it makes no torque inference.

Minimum Starting PWM remains unavailable because the supported firmware executes one fixed approved duty per run. Startup Current remains unavailable for peak conclusions because acquisition bandwidth and device event timing need validation. Historical observations for both tests are still displayed.

## Verification and physical requirements

See COMPLETION_REPORT.md for actual software build/test results and the test-by-test matrix. The code was not connected to a physical Pi/STM32 motor rig. Device identity on the Pi, actual firmware installation, encoder calibration, procedure commissioning, healthy labels and baseline approval remain physical/operator requirements. No firmware was flashed or motor energized by this update.
