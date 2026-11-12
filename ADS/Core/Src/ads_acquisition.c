#include "ads_acquisition.h"
#include <string.h>
#include <limits.h>
void ADS_Acquisition_Init(ADS_Acquisition *a)
{ memset(a,0,sizeof(*a)); a->info.encoder_direction="UNKNOWN"; }
void ADS_Acquisition_Electrical(ADS_Acquisition *a, uint16_t bus, int16_t shunt,
                               uint32_t shunt_mohms, int ok, uint32_t begin, uint32_t end, int calibrated)
{
  a->info.sample_sequence++; a->info.electrical_sequence++;
  a->info.electrical_started_ms=begin; a->info.electrical_completed_ms=end;
  a->info.voltage_current_calibrated=calibrated!=0;
  for(unsigned i=0;i<3;i++) a->channels[i]=(ADS_Sample){0,end,0};
  /* CNVR set, OVF clear; board adapter triggers one shunt+bus conversion
   * then reads both held registers. Shunt and bus are sequential ADC samples. */
  /* Validity describes acquisition; calibration remains separate metadata.
   * The motor readiness gate still requires verified electrical calibration. */
  if(!ok || !shunt_mohms || !(bus&2U) || (bus&1U) || (uint32_t)(end-begin)>20U) return;
  int32_t mv=(int32_t)(bus>>3)*4;
  int32_t ma=(int32_t)((int64_t)shunt*10/shunt_mohms);
  int64_t mw=(int64_t)mv*ma/1000;
  a->channels[0]=(ADS_Sample){mv,end,1};
  a->channels[1]=(ADS_Sample){ma,end,1};
  if(mw>=INT32_MIN && mw<=INT32_MAX) a->channels[2]=(ADS_Sample){(int32_t)mw,end,1};
}
void ADS_Acquisition_Encoder(ADS_Acquisition *a, int32_t delta, uint32_t elapsed,
                            uint32_t cpr, uint32_t gear_num, uint32_t gear_den,
                            int sign, uint32_t now, int calibrated)
{
  a->info.encoder_started_ms=now-elapsed; a->info.encoder_completed_ms=now;
  a->info.sample_sequence++; a->info.encoder_calibrated=calibrated!=0;
  a->channels[4]=(ADS_Sample){0,now,0}; a->info.encoder_direction="UNKNOWN";
  /* Provisional conversion is useful telemetry; calibration stays explicit. */
  if(!elapsed || elapsed>2000 || !cpr || !gear_num || !gear_den ||
     (sign!=1 && sign!=-1) || cpr>1000000 || gear_num>10000 || gear_den>10000 ||
     delta>1000000 || delta< -1000000) return;
  int64_t rpm_milli=(int64_t)delta*60000000LL*gear_den*sign/((int64_t)cpr*elapsed*gear_num);
  if(rpm_milli<INT32_MIN || rpm_milli>INT32_MAX) return;
  a->channels[4]=(ADS_Sample){(int32_t)rpm_milli,now,1};
  a->info.encoder_direction=rpm_milli>0?"FORWARD":rpm_milli<0?"REVERSE":"STATIONARY";
}
void ADS_Acquisition_Temperature(ADS_Acquisition *a, const uint8_t *scratch, int converted,
                               uint32_t started, uint32_t now, int calibrated)
{
  a->info.temperature_started_ms=started; a->info.temperature_completed_ms=now;
  uint8_t crc=0;
  a->info.sample_sequence++; a->info.temperature_calibrated=calibrated!=0;
  a->channels[3]=(ADS_Sample){0,now,0};
  if(!converted || !scratch) return;
  for(unsigned i=0;i<8;i++) {
    uint8_t v=scratch[i];
    for(unsigned bit=0;bit<8;bit++) { uint8_t mix=(crc^v)&1U; crc>>=1; if(mix)crc^=0x8cU; v>>=1; }
  }
  if(crc!=scratch[8] || scratch[5]!=0xffU || scratch[6]!=0x0cU || scratch[7]!=0x10U) return;
  int16_t raw=(int16_t)(((uint16_t)scratch[1]<<8)|scratch[0]);
  unsigned resolution=(scratch[4]>>5)&3U;
  if((scratch[4]&0x9fU)!=0x1fU) return;
  raw=(int16_t)((uint16_t)raw & (uint16_t)~((1U<<(3U-resolution))-1U));
  if(raw< -55*16 || raw>125*16) return;
  /* 0 C is valid; validity never depends on the value being nonzero. */
  a->channels[3]=(ADS_Sample){(int32_t)raw*1000/16,now,1};
}
void ADS_Acquisition_Snapshot(ADS_Acquisition *a, ADS_Sample *out, uint32_t now)
{
  memcpy(out,a->channels,sizeof(a->channels));
  for(unsigned i=0;i<5;i++) if((uint32_t)(now-out[i].timestamp_ms)>(i==3?3000U:1500U)) out[i].valid=0;
}
