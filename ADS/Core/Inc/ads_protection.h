#ifndef ADS_PROTECTION_H
#define ADS_PROTECTION_H
#include "ads_protocol.h"
/* NULL only for fresh, same-acquisition, in-range motor electrical samples. */
const char *ADS_Protection_Electrical(const ADS_Sample samples[5], uint32_t now);
int ADS_Protection_DownstreamSample(const ADS_Sample samples[5], uint32_t acquisition_started, uint32_t relay_started, uint32_t now);
#endif
