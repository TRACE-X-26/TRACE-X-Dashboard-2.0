#ifndef ADS_MOTOR_H
#define ADS_MOTOR_H
#include <stdint.h>
#include "ads_board_config.h"

/* Operator selected COM-LOW on S1: PB5 LOW energizes, HIGH releases.
 * GPIO command levels are not relay contact or reset-time feedback. */
#define ADS_RELAY_NO_COM_DESIGN_CONFIRMED 1
#ifndef ADS_RELAY_POWER_PATH_VERIFIED
#define ADS_RELAY_POWER_PATH_VERIFIED 1
#endif
#ifndef ADS_RELAY_POLARITY_VERIFIED
#define ADS_RELAY_POLARITY_VERIFIED 1
#endif
#ifndef ADS_RELAY_SAFE_OUTPUT_VERIFIED
#define ADS_RELAY_SAFE_OUTPUT_VERIFIED 0
#endif
#ifndef ADS_RELAY_ACTIVE_LEVEL
#define ADS_RELAY_ACTIVE_LEVEL 0
#endif
#ifndef ADS_RELAY_INACTIVE_LEVEL
#define ADS_RELAY_INACTIVE_LEVEL (ADS_RELAY_ACTIVE_LEVEL == -1 ? -1 : 1 - ADS_RELAY_ACTIVE_LEVEL)
#endif
/* Preserve the earlier board-configuration name; it must agree with inactive. */
#ifndef ADS_RELAY_DISCONNECT_LEVEL
#define ADS_RELAY_DISCONNECT_LEVEL ADS_RELAY_INACTIVE_LEVEL
#endif
#if (ADS_RELAY_POWER_PATH_VERIFIED != 0 && ADS_RELAY_POWER_PATH_VERIFIED != 1) || \
    (ADS_RELAY_POLARITY_VERIFIED != 0 && ADS_RELAY_POLARITY_VERIFIED != 1) || \
    (ADS_RELAY_SAFE_OUTPUT_VERIFIED != 0 && ADS_RELAY_SAFE_OUTPUT_VERIFIED != 1)
#error "Relay verification flags must be 0 or 1"
#endif
#if ADS_RELAY_POWER_PATH_VERIFIED && ADS_RELAY_DISCONNECT_LEVEL != 0 && ADS_RELAY_DISCONNECT_LEVEL != 1
#error "A verified design requires an explicit relay disconnect level (0 or 1)"
#endif
#if ADS_RELAY_POLARITY_VERIFIED && \
    ((ADS_RELAY_ACTIVE_LEVEL != 0 && ADS_RELAY_ACTIVE_LEVEL != 1) || \
     ADS_RELAY_INACTIVE_LEVEL != 1 - ADS_RELAY_ACTIVE_LEVEL)
#error "Verified relay polarity requires opposite active/inactive binary levels"
#endif
#if ADS_RELAY_DISCONNECT_LEVEL != ADS_RELAY_INACTIVE_LEVEL
#error "Relay disconnect level must match inactive level"
#endif
#define ADS_MOTOR_RELAY_VERIFIED (ADS_RELAY_POWER_PATH_VERIFIED && \
    ADS_RELAY_POLARITY_VERIFIED && ADS_RELAY_SAFE_OUTPUT_VERIFIED)
#define ADS_MOTOR_WATCHDOG_TIMEOUT_MS 2000U

int ADS_Motor_ProtectionReady(void);
int ADS_Motor_IdleReady(void);
int ADS_Motor_PowerSampleState(uint32_t powered_ms);
int ADS_Motor_PreparePower(void);
int ADS_Motor_PowerState(void); /* 0 off, 1 checking, 2 ready, 3 running */
void ADS_Motor_Init(void);
int ADS_Motor_OutputEnabled(void);
const char *ADS_Motor_BlockReason(void);
/* NORMAL mode uses only installed, verified PC8 active-HIGH feedback.
 * Supervised readiness is separate and never changes this function to true. */
int ADS_Motor_InterlocksReady(void);
int ADS_Motor_OperationReady(void);
int ADS_Motor_PowerFeedbackState(void);
int ADS_Motor_Rearm(void);
int ADS_Motor_StartPWM(uint32_t pwm, uint32_t duration_ms);
/* Idempotent, nonblocking; callable before Init/from faults. Disables TIM2 CH3,
 * holds PB10 low and requests PB5 de-energization only with verified config.
 * No contact/supply feedback: this never confirms physical power removal. */
void ADS_Motor_Stop(void);
void ADS_Motor_Fault(void);
/* STM32-local communication watchdog, independent of Pi/UI scheduling.
 * Poll is also called from SysTick. Neither heartbeat nor Stop clears a latch.
 * Init is startup-only, never a remote fault recovery operation. */
void ADS_Motor_Heartbeat(uint32_t now_ms);
void ADS_Motor_Poll(uint32_t now_ms);
int ADS_Motor_IsLatched(void);
int ADS_Motor_RelayConfigured(void);
#endif
