#ifndef TEST_HAL_H
#define TEST_HAL_H
#include <stdint.h>
typedef struct { unsigned port; } GPIO_TypeDef;
extern GPIO_TypeDef test_gpio_a, test_gpio_b, test_gpio_c;
#define GPIOA (&test_gpio_a)
#define GPIOB (&test_gpio_b)
#define GPIOC (&test_gpio_c)
#define GPIO_PIN_4 (1U << 4)
#define GPIO_PIN_5 (1U << 5)
#define GPIO_PIN_8 (1U << 8)
#define GPIO_PIN_10 (1U << 10)
#define GPIO_MODE_AF_PP 2U
#define GPIO_AF1_TIM2 1U
#define GPIO_MODE_INPUT 0U
#define GPIO_MODE_OUTPUT_PP 1U
#define GPIO_NOPULL 0U
#define GPIO_PULLDOWN 2U
#define __HAL_RCC_GPIOC_CLK_ENABLE() ((void)0)
#define GPIO_SPEED_FREQ_LOW 0U
typedef enum { GPIO_PIN_RESET, GPIO_PIN_SET } GPIO_PinState;
typedef struct { uint32_t Pin, Mode, Pull, Speed, Alternate; } GPIO_InitTypeDef;
typedef struct { volatile uint32_t CR1, CCER, CCR3, PSC, ARR, CNT, CCMR2, EGR; } TIM_TypeDef;
extern TIM_TypeDef test_tim2;
#define TIM2 (&test_tim2)
#define TIM_CCER_CC3E (1U << 8)
#define TIM_CR1_CEN 1U
#define TIM_CR1_ARPE (1U<<7)
#define TIM_CCMR2_OC3PE (1U<<3)
#define TIM_EGR_UG 1U
#define __HAL_RCC_GPIOA_CLK_ENABLE() ((void)0)
static inline uint32_t HAL_RCC_GetPCLK1Freq(void) { return 42000000U; }
void test_enable_tim2(void);
#define __HAL_RCC_TIM2_CLK_ENABLE() test_enable_tim2()
uint32_t HAL_GetTick(void);
void test_enable_gpio_b(void);
#define __HAL_RCC_GPIOB_CLK_ENABLE() test_enable_gpio_b()
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *,uint16_t);
void HAL_GPIO_WritePin(GPIO_TypeDef *, uint16_t, GPIO_PinState);
void HAL_GPIO_Init(GPIO_TypeDef *, GPIO_InitTypeDef *);
#endif
