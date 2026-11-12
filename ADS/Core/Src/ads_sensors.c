#include "main.h"
#include "ads_sensors.h"
#include "ads_acquisition.h"
#include "ads_ina219.h"
#include "ads_protection.h"
#include "ads_motor.h"
static ADS_INA219 motor_ina, circuit_ina;
#include "ads_board_config.h"
#include <string.h>
static ADS_Acquisition cache;
#if ADS_SENSOR_WIRING_VERIFIED
/* Ported from /Users/markussanford/ADS/Core/Src/main.c. This is available source,
 * not proof of what is flashed. Independent INA219 instances share I2C1. */
static I2C_HandleTypeDef i2c;
static uint8_t initialized;
#if ADS_TEMPERATURE_ENABLED
static uint8_t conversion_active;
static uint32_t temperature_last;
#endif
static uint32_t encoder_last;
static volatile uint32_t encoder_count;
#if ADS_TEMPERATURE_ENABLED
static void delay_us(uint32_t us)
{
  uint32_t start=DWT->CYCCNT, cycles=(SystemCoreClock/1000000U)*us;
  while((uint32_t)(DWT->CYCCNT-start)<cycles) {}
}
static void low(void) { HAL_GPIO_WritePin(GPIOA,GPIO_PIN_10,GPIO_PIN_RESET); }
static void release(void) { HAL_GPIO_WritePin(GPIOA,GPIO_PIN_10,GPIO_PIN_SET); }
static int presence(void)
{
  /* Keep the 480us reset pulse interruptible; only sample edge timing is masked.
   * Each bit masks <70us, never the 750ms conversion. Bench timing required. */
  low(); delay_us(480);
  uint32_t irq=__get_PRIMASK(); __disable_irq();
  release(); delay_us(70);
  int found=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_10)==GPIO_PIN_RESET;
  __set_PRIMASK(irq); delay_us(410); return found;
}
static void write_byte(uint8_t value)
{
  for(unsigned bit=0;bit<8;bit++) {
    uint32_t irq=__get_PRIMASK(); __disable_irq();
    low(); delay_us(value&1U?6:60); release(); delay_us(value&1U?64:10);
    __set_PRIMASK(irq); value>>=1;
  }
}
static uint8_t read_byte(void)
{
  uint8_t value=0;
  for(unsigned bit=0;bit<8;bit++) {
    uint32_t irq=__get_PRIMASK(); __disable_irq();
    low(); delay_us(6); release(); delay_us(9);
    if(HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_10)==GPIO_PIN_SET) value|=(uint8_t)(1U<<bit);
    delay_us(55); __set_PRIMASK(irq);
  }
  return value;
}
#endif
static int ina_ready(uint16_t address,void *context)
{ (void)context; return initialized && HAL_I2C_IsDeviceReady(&i2c,address,1,3)==HAL_OK; }
static int ina_write(uint16_t address,uint8_t reg,uint16_t value,void *context)
{
  (void)context; uint8_t bytes[2]={(uint8_t)(value>>8),(uint8_t)value};
  return HAL_I2C_Mem_Write(&i2c,address,reg,I2C_MEMADD_SIZE_8BIT,bytes,2,3)==HAL_OK;
}
static int ina_read(uint16_t address,uint8_t reg,uint16_t *value,void *context)
{
  (void)context; uint8_t bytes[2];
  if(HAL_I2C_Mem_Read(&i2c,address,reg,I2C_MEMADD_SIZE_8BIT,bytes,2,3)!=HAL_OK) return 0;
  *value=((uint16_t)bytes[0]<<8)|bytes[1]; return 1;
}
static uint32_t ina_tick(void *context) { (void)context; return HAL_GetTick(); }
static const ADS_INA219_Bus ina_bus={ina_ready,ina_write,ina_read,ina_tick,NULL};
void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
  if(pin==GPIO_PIN_6) {
    /* A rising-edge x1 decoding; B level establishes signed rotation. */
    if(HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_6)==HAL_GPIO_ReadPin(GPIOC,GPIO_PIN_7)) encoder_count++;
    else encoder_count--;
  }
}
#endif
void ADS_Sensors_Init(void)
{
  ADS_Acquisition_Init(&cache);
  ADS_INA219_Init(&motor_ina,ADS_MOTOR_INA219_ADDRESS,ADS_INA219_SHUNT_MOHMS,ADS_INA219_CALIBRATED);
  ADS_INA219_Init(&circuit_ina,ADS_CIRCUIT_INA219_ADDRESS,ADS_CIRCUIT_INA219_SHUNT_MOHMS,ADS_CIRCUIT_INA219_CALIBRATED);
#if ADS_SENSOR_WIRING_VERIFIED
  GPIO_InitTypeDef gpio={0};
  __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_I2C1_CLK_ENABLE();
  gpio.Pin=GPIO_PIN_8|GPIO_PIN_9; gpio.Mode=GPIO_MODE_AF_OD; gpio.Pull=GPIO_NOPULL;
  gpio.Speed=GPIO_SPEED_FREQ_VERY_HIGH; gpio.Alternate=GPIO_AF4_I2C1; HAL_GPIO_Init(GPIOB,&gpio);
  i2c.Instance=I2C1; i2c.Init.ClockSpeed=100000; i2c.Init.DutyCycle=I2C_DUTYCYCLE_2;
  i2c.Init.AddressingMode=I2C_ADDRESSINGMODE_7BIT;
  initialized=HAL_I2C_Init(&i2c)==HAL_OK;
  gpio.Pin=GPIO_PIN_6; gpio.Mode=GPIO_MODE_IT_RISING; HAL_GPIO_Init(GPIOA,&gpio);
  gpio.Pin=GPIO_PIN_7; gpio.Mode=GPIO_MODE_INPUT; HAL_GPIO_Init(GPIOC,&gpio);
  HAL_NVIC_SetPriority(EXTI9_5_IRQn,2,0); HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
#if ADS_TEMPERATURE_ENABLED
  gpio.Pin=GPIO_PIN_10; gpio.Mode=GPIO_MODE_OUTPUT_OD; gpio.Speed=GPIO_SPEED_FREQ_HIGH;
  /* Preload released level. External 3.3V pullup and non-parasite supply required. */
  release(); HAL_GPIO_Init(GPIOA,&gpio);
  CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT=0; DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
  temperature_last=HAL_GetTick();
#endif
  encoder_last=HAL_GetTick();
#endif
}
void ADS_Sensors_Poll(void)
{
#if ADS_SENSOR_WIRING_VERIFIED
  uint32_t now=HAL_GetTick();
  ADS_INA219_Poll(&motor_ina,&ina_bus); /* Motor first; independent timestamps. */
  ADS_INA219_Poll(&circuit_ina,&ina_bus);
  if (cache.info.electrical_sequence!=motor_ina.acquisition.info.electrical_sequence) {
    uint32_t irq=__get_PRIMASK(); __disable_irq();
    memcpy(cache.channels,motor_ina.acquisition.channels,3*sizeof(ADS_Sample));
    cache.info.sample_sequence++;
    cache.info.electrical_sequence=motor_ina.acquisition.info.electrical_sequence;
    cache.info.electrical_started_ms=motor_ina.acquisition.info.electrical_started_ms;
    cache.info.electrical_completed_ms=motor_ina.acquisition.info.electrical_completed_ms;
    cache.info.voltage_current_calibrated=motor_ina.calibrated;
    __set_PRIMASK(irq);
  }
  if((uint32_t)(now-encoder_last)>=1000U) {
    uint32_t irq=__get_PRIMASK(); __disable_irq();
    int32_t delta=(int32_t)encoder_count; encoder_count=0; __set_PRIMASK(irq);
    ADS_Acquisition_Encoder(&cache,delta,now-encoder_last,ADS_ENCODER_A_COUNTS_PER_REV,
      ADS_ENCODER_GEAR_NUM,ADS_ENCODER_GEAR_DEN,ADS_ENCODER_FORWARD_SIGN,now,ADS_ENCODER_CALIBRATED);
    encoder_last=now;
  }
#if ADS_TEMPERATURE_ENABLED
  if(!conversion_active && (uint32_t)(now-temperature_last)>=1000U) {
    if(presence()) { write_byte(0xcc); write_byte(0x44); conversion_active=1; }
    else ADS_Acquisition_Temperature(&cache,NULL,0,now,now,ADS_TEMPERATURE_CALIBRATED);
    temperature_last=now;
  } else if(conversion_active && (uint32_t)(now-temperature_last)>=750U) {
    uint8_t scratch[9]; int done=0;
    /* Read conversion completion bit before reset; reject stuck-low/unfinished. */
    if(read_byte()==0xffU && presence()) {
      write_byte(0xcc); write_byte(0xbe);
      for(unsigned i=0;i<9;i++) scratch[i]=read_byte();
      done=1;
    }
    ADS_Acquisition_Temperature(&cache,scratch,done,temperature_last,HAL_GetTick(),ADS_TEMPERATURE_CALIBRATED);
    conversion_active=0; temperature_last=now;
  }
#endif
#endif
}
void ADS_Sensors_Acquire(ADS_Sample samples[5], void *context)
{ (void)context; ADS_Acquisition_Snapshot(&cache,samples,HAL_GetTick()); }
void ADS_Sensors_Info(ADS_MeasurementInfo *info, void *context)
{ (void)context; *info=cache.info; }
void ADS_Sensors_Branches(ADS_ElectricalBranch out[2], void *context)
{
  (void)context; uint32_t now=HAL_GetTick();
  ADS_INA219_Snapshot(&motor_ina,&out[0],now);
  ADS_INA219_Snapshot(&circuit_ina,&out[1],now);
}
int ADS_Sensors_Ready(void)
{
  ADS_Sample s[5]; ADS_Sensors_Acquire(s,NULL);
  if(!ADS_INA219_CALIBRATED) return 0;
  if(ADS_TEMPERATURE_ENABLED && !ADS_TEMPERATURE_CALIBRATED) return 0;
  if(!s[0].valid || !s[1].valid || !s[4].valid || (ADS_TEMPERATURE_ENABLED && !s[3].valid)) return 0;
  if(!ADS_PROTECTION_LIMITS_VERIFIED) return 0;
  if(ADS_Protection_Electrical(s,HAL_GetTick())) return 0;
  return !ADS_TEMPERATURE_ENABLED || (ADS_MOTOR_MAX_TEMPERATURE_MC>0 && s[3].milli_value<ADS_MOTOR_MAX_TEMPERATURE_MC);
}

/* Strong board implementation; the output driver fails closed if absent. */
int ADS_Motor_ProtectionReady(void) { return ADS_Sensors_Ready(); }

int ADS_Motor_IdleReady(void)
{
  ADS_Sample s[5];ADS_Sensors_Acquire(s,0);
  if(!ADS_INA219_CALIBRATED || !ADS_PROTECTION_LIMITS_VERIFIED || !s[4].valid || s[4].milli_value!=0) return 0;
  /* Before the relay closes, zero voltage is expected, not a range pass. */
  for(unsigned i=0;i<3;i++) if(!s[i].valid || s[i].timestamp_ms!=s[0].timestamp_ms) return 0;
  int64_t current=s[1].milli_value;if(current<0)current=-current;
  if(ADS_Motor_PowerState()==0 && s[0].milli_value>=(int32_t)ADS_MOTOR_MIN_VOLTAGE_MV) return 0;
  return s[0].milli_value>=0 && s[0].milli_value<=(int32_t)ADS_MOTOR_MAX_VOLTAGE_MV && current<(int64_t)ADS_MOTOR_MAX_CURRENT_MA;
}
int ADS_Motor_PowerSampleState(uint32_t powered_ms)
{
  ADS_Sample s[5];ADS_Sensors_Acquire(s,0);
  return ADS_Protection_DownstreamSample(s,cache.info.electrical_started_ms,powered_ms,HAL_GetTick());
}
