#ifndef ADS_CIRCUIT_H
#define ADS_CIRCUIT_H
#include <stdint.h>
/* Circuit watchdog runs from SysTick as well as the main loop. */
void ADS_Circuit_Poll(uint32_t now_ms);
void ADS_Circuit_Fault(void);
#endif
