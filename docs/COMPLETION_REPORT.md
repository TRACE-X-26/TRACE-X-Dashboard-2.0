# Trace X completion and verification report

Date November 11, 2026.

## Delivered software

The interrupted motor-data work has been resumed against upstream d150534 and completed for the supported, evidence-gated software scope. The current code includes an idempotent archive audit/import, per-run descriptive statistics, provisional reference exports, explicit baseline approval, matched physical-run comparisons, experimental grouped classifier validation, the complete experiment catalog, guided observation workflows, condition recording, durable history and export, and the existing supervised CRC32 motor command path.

Temperature is removed from the health rules, required features, scoring and visible measurement channels. Original raw archives and legacy storage fields remain provenance records.

## Source coverage

Both available original ZIPs were audited. The separately named motor_test_results(1).zip was not supplied in Downloads; the earlier motor_test_results.zip was included. The workbook was inspected across all six sheets. Its inventory includes repeated/path variants and secondary formatting, so it does not replace the original hash-based CSV audit. The passive collector source was inspected without execution.

134 CSV archive entries resolve to 74 distinct byte contents, with 60 duplicate copies and zero rejected CSVs. Original bytes are retained under their hashes. Independent repeated runs are preserved when contents differ; identical empty/status-only files retain all source aliases. Equal sample values do not turn one recording into multiple independent experiments.

| Test | Unique CSV contents | With extracted measurement rows |
| --- | --- | --- |
| 1 · Safe Idle | 1 | 0 |
| 2 · 10% PWM | 17 | 3 |
| 3 · 25% PWM | 13 | 13 |
| 4 · 50% PWM | 6 | 6 |
| 5 · 75% PWM | 2 | 2 |
| 6 · 100% PWM | 3 | 3 |
| 7 · Minimum Starting PWM | 6 | 6 |
| 8 · Steady-State RPM | 4 | 4 |
| 9 · Voltage Stability | 2 | 2 |
| 10 · Startup Current | 2 | 2 |
| 11 · Power Consumption | 1 | 1 |
| 12 · Weight / Load Testing | 8 | 8 |
| 13 · Excessive Friction | 9 | 9 |

The committed reference_data package makes the processed historical summaries available from a fresh GitHub clone. The full canonical JSON, feature CSV, provisional references, assessment-exclusion flags and original CSV bytes are delivered in Trace-X-Motor-Audit.zip. Histories in the SQLite database are preserved by the existing content-hash import path. Raw-message readings are parsed even when numeric CSV columns are blank. Adjacent lines are never multiplied into instantaneous power. Reported power remains reported. Unmarked or stop-only captures have descriptive observations, with the missing start reported.

## Baselines and diagnostic conclusions

Current archive approval count is zero. Candidate exports contain descriptive statistics and explicit missing-context/calibration reasons. There are no fabricated healthy labels or approved operating envelopes. The review workflow requires at least five independently confirmed physical captures, complete matching context, acquisition validity, calibrated electrical and encoder readings, a confirmed stop, and supplied repeatability/stability criteria. Reviewer identity, approval evidence and date are necessary for promotion.

The production algorithm provides observed values, reference bands, deviations, stability criteria, supporting observations, ambiguous possible causes and follow-up tests. It abstains for missing or conflicting device timestamps, unverified RPM, unmatched conditions, incomplete capture and absent approved baseline. Electrical/RPM observations remain visible while health assessment abstains. No physical numerical health index or remaining-life probability is claimed.

The experimental training pipeline requires verified physical labels and measurements, full matched context and at least three recording sessions per class. It uses session-held-out validation with fold-local scaling. No trained physical classifier, confusion matrix or claimed physical accuracy can be produced from this archive's unverified labels. Production predictions stay disabled. Synthetic unit fixtures exercise the pipeline only.

## Test execution matrix

| Test | Software | Physical execution |
| --- | --- | --- |
| 1 Safe Idle | Implemented and simulated | Commissioning/prechecks required; zero duty only |
| 2 10% PWM | Implemented and simulated | Blocked by current 50% profile |
| 3 25% PWM | Implemented and simulated | Blocked by current 50% profile |
| 4 50% PWM | Implemented and simulated | Eligible only after configured identity, live prechecks and fresh operator confirmation |
| 5 75% PWM | Implemented and simulated | Blocked by current 50% profile |
| 6 100% PWM | Implemented and simulated | Blocked by current 50% profile |
| 7 Minimum Starting PWM | Catalog and historical analysis | Unavailable; approved step-from-rest protocol missing |
| 8 Steady-State RPM | Fixed-duty observation and device-timed settled window | Individual procedure approval required |
| 9 Voltage Stability | Fixed-duty observation and per-run variability | Individual procedure approval required |
| 10 Startup Current | Catalog and historical observations | Peak acquisition unavailable; cadence/start alignment needs commissioning |
| 11 Power Consumption | Fixed-duty observation and same-sample branch power | Individual procedure approval required |
| 12 Weight / Load | Guided fixed-duty observation, condition/mass recording | Operator applies load; individual procedure approval required |
| 13 Excessive Friction | Guided fixed-duty observation and condition recording | Operator applies condition; individual procedure approval required |

The five additional observation workflows use a three-second settling interval and at least five seconds of acquisition. These are explicit procedure settings that require physical validation. Additional hardware approvals were not added automatically. A supervised run contains one procedure per fresh authorization. The physical limits remain 50% PWM, 30 seconds maximum, 1.5 A cutoff and 11–13 V, as recorded in the existing operator profile. No autonomous mechanical actuator or torque model is claimed.

## Verification performed

- Python/API, host C firmware and integration suite passed 188 tests.
- Targeted baseline-package tests passed after the final stability gate was added.
- TypeScript compilation, Vite production build and ESLint passed. Vite reports the existing bundle-size advisory above 500 kB.
- The actual ARM target compiled with the supervised operator profile using the installed STM32CubeIDE ARM GCC toolchain. ELF text/data/BSS sizes were 30048/92/19532 bytes.
- Database backup was exercised against a temporary WAL-mode SQLite fixture and retained committed rows.
- The live local application was opened in the browser. Archived Test 12 readings, the new test choices, temperature-free diagnostic fields and existing page structure were visually inspected.
- CSS and navigation structure were not redesigned. The duration control now shows seconds for automated procedures. Native prompts collect physical conditions. Numeric comparisons render inside existing results/history panels.
- A full pixel comparison against an original screenshot and actual 1024×600 Pi touchscreen acceptance remain unverified.

## Physical/operator requirements

No physical motor test was performed by this agent, no board was flashed, and the Pi installation was not remotely updated. The Pi operator must install the published software, configure the real ST-LINK identity, verify the flashed firmware/profile agreement, complete encoder calibration, commission additional procedures and approve known-good reference captures. The existing hardware attestations remain operator reports.

These are commissioning and evidence requirements. Tests 7 and 10 remain explicitly unavailable, as the request requires when the necessary hardware/procedure evidence is absent. Deployment commands are in MOTOR_DATA_INTEGRATION.md.
