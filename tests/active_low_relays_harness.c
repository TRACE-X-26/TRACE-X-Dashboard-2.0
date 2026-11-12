/* Actual relay drivers with fake GPIO only; no attached board. */
#include "main.h"
#include "ads_motor.h"
#include "ads_circuit_relay.h"
#include <assert.h>
GPIO_TypeDef test_gpio_a={0},test_gpio_b={1},test_gpio_c={2};
TIM_TypeDef test_tim2;
static uint32_t tick;
static int motor_level=-1,circuit_level=-1;
static unsigned motor_high_writes,circuit_high_writes;
#ifndef TEST_PROTECTION_MISSING
static int protection_ready=1;
int ADS_Motor_ProtectionReady(void) { return protection_ready; }
#endif
int ADS_Motor_IdleReady(void) { return 1; }
static int fake_power_sample=1;
int ADS_Motor_PowerSampleState(uint32_t powered_ms) { (void)powered_ms;return fake_power_sample; }
#ifndef TEST_PREPOWER
static int fixture_start(uint32_t pwm,uint32_t duration)
{
  if(pwm==ADS_BENCH_PWM_PERCENT && duration && duration<=ADS_BENCH_MAX_DURATION_MS && ADS_Motor_PowerState()==0) {
    if(!ADS_Motor_PreparePower()) return 0;
    ADS_Motor_Poll(tick);
  }
  return ADS_Motor_StartPWM(pwm,duration);
}
#endif
uint32_t HAL_GetTick(void) { return tick; }
void test_enable_tim2(void) {}
void test_enable_gpio_b(void) {}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *p,uint16_t pin)
{ (void)p; (void)pin; return GPIO_PIN_RESET; }
void HAL_GPIO_WritePin(GPIO_TypeDef *p,uint16_t pin,GPIO_PinState level)
{
  if(p==GPIOB && pin==GPIO_PIN_5) {
    motor_level=level; if(level==GPIO_PIN_SET) motor_high_writes++;
  }
  if(p==GPIOB && pin==GPIO_PIN_4) {
    circuit_level=level; if(level==GPIO_PIN_SET) circuit_high_writes++;
  }
}
void HAL_GPIO_Init(GPIO_TypeDef *p,GPIO_InitTypeDef *gpio)
{
  if(p==GPIOB && gpio->Pin==GPIO_PIN_5 && gpio->Mode==GPIO_MODE_OUTPUT_PP)
    assert(motor_level==1); /* Inactive latch preloaded before output enable. */
  if(p==GPIOB && gpio->Pin==GPIO_PIN_4 && gpio->Mode==GPIO_MODE_OUTPUT_PP)
    assert(circuit_level==1);
}
int main(void)
{
  assert(ADS_RELAY_ACTIVE_LEVEL==0 && ADS_RELAY_INACTIVE_LEVEL==1);
  assert(ADS_CIRCUIT_RELAY_ACTIVE_LEVEL==0 && ADS_CIRCUIT_RELAY_INACTIVE_LEVEL==1);
  ADS_Motor_Init();ADS_CircuitRelay_Init();
  assert(motor_level==1 && circuit_level==1 && !TIM2->CCR3);
#if defined(TEST_PREPOWER)
  fake_power_sample=0;
  assert(!ADS_Motor_PreparePower());
  assert(ADS_Motor_Rearm() && ADS_Motor_PreparePower());
  assert(motor_level==0 && TIM2->CCR3==0 && !(TIM2->CCER&TIM_CCER_CC3E));
  tick=50;ADS_Motor_Poll(tick);assert(ADS_Motor_PowerState()==1);
  assert(!ADS_Motor_StartPWM(50,1000));
  fake_power_sample=1;tick=100;ADS_Motor_Poll(tick);
  assert(ADS_Motor_PowerState()==2 && TIM2->CCR3==0);
  assert(ADS_Motor_StartPWM(50,1000));assert(motor_level==0 && TIM2->CCR3==500);
  ADS_Motor_Stop();assert(motor_level==1);
  fake_power_sample=0;assert(ADS_Motor_Rearm() && ADS_Motor_PreparePower());
  tick+=1500;ADS_Motor_Poll(tick);assert(motor_level==1 && ADS_Motor_IsLatched());
  assert(!ADS_Motor_PreparePower());
  assert(ADS_Motor_Rearm() && ADS_Motor_PreparePower());
  fake_power_sample=-1;tick++;ADS_Motor_Poll(tick);assert(motor_level==1 && ADS_Motor_IsLatched());
  return 0;
#elif defined(TEST_DEFAULT_DISABLED)
  assert(!ADS_Motor_OutputEnabled());assert(!ADS_Motor_Rearm());
  assert(!fixture_start(50,1000));ADS_CircuitRelay_On();
  assert(motor_level==1 && circuit_level==1);return 0;
#elif defined(TEST_PROTECTION_MISSING)
  assert(ADS_Motor_Rearm());assert(!fixture_start(50,1000));
  ADS_Motor_Stop();assert(motor_level==1);return 0;
#else
  ADS_CircuitRelay_On();assert(circuit_level==0 && motor_level==1);
  ADS_CircuitRelay_Off();ADS_CircuitRelay_Off();assert(circuit_level==1);
  assert(ADS_Motor_Rearm() && fixture_start(50,1000));
  assert(motor_level==0 && circuit_level==1);
  tick=1000;ADS_Motor_Poll(tick);assert(motor_level==1);
  assert(ADS_Motor_Rearm() && fixture_start(50,1000));
  ADS_Motor_Fault();assert(motor_level==1);
  assert(!fixture_start(50,1000));
  assert(ADS_Motor_Rearm() && fixture_start(50,30000));
  tick+=2000;ADS_Motor_Poll(tick);assert(motor_level==1 && ADS_Motor_IsLatched());
  assert(ADS_Motor_Rearm() && fixture_start(50,1000));
  protection_ready=0;tick++;ADS_Motor_Poll(tick);
  assert(motor_level==1 && ADS_Motor_IsLatched());
  protection_ready=1;ADS_Motor_Heartbeat(tick);
  assert(!fixture_start(50,1000)); /* Sensor recovery cannot restart. */
  assert(motor_high_writes>3 && circuit_high_writes>=3);
  return 0;
#endif
}
