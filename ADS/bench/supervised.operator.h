#ifndef ADS_SUPERVISED_OPERATOR_H
#define ADS_SUPERVISED_OPERATOR_H
/* Operator confirmed relay/reset, physical cutoff, communication-loss stop,
 * and motor electrical measurement checks on 2026-11-11, then authorized this
 * supervised build. These are operator attestations, not measurements made
 * by the coding agent. The generic example and default build stay disabled. */
#include "supervised.example.h"
#undef ADS_PHYSICAL_OUTPUT_ENABLED
#define ADS_PHYSICAL_OUTPUT_ENABLED 1
#undef ADS_SUPERVISED_TESTING_APPROVED
#define ADS_SUPERVISED_TESTING_APPROVED 1
#undef ADS_RELAY_SAFE_OUTPUT_VERIFIED
#define ADS_RELAY_SAFE_OUTPUT_VERIFIED 1
#undef ADS_KILL_SWITCH_VERIFIED
#define ADS_KILL_SWITCH_VERIFIED 1
#undef ADS_COMM_LOSS_STOP_VERIFIED
#define ADS_COMM_LOSS_STOP_VERIFIED 1
#undef ADS_INA219_CALIBRATED
#define ADS_INA219_CALIBRATED 1
/* Operator confirmed D5/PB4 -> IN2, COM-LOW: LOW on / HIGH off, common cutoff.
 * Circuit power is a bounded manual supply operation, not an automatic
 * circuit diagnostic or a calibrated health assessment. */
#define ADS_CIRCUIT_OUTPUT_ENABLED 1
#define ADS_CIRCUIT_RELAY_VERIFIED 1
/* No download or real hardware test was performed by the coding agent.
 * Live validity, voltage/current checks, heartbeat, ARM, operator confirmation,
 * fixed PWM, bounded deadline and fault shutdown remain enforced. */
#endif
