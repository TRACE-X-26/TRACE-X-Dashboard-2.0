#include "main.h"
#include "ads_motor.h"

static volatile uint32_t last_heartbeat_ms;
static volatile uint8_t watchdog_ready;
static volatile uint8_t shutdown_latched;
static volatile uint8_t run_deadline_active;
static volatile uint32_t run_start_ms, run_duration_ms;
static volatile uint32_t power_started_ms;
static volatile int power_state;
static volatile uint8_t power_authorized;

__attribute__((weak)) int ADS_Motor_ProtectionReady(void) { return 0; }
__attribute__((weak)) int ADS_Motor_IdleReady(void) { return 0; }
__attribute__((weak)) int ADS_Motor_PowerSampleState(uint32_t powered_ms) { (void)powered_ms; return -1; }
int ADS_Motor_PowerState(void) { return power_state; }

static void pwm_off(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* PB10 is TIM2 CH3. Disable the channel and timer before changing the pad;
   * clearing CCR3 alone is insufficient when compare preload is enabled. */
  __HAL_RCC_TIM2_CLK_ENABLE();
  TIM2->CCER &= ~TIM_CCER_CC3E;
  TIM2->CR1 &= ~TIM_CR1_CEN;
  TIM2->CCR3 = 0U;

  HAL_GPIO_WritePin(MOTOR_PWM_GPIO_Port, MOTOR_PWM_Pin, GPIO_PIN_RESET);
  gpio.Pin = MOTOR_PWM_Pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(MOTOR_PWM_GPIO_Port, &gpio);

 }
void ADS_Motor_Stop(void)
{
  run_deadline_active=0;power_state=0;power_authorized=0;
  pwm_off();
  GPIO_InitTypeDef gpio={0};
  gpio.Pin = MOTOR_RELAY_Pin;
#if ADS_RELAY_POLARITY_VERIFIED
  /* Preload before switching the pin to output; never pulse the other level. */
  HAL_GPIO_WritePin(MOTOR_RELAY_GPIO_Port, MOTOR_RELAY_Pin,
                   ADS_RELAY_DISCONNECT_LEVEL ? GPIO_PIN_SET : GPIO_PIN_RESET);
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
#else
  /* Unknown relay polarity: neither low nor high nor a pull is assumed safe.
   * Reset-time disconnection requires a verified external fail-safe circuit. */
  gpio.Mode = GPIO_MODE_INPUT;
#endif
  HAL_GPIO_Init(MOTOR_RELAY_GPIO_Port, &gpio);
}

void ADS_Motor_Init(void)
{
  /* Direction is deliberately left at its reset configuration. No direction
   * or start operation is available until physical acceptance is complete. */
  ADS_Motor_Stop();
#if ADS_POWER_FEEDBACK_INSTALLED && ADS_POWER_FEEDBACK_WIRING_VERIFIED
  __HAL_RCC_GPIOC_CLK_ENABLE();
  GPIO_InitTypeDef feedback={0};
  feedback.Pin=MOTOR_POWER_FEEDBACK_Pin; feedback.Mode=GPIO_MODE_INPUT;
  feedback.Pull=GPIO_PULLDOWN; feedback.Speed=GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(MOTOR_POWER_FEEDBACK_GPIO_Port,&feedback);
#endif
  /* A fault arriving before initialization must stay latched. Static storage
   * is reset only by MCU reset; there is no software rearm operation. */
  if (!watchdog_ready) last_heartbeat_ms = HAL_GetTick();
  watchdog_ready = 1U;
}

void ADS_Motor_Fault(void)
{
  shutdown_latched = 1U;
  ADS_Motor_Stop();
}

void ADS_Motor_Poll(uint32_t now_ms)
{
  if(power_state==1 || power_state==2) {
    int state=ADS_Motor_PowerSampleState(power_started_ms);
    if(!ADS_Motor_OperationReady() || state<0 || (uint32_t)(now_ms-power_started_ms)>=ADS_POWER_CHECK_TIMEOUT_MS) ADS_Motor_Fault();
    else if(state==1) power_state=2;
  }
  if (run_deadline_active && (!ADS_Motor_OperationReady() || !ADS_Motor_ProtectionReady())) ADS_Motor_Fault();
  if (run_deadline_active && (uint32_t)(now_ms-run_start_ms)>=run_duration_ms)
    ADS_Motor_Stop();
  if (watchdog_ready && !shutdown_latched &&
      (uint32_t)(now_ms - last_heartbeat_ms) >= ADS_MOTOR_WATCHDOG_TIMEOUT_MS)
  {
    shutdown_latched = 1U;
    ADS_Motor_Stop();
  }
}

void ADS_Motor_Heartbeat(uint32_t now_ms)
{
  /* Check the OLD deadline first, so a late heartbeat cannot hide a timeout. */
  ADS_Motor_Poll(now_ms);
  if (watchdog_ready && !shutdown_latched) last_heartbeat_ms = now_ms;
}

int ADS_Motor_IsLatched(void)
{
  return shutdown_latched != 0U;
}

int ADS_Motor_RelayConfigured(void)
{
  return ADS_MOTOR_RELAY_VERIFIED;
}

int ADS_Motor_PowerFeedbackState(void)
{
#if ADS_POWER_FEEDBACK_INSTALLED && ADS_POWER_FEEDBACK_WIRING_VERIFIED
  return HAL_GPIO_ReadPin(MOTOR_POWER_FEEDBACK_GPIO_Port,MOTOR_POWER_FEEDBACK_Pin)==GPIO_PIN_SET;
#else
  return -1; /* Unknown/uninstalled is never HIGH. */
#endif
}
__attribute__((weak)) int ADS_Motor_InterlocksReady(void)
{ return ADS_Motor_PowerFeedbackState()==1; }
int ADS_Motor_OperationReady(void)
{
#if ADS_MOTOR_OPERATING_MODE == ADS_MODE_SUPERVISED_TEST
  /* Deliberately separate acceptance path. Per-run operator confirmation is
   * additionally enforced by ADS_Test before ARM/START. No feedback is claimed. */
  return ADS_BOARD_ACCEPTED && ADS_SUPERVISED_TESTING_APPROVED &&
    (!ADS_POWER_FEEDBACK_INSTALLED || ADS_Motor_InterlocksReady());
#else
  return ADS_Motor_InterlocksReady();
#endif
}
int ADS_Motor_OutputEnabled(void) { return ADS_BOARD_ACCEPTED; }
const char *ADS_Motor_BlockReason(void)
{
  /* Report disabled build and wiring prerequisites explicitly. Reporting never changes output authorization. */
  if (!ADS_PHYSICAL_OUTPUT_ENABLED) return "PHYSICAL_OUTPUT_DISABLED_IN_BUILD";
  if (!ADS_MOTOR_WIRING_VERIFIED) return "MOTOR_WIRING_UNVERIFIED";
  if (!ADS_RELAY_POWER_PATH_VERIFIED || !ADS_RELAY_POLARITY_VERIFIED) return "MOTOR_RELAY_WIRING_UNVERIFIED";
  if (!ADS_PROTECTION_LIMITS_VERIFIED) return "PROTECTION_LIMITS_UNVERIFIED";
  if (!ADS_RELAY_SAFE_OUTPUT_VERIFIED) return "RELAY_RESET_BEHAVIOR_UNVERIFIED";
  if (ADS_MOTOR_OPERATING_MODE==ADS_MODE_SUPERVISED_TEST && !ADS_SUPERVISED_TESTING_APPROVED) return "SUPERVISED_MODE_NOT_APPROVED";
  if (ADS_FORWARD_GPIO_LEVEL!=0 && ADS_FORWARD_GPIO_LEVEL!=1) return "DIRECTION_LEVEL_UNCONFIGURED";
  if (!ADS_SENSOR_WIRING_VERIFIED || !ADS_INA219_CALIBRATED) return "ELECTRICAL_MEASUREMENT_UNVERIFIED";
  if (!ADS_KILL_SWITCH_VERIFIED || !ADS_COMM_LOSS_STOP_VERIFIED) return "SHUTDOWN_ACCEPTANCE_REQUIRED";
  if (ADS_MOTOR_OPERATING_MODE==ADS_MODE_NORMAL && !ADS_POWER_FEEDBACK_INSTALLED) return "POWER_FEEDBACK_NOT_INSTALLED";
  if (!ADS_Motor_OperationReady()) return "INTERLOCK_NOT_READY";
  return ADS_BOARD_ACCEPTED ? "NONE" : "CONTROL_DISABLED";
}

int ADS_Motor_Rearm(void)
{
#if ADS_BOARD_ACCEPTED
  /* Explicit command adapter only; never called by heartbeat/reconnect/Init. */
  if (!ADS_Motor_OperationReady()) return 0;
  ADS_Motor_Stop();
  shutdown_latched=0;power_authorized=1; last_heartbeat_ms=HAL_GetTick(); watchdog_ready=1;
  return 1;
#else
  return 0;
#endif
}
int ADS_Motor_PreparePower(void)
{
#if ADS_BOARD_ACCEPTED
  if(shutdown_latched || !power_authorized || power_state || !ADS_Motor_OperationReady() || !ADS_Motor_IdleReady()) return 0;
  ADS_Motor_Stop(); /* PWM held LOW; circuit relay remains independent. */
  power_started_ms=HAL_GetTick();power_state=1;
  HAL_GPIO_WritePin(GPIOB,MOTOR_RELAY_Pin,ADS_RELAY_ACTIVE_LEVEL?GPIO_PIN_SET:GPIO_PIN_RESET);
  return 1;
#else
  return 0;
#endif
}
int ADS_Motor_StartPWM(uint32_t pwm, uint32_t duration_ms)
{
#if ADS_BOARD_ACCEPTED
  GPIO_InitTypeDef gpio={0};
  if (shutdown_latched || power_state!=2 || !ADS_Motor_OperationReady() || !ADS_Motor_ProtectionReady() || pwm!=ADS_BENCH_PWM_PERCENT || !duration_ms ||
      duration_ms>ADS_BENCH_MAX_DURATION_MS || HAL_RCC_GetPCLK1Freq()!=42000000U) return 0;
  pwm_off(); /* Keep the verified, already-energized relay closed. */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOA,MOTOR_DIRECTION_Pin,ADS_FORWARD_GPIO_LEVEL?GPIO_PIN_SET:GPIO_PIN_RESET);
  gpio.Pin=MOTOR_DIRECTION_Pin; gpio.Mode=GPIO_MODE_OUTPUT_PP; gpio.Pull=GPIO_NOPULL;
  gpio.Speed=GPIO_SPEED_FREQ_LOW; HAL_GPIO_Init(GPIOA,&gpio);
  /* Same 84 MHz / 84 / 1000 = 1 kHz setup as the recovered motor-test project.
   * Current .ioc intentionally leaves this gated user-code setup ungenerated. */
  TIM2->PSC=83U; TIM2->ARR=999U; TIM2->CNT=0;
  TIM2->CCMR2=(6U<<4)|TIM_CCMR2_OC3PE;
  TIM2->CCER=0; TIM2->CCR3=(1000U*pwm)/100U;
  TIM2->CR1=TIM_CR1_ARPE; TIM2->EGR=TIM_EGR_UG;
  gpio.Pin=MOTOR_PWM_Pin; gpio.Mode=GPIO_MODE_AF_PP; gpio.Alternate=GPIO_AF1_TIM2;
  HAL_GPIO_Init(GPIOB,&gpio);
  run_start_ms=HAL_GetTick(); run_duration_ms=duration_ms; run_deadline_active=1; power_state=3;
  /* Direction is established and compare staged with PWM disabled.
   * Energize the motor branch before enabling the PWM channel. */
  HAL_GPIO_WritePin(GPIOB,MOTOR_RELAY_Pin,ADS_RELAY_ACTIVE_LEVEL?GPIO_PIN_SET:GPIO_PIN_RESET);
  TIM2->CCER=TIM_CCER_CC3E; TIM2->CR1|=TIM_CR1_CEN;
  return 1;
#else
  (void)pwm; (void)duration_ms; return 0;
#endif
}
