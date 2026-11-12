#ifndef ADS_INA219_H
#define ADS_INA219_H
#include "ads_acquisition.h"
/* Bus adapters receive HAL-style addresses (7-bit address shifted once). */
typedef struct {
  int (*ready)(uint16_t, void *);
  int (*write)(uint16_t, uint8_t, uint16_t, void *);
  int (*read)(uint16_t, uint8_t, uint16_t *, void *);
  uint32_t (*tick)(void *);
  void *context;
} ADS_INA219_Bus;
typedef struct {
  ADS_Acquisition acquisition;
  uint32_t shunt_mohms, last_attempt, started;
  uint8_t address, calibrated, connected, configured, pending, attempted;
  const char *status;
} ADS_INA219;
void ADS_INA219_Init(ADS_INA219 *, uint8_t, uint32_t, int);
void ADS_INA219_Poll(ADS_INA219 *, const ADS_INA219_Bus *);
void ADS_INA219_Snapshot(ADS_INA219 *, ADS_ElectricalBranch *, uint32_t);
#endif
