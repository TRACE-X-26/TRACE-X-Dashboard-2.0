#include "ads_protection.h"
#include "ads_board_config.h"
const char *ADS_Protection_Electrical(const ADS_Sample s[5], uint32_t now)
{
  for(unsigned i=0;i<3;i++) {
    if(!s[i].valid) return "INVALID_SENSOR_DATA";
    if((uint32_t)(now-s[i].timestamp_ms)>1500U) return "STALE_SENSOR_DATA";
    if(s[i].timestamp_ms!=s[0].timestamp_ms) return "MIXED_ACQUISITION";
  }
  if(s[0].milli_value<(int32_t)ADS_MOTOR_MIN_VOLTAGE_MV ||
     s[0].milli_value>(int32_t)ADS_MOTOR_MAX_VOLTAGE_MV) return "SUPPLY_OUT_OF_RANGE";
  int64_t current=s[1].milli_value;
  if(current<0) current=-current;
  if(current>=(int64_t)ADS_MOTOR_MAX_CURRENT_MA) return "OVERCURRENT";
  return 0;
}

int ADS_Protection_DownstreamSample(const ADS_Sample s[5], uint32_t acquisition_started, uint32_t relay_started, uint32_t now)
{
  for(unsigned i=0;i<3;i++)
    if(!s[i].valid || (uint32_t)(now-s[i].timestamp_ms)>1500U || s[i].timestamp_ms!=s[0].timestamp_ms) return -1;
  int64_t current=s[1].milli_value;if(current<0)current=-current;
  if(current>=(int64_t)ADS_MOTOR_MAX_CURRENT_MA || s[0].milli_value<0 || s[0].milli_value>(int32_t)ADS_MOTOR_MAX_VOLTAGE_MV) return -1;
  if((int32_t)(acquisition_started-relay_started)<(int32_t)ADS_POWER_CHECK_SETTLE_MS) return 0;
  return ADS_Protection_Electrical(s,now) ? -1 : 1;
}
