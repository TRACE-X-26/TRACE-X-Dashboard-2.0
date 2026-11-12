#include "main.h"
#include "ads_motor.h"
#include <assert.h>
GPIO_TypeDef test_gpio_a={0},test_gpio_b={1};
TIM_TypeDef test_tim2;
static uint32_t tick;
static unsigned relay_activations;
static int relay_active;
static int interlocks=1;
int ADS_Motor_InterlocksReady(void) { return interlocks; }
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
void HAL_GPIO_WritePin(GPIO_TypeDef *port,uint16_t pin,GPIO_PinState level)
{
  assert(!(port==GPIOB && pin==GPIO_PIN_4)); /* circuit relay independent */
  if(port==GPIOB && pin==GPIO_PIN_5) {
    relay_active=(int)level==ADS_RELAY_ACTIVE_LEVEL;
    if(relay_active) {
      relay_activations++;
      assert(!(TIM2->CCER&TIM_CCER_CC3E)); /* Relay before PWM enable. */
      assert(TIM2->CCR3==0 || TIM2->CCR3==100);
    }
  }
}
void HAL_GPIO_Init(GPIO_TypeDef *port,GPIO_InitTypeDef *gpio)
{
  assert(!(port==GPIOB && gpio->Pin==GPIO_PIN_4));
  if(port==GPIOB && gpio->Pin==GPIO_PIN_10 && gpio->Mode==GPIO_MODE_AF_PP)
    assert(gpio->Alternate==GPIO_AF1_TIM2);
}
int main(void)
{
  assert(ADS_Motor_OutputEnabled()); ADS_Motor_Init(); assert(!relay_active);
  assert(!fixture_start(50,1000)); assert(!relay_activations);
  assert(!fixture_start(10,1001)); assert(!relay_activations);
  assert(ADS_Motor_Rearm()); assert(fixture_start(10,1000));
  assert(relay_active && TIM2->PSC==83 && TIM2->ARR==999);
  tick=999; ADS_Motor_Poll(tick); assert(relay_active);
  tick=1000; ADS_Motor_Poll(tick); assert(!relay_active && !TIM2->CCR3);
  ADS_Motor_Stop(); ADS_Motor_Stop(); assert(!relay_active);
  assert(ADS_Motor_Rearm());assert(fixture_start(10,1000));
  tick=3000; ADS_Motor_Poll(tick); assert(!relay_active && ADS_Motor_IsLatched());
  assert(!fixture_start(10,1000));
  ADS_Motor_Heartbeat(tick); assert(ADS_Motor_IsLatched());
  assert(ADS_Motor_Rearm()); assert(fixture_start(10,1000));
  ADS_Motor_Fault(); assert(!relay_active && ADS_Motor_IsLatched());
  assert(!fixture_start(10,1000));
  assert(ADS_Motor_Rearm()); assert(fixture_start(10,1000));
  interlocks=0; ADS_Motor_Poll(tick); assert(!relay_active && ADS_Motor_IsLatched());
  assert(!ADS_Motor_Rearm()); interlocks=1;
  assert(!fixture_start(10,1000)); /* releasing interlock never clears latch */
  return 0;
}
