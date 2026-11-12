# Circuit 4 LM324 diagnostic integration

Source: circuit description and multimeter measurements supplied by the operator in chat, November 2, 2026. This supersedes the earlier unspecified circuit placeholder. No physical wiring, firmware flashing or powered circuit test was performed during this implementation.

## Built asset

The versioned preset `CIRCUIT-4-LM324` uses a 5 V supply, LM324, R1/R2=10 kΩ, RV1=10 kΩ adjusted to ≈2.0 V, R3=1 kΩ, R4=4.7 kΩ, R5=1 kΩ, Q1=2N3904, LED1 and manual S1/S2 switches. The dashboard retains the existing simulated circuit and adds **Circuit diagnostics → Physical circuit capture**.

Preset topology:

```text
+5 V → R1 → TP4 → S1 → TP1 → R2 → GND
                         ├→ LM324 pin 3 (+)
                         └→ S2 → R3 → GND
+5 V → RV1 → GND; wiper TP2 → LM324 pin 2 (−)
LM324 pin 1 / TP3 → R4 → Q1 base
+5 V → R5 → LED anode; LED cathode → Q1 collector; emitter → GND
LM324 pin 4 = +5 V; pin 11 = GND
```

There are **five probe points**: TP0 supply, TP1 divider/input, TP2 reference, TP3 output and TP4 above S1. Every probe reading is relative to circuit GND. A stored topology graphic and instructions are included; it is not physical verification of wiring or switch state.

## Reference evidence

| Point | Normal (V) | S1 open (V) | S2 shunt (V) |
|---|---:|---:|---:|
| TP0 | ≈5 nominal | ≈5 expected | ≈5 expected |
| TP1 | 2.4744 | 0.000166 | 0.40643 |
| TP2 | 2.0167 | 2.01461 | 2.01425 |
| TP3 | 3.6877 | 0.003477 | 0.003451 |
| TP4 | 2.4742 | 4.9670 | 0.40644 |

TP1–TP4 are operator-reported multimeter observations, not readings acquired through STM32. Their decimal precision must not be confused with STM32 ADC resolution or calibration. The dashboard can check its rules against these supplied examples without fabricating a live capture or adding examples to hardware history. One example per condition cannot establish independent accuracy, uncertainty, or repeatability.

## Provisional diagnostic rules

First require complete finite TP0–TP4 values. Gate supply to 4.75–5.25 V and reference to 1.8–2.2 V. These are provisional engineering guard bands, not experimentally validated tolerances.

- **NORMAL_SIGNATURE:** TP1/TP4 each 2.2–2.8 V and agree within 0.15 V; TP3 HIGH at 3.0–4.3 V.
- **S1_OPEN_SIGNATURE:** TP1 −0.05–0.10 V; TP4 within 90% of supply to supply+0.10 V; TP4−TP1 at least 80% of supply; TP3 LOW at −0.05–0.10 V. Suspected region: S1/connection between TP4 and TP1, not unique proof of a switch failure.
- **S2_SHUNT_SIGNATURE:** TP1/TP4 each 0.25–0.65 V and agree within 0.15 V; TP3 LOW at −0.05–0.10 V. Suspected region: TP1-to-GND shunt path; another low-resistance path could look similar.
- Other patterns: **INCONCLUSIVE**. Supply/reference failures have distinct gate results. A missing channel yields **INSUFFICIENT_DATA**. Both fault switches active simultaneously are not separately identified. The proposed 15 kΩ R2 condition is not a trained or verified class.

Every report states the model version `circuit4-lm324-v1`, evidence/calibration limitation, predicted classification, reason and suspected region. The expected-value table compares each probe with the supplied normal reference:

`difference_V = measured − normal_reference`

`deviation_percent = 100 × (measured − normal_reference) / normal_reference`

This percentage is signed measurement deviation, not a confidence or health percentage. No trained ML model is claimed. The classifier receives only measured values, not the actual introduced fault label. Future validation ground truth must be recorded separately.

## Operator capture workflow

1. Restart the backend to load new routes/preset; refresh the dashboard. Select Physical circuit capture and Circuit 4. Existing installations need the updated source/build; uploading an older ZIP will not add these routes.
2. Inspect topology/reference values. Normal is S1 closed and S2 open. The operator chooses and maintains the physical test condition; the software does not move switches or close relays.
3. Confirm supply, RV1 and switches will remain unchanged across all five probe captures; start the session.
4. Follow TP0 → TP1 → TP2 → TP3 → TP4. Confirm physical probe placement at each step, then wait for a **new** matching STM32 reading and capture it.
5. Review measured voltages, configured normal ranges, deviations, predicted signature and uncertainty. Individual normal-range failures are expected for deliberate fault experiments; final classification uses the multi-point pattern.
6. Saved physical tests retain an immutable asset snapshot, raw captured engineering values, receipt/capture times, calibration status and result. They are separate from simulations and motor history. Incomplete tests can be resumed from the saved-test list.

The receiver must be connected. Frames older than three seconds, frames received before probe confirmation, invalid fields and mismatched asset/point/channel values are rejected. Optimistic session versions reject concurrent stale updates. Host receipt freshness does not prove device acquisition freshness; firmware framing and timing still require validation.

## Expected circuit telemetry

The new consumer accepts explicit circuit-mode JSON in the existing passive receiver. Example schema only:

```json
{"mode":"CIRCUIT","asset_id":"CIRCUIT-4-LM324","test_point_id":"TP1","test_point_voltage_V":2.4744,"valid":true}
```

Optional separate engineering channels are `circuit_supply_voltage_V`, `circuit_current_A` and `circuit_power_W`. Each frame requires the asset and point identifiers. These channels are kept separate from motor channels; INA219 supply voltage is never substituted for probe voltage. Circuit 4 classification needs probe voltage at each TP0–TP4, so INA219 #2 current is additional context rather than a prerequisite.

No ADC factor is applied to received engineering voltages. Raw ADC conversion through the 30 kΩ/10 kΩ divider must be implemented and calibrated in the acquisition firmware exactly once. No BAT54S fixed-drop or capacitor correction is added. Generic unlabeled legacy motor messages cannot identify a circuit test point and are not accepted as such.

**Remaining hardware integration:** the checked-out firmware leaves HAL ADC disabled and does not publish this circuit telemetry contract. Probe conditioning, INA219 #2 at intended 0x41, I2C routing and tagged acquisition have not been end-to-end verified. The software must not pretend the STM32 knows which removable point the operator is probing: the acquisition/test-point labeling workflow needs implementation and validation in the verified firmware or a future explicit backend mapping. No command or firmware write was added in this increment.

## Implementation and validation

New modules: `diagnostic_platform/circuit4.py`, `physical_circuits.py`, `frontend/src/PhysicalCircuit.tsx`, `Circuit4Diagram.tsx`. Existing circuit simulation and motor control protections are preserved. SQLite adds `circuit_assets` and `circuit_captures`; preset startup initialization does not overwrite an existing custom asset. The preset ID is reserved against accidental edits; create a different ID for modified circuits.

API paths:

- `/api/circuits/assets` — list/save actual circuit definitions.
- `/api/circuits/circuit4/reference-analysis` — clearly labeled supplied multimeter example analysis.
- `/api/circuits/captures` — start/list persisted capture sessions.
- `/api/circuits/captures/{id}/arm` — operator probe confirmation.
- `/api/circuits/captures/{id}/capture` — store a fresh matching reading and update analysis.

Tests cover supplied signatures, withholding unsupported classifications, normal-reference deviations, finite-data gates, asset/test-point isolation, stale/invalid/disconnected data, probe confirmation, full software capture/persistence and no motor actuation. Software validation does not establish physical diagnostic accuracy. Browser visual verification of these new pages was not completed because browser access was declined.

Observed results: 97 Python tests pass, frontend production build and ESLint pass, and `git diff --check` passes. Vite retains its bundle-size advisory. The Pi transfer ZIP has been rebuilt with this increment. Source changes remain local and uncommitted; they have not been pushed to GitHub.
