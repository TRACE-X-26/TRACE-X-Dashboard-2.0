#include "main.h"
#include "ads_motor.h"
#include <assert.h>
GPIO_TypeDef test_gpio_a={0},test_gpio_b={1},test_gpio_c={2};
TIM_TypeDef test_tim2;
static uint32_t tick;
static int feedback,relay_on;
static unsigned feedback_reads,feedback_configures;
int ADS_Motor_ProtectionReady(void) { return 1; }
int ADS_Motor_IdleReady(void) { return 1; }
int ADS_Motor_PowerSampleState(uint32_t powered_ms) { (void)powered_ms;return 1; }
static int fixture_start(uint32_t pwm,uint32_t duration)
{
  if(pwm==ADS_BENCH_PWM_PERCENT && duration && duration<=ADS_BENCH_MAX_DURATION_MS && ADS_Motor_PowerState()==0) {
    if(!ADS_Motor_PreparePower()) return 0;
    ADS_Motor_Poll(tick);
  }
  return ADS_Motor_StartPWM(pwm,duration);
}
uint32_t HAL_GetTick(void) { return tick; }
void test_enable_tim2(void) {}
void test_enable_gpio_b(void) {}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port,uint16_t pin)
{
  assert(port==GPIOC && pin==GPIO_PIN_8);feedback_reads++;
  return feedback?GPIO_PIN_SET:GPIO_PIN_RESET;
}
void HAL_GPIO_Init(GPIO_TypeDef *port,GPIO_InitTypeDef *gpio)
{
  assert(!(port==GPIOB && gpio->Pin==GPIO_PIN_4));
  if(port==GPIOC) {
    assert(gpio->Pin==GPIO_PIN_8 && gpio->Mode==GPIO_MODE_INPUT && gpio->Pull==GPIO_PULLDOWN);
    feedback_configures++;
  }
}
void HAL_GPIO_WritePin(GPIO_TypeDef *port,uint16_t pin,GPIO_PinState level)
{
  assert(!(port==GPIOB && pin==GPIO_PIN_4));
  assert(port!=GPIOC); /* Feedback must never be driven. */
  if(port==GPIOB && pin==GPIO_PIN_5)relay_on=(int)level==ADS_RELAY_ACTIVE_LEVEL;
}
int main(void)
{
  ADS_Motor_Init(); assert(!relay_on && !TIM2->CCR3);
  if(!ADS_PROTECTION_LIMITS_VERIFIED || (ADS_MOTOR_OPERATING_MODE==ADS_MODE_SUPERVISED_TEST && !ADS_SUPERVISED_TESTING_APPROVED)) {
    assert(!ADS_Motor_OutputEnabled());assert(!ADS_Motor_Rearm());
    assert(!fixture_start(ADS_BENCH_PWM_PERCENT,1000));return 0;
  }
  assert(ADS_Motor_OutputEnabled());
#if ADS_POWER_FEEDBACK_INSTALLED && ADS_POWER_FEEDBACK_WIRING_VERIFIED
  assert(feedback_configures==1 && !ADS_Motor_InterlocksReady());
  assert(!ADS_Motor_Rearm());feedback=1;
  assert(ADS_Motor_InterlocksReady() && ADS_Motor_OperationReady());
  assert(ADS_Motor_Rearm() && fixture_start(ADS_BENCH_PWM_PERCENT,1000));
  feedback=0;tick=100;ADS_Motor_Poll(tick);
  assert(!relay_on && !TIM2->CCR3 && ADS_Motor_IsLatched());
  feedback=1;ADS_Motor_Heartbeat(tick);
  assert(!fixture_start(ADS_BENCH_PWM_PERCENT,1000)); /* HIGH recovery never restarts. */
#else
  assert(!feedback_reads && !feedback_configures);
  assert(!ADS_Motor_InterlocksReady() && ADS_Motor_PowerFeedbackState()==-1);
  if(ADS_MOTOR_OPERATING_MODE==ADS_MODE_NORMAL || ADS_POWER_FEEDBACK_INSTALLED) {
    assert(!ADS_Motor_OperationReady());assert(!ADS_Motor_Rearm());return 0;
  }
  assert(ADS_Motor_OperationReady()); /* Explicitly accepted supervised mode. */
#endif
  assert(ADS_Motor_Rearm() && fixture_start(ADS_BENCH_PWM_PERCENT,1000));
  assert(relay_on);tick+=1000;ADS_Motor_Poll(tick);
  assert(!relay_on && !TIM2->CCR3); /* Local deadline works in either mode. */
  assert(ADS_Motor_Rearm() && fixture_start(ADS_BENCH_PWM_PERCENT,1000));
  tick+=2000;ADS_Motor_Poll(tick);
  assert(!relay_on && ADS_Motor_IsLatched());
  assert(!fixture_start(ADS_BENCH_PWM_PERCENT,1000));
  return 0;
}
