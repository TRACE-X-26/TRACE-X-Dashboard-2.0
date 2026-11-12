> Superseded: use [PROTECTED_HARDWARE_INTEGRATION.md](PROTECTED_HARDWARE_INTEGRATION.md). Version 0.6.0 restores electrical protection and requires verified upstream sensing; default outputs are disabled.

> Current behavior: motor voltage/current cutoffs were removed at the operator's request. Use [BRANCH_POWER_UPDATE.md](BRANCH_POWER_UPDATE.md) for firmware 0.5.2, matching Pi profile migration, flashing and deployment. Older threshold statements below describe earlier versions.

# Motor protection configuration — November 11, 2026

Latest operator-requested change: supply window widened from 11–13 V to
**10–14 V** in firmware and Pi profiles. Current cutoff remains 1.5 A.
Existing acceptance flags were retained; this edit is configuration, not a new
independent bench verification. Firmware and Pi settings must both be updated;
a running Pi or flashed board is not changed by editing this repository.

Subsequent operator confirmation also enabled the separate supervised operator
profile. See [current build instructions](SUPERVISED_OPERATOR_BUILD.md).
Statements below about remaining disabled gates describe the earlier cutoff-only
update; the generic disabled example still retains those gates.

Current cutoff: **1.5 A** (1500 mA). Supply acceptance window: **10.0–14.0 V**.
Current at or above the cutoff fails readiness; voltage outside the window fails
readiness. Existing fault shutdown uses motor INA219 readings only.

The operator previously reported the 1.5 A / 11–13 V settings verified on
2026-11-11. The later request widens the voltage window to 10–14 V and retains
the existing protection-limits acceptance flag. This records operator confirmation, not an
independent bench check by the coding agent or a manufacturer rating.

The proposed current setting was selected above the historical maximum logged
reading of 1.133 A. Those approximately one-second recordings do not establish
instantaneous startup peaks, allowable sustained current, or safe stall duration.
No new startup grace period or overload delay has been introduced.

This supersedes the earlier provisional 2.5 A setting and its unverified flag.
Other approvals remain independent: relay reset behavior, physical cutoff,
communication-loss shutdown, measurement calibration and supervised-mode
approval are unchanged. Physical output permission remains disabled; these
changes alone do not authorize a motor start. No hardware was flashed or run.

Latest range update: 202 tests passed; default-disabled and supervised-enabled
ARM builds passed. Neither the running Pi profile nor the flashed board was
changed by this local edit.
