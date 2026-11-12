#include "main.h"
#include "ads_motor.h"
#include <assert.h>
#include <string.h>
#include "ads_protocol.h"

GPIO_TypeDef test_gpio_a = {0}, test_gpio_b = {1};
TIM_TypeDef test_tim2;
static uint32_t tick;
uint32_t HAL_GetTick(void) { return tick; }
void test_enable_tim2(void) {}
static unsigned clock_enabled, pwm_writes, relay_writes, order;
static GPIO_PinState pwm_level = GPIO_PIN_SET, relay_level = GPIO_PIN_SET;
static uint32_t pwm_mode = 99, relay_mode = 99;
void test_enable_gpio_b(void) { clock_enabled = 1; }
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState level)
{
  assert(clock_enabled && port == GPIOB);
  assert((TIM2->CCER & TIM_CCER_CC3E) == 0 && (TIM2->CR1 & TIM_CR1_CEN) == 0 && TIM2->CCR3 == 0);
  if (pin == GPIO_PIN_10) { pwm_writes++; pwm_level = level; order = 1; }
  else {
    assert(pin == GPIO_PIN_5 && order == 2);
    relay_writes++; relay_level = level; order = 3;
  }
}
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *gpio)
{
  assert(clock_enabled && port == GPIOB && gpio->Pull == GPIO_NOPULL);
  if (gpio->Pin == GPIO_PIN_10) {
    assert(order == 1 && pwm_level == GPIO_PIN_RESET);
    pwm_mode = gpio->Mode; order = 2;
  } else {
    assert(gpio->Pin == GPIO_PIN_5);
    relay_mode = gpio->Mode;
#if ADS_RELAY_POLARITY_VERIFIED
    assert(order == 3); /* Relay was preloaded before output was enabled. */
#else
    assert(order == 2);
#endif
  }
}
static void assert_stopped(void)
{
  assert(pwm_mode == GPIO_MODE_OUTPUT_PP && pwm_level == GPIO_PIN_RESET);
  assert(ADS_Motor_RelayConfigured() == ADS_MOTOR_RELAY_VERIFIED);
#if ADS_RELAY_POLARITY_VERIFIED
  assert(relay_mode == GPIO_MODE_OUTPUT_PP);
  assert(relay_level == (ADS_RELAY_DISCONNECT_LEVEL ? GPIO_PIN_SET : GPIO_PIN_RESET));
  assert(relay_writes == pwm_writes);
#else
  assert(relay_mode == GPIO_MODE_INPUT && relay_writes == 0);
#endif
}
static void fake_running(void)
{
  TIM2->CCER = TIM_CCER_CC3E | 1U;
  TIM2->CR1 = TIM_CR1_CEN;
  TIM2->CCR3 = 500;
  pwm_level = GPIO_PIN_SET;
  pwm_mode = 99;
}
static uint32_t protocol_tick(void *context) { (void)context; return tick; }
static void protocol_stop(void *context) { (void)context; ADS_Motor_Stop(); }
static void protocol_heartbeat(uint32_t now, void *context) { (void)context; ADS_Motor_Heartbeat(now); }
static void feed(ADS_Protocol *protocol, const char *text)
{ for (; *text; text++) ADS_Protocol_ProcessByte(protocol, (uint8_t)*text); }
int main(int argc, char **argv)
{
  assert(!ADS_Motor_OutputEnabled()); /* Unresolved production gates block start. */
  /* Poll before initialization must neither drive GPIO nor arm outputs. */
  ADS_Motor_Poll(5000); assert(pwm_writes == 0);
  if (argc > 1 && strcmp(argv[1], "fault-before-init") == 0) {
    ADS_Motor_Fault(); ADS_Motor_Init();
    assert(ADS_Motor_IsLatched()); assert_stopped(); return 0;
  }
  if (argc > 1 && strcmp(argv[1], "wrap") == 0) tick = UINT32_MAX - 1000U;
  ADS_Motor_Init(); assert_stopped();
  if (argc > 1 && strcmp(argv[1], "late") == 0) {
    fake_running(); ADS_Motor_Heartbeat(2000);
    assert(ADS_Motor_IsLatched()); assert_stopped(); return 0;
  }
  if (argc > 1 && (strcmp(argv[1], "watchdog") == 0 || strcmp(argv[1], "wrap") == 0)) {
    uint32_t initial = tick;
    fake_running();
    ADS_Motor_Poll(initial + 1999U); assert(!ADS_Motor_IsLatched());
    ADS_Motor_Poll(initial + 2000U); assert(ADS_Motor_IsLatched()); assert_stopped();
    ADS_Motor_Heartbeat(initial + 2001U); assert(ADS_Motor_IsLatched());
    ADS_Motor_Init(); assert(ADS_Motor_IsLatched()); assert_stopped();
    return 0;
  }
  if (argc > 1 && strcmp(argv[1], "fault") == 0) {
    fake_running(); ADS_Motor_Fault(); assert_stopped();
    ADS_Motor_Heartbeat(1); ADS_Motor_Init();
    assert(ADS_Motor_IsLatched()); assert_stopped(); return 0;
  }
  if (argc > 1 && strcmp(argv[1], "protocol") == 0) {
    ADS_Protocol protocol;
    ADS_Protocol_Init(&protocol, NULL, protocol_tick, NULL);
    ADS_Protocol_SetHardwareCallbacks(&protocol, NULL, protocol_stop);
    ADS_Protocol_SetHeartbeatCallback(&protocol, protocol_heartbeat);
    tick = 1000;
    feed(&protocol, "{\"version\":1,\"type\":\"heartbeat\",\"seq\":1,\"device_id\":\"pi\",\"timestamp_ms\":0,\"payload\":{}}\n");
    ADS_Motor_Poll(2999); assert(!ADS_Motor_IsLatched());
    /* Malformed input and rejected motor commands never renew the watchdog. */
    tick = 2999;
    feed(&protocol, "{broken}\n");
    feed(&protocol, "{\"version\":1,\"type\":\"command\",\"seq\":2,\"device_id\":\"pi\",\"timestamp_ms\":0,\"payload\":{\"command\":\"START_TEST\",\"arguments\":{}}}\n");
    assert_stopped();
    fake_running(); ADS_Motor_Poll(3000); assert(ADS_Motor_IsLatched()); assert_stopped();
    /* A late heartbeat cannot hide an expired motor deadline. */
    ADS_Motor_Heartbeat(3001); assert(ADS_Motor_IsLatched());
    return 0;
  }
  /* Also supports a fault arriving before normal initialization. */
  ADS_Motor_Stop(); assert_stopped();
  ADS_Motor_Init(); assert_stopped();
  /* Emulate a prior output state; shutdown must restore zero duty/off request. */
  fake_running();
  relay_level = ADS_RELAY_DISCONNECT_LEVEL == 1 ? GPIO_PIN_RESET : GPIO_PIN_SET;
  ADS_Motor_Stop(); assert_stopped();
  for (unsigned i = 0; i < 100; i++) { ADS_Motor_Stop(); assert_stopped(); }
  /* Reinitialization after a fault/reset must remain stopped, never rearm. */
  ADS_Motor_Init(); assert_stopped();
  return 0;
}
