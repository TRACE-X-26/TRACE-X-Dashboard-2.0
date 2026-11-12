#ifndef ADS_SENSORS_H
#define ADS_SENSORS_H
#include "ads_protocol.h"
void ADS_Sensors_Init(void);
void ADS_Sensors_Poll(void);
void ADS_Sensors_Acquire(ADS_Sample samples[5], void *context);
void ADS_Sensors_Info(ADS_MeasurementInfo *, void *context);
void ADS_Sensors_Branches(ADS_ElectricalBranch branches[2], void *context);
int ADS_Sensors_Ready(void);
#endif
