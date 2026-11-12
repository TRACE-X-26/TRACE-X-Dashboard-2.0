#ifndef ADS_ACQUISITION_H
#define ADS_ACQUISITION_H
#include "ads_protocol.h"
/* Pure conversions/cache, independent of HAL. Failed inputs immediately invalidate. */
typedef struct {
  ADS_Sample channels[5];
  ADS_MeasurementInfo info;
} ADS_Acquisition;
void ADS_Acquisition_Init(ADS_Acquisition *);
void ADS_Acquisition_Electrical(ADS_Acquisition *, uint16_t, int16_t, uint32_t, int,
                               uint32_t, uint32_t, int);
void ADS_Acquisition_Encoder(ADS_Acquisition *, int32_t, uint32_t, uint32_t,
                            uint32_t, uint32_t, int, uint32_t, int);
void ADS_Acquisition_Temperature(ADS_Acquisition *, const uint8_t *, int, uint32_t, uint32_t, int);
void ADS_Acquisition_Snapshot(ADS_Acquisition *, ADS_Sample *, uint32_t);
#endif
