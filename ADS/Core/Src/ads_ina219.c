#include "ads_ina219.h"
#include <string.h>
void ADS_INA219_Init(ADS_INA219 *s, uint8_t address, uint32_t shunt, int calibrated)
{
  memset(s,0,sizeof(*s)); ADS_Acquisition_Init(&s->acquisition);
  s->address=address; s->shunt_mohms=shunt; s->calibrated=calibrated!=0;
  s->status="NOT_INITIALIZED";
}
static void finish(ADS_INA219 *s, int ok, uint16_t bus, int16_t shunt, uint32_t now, const char *status)
{
  ADS_Acquisition_Electrical(&s->acquisition,bus,shunt,s->shunt_mohms,ok,
                           s->started,now,s->calibrated);
  s->pending=0; s->status=status;
}
void ADS_INA219_Poll(ADS_INA219 *s, const ADS_INA219_Bus *bus)
{
  uint32_t now=bus->tick(bus->context);
  uint16_t address=(uint16_t)s->address<<1;
  if (!s->pending) {
    if (s->attempted && (uint32_t)(now-s->last_attempt)<100U) return;
    s->attempted=1; s->last_attempt=now; s->started=now;
    s->connected=bus->ready(address,bus->context)!=0;
    if (!s->connected) {
      s->configured=0; finish(s,0,0,0,bus->tick(bus->context),"NOT_CONNECTED"); return;
    }
    /* Trigger one held shunt+bus pair. Every sensor is configured independently. */
    s->started=bus->tick(bus->context);
    s->configured=bus->write(address,0,0x399bU,bus->context)!=0;
    if (!s->configured) { finish(s,0,0,0,bus->tick(bus->context),"CONFIG_ERROR"); return; }
    s->pending=1; s->status="CONNECTED"; return;
  }
  uint16_t voltage=0,shunt=0;
  if (!bus->read(address,2,&voltage,bus->context)) {
    /* Presence is distinct from a failed register read. No other address is tried. */
    s->connected=bus->ready(address,bus->context)!=0;
    finish(s,0,0,0,bus->tick(bus->context),s->connected?"READ_ERROR":"NOT_CONNECTED"); return;
  }
  now=bus->tick(bus->context);
  if ((uint32_t)(now-s->started)>20U) { finish(s,0,0,0,now,"CONVERSION_TIMEOUT"); return; }
  if (voltage&1U) { finish(s,0,0,0,now,"OVERFLOW"); return; }
  if (!(voltage&2U)) return;
  if (!bus->read(address,1,&shunt,bus->context)) {
    s->connected=bus->ready(address,bus->context)!=0;
    finish(s,0,0,0,bus->tick(bus->context),s->connected?"READ_ERROR":"NOT_CONNECTED"); return;
  }
  now=bus->tick(bus->context);
  finish(s,(uint32_t)(now-s->started)<=20U,voltage,(int16_t)shunt,now,
         (uint32_t)(now-s->started)<=20U?"CONNECTED":"CONVERSION_TIMEOUT");
}
void ADS_INA219_Snapshot(ADS_INA219 *s, ADS_ElectricalBranch *out, uint32_t now)
{
  ADS_Sample channels[5]; ADS_Acquisition_Snapshot(&s->acquisition,channels,now);
  memset(out,0,sizeof(*out)); memcpy(out->samples,channels,sizeof(out->samples));
  out->address=s->address; out->connected=s->connected; out->configured=s->configured;
  out->calibrated=s->calibrated; out->status=s->status;
  out->sequence=s->acquisition.info.electrical_sequence;
  out->started_ms=s->acquisition.info.electrical_started_ms;
  out->completed_ms=s->acquisition.info.electrical_completed_ms;
  if (out->sequence && (uint32_t)(now-out->completed_ms)>1500U) out->status="STALE";
}
