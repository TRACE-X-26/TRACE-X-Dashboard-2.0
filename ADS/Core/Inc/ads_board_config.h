#ifndef ADS_BOARD_CONFIG_H
#define ADS_BOARD_CONFIG_H
#if defined(ADS_USE_PROTECTED_PROFILE) && ADS_USE_PROTECTED_PROFILE
#include "../../bench/protected.example.h"
#endif
#if defined(ADS_USE_OPERATOR_PROFILE) && ADS_USE_OPERATOR_PROFILE
/* CubeIDE Debug/Release explicitly select the operator-confirmed profile.
 * Makefile defaults omit this selector and remain output-disabled. */
#include "../../bench/supervised.operator.h"
#endif
/* Confirmed wiring and dual INA219 addresses; provisional encoder scaling.
 * Essential unresolved output protection gates remain OFF.
 * Define overrides only in a separately reviewed, identified bench build. */
#ifndef ADS_PHYSICAL_OUTPUT_ENABLED
#define ADS_PHYSICAL_OUTPUT_ENABLED 0
#endif
#ifndef ADS_CIRCUIT_OUTPUT_ENABLED
#define ADS_CIRCUIT_OUTPUT_ENABLED 0
#endif
#ifndef ADS_CIRCUIT_RELAY_VERIFIED
#define ADS_CIRCUIT_RELAY_VERIFIED 0
#endif
/* S2 COM-LOW matches the operator's current circuit relay jumper. */
#ifndef ADS_CIRCUIT_RELAY_ACTIVE_LEVEL
#define ADS_CIRCUIT_RELAY_ACTIVE_LEVEL 0
#endif
#define ADS_CIRCUIT_RELAY_INACTIVE_LEVEL (1 - ADS_CIRCUIT_RELAY_ACTIVE_LEVEL)
#if ADS_CIRCUIT_RELAY_ACTIVE_LEVEL != 0 && ADS_CIRCUIT_RELAY_ACTIVE_LEVEL != 1
#error "Circuit relay active level must be 0 or 1"
#endif
#ifndef ADS_MOTOR_WIRING_VERIFIED
#define ADS_MOTOR_WIRING_VERIFIED 1
#endif
#ifndef ADS_KILL_SWITCH_VERIFIED
#define ADS_KILL_SWITCH_VERIFIED 0
#endif
#ifndef ADS_COMM_LOSS_STOP_VERIFIED
#define ADS_COMM_LOSS_STOP_VERIFIED 0
#endif
#ifndef ADS_BENCH_PWM_PERCENT
#define ADS_BENCH_PWM_PERCENT 50U
#endif
#ifndef ADS_BENCH_MAX_DURATION_MS
#define ADS_BENCH_MAX_DURATION_MS 30000U
#endif
#ifndef ADS_FORWARD_GPIO_LEVEL
#define ADS_FORWARD_GPIO_LEVEL 0
#endif
#ifndef ADS_SENSOR_WIRING_VERIFIED
#define ADS_SENSOR_WIRING_VERIFIED 1
#endif
#ifndef ADS_INA219_CALIBRATED
#define ADS_INA219_CALIBRATED 0
#endif
#ifndef ADS_INA219_SHUNT_MOHMS
#define ADS_INA219_SHUNT_MOHMS 100U
#endif
#ifndef ADS_ENCODER_CALIBRATED
#define ADS_ENCODER_CALIBRATED 0
#endif
/* Rising edges on A per encoder-shaft revolution; NOT quadrature x4 CPR. */
#ifndef ADS_ENCODER_A_COUNTS_PER_REV
#define ADS_ENCODER_A_COUNTS_PER_REV 11U
#endif
/* Encoder revolutions per reported motor/output-shaft revolution. */
#ifndef ADS_ENCODER_GEAR_NUM
#define ADS_ENCODER_GEAR_NUM 34U
#endif
#ifndef ADS_ENCODER_GEAR_DEN
#define ADS_ENCODER_GEAR_DEN 1U
#endif
#ifndef ADS_ENCODER_FORWARD_SIGN
#define ADS_ENCODER_FORWARD_SIGN 1
#endif
#ifndef ADS_TEMPERATURE_ENABLED
#define ADS_TEMPERATURE_ENABLED 0
#endif
#ifndef ADS_TEMPERATURE_CALIBRATED
#define ADS_TEMPERATURE_CALIBRATED 0
#endif
/* Required runtime cutoffs must be supplied by bench profile, not invented. */
#ifndef ADS_MOTOR_INA219_ADDRESS
#define ADS_MOTOR_INA219_ADDRESS 0x40U
#endif
#ifndef ADS_CIRCUIT_INA219_ADDRESS
#define ADS_CIRCUIT_INA219_ADDRESS 0x41U
#endif
#ifndef ADS_CIRCUIT_INA219_SHUNT_MOHMS
#define ADS_CIRCUIT_INA219_SHUNT_MOHMS 100U
#endif
#ifndef ADS_CIRCUIT_INA219_CALIBRATED
#define ADS_CIRCUIT_INA219_CALIBRATED 0
#endif
#if ADS_MOTOR_INA219_ADDRESS != 0x40U || ADS_CIRCUIT_INA219_ADDRESS != 0x41U
#error "TRACE-X INA219 motor/circuit addresses must remain 0x40/0x41"
#endif
#if ADS_CIRCUIT_INA219_SHUNT_MOHMS == 0
#error "Circuit INA219 shunt must be positive"
#endif
#ifndef ADS_MOTOR_MAX_TEMPERATURE_MC
#define ADS_MOTOR_MAX_TEMPERATURE_MC 0
#endif
/* Explicit operating mode: no automatic fallback from NORMAL to supervision. */
#define ADS_MODE_NORMAL 0
#define ADS_MODE_SUPERVISED_TEST 1
#ifndef ADS_MOTOR_OPERATING_MODE
#define ADS_MOTOR_OPERATING_MODE ADS_MODE_NORMAL
#endif
#ifndef ADS_SUPERVISED_TESTING_APPROVED
#define ADS_SUPERVISED_TESTING_APPROVED 0
#endif
/* Protected motor operation. These are limits, not proof of commissioning. */
#define ADS_ELECTRICAL_LIMITS_ENABLED 1
#ifndef ADS_MOTOR_MIN_VOLTAGE_MV
#define ADS_MOTOR_MIN_VOLTAGE_MV 10000U
#endif
#ifndef ADS_MOTOR_MAX_VOLTAGE_MV
#define ADS_MOTOR_MAX_VOLTAGE_MV 14000U
#endif
#ifndef ADS_MOTOR_MAX_CURRENT_MA
#define ADS_MOTOR_MAX_CURRENT_MA 1500U
#endif
#ifndef ADS_PROTECTION_LIMITS_VERIFIED
#define ADS_PROTECTION_LIMITS_VERIFIED 0
#endif
#define ADS_POWER_CHECK_TIMEOUT_MS 1500U
#define ADS_POWER_CHECK_SETTLE_MS 50U
#if ADS_MOTOR_MIN_VOLTAGE_MV == 0 || ADS_MOTOR_MAX_VOLTAGE_MV <= ADS_MOTOR_MIN_VOLTAGE_MV || ADS_MOTOR_MAX_CURRENT_MA == 0
#error "Valid positive motor electrical protection limits required"
#endif
#ifndef ADS_POWER_FEEDBACK_INSTALLED
#define ADS_POWER_FEEDBACK_INSTALLED 0
#endif
#ifndef ADS_POWER_FEEDBACK_WIRING_VERIFIED
#define ADS_POWER_FEEDBACK_WIRING_VERIFIED 0
#endif
#if ADS_MOTOR_OPERATING_MODE != ADS_MODE_NORMAL && ADS_MOTOR_OPERATING_MODE != ADS_MODE_SUPERVISED_TEST
#error "Invalid motor operating mode"
#endif
#if ADS_POWER_FEEDBACK_WIRING_VERIFIED && !ADS_POWER_FEEDBACK_INSTALLED
#error "Feedback verification requires an installed feedback connection"
#endif
#if (ADS_SUPERVISED_TESTING_APPROVED != 0 && ADS_SUPERVISED_TESTING_APPROVED != 1) || \
    (ADS_POWER_FEEDBACK_INSTALLED != 0 && ADS_POWER_FEEDBACK_INSTALLED != 1) || \
    (ADS_POWER_FEEDBACK_WIRING_VERIFIED != 0 && ADS_POWER_FEEDBACK_WIRING_VERIFIED != 1)
#error "Mode acceptance and feedback flags must be boolean 0 or 1"
#endif
#define ADS_MODE_ACCEPTED (ADS_MOTOR_OPERATING_MODE == ADS_MODE_NORMAL || ADS_SUPERVISED_TESTING_APPROVED)
#define ADS_BOARD_ACCEPTED (ADS_PHYSICAL_OUTPUT_ENABLED && ADS_MODE_ACCEPTED && ADS_PROTECTION_LIMITS_VERIFIED && ADS_MOTOR_WIRING_VERIFIED && \
 ADS_KILL_SWITCH_VERIFIED && ADS_COMM_LOSS_STOP_VERIFIED && ADS_MOTOR_RELAY_VERIFIED && \
 ADS_SENSOR_WIRING_VERIFIED && ADS_INA219_CALIBRATED && \
 (!ADS_TEMPERATURE_ENABLED || ADS_TEMPERATURE_CALIBRATED) && ADS_BENCH_PWM_PERCENT > 0 && ADS_BENCH_PWM_PERCENT <= 100 && \
 ADS_BENCH_MAX_DURATION_MS > 0 && ADS_BENCH_MAX_DURATION_MS <= 30000 && \
 (ADS_FORWARD_GPIO_LEVEL == 0 || ADS_FORWARD_GPIO_LEVEL == 1) && \
 (!ADS_TEMPERATURE_ENABLED || ADS_MOTOR_MAX_TEMPERATURE_MC > 0))
#if ADS_INA219_SHUNT_MOHMS == 0
#error "INA219 shunt must be positive"
#endif
#if ADS_ENCODER_CALIBRATED && (!ADS_ENCODER_A_COUNTS_PER_REV || !ADS_ENCODER_GEAR_NUM || !ADS_ENCODER_GEAR_DEN)
#error "Encoder calibration requires counts and gear relationship"
#endif
#if ADS_ENCODER_FORWARD_SIGN != 1 && ADS_ENCODER_FORWARD_SIGN != -1
#error "Encoder sign must be +1 or -1"
#endif
#endif
