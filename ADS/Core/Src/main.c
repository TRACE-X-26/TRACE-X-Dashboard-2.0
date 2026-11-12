/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "ads_protocol.h"
#include "ads_motor.h"
#include "ads_sensors.h"
#include "ads_circuit.h"
#include "ads_circuit_relay.h"
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
static ADS_Protocol ads_protocol;
static ADS_Test motor_test;
static ADS_Test circuit_test;
static uint8_t circuit_ready;
/* ISR receives bytes while bounded I2C/one-wire operations and TX execute. */
static uint8_t rx_byte, rx_ring[1024];
static volatile uint16_t rx_head, rx_tail;
static volatile uint8_t rx_fault;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */
static int ADS_UART_Transmit(const uint8_t *data, size_t length, void *context);
static uint32_t ADS_GetTick(void *context);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
/* Independent D5/PB4/IN2 supply channel. No motor PWM is used here. */
static void ADS_StopCircuit(void *context)
{
  (void)context;
  ADS_CircuitRelay_Off();
}
static int ADS_CircuitReady(void *context)
{
  (void)context; ADS_ElectricalBranch branches[2];
  if(motor_test.running || motor_test.armed) return 0;
  ADS_Sensors_Branches(branches,NULL);
  return branches[1].connected && branches[1].configured &&
    branches[1].samples[0].valid && branches[1].samples[1].valid;
}
static int ADS_StartCircuit(uint32_t unused,uint32_t duration,void *context)
{
  (void)unused; (void)duration; (void)context;
#if ADS_PHYSICAL_OUTPUT_ENABLED && ADS_CIRCUIT_OUTPUT_ENABLED && ADS_CIRCUIT_RELAY_VERIFIED && ADS_KILL_SWITCH_VERIFIED && ADS_COMM_LOSS_STOP_VERIFIED
  uint32_t irq=__get_PRIMASK(); __disable_irq();
  if(circuit_test.locked || (uint32_t)(HAL_GetTick()-circuit_test.last_heartbeat_ms)>=2000U || !ADS_CircuitReady(NULL)) { __set_PRIMASK(irq); return 0; }
  ADS_Motor_Stop();
  ADS_CircuitRelay_On();
  __set_PRIMASK(irq);
  return 1;
#else
  return 0;
#endif
}
void ADS_Circuit_Poll(uint32_t now_ms)
{
  if(circuit_ready) ADS_Test_Poll(&circuit_test,now_ms);
}
void ADS_Circuit_Fault(void)
{
  ADS_StopCircuit(NULL);
  if(circuit_ready) ADS_Test_Fault(&circuit_test,HAL_GetTick(),"OUTPUTS_STOPPED");
}
static void ADS_HeartbeatMotor(uint32_t now_ms, void *context)
{
  (void)context;
  ADS_Motor_Heartbeat(now_ms);
}

static void ADS_StopMotor(void *context)
{
  (void)context;
  ADS_Motor_Stop();
  ADS_Circuit_Fault();
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart->Instance!=USART2) return;
  uint16_t next=(uint16_t)((rx_head+1U)&1023U);
  if (next==rx_tail) { rx_fault=1; ADS_Motor_Fault(); ADS_Circuit_Fault(); }
  else { rx_ring[rx_head]=rx_byte; __DMB(); rx_head=next; }
  if (HAL_UART_Receive_IT(&huart2,&rx_byte,1)!=HAL_OK) { rx_fault=1; ADS_Motor_Fault(); ADS_Circuit_Fault(); }
}
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
  if (uart->Instance==USART2) { rx_fault=1; ADS_Motor_Fault(); ADS_Circuit_Fault(); }
}
static void ADS_ReceivePoll(void)
{
  if (rx_fault) {
    uint32_t irq=__get_PRIMASK(); __disable_irq();
    rx_head=rx_tail=0; rx_fault=0;
    ads_protocol.receive_length=0; ads_protocol.receive_overflow=1;
    HAL_UART_AbortReceive(&huart2);
    if (HAL_UART_Receive_IT(&huart2,&rx_byte,1)!=HAL_OK) rx_fault=1;
    __set_PRIMASK(irq);
    ADS_Test_Fault(&motor_test,HAL_GetTick(),"UART_RECEIVE_FAULT");
    ADS_Test_Fault(&circuit_test,HAL_GetTick(),"UART_RECEIVE_FAULT");
  }
  for(unsigned budget=0;budget<512 && rx_tail!=rx_head && !rx_fault;budget++) {
    uint8_t byte=rx_ring[rx_tail]; __DMB(); rx_tail=(uint16_t)((rx_tail+1U)&1023U);
    ADS_Protocol_ProcessByte(&ads_protocol,byte);
  }
}
static int ADS_TestReady(void *context)
{
  (void)context;
  return (!(motor_test.running || motor_test.armed) || !ADS_Motor_IsLatched()) && !circuit_test.running && !circuit_test.armed && ADS_Motor_OperationReady() && (motor_test.running ? ADS_Sensors_Ready() : ADS_Motor_IdleReady());
}
static int ADS_TestPreparePower(void *context)
{
  (void)context;uint32_t irq=__get_PRIMASK();__disable_irq();
  int result=ADS_Motor_PreparePower();__set_PRIMASK(irq);return result;
}
static int ADS_TestPowerState(void *context) { (void)context;return ADS_Motor_PowerState(); }
static int ADS_TestFeedback(void *context)
{ (void)context; return ADS_Motor_PowerFeedbackState(); }
static int ADS_TestArm(void *context)
{
  (void)context;
  uint32_t irq=__get_PRIMASK(); __disable_irq();
  int armed=ADS_Motor_Rearm();
  __set_PRIMASK(irq);
  return armed;
}
static int ADS_TestStart(uint32_t pwm, uint32_t duration, void *context)
{
  (void)context;
  /* Atomic against SysTick/fault-stop between readiness and activation. */
  uint32_t irq=__get_PRIMASK(); __disable_irq();
  int started=ADS_Motor_StartPWM(pwm,duration);
  __set_PRIMASK(irq);
  return started;
}
static int ADS_UART_Transmit(const uint8_t *data, size_t length, void *context)
{
  UART_HandleTypeDef *uart = (UART_HandleTypeDef *)context;
  /* Larger dual-sensor frames must not starve conversion polling. Keep the
   * existing blocking HAL interface, but service acquisition between bounded
   * 24-byte chunks (~2.1 ms at 115200). No nested protocol processing here. */
  while (length) {
    uint16_t chunk=(uint16_t)(length>24U?24U:length);
    if (HAL_UART_Transmit(uart,(uint8_t *)data,chunk,100U)!=HAL_OK) {
      ADS_Motor_Fault(); ADS_Circuit_Fault(); return -1;
    }
    data+=chunk; length-=chunk;
    ADS_Sensors_Poll(); ADS_Motor_Poll(HAL_GetTick());
  }
  return 0;
}

static uint32_t ADS_GetTick(void *context)
{
  (void)context;
  return HAL_GetTick();
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */
  ADS_Motor_Init();
  ADS_CircuitRelay_Init();

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
  ADS_Protocol_Init(&ads_protocol, ADS_UART_Transmit, ADS_GetTick, &huart2);
  ads_protocol.require_crc=1;
  ADS_Sensors_Init();
  ADS_Test_Init(&motor_test, ADS_BENCH_PWM_PERCENT, ADS_BENCH_MAX_DURATION_MS,
                ADS_Motor_OutputEnabled(), ADS_TestReady, ADS_TestStart, ADS_StopMotor, NULL);
  motor_test.power_required=1;motor_test.prepare_power=ADS_TestPreparePower;motor_test.power_state=ADS_TestPowerState;
  motor_test.disabled_reason=ADS_Motor_BlockReason();
  motor_test.supervised_required=ADS_MOTOR_OPERATING_MODE==ADS_MODE_SUPERVISED_TEST;
  motor_test.power_feedback_installed=ADS_POWER_FEEDBACK_INSTALLED;
  motor_test.power_feedback_verified=ADS_POWER_FEEDBACK_WIRING_VERIFIED;
  motor_test.feedback=ADS_TestFeedback;
  motor_test.arm=ADS_TestArm;
  ADS_Protocol_SetHardwareCallbacks(&ads_protocol, ADS_Sensors_Acquire, ADS_StopMotor);
  ADS_Protocol_SetMeasurementInfo(&ads_protocol, ADS_Sensors_Info);
  ADS_Protocol_SetBranches(&ads_protocol, ADS_Sensors_Branches);
  ADS_Protocol_SetMotorTest(&ads_protocol, &motor_test);
  ADS_Test_Init(&circuit_test,100,30000,
    ADS_PHYSICAL_OUTPUT_ENABLED && ADS_CIRCUIT_OUTPUT_ENABLED && ADS_CIRCUIT_RELAY_VERIFIED && ADS_KILL_SWITCH_VERIFIED && ADS_COMM_LOSS_STOP_VERIFIED && ADS_SUPERVISED_TESTING_APPROVED,
    ADS_CircuitReady,ADS_StartCircuit,ADS_StopCircuit,NULL);
  circuit_test.supervised_required=1;
  circuit_test.disabled_reason="CIRCUIT_CONTROL_DISABLED";
  circuit_ready=1;
  ADS_Protocol_SetCircuitTest(&ads_protocol,&circuit_test);
  ADS_Protocol_SetHeartbeatCallback(&ads_protocol, ADS_HeartbeatMotor);
  /* Independent watchdog: main-loop lockup resets to disabled startup.
   * LSI tolerance means the nominal ~2s setting needs bench measurement. */
  IWDG->KR=0x5555U; IWDG->PR=4U; IWDG->RLR=1000U; IWDG->KR=0xccccU;
  IWDG->KR=0xaaaaU;
  HAL_NVIC_SetPriority(USART2_IRQn,1,0);
  HAL_NVIC_EnableIRQ(USART2_IRQn);
  if (HAL_UART_Receive_IT(&huart2,&rx_byte,1)!=HAL_OK) Error_Handler();
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
      IWDG->KR=0xaaaaU;
      ADS_Motor_Poll(HAL_GetTick());
      ADS_Sensors_Poll();
      if ((motor_test.running || motor_test.armed) && ADS_Motor_IsLatched())
        ADS_Test_Fault(&motor_test, HAL_GetTick(), "MCU_SHUTDOWN_LATCHED");
      ADS_Test_Poll(&motor_test, HAL_GetTick());
      ADS_Protocol_EmitMotorEvents(&ads_protocol);

#if ADS_PROTOCOL_LEGACY_BANNER_ENABLED
      char msg[] = "STM32 CONNECTED TO PI\r\n";
      HAL_UART_Transmit(&huart2, (uint8_t *)msg, strlen(msg), 100U);
      HAL_Delay(1000);
#else
      ADS_ReceivePoll();
      ADS_Protocol_Poll(&ads_protocol);
#endif
	  }
  }
  /* USER CODE END 3 */

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  ADS_Motor_Fault(); ADS_Circuit_Fault();
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
