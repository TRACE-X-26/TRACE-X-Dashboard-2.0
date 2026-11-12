#include "ads_protection.h"
#include <assert.h>
#include <string.h>
#include <stdint.h>
static void expect(ADS_Sample s[5], uint32_t now, const char *reason)
{
  const char *actual=ADS_Protection_Electrical(s,now);
  assert(reason ? actual && !strcmp(actual,reason) : !actual);
}
int main(void)
{
  ADS_Sample s[5]={0};
  for(unsigned i=0;i<3;i++) { s[i].valid=1;s[i].timestamp_ms=100; }
  s[0].milli_value=11900;s[1].milli_value=0;expect(s,100,0);
  s[0].milli_value=10000;expect(s,100,0);
  s[0].milli_value=14000;expect(s,100,0);
  s[0].milli_value=9999;expect(s,100,"SUPPLY_OUT_OF_RANGE");
  s[0].milli_value=14001;expect(s,100,"SUPPLY_OUT_OF_RANGE");
  s[0].milli_value=0;expect(s,100,"SUPPLY_OUT_OF_RANGE");
  s[0].milli_value=11900;
  s[1].milli_value=1499;expect(s,100,0);
  s[1].milli_value=1500;expect(s,100,"OVERCURRENT");
  s[1].milli_value=-1500;expect(s,100,"OVERCURRENT");
  s[1].milli_value=INT32_MIN;expect(s,100,"OVERCURRENT");
  s[1].milli_value=0;s[1].valid=0;expect(s,100,"INVALID_SENSOR_DATA");
  s[1].valid=1;expect(s,1601,"STALE_SENSOR_DATA");
  s[1].timestamp_ms=101;expect(s,101,"MIXED_ACQUISITION");
  for(unsigned i=0;i<3;i++)s[i].timestamp_ms=UINT32_MAX-100;
  expect(s,10,0); /* rollover-safe acquisition age */
  for(unsigned i=0;i<3;i++)s[i].timestamp_ms=100;
  s[0].milli_value=0;s[1].milli_value=0;
  assert(ADS_Protection_DownstreamSample(s,49,0,100)==0);
  assert(ADS_Protection_DownstreamSample(s,50,0,100)==-1);
  s[0].milli_value=11900;
  assert(ADS_Protection_DownstreamSample(s,49,0,100)==0);
  assert(ADS_Protection_DownstreamSample(s,50,0,100)==1);
  s[1].milli_value=1500;
  assert(ADS_Protection_DownstreamSample(s,0,0,100)==-1);
  s[1].milli_value=0;s[0].valid=0;
  assert(ADS_Protection_DownstreamSample(s,0,0,100)==-1);
  return 0;
}
