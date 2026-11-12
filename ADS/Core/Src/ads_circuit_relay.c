#include "main.h"
#include "ads_board_config.h"
#include "ads_circuit_relay.h"

void ADS_CircuitRelay_Off(void)
{
#if ADS_CIRCUIT_RELAY_VERIFIED
  __HAL_RCC_GPIOB_CLK_ENABLE();
  HAL_GPIO_WritePin(CIRCUIT_RELAY_GPIO_Port,CIRCUIT_RELAY_Pin,
    ADS_CIRCUIT_RELAY_INACTIVE_LEVEL ? GPIO_PIN_SET : GPIO_PIN_RESET);
#endif
}
void ADS_CircuitRelay_Init(void)
{
#if ADS_CIRCUIT_RELAY_VERIFIED
  /* Preload inactive HIGH before changing a COM-LOW relay pin to output. */
  ADS_CircuitRelay_Off();
  GPIO_InitTypeDef gpio={0};
  gpio.Pin=CIRCUIT_RELAY_Pin; gpio.Mode=GPIO_MODE_OUTPUT_PP;
  gpio.Pull=GPIO_NOPULL; gpio.Speed=GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(CIRCUIT_RELAY_GPIO_Port,&gpio);
#endif
}
void ADS_CircuitRelay_On(void)
{
#if ADS_PHYSICAL_OUTPUT_ENABLED && ADS_CIRCUIT_OUTPUT_ENABLED && ADS_CIRCUIT_RELAY_VERIFIED && ADS_KILL_SWITCH_VERIFIED && ADS_COMM_LOSS_STOP_VERIFIED && ADS_SUPERVISED_TESTING_APPROVED
  HAL_GPIO_WritePin(CIRCUIT_RELAY_GPIO_Port,CIRCUIT_RELAY_Pin,
    ADS_CIRCUIT_RELAY_ACTIVE_LEVEL ? GPIO_PIN_SET : GPIO_PIN_RESET);
#else
  ADS_CircuitRelay_Off();
#endif
}
