#ifndef ADS_SUPERVISED_EXAMPLE_H
#define ADS_SUPERVISED_EXAMPLE_H
/* Explicit SUPERVISED_TEST build. This example is NOT a bench approval and
 * cannot energize output. Copy for an individually reviewed bench build. */
#define ADS_MOTOR_OPERATING_MODE 1
#define ADS_POWER_FEEDBACK_INSTALLED 0
#define ADS_POWER_FEEDBACK_WIRING_VERIFIED 0
#define ADS_PHYSICAL_OUTPUT_ENABLED 0
#define ADS_SUPERVISED_TESTING_APPROVED 0
#define ADS_RELAY_SAFE_OUTPUT_VERIFIED 0
#define ADS_KILL_SWITCH_VERIFIED 0
#define ADS_COMM_LOSS_STOP_VERIFIED 0
#define ADS_INA219_CALIBRATED 0
/* Limits operator-confirmed 2026-11-11; other acceptance flags remain unresolved. */
#define ADS_BENCH_MAX_DURATION_MS 30000U
#endif
