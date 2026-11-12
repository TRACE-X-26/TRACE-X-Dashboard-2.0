#include "ads_protocol.h"
#include "ads_acquisition.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint32_t now;
static unsigned starts,stops;
static int sensors_ok=1;
static int fake_power;
static uint32_t fake_power_started;
static int prepare_power(void *ctx) { (void)ctx;fake_power=1;fake_power_started=now;return 1; }
static int power_state(void *ctx) { (void)ctx;return now-fake_power_started>=1500U ? 0 : fake_power; }
static ADS_Test *motor_branch, *circuit_branch;
static int ready(void *ctx) {
  if(ctx==motor_branch && circuit_branch && (circuit_branch->armed || circuit_branch->running)) return 0;
  if(ctx==circuit_branch && motor_branch && (motor_branch->armed || motor_branch->running)) return 0;
  return sensors_ok;
}
static int start(uint32_t p,uint32_t d,void *ctx)
{ (void)ctx; assert((p==10 || p==25 || p==50 || p==75 || p==100) && d<=30000); starts++; return 1; }
static void stop(void *ctx) { (void)ctx; stops++; }
static uint32_t tick(void *ctx) { (void)ctx; return now; }
static int transmit(const uint8_t *b,size_t n,void *ctx)
{ (void)ctx; return fwrite(b,1,n,stdout)==n?0:-1; }
static int command(ADS_Test *t,const char *c,uint32_t seq,uint32_t pwm,uint32_t duration)
{ const char *why; return ADS_Test_Command(t,c,seq,pwm,duration,"FORWARD",now,&why); }
static void zero_scratch(uint8_t s[9])
{
  memset(s,0,9); s[4]=0x7f; s[5]=0xff; s[6]=0x0c; s[7]=0x10;
  uint8_t crc=0;
  for(unsigned i=0;i<8;i++) { uint8_t v=s[i]; for(unsigned j=0;j<8;j++) { uint8_t mix=(crc^v)&1U; crc>>=1; if(mix)crc^=0x8c; v>>=1; } }
  s[8]=crc;
}
static void conversions(void)
{
  ADS_Acquisition a; ADS_Sample s[5];
  uint8_t zero[9]; zero_scratch(zero);
  ADS_Acquisition_Init(&a);
  ADS_Acquisition_Temperature(&a,zero,1,0,0,0);
  assert(a.channels[3].valid && a.channels[3].milli_value==0);
  assert(!a.info.temperature_calibrated);
  zero[8]^=1;
  ADS_Acquisition_Temperature(&a,zero,1,1,1,1); assert(!a.channels[3].valid);
  ADS_Acquisition_Temperature(&a,NULL,0,2,2,1); assert(!a.channels[3].valid);
  ADS_Acquisition_Electrical(&a,(3000U<<3)|2,1000,100,1,10,12,1);
  assert(a.channels[0].milli_value==12000 && a.channels[1].milli_value==100);
  assert(a.channels[2].milli_value==1200 && a.channels[0].timestamp_ms==a.channels[1].timestamp_ms);
  ADS_Acquisition_Electrical(&a,2,0,100,1,13,13,1);
  assert(a.channels[0].valid && a.channels[1].valid && a.channels[1].milli_value==0);
  ADS_Acquisition_Electrical(&a,3,0,100,1,13,13,1); assert(!a.channels[0].valid);
  ADS_Acquisition_Electrical(&a,2,0,100,1,13,13,0);
  assert(a.channels[0].valid && !a.info.voltage_current_calibrated);
  ADS_Acquisition_Electrical(&a,2,0,100,0,13,13,1); assert(!a.channels[0].valid);
  ADS_Acquisition_Encoder(&a,400,1000,400,1,1,1,20,1);
  assert(a.channels[4].milli_value==60000 && !strcmp(a.info.encoder_direction,"FORWARD"));
  ADS_Acquisition_Encoder(&a,-400,1000,400,2,1,1,20,1);
  assert(a.channels[4].milli_value== -30000 && !strcmp(a.info.encoder_direction,"REVERSE"));
  ADS_Acquisition_Encoder(&a,0,1000,400,1,1,1,20,1);
  assert(a.channels[4].valid && a.channels[4].milli_value==0);
  ADS_Acquisition_Encoder(&a,374,1000,11,34,1,1,20,0);
  assert(a.channels[4].valid && a.channels[4].milli_value==60000);
  assert(!a.info.encoder_calibrated); /* Assumed 374/output rev stays provisional. */
  ADS_Acquisition_Snapshot(&a,s,1521); assert(!s[4].valid);
  ADS_Acquisition_Encoder(&a,10,1000,0,1,1,1,20,0); assert(!a.channels[4].valid);
}
static void scenarios(void)
{
  ADS_Test t; const char *reason;
  conversions();
  ADS_Test_Init(&t,10,1000,0,ready,start,stop,NULL);
  assert(!command(&t,"ARM_TEST",1,0,0)); assert(!starts);
  assert(command(&t,"STOP_TEST",2,0,0));
  ADS_Test_Init(&t,10,1000,1,ready,start,stop,NULL);
  assert(!command(&t,"ARM_TEST",1,0,0));
  ADS_Test_Heartbeat(&t,0); assert(command(&t,"ARM_TEST",2,0,0));
  assert(!command(&t,"SET_PWM",3,11,0)); assert(t.applied_pwm==0);
  assert(command(&t,"SET_PWM",4,10,0)); assert(t.applied_pwm==0);
  assert(!command(&t,"START_TEST",5,10,1001));
  assert(command(&t,"START_TEST",6,10,1000)); assert(starts==1);
  assert(!command(&t,"START_TEST",6,10,1000)); assert(starts==1 && t.started_ms==0);
  assert(!command(&t,"START_TEST",7,10,1000)); assert(starts==1);
  assert(!ADS_Test_Command(&t,"SET_DIRECTION",8,0,0,"REVERSE",0,&reason));
  now=999; ADS_Test_Poll(&t,now); assert(t.running);
  now=1000; ADS_Test_Poll(&t,now); assert(!t.running && t.stop_event_seq==2);
  assert(!command(&t,"START_TEST",9,10,1000));
  assert(!command(&t,"ARM_TEST",10,0,0)); /* new heartbeat for each explicit arm */
  ADS_Test_Heartbeat(&t,now); assert(command(&t,"ARM_TEST",11,0,0));
  assert(command(&t,"START_TEST",12,10,1000));
  assert(command(&t,"STOP_TEST",13,0,0)); uint32_t event=t.stop_event_seq;
  assert(command(&t,"STOP_TEST",13,0,0)); assert(t.stop_event_seq==event);
  ADS_Test_Heartbeat(&t,now); assert(command(&t,"ARM_TEST",14,0,0));
  ADS_Test_Fault(&t,now,"TEST_FAULT"); assert(t.locked && !t.applied_pwm);
  assert(!command(&t,"START_TEST",15,10,1000));
  ADS_Test_Heartbeat(&t,now); assert(t.locked); assert(command(&t,"ARM_TEST",16,0,0));
  now=3000; ADS_Test_Heartbeat(&t,now); assert(t.locked); /* exact 2s loss; late HB doesn't rearm */
  assert(!command(&t,"START_TEST",17,10,1000));
  sensors_ok=0; assert(!command(&t,"ARM_TEST",18,0,0));
  sensors_ok=1; assert(command(&t,"ARM_TEST",19,0,0));
  assert(command(&t,"START_TEST",20,10,1000)); sensors_ok=0;
  ADS_Test_Poll(&t,now); assert(t.locked && !t.running);
  sensors_ok=1; ADS_Test_Init(&t,10,1000,1,ready,start,stop,NULL);
  now=UINT32_MAX-500; ADS_Test_Heartbeat(&t,now); assert(command(&t,"ARM_TEST",1,0,0));
  assert(command(&t,"START_TEST",2,10,1000)); now+=1000;
  ADS_Test_Poll(&t,now); assert(!t.running && !t.locked);
  assert(stops>5);
  /* Each preset works only when explicitly selected as the approved duty. */
  const uint32_t presets[]={10,25,50,75,100};
  for(unsigned i=0;i<5;i++) {
    now=0; ADS_Test_Init(&t,presets[i],30000,1,ready,start,stop,NULL);
    ADS_Test_Heartbeat(&t,now); assert(command(&t,"ARM_TEST",1,0,0));
    assert(!command(&t,"SET_PWM",2,presets[(i+1)%5],0));
    assert(command(&t,"START_TEST",3,presets[i],30000));
    for(now=1000;now<30000;now+=1000) ADS_Test_Heartbeat(&t,now);
    ADS_Test_Poll(&t,30000);
    assert(!t.running && !t.applied_pwm && !strcmp(t.reason,"COMPLETED"));
    assert(!command(&t,"START_TEST",3,presets[i],30000));
    assert(!t.running); /* Replay cannot restart after normal completion. */
  }
}
static ADS_Acquisition data;
static void acquire(ADS_Sample out[5],void *ctx)
{ (void)ctx; ADS_Acquisition_Snapshot(&data,out,now); }
static void info(ADS_MeasurementInfo *out,void *ctx) { (void)ctx; *out=data.info; }
int main(int argc,char **argv)
{
  if(argc==1) { scenarios(); return 0; }
  ADS_Test t,circuit; ADS_Protocol p;
  ADS_Test_Init(&t,10,1000,strcmp(argv[1],"disabled")!=0,ready,start,stop,NULL);
  if(!strcmp(argv[1],"downstream")) { t.power_required=1;t.prepare_power=prepare_power;t.power_state=power_state; }
  t.supervised_required=!strcmp(argv[1],"supervised");
  ADS_Protocol_Init(&p,transmit,tick,NULL); ADS_Protocol_SetMotorTest(&p,&t);
  if(!strcmp(argv[1],"crc")) p.require_crc=1;
  if(!strcmp(argv[1],"circuit") || !strcmp(argv[1],"circuit-disabled")) {
    motor_branch=&t; circuit_branch=&circuit; t.context=&t;
    ADS_Test_Init(&circuit,100,30000,strcmp(argv[1],"circuit-disabled")!=0,ready,start,stop,&circuit);
    circuit.supervised_required=1;
    ADS_Protocol_SetCircuitTest(&p,&circuit);
  }
  ADS_Acquisition_Init(&data);
  ADS_Acquisition_Electrical(&data,(3000U<<3)|2,0,100,1,0,0,1);
  uint8_t zero[9]; zero_scratch(zero); ADS_Acquisition_Temperature(&data,zero,1,0,0,1);
  ADS_Acquisition_Encoder(&data,0,1000,400,1,1,1,0,1);
  ADS_Protocol_SetHardwareCallbacks(&p,acquire,NULL);
  ADS_Protocol_SetMeasurementInfo(&p,info);
  int ch; while((ch=getchar())!=EOF) {
    if(ch=='+') { fake_power=2;ADS_Protocol_Poll(&p); }
    else if(ch=='!') { sensors_ok=0; ADS_Protocol_Poll(&p); }
    else if(ch=='@') { now+=1000; ADS_Protocol_Poll(&p); }
    else ADS_Protocol_ProcessByte(&p,(uint8_t)ch);
  }
  return 0;
}
