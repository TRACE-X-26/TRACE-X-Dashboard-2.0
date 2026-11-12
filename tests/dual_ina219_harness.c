#include "ads_ina219.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static ADS_INA219 sensors[2];
static uint32_t now;
static int present[2]={1,1},read_error[2],timeout[2],overflow[2],zero[2],writes[2];
static unsigned index_for(uint16_t address)
{ assert(address==0x80 || address==0x82); return address==0x80?0:1; }
static int ready(uint16_t address,void *ctx)
{ (void)ctx; return present[index_for(address)]; }
static int write_reg(uint16_t address,uint8_t reg,uint16_t value,void *ctx)
{
  (void)ctx; unsigned i=index_for(address); assert(reg==0 && value==0x399b);
  writes[i]++; return present[i];
}
static int read_reg(uint16_t address,uint8_t reg,uint16_t *value,void *ctx)
{
  (void)ctx; unsigned i=index_for(address);
  if(!present[i] || read_error[i]) return 0;
  if(reg==2) *value=(uint16_t)(((zero[i]?0:(i?1250:3000))<<3)|(timeout[i]?0:2)|(overflow[i]?1:0));
  else { assert(reg==1); *value=(uint16_t)(zero[i]?0:(i?-2000:1000)); }
  return 1;
}
static uint32_t tick(void *ctx) { (void)ctx;return now; }
static ADS_INA219_Bus bus={ready,write_reg,read_reg,tick,NULL};
static void poll(void) { ADS_INA219_Poll(&sensors[0],&bus);ADS_INA219_Poll(&sensors[1],&bus); }
static void branches(ADS_ElectricalBranch out[2],void *ctx)
{ (void)ctx;for(unsigned i=0;i<2;i++) ADS_INA219_Snapshot(&sensors[i],&out[i],now); }
static void acquire(ADS_Sample out[5],void *ctx)
{ (void)ctx; ADS_Acquisition_Snapshot(&sensors[0].acquisition,out,now); }
static int transmit(const uint8_t *data,size_t size,void *ctx)
{ (void)ctx; return fwrite(data,1,size,stdout)==size?0:-1; }
int main(int argc,char **argv)
{
  ADS_INA219_Init(&sensors[0],0x40,100,0);ADS_INA219_Init(&sensors[1],0x41,100,0);
  if(argc>1) {
    if(!strcmp(argv[1],"motor_missing")) present[0]=0;
    if(!strcmp(argv[1],"circuit_missing")) present[1]=0;
    if(!strcmp(argv[1],"zero")) zero[0]=zero[1]=1;
    if(!strcmp(argv[1],"timeout")) timeout[1]=1;
    if(!strcmp(argv[1],"overflow")) overflow[1]=1;
    if(!strcmp(argv[1],"read_error")) read_error[1]=1;
  }
  poll();now=2;poll();
  if(argc>1 && !strcmp(argv[1],"timeout")) {now=21;poll();}
  if(argc>1) {
    ADS_Protocol protocol;ADS_Protocol_Init(&protocol,transmit,tick,NULL);protocol.require_crc=1;
    ADS_Protocol_SetHardwareCallbacks(&protocol,acquire,NULL);ADS_Protocol_SetBranches(&protocol,branches);
    int byte;while((byte=getchar())!=EOF) ADS_Protocol_ProcessByte(&protocol,(uint8_t)byte);
    return 0;
  }
  ADS_ElectricalBranch out[2];branches(out,NULL);
  assert(writes[0]==1 && writes[1]==1);
  assert(out[0].samples[0].milli_value==12000 && out[1].samples[0].milli_value==5000);
  assert(out[0].samples[1].milli_value==100 && out[1].samples[1].milli_value==-200);
  assert(out[0].samples[2].milli_value==1200 && out[1].samples[2].milli_value==-1000);
  present[1]=0;now=100;poll();now=102;poll();branches(out,NULL);
  assert(out[0].samples[0].valid && !out[1].samples[0].valid && !out[1].connected);
  assert(!strcmp(out[1].status,"NOT_CONNECTED"));
  present[1]=1;present[0]=0;now=200;poll();now=202;poll();branches(out,NULL);
  assert(!out[0].samples[0].valid && out[1].samples[0].valid);
  now=1800;branches(out,NULL);assert(!out[1].samples[0].valid && !strcmp(out[1].status,"STALE"));
  return 0;
}
