#include "ads_protocol.h"
#include "ads_board_config.h"
#include "ads_motor.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ADS_DEVICE_ID "STM32-ADS"
#define ADS_FIRMWARE_VERSION "0.7.0-downstream-protected"

static uint32_t ADS_Protocol_Now(const ADS_Protocol *protocol)
{
  return protocol->tick != NULL ? protocol->tick(protocol->callback_context) : 0U;
}

/* Bounded JSON recognizer. Keys are resolved only in their owning object.
 * Escaped strings are deliberately rejected in this ASCII command subset. */
typedef struct { const char *start, *end; int parent; char kind; } Token;
static Token tokens[64];
static unsigned token_count;
static const char *cursor;
static void whitespace(void) { while (isspace((unsigned char)*cursor)) cursor++; }
static int parse_value(int parent, unsigned depth)
{
  unsigned index;
  char closing;
  if (depth > 8U || token_count >= 64U) return 0;
  whitespace();
  index = token_count++;
  tokens[index] = (Token){cursor, NULL, parent, *cursor};
  if (*cursor == '{' || *cursor == '[')
  {
    closing = *cursor++ == '{' ? '}' : ']';
    whitespace();
    if (*cursor != closing) for (;;)
    {
      if (closing == '}')
      {
        unsigned key = token_count, j;
        if (*cursor != '"' || !parse_value((int)index, depth + 1U)) return 0;
        for (j = index + 1U; j < key; j++)
          if (tokens[j].parent == (int)index && tokens[j].kind == 'K' &&
              tokens[j].end - tokens[j].start == tokens[key].end - tokens[key].start &&
              memcmp(tokens[j].start, tokens[key].start,
                     (size_t)(tokens[key].end - tokens[key].start)) == 0) return 0;
        tokens[key].kind = 'K';
        whitespace(); if (*cursor++ != ':') return 0;
      }
      if (!parse_value((int)index, depth + 1U)) return 0;
      whitespace();
      if (*cursor != ',') break;
      cursor++; whitespace();
    }
    if (*cursor++ != closing) return 0;
  }
  else if (*cursor == '"')
  {
    cursor++;
    while (*cursor && *cursor != '"')
    { if ((unsigned char)*cursor < 32U || *cursor == '\\' || (unsigned char)*cursor > 126U) return 0; cursor++; }
    if (*cursor++ != '"') return 0;
  }
  else if (*cursor == '-' || isdigit((unsigned char)*cursor))
  {
    if (*cursor == '-') cursor++;
    if (!isdigit((unsigned char)*cursor)) return 0;
    if (*cursor == '0' && isdigit((unsigned char)cursor[1])) return 0;
    while (isdigit((unsigned char)*cursor)) cursor++;
    if (*cursor == '.') {
      cursor++; if (!isdigit((unsigned char)*cursor)) return 0;
      while (isdigit((unsigned char)*cursor)) cursor++;
    }
    if (*cursor == 'e' || *cursor == 'E') {
      cursor++; if (*cursor=='+' || *cursor=='-') cursor++;
      if (!isdigit((unsigned char)*cursor)) return 0;
      while (isdigit((unsigned char)*cursor)) cursor++;
    }
  }
  else if (strncmp(cursor, "true", 4) == 0) cursor += 4;
  else if (strncmp(cursor, "false", 5) == 0) cursor += 5;
  else if (strncmp(cursor, "null", 4) == 0) cursor += 4;
  else return 0;
  tokens[index].end = cursor;
  return 1;
}
static const char *ADS_Protocol_FindValue(const char *json, const char *key)
{
  unsigned i;
  int parent = 0;
  (void)json;
  if (strcmp(key, "\"command\"") == 0 || strcmp(key, "\"arguments\"") == 0)
    for (i = 1; i + 1U < token_count; i++)
      if (tokens[i].parent == 0 && tokens[i].kind == 'K' &&
          tokens[i].end - tokens[i].start == 9 && memcmp(tokens[i].start, "\"payload\"", 9) == 0)
        { parent = (int)i + 1; break; }
  if (!strcmp(key, "\"pwm_percent\"") || !strcmp(key, "\"duration_ms\"") || !strcmp(key, "\"direction\"") || !strcmp(key, "\"supervised_confirmed\"")) {
    const char *args = ADS_Protocol_FindValue(json, "\"arguments\"");
    if (!args) return NULL;
    for (i=0; i<token_count; i++) if (tokens[i].start==args) { parent=(int)i; break; }
  }
  for (i = 1; i + 1U < token_count; i++)
    if (tokens[i].parent == parent && tokens[i].kind == 'K' &&
        (size_t)(tokens[i].end - tokens[i].start) == strlen(key) &&
        memcmp(tokens[i].start, key, strlen(key)) == 0) return tokens[i + 1U].start;
  return NULL;
}
static int ADS_Protocol_ReadUint32(const char *json, const char *key, uint32_t *value)
{
  const char *p = ADS_Protocol_FindValue(json, key);
  uint32_t n = 0;
  if (!p || !isdigit((unsigned char)*p)) return 0;
  while (isdigit((unsigned char)*p))
  { unsigned d = (unsigned)(*p++ - '0'); if (n > (UINT32_MAX - d) / 10U) return 0; n = n * 10U + d; }
  if (*p && *p!=',' && *p!='}' && !isspace((unsigned char)*p)) return 0;
  *value = n; return 1;
}
static int ADS_Protocol_ReadString(const char *json, const char *key, char *value, size_t size)
{
  const char *p = ADS_Protocol_FindValue(json, key), *end;
  size_t n;
  if (!p || *p != '"') return 0;
  end = strchr(++p, '"'); if (!end) return 0;
  n = (size_t)(end - p); if (n >= size) return 0;
  memcpy(value, p, n); value[n] = 0; return 1;
}

static uint32_t ADS_CRC32(const uint8_t *data, size_t size)
{
  uint32_t crc=0xffffffffU;
  for(size_t i=0;i<size;i++) {
    crc^=data[i];
    for(unsigned bit=0;bit<8;bit++) crc=(crc>>1)^((crc&1U)?0xedb88320U:0U);
  }
  return ~crc;
}
static void ADS_Protocol_Transmit(ADS_Protocol *protocol, const char *frame)
{
  if ((protocol->transmit != NULL) && (frame != NULL))
  {
    size_t size=strlen(frame);
    if(protocol->require_crc) {
      char trailer[12];
      while(size && (frame[size-1]=='\n' || frame[size-1]=='\r')) size--;
      snprintf(trailer,sizeof(trailer),"*%08lX\n",(unsigned long)ADS_CRC32((const uint8_t *)frame,size));
      (void)protocol->transmit((const uint8_t *)frame,size,protocol->callback_context);
      (void)protocol->transmit((const uint8_t *)trailer,strlen(trailer),protocol->callback_context);
    } else (void)protocol->transmit((const uint8_t *)frame,size,protocol->callback_context);
  }
}

static void ADS_Protocol_SendError(ADS_Protocol *protocol, uint32_t reply_to,
                                   const char *code, const char *message)
{
  char frame[512];
  int written;

  protocol->transmit_sequence++;
  written = snprintf(
      frame, sizeof(frame),
      "{\"version\":1,\"type\":\"error\",\"seq\":%lu,"
      "\"device_id\":\"%s\",\"timestamp_ms\":%lu,\"payload\":{"
      "\"reply_to\":%lu,\"code\":\"%s\",\"message\":\"%s\"}}\n",
      (unsigned long)protocol->transmit_sequence, ADS_DEVICE_ID,
      (unsigned long)ADS_Protocol_Now(protocol), (unsigned long)reply_to,
      code, message);
  if ((written > 0) && ((size_t)written < sizeof(frame)))
  {
    ADS_Protocol_Transmit(protocol, frame);
  }
}


static const char *ADS_Protocol_FeedbackState(ADS_Test *t)
{
  if(!t->power_feedback_installed) return "NOT_INSTALLED";
  if(!t->power_feedback_verified || !t->feedback) return "UNVERIFIED";
  int state=t->feedback(t->context);
  return state==1?"HIGH":state==0?"LOW":"UNVERIFIED";
}

static void ADS_Protocol_MotorResult(ADS_Protocol *p, uint32_t reply, int accepted, const char *reason, const char *type)
{
  char frame[1280];
  ADS_Test *t=p->motor_test;
  int n=snprintf(frame,sizeof(frame),
    "{\"version\":1,\"type\":\"%s\",\"seq\":%lu,\"device_id\":\"STM32-ADS\",\"timestamp_ms\":%lu,"
    "\"payload\":{\"reply_to\":%lu,\"result\":{\"accepted\":%s,\"reason\":\"%s\",\"state\":\"%s\","
    "\"requested_pwm_percent\":%lu,\"applied_pwm_percent\":%lu,\"direction\":\"%s\",\"fixed_direction\":\"FORWARD\",\"faults\":%s,"
    "\"run_id\":%lu,\"started_ms\":%lu,\"stopped_ms\":%lu,\"duration_ms\":%lu,"
    "\"last_control_seq\":%lu,\"stop_reason\":\"%s\",\"hardware_control\":%s,\"physical_stop_verified\":false,\"operating_mode\":\"%s\",\"power_feedback_installed\":%s,\"power_feedback_state\":\"%s\",\"supervised_confirmed\":%s,\"power_check_required\":%s,\"power_started_ms\":%lu,\"motor_relay_requested_on\":%s}}}\n",
    type,(unsigned long)++p->transmit_sequence,(unsigned long)ADS_Protocol_Now(p),(unsigned long)reply,
    accepted?"true":"false",reason,t->state,(unsigned long)t->requested_pwm,(unsigned long)t->applied_pwm,
    t->output_enabled?"FORWARD":"UNCONFIGURED",t->locked?"[\"MOTOR_LOCKOUT\"]":"[]",
    (unsigned long)t->run_id,(unsigned long)t->started_ms,(unsigned long)t->stopped_ms,
    (unsigned long)t->duration_ms,(unsigned long)t->last_control_seq,t->reason,t->output_enabled?"true":"false",
    t->supervised_required?"SUPERVISED_TEST":"NORMAL",t->power_feedback_installed?"true":"false",
    ADS_Protocol_FeedbackState(t),t->supervised_confirmed?"true":"false",t->power_required?"true":"false",(unsigned long)t->power_started_ms,(t->power_requested || t->running)?"true":"false");
  if(n>0 && (size_t)n<sizeof(frame)) ADS_Protocol_Transmit(p,frame);
}
void ADS_Protocol_SetMotorTest(ADS_Protocol *p, ADS_Test *t) { p->motor_test=t; }
void ADS_Protocol_SetCircuitTest(ADS_Protocol *p, ADS_Test *t) { p->circuit_test=t; }
void ADS_Protocol_SetMeasurementInfo(ADS_Protocol *p, ADS_InfoFn f) { p->info=f; }
void ADS_Protocol_SetBranches(ADS_Protocol *p, ADS_BranchesFn f) { p->branches=f; }
void ADS_Protocol_EmitMotorEvents(ADS_Protocol *p)
{
  ADS_Test *t=p->motor_test;
  if(!t) return;
  for(unsigned which=0;which<2;which++) {
    uint32_t seq=which?t->stop_event_seq:t->start_event_seq;
    uint32_t *sent=which?&p->sent_stop_event:&p->sent_start_event;
    if(seq && seq!=*sent) {
      char frame[640];
      int n=snprintf(frame,sizeof(frame),
        "{\"version\":1,\"type\":\"event\",\"seq\":%lu,\"device_id\":\"STM32-ADS\",\"timestamp_ms\":%lu,"
        "\"payload\":{\"event\":\"%s\",\"event_sequence\":%lu,\"run_id\":%lu,\"reason\":\"%s\","
        "\"applied_pwm_percent\":%lu,\"physical_motion_confirmed\":false,\"physical_stop_verified\":false}}\n",
        (unsigned long)++p->transmit_sequence,(unsigned long)(which?t->stopped_ms:t->started_ms),
        which?"MOTOR_STOP":"MOTOR_START",(unsigned long)seq,(unsigned long)t->run_id,
        which?t->reason:"OUTPUT_APPLIED",(unsigned long)(which?0:t->applied_pwm));
      if(n>0 && (size_t)n<sizeof(frame)) ADS_Protocol_Transmit(p,frame);
      *sent=seq;
    }
  }
}

static void ADS_Protocol_SendStatus(ADS_Protocol *protocol, uint32_t reply_to)
{
  if (protocol->motor_test) {
    ADS_Protocol_MotorResult(protocol,reply_to,1,"NONE","status"); return;
  }
  char frame[640];
  const char *state = protocol->safety_state == ADS_PROTOCOL_SAFE_IDLE
                          ? "SAFE_IDLE"
                          : "COMMUNICATION_TIMEOUT";
  uint32_t age = protocol->has_received_request
                     ? ADS_Protocol_Now(protocol) - protocol->last_valid_request_ms
                     : 0U;
  int written;

  protocol->transmit_sequence++;
  written = snprintf(
      frame, sizeof(frame),
      "{\"version\":1,\"type\":\"status\",\"seq\":%lu,"
      "\"device_id\":\"%s\",\"timestamp_ms\":%lu,\"payload\":{"
      "\"reply_to\":%lu,\"result\":{\"device_id\":\"%s\","
      "\"state\":\"%s\",\"pwm_percent\":0,"
      "\"direction\":\"UNCONFIGURED\",\"faults\":%s,"
      "\"hardware_control\":false,\"communication_age_ms\":%lu,"
      "\"heartbeat_timeout_ms\":%u}}}\n",
      (unsigned long)protocol->transmit_sequence, ADS_DEVICE_ID,
      (unsigned long)ADS_Protocol_Now(protocol), (unsigned long)reply_to,
      ADS_DEVICE_ID, state, protocol->safety_state == ADS_PROTOCOL_SAFE_IDLE ? "[]" : "[\"COMMUNICATION_TIMEOUT\"]", (unsigned long)age,
      ADS_PROTOCOL_HEARTBEAT_TIMEOUT_MS);
  if ((written > 0) && ((size_t)written < sizeof(frame)))
  {
    ADS_Protocol_Transmit(protocol, frame);
  }
}

static void ADS_Protocol_SendCapabilities(ADS_Protocol *protocol,
                                          uint32_t reply_to)
{
  char frame[2048];
  int written;
  if (protocol->motor_test) {
    ADS_Test *t=protocol->motor_test;
    written=snprintf(frame,sizeof(frame),
      "{\"version\":1,\"type\":\"capabilities\",\"seq\":%lu,\"device_id\":\"STM32-ADS\",\"timestamp_ms\":%lu,"
      "\"payload\":{\"reply_to\":%lu,\"result\":{\"device_id\":\"STM32-ADS\",\"firmware_version\":\"%s\","
      "\"measurement_types\":[\"voltage\",\"current\",\"power\",\"temperature\",\"rpm\"],"
      "\"commands\":[\"GET_STATUS\",\"GET_CAPABILITIES\",\"GET_FAULTS\",\"READ_MEASUREMENTS\",\"ARM_TEST\",\"PREPARE_TEST_POWER\",\"START_TEST\",\"SET_PWM\",\"STOP_TEST\",\"STOP_MOTOR\",\"EMERGENCY_STOP\",\"CLEAR_FAULTS\",\"GET_DEVICE_INFO\",\"GET_SENSOR_DATA\",\"GET_CIRCUIT_STATUS\",\"ARM_CIRCUIT\",\"START_CIRCUIT\",\"STOP_CIRCUIT\"],"
      "\"ina219_addresses\":{\"MOTOR\":64,\"CIRCUIT\":65},\"integrity\":\"%s\",\"hardware_control\":%s,\"fixed_pwm_percent\":%lu,\"max_duration_ms\":%lu,\"fixed_direction\":\"FORWARD\",\"heartbeat_timeout_ms\":2000,\"temperature_enabled\":%s,\"hardware_block_reason\":\"%s\",\"encoder_calibration\":\"PROVISIONAL_UNTIL_BENCH_VERIFIED\",\"operating_mode\":\"%s\",\"power_feedback_installed\":%s,\"power_feedback_state\":\"%s\",\"electrical_limits_enabled\":true,\"protection_limits_verified\":%s,\"supply_sensing\":\"DOWNSTREAM_POWER_CHECK\",\"supply_sensing_verified\":%s,\"power_check_required\":true,\"power_check_timeout_ms\":1500,\"power_check_settle_ms\":50,\"min_voltage_mv\":%lu,\"max_voltage_mv\":%lu,\"max_current_ma\":%lu,\"circuit_power_control\":%s,\"circuit_max_duration_ms\":30000,\"circuit_relay\":\"D5/PB4/IN2\",\"motor_relay_active_level\":%d,\"circuit_relay_active_level\":%d}}}\n",
      (unsigned long)++protocol->transmit_sequence,(unsigned long)ADS_Protocol_Now(protocol),(unsigned long)reply_to,
      ADS_FIRMWARE_VERSION,protocol->require_crc?"CRC32":"OPTIONAL_CRC32",t->output_enabled?"true":"false",(unsigned long)t->fixed_pwm,(unsigned long)t->max_duration_ms,ADS_TEMPERATURE_ENABLED?"true":"false",t->disabled_reason,
      t->supervised_required?"SUPERVISED_TEST":"NORMAL",t->power_feedback_installed?"true":"false",
      ADS_Protocol_FeedbackState(t),
      ADS_PROTECTION_LIMITS_VERIFIED?"true":"false","true",
      (unsigned long)ADS_MOTOR_MIN_VOLTAGE_MV,(unsigned long)ADS_MOTOR_MAX_VOLTAGE_MV,(unsigned long)ADS_MOTOR_MAX_CURRENT_MA,
      protocol->circuit_test && protocol->circuit_test->output_enabled?"true":"false",
      ADS_RELAY_ACTIVE_LEVEL,ADS_CIRCUIT_RELAY_ACTIVE_LEVEL);
    if(written>0 && (size_t)written<sizeof(frame)) ADS_Protocol_Transmit(protocol,frame);
    return;
  }
  protocol->transmit_sequence++;
  written = snprintf(
      frame, sizeof(frame),
      "{\"version\":1,\"type\":\"capabilities\",\"seq\":%lu,"
      "\"device_id\":\"%s\",\"timestamp_ms\":%lu,\"payload\":{"
      "\"reply_to\":%lu,\"result\":{\"device_id\":\"%s\","
      "\"firmware_version\":\"%s\",\"measurement_types\":[],"
      "\"commands\":[\"GET_STATUS\",\"GET_CAPABILITIES\","
      "\"GET_FAULTS\",\"READ_MEASUREMENTS\"],\"hardware_control\":false}}}\n",
      (unsigned long)protocol->transmit_sequence, ADS_DEVICE_ID,
      (unsigned long)ADS_Protocol_Now(protocol), (unsigned long)reply_to,
      ADS_DEVICE_ID, ADS_FIRMWARE_VERSION);
  if ((written > 0) && ((size_t)written < sizeof(frame)))
  {
    ADS_Protocol_Transmit(protocol, frame);
  }
}

static void ADS_Protocol_SendAck(ADS_Protocol *protocol, uint32_t reply_to,
                                 const char *result)
{
  char frame[512];
  int written;

  protocol->transmit_sequence++;
  written = snprintf(
      frame, sizeof(frame),
      "{\"version\":1,\"type\":\"ack\",\"seq\":%lu,"
      "\"device_id\":\"%s\",\"timestamp_ms\":%lu,\"payload\":{"
      "\"reply_to\":%lu,\"result\":%s}}\n",
      (unsigned long)protocol->transmit_sequence, ADS_DEVICE_ID,
      (unsigned long)ADS_Protocol_Now(protocol), (unsigned long)reply_to,
      result);
  if ((written > 0) && ((size_t)written < sizeof(frame)))
  {
    ADS_Protocol_Transmit(protocol, frame);
  }
}

/* Called only by the foreground protocol owner, never from an interrupt. */
static size_t ADS_Protocol_Branch(char *out,size_t capacity,const ADS_ElectricalBranch *b)
{
  static const char *names[]={"voltage","current","power"};
  static const char *units[]={"V","A","W"};
  int valid=b->connected && b->configured && b->samples[0].valid && b->samples[1].valid && b->samples[2].valid;
  int n=snprintf(out,capacity,
    "{\"address\":%u,\"connected\":%s,\"configured\":%s,\"status\":\"%s\",\"valid\":%s,"
    "\"calibrated\":%s,\"sequence\":%lu,\"started_ms\":%lu,\"timestamp_ms\":%lu,\"measurements\":{",
    b->address,b->connected?"true":"false",b->configured?"true":"false",b->status?b->status:"NOT_INITIALIZED",
    valid?"true":"false",b->calibrated?"true":"false",(unsigned long)b->sequence,
    (unsigned long)b->started_ms,(unsigned long)b->completed_ms);
  if(n<0 || (size_t)n>=capacity) return capacity;
  size_t used=(size_t)n;
  for(unsigned i=0;i<3;i++) {
    char value[40]="null";
    int good=valid && b->samples[i].milli_value>=-2000000000 && b->samples[i].milli_value<=2000000000;
    if(good) {
      int32_t v=b->samples[i].milli_value;
      unsigned long magnitude=(unsigned long)(v<0?-v:v);
      snprintf(value,sizeof(value),"%s%lu.%03lu",v<0?"-":"",magnitude/1000U,magnitude%1000U);
    }
    n=snprintf(out+used,capacity-used,
      "%s\"%s\":{\"value\":%s,\"unit\":\"%s\",\"valid\":%s,\"timestamp_ms\":%lu}",
      i?",":"",names[i],value,units[i],good?"true":"false",(unsigned long)b->samples[i].timestamp_ms);
    if(n<0 || (size_t)n>=capacity-used) return capacity;
    used+=(size_t)n;
  }
  if(capacity-used<3) return capacity;
  memcpy(out+used,"}}",3); return used+2;
}

static void ADS_Protocol_SendMeasurements(ADS_Protocol *protocol, uint32_t reply_to)
{
  static const char *names[] = {"voltage", "current", "power", "temperature", "rpm"};
  static const char *units[] = {"V", "A", "W", "degC", "rpm"};
  ADS_Sample samples[5] = {{0}};
  static char result[3072];
  size_t used = 0;
  unsigned i;
  if (protocol->acquire != NULL) protocol->acquire(samples, protocol->callback_context);
  used = (size_t)snprintf(result, sizeof(result), "{\"measurements\":{");
  for (i = 0; i < 5; i++)
  {
    char value[40] = "null";
    int valid = samples[i].valid && samples[i].milli_value >= -2000000000 && samples[i].milli_value <= 2000000000;
    /* Fixed-point formatting avoids newlib's optional printf float support. */
    if (valid) {
      int32_t v = samples[i].milli_value;
      unsigned long magnitude = (unsigned long)(v < 0 ? -v : v);
      snprintf(value, sizeof(value), "%s%lu.%03lu", v < 0 ? "-" : "", magnitude / 1000U, magnitude % 1000U);
    }
    used += (size_t)snprintf(result + used, sizeof(result) - used,
      "%s\"%s\":{\"value\":%s,\"unit\":\"%s\",\"valid\":%s,\"timestamp_ms\":%lu}",
      i ? "," : "", names[i], value, units[i], valid ? "true" : "false", (unsigned long)samples[i].timestamp_ms);
  }
  if (protocol->info) {
    ADS_MeasurementInfo info={0};
    protocol->info(&info,protocol->callback_context);
    snprintf(result+used,sizeof(result)-used,
      "},\"sample_sequence\":%lu,\"electrical_sequence\":%lu,\"electrical_started_ms\":%lu,\"electrical_completed_ms\":%lu,"
      "\"encoder_started_ms\":%lu,\"encoder_completed_ms\":%lu,\"temperature_started_ms\":%lu,\"temperature_completed_ms\":%lu,"
      "\"voltage_current_calibrated\":%s,\"encoder_calibrated\":%s,\"temperature_calibrated\":%s,"
      "\"encoder_direction\":\"%s\",\"source\":\"stm32_serial\"}",
      (unsigned long)info.sample_sequence,(unsigned long)info.electrical_sequence,
      (unsigned long)info.electrical_started_ms,(unsigned long)info.electrical_completed_ms,
      (unsigned long)info.encoder_started_ms,(unsigned long)info.encoder_completed_ms,
      (unsigned long)info.temperature_started_ms,(unsigned long)info.temperature_completed_ms,
      info.voltage_current_calibrated?"true":"false",info.encoder_calibrated?"true":"false",
      info.temperature_calibrated?"true":"false",info.encoder_direction?info.encoder_direction:"UNKNOWN");
  } else snprintf(result + used, sizeof(result) - used, "}}");
  if (protocol->branches) {
    ADS_ElectricalBranch branches[2]; memset(branches,0,sizeof(branches));
    protocol->branches(branches,protocol->callback_context);
    used=strlen(result)-1; /* Replace only the result object's final brace. */
    const char *labels[]={"MOTOR","CIRCUIT"};
    int n=snprintf(result+used,sizeof(result)-used,",\"ina219\":{");
    if(n<0 || (size_t)n>=sizeof(result)-used) return;
    used+=(size_t)n;
    for(unsigned branch=0;branch<2;branch++) {
      n=snprintf(result+used,sizeof(result)-used,"%s\"%s\":",branch?",":"",labels[branch]);
      if(n<0 || (size_t)n>=sizeof(result)-used) return;
      used+=(size_t)n;
      size_t count=ADS_Protocol_Branch(result+used,sizeof(result)-used,&branches[branch]);
      if(count>=sizeof(result)-used) return;
      used+=count;
    }
    if(sizeof(result)-used<3) return;
    memcpy(result+used,"}}",3);
  }
  {
    static char frame[4096];
    int written = snprintf(frame, sizeof(frame),
      "{\"version\":1,\"type\":\"measurement\",\"seq\":%lu,\"device_id\":\"%s\",\"timestamp_ms\":%lu,\"payload\":{\"reply_to\":%lu,\"result\":%s}}\n",
      (unsigned long)++protocol->transmit_sequence, ADS_DEVICE_ID,
      (unsigned long)ADS_Protocol_Now(protocol), (unsigned long)reply_to, result);
    if (written > 0 && (size_t)written < sizeof(frame)) ADS_Protocol_Transmit(protocol, frame);
  }
}

void ADS_Protocol_SetHardwareCallbacks(ADS_Protocol *protocol, ADS_AcquireFn acquire, ADS_StopFn stop)
{
  protocol->acquire = acquire;
  protocol->stop = stop;
  if (stop != NULL) stop(protocol->callback_context);
}

static int ADS_Protocol_IsControlCommand(const char *command)
{
  return !strcmp(command,"CLEAR_FAULTS") || !strcmp(command,"EMERGENCY_STOP") || (strcmp(command, "ARM_TEST") == 0) || (strcmp(command, "PREPARE_TEST_POWER") == 0) || (strcmp(command, "START_TEST") == 0) ||
         (strcmp(command, "STOP_TEST") == 0) ||
         (strcmp(command, "SET_PWM") == 0) ||
         (strcmp(command, "SET_DIRECTION") == 0) ||
         (strcmp(command, "STOP_MOTOR") == 0);
}

static void ADS_Protocol_CircuitResult(ADS_Protocol *p,uint32_t reply,int accepted,const char *reason)
{
  char frame[768]; ADS_Test *t=p->circuit_test;
  int n=snprintf(frame,sizeof(frame),
    "{\"version\":1,\"type\":\"ack\",\"seq\":%lu,\"device_id\":\"STM32-ADS\",\"timestamp_ms\":%lu,"
    "\"payload\":{\"reply_to\":%lu,\"result\":{\"accepted\":%s,\"reason\":\"%s\",\"branch\":\"CIRCUIT\","
    "\"state\":\"%s\",\"power_on\":%s,\"relay_command_high\":%s,\"physical_power_verified\":false,"
    "\"last_control_seq\":%lu,\"run_id\":%lu,\"started_ms\":%lu,\"stopped_ms\":%lu,\"stop_reason\":\"%s\"}}}\n",
    (unsigned long)++p->transmit_sequence,(unsigned long)ADS_Protocol_Now(p),(unsigned long)reply,
    accepted?"true":"false",reason,t?t->state:"UNAVAILABLE",t && t->running?"true":"false",
    (t && t->running ? ADS_CIRCUIT_RELAY_ACTIVE_LEVEL : ADS_CIRCUIT_RELAY_INACTIVE_LEVEL)?"true":"false",(unsigned long)(t?t->last_control_seq:0),
    (unsigned long)(t?t->run_id:0),(unsigned long)(t?t->started_ms:0),
    (unsigned long)(t?t->stopped_ms:0),t?t->reason:"CIRCUIT_CONTROL_UNAVAILABLE");
  if(n>0 && (size_t)n<sizeof(frame)) ADS_Protocol_Transmit(p,frame);
}

static void ADS_Protocol_HandleFrame(ADS_Protocol *protocol, const char *frame)
{
  uint32_t version = 0U;
  uint32_t request_sequence = 0U;
  char type[24];
  char device_id[40];
  char command[32];
  const char *timestamp_value;
  const char *payload_value;

  token_count = 0; cursor = frame;
  if (!parse_value(-1, 0U))
  { ADS_Protocol_SendError(protocol, 0, "MALFORMED_FRAME", "Invalid JSON structure"); return; }
  whitespace();
  if (*cursor || tokens[0].kind != '{')
  { ADS_Protocol_SendError(protocol, 0, "MALFORMED_FRAME", "Expected one JSON object"); return; }
  timestamp_value = ADS_Protocol_FindValue(frame, "\"timestamp_ms\"");
  payload_value = ADS_Protocol_FindValue(frame, "\"payload\"");

  if (!ADS_Protocol_ReadUint32(frame, "\"version\"", &version) ||
      !ADS_Protocol_ReadUint32(frame, "\"seq\"", &request_sequence) ||
      !ADS_Protocol_ReadString(frame, "\"type\"", type, sizeof(type)) ||
      !ADS_Protocol_ReadString(frame, "\"device_id\"", device_id,
                              sizeof(device_id)) ||
      (device_id[0] == '\0') || (timestamp_value == NULL) ||
      !isdigit((unsigned char)*timestamp_value) || (payload_value == NULL) ||
      (*payload_value != '{'))
  {
    ADS_Protocol_SendError(protocol, request_sequence, "MALFORMED_FRAME",
                           "Required protocol fields are missing or invalid");
    return;
  }
  if (version != ADS_PROTOCOL_VERSION)
  {
    ADS_Protocol_SendError(protocol, request_sequence, "UNSUPPORTED_VERSION",
                           "Only protocol version 1 is supported");
    return;
  }


  ADS_Protocol_Poll(protocol);
  if (strcmp(type, "heartbeat") == 0)
  {
    protocol->last_valid_request_ms = ADS_Protocol_Now(protocol);
    protocol->has_received_request = 1U;
    if (protocol->heartbeat != NULL)
      protocol->heartbeat(protocol->last_valid_request_ms, protocol->callback_context);
    if (protocol->motor_test) {
      ADS_Test_Heartbeat(protocol->motor_test,protocol->last_valid_request_ms);
      protocol->safety_state=protocol->motor_test->locked?ADS_PROTOCOL_COMMUNICATION_TIMEOUT:ADS_PROTOCOL_SAFE_IDLE;
    }
    if (protocol->circuit_test) ADS_Test_Heartbeat(protocol->circuit_test,protocol->last_valid_request_ms);
    ADS_Protocol_SendAck(
        protocol, request_sequence,
        protocol->safety_state == ADS_PROTOCOL_SAFE_IDLE ?
        "{\"alive\":true,\"state\":\"SAFE_IDLE\",\"hardware_control\":false}" :
        "{\"alive\":true,\"state\":\"COMMUNICATION_TIMEOUT\",\"hardware_control\":false}");
    return;
  }
  if (strcmp(type, "command") != 0)
  {
    ADS_Protocol_SendError(protocol, request_sequence,
                           "UNSUPPORTED_MESSAGE_TYPE",
                           "Firmware accepts command and heartbeat requests");
    return;
  }
  if (!ADS_Protocol_ReadString(frame, "\"command\"", command,
                               sizeof(command)))
  {
    ADS_Protocol_SendError(protocol, request_sequence, "MALFORMED_COMMAND",
                           "Command name is missing or invalid");
    return;
  }
  {
    const char *arguments = ADS_Protocol_FindValue(frame, "\"arguments\"");
    if (arguments == NULL || *arguments != '{')
    { ADS_Protocol_SendError(protocol, request_sequence, "MALFORMED_COMMAND", "Arguments must be an object"); return; }
  }
  if (!strcmp(command,"GET_CIRCUIT_STATUS")) {
    ADS_Protocol_CircuitResult(protocol,request_sequence,1,"NONE"); return;
  }
  if (!strcmp(command,"ARM_CIRCUIT") || !strcmp(command,"START_CIRCUIT") || !strcmp(command,"STOP_CIRCUIT")) {
    ADS_Test *t=protocol->circuit_test; const char *reason="CIRCUIT_CONTROL_UNAVAILABLE";
    int accepted=0; uint32_t duration=0;
    if(t) {
      const char *confirmation=ADS_Protocol_FindValue(frame,"\"supervised_confirmed\"");
      t->operator_confirmation=confirmation && !strncmp(confirmation,"true",4);
      if(strcmp(command,"START_CIRCUIT") || ADS_Protocol_ReadUint32(frame,"\"duration_ms\"",&duration))
        accepted=ADS_Test_Command(t,!strcmp(command,"ARM_CIRCUIT")?"ARM_TEST":
          !strcmp(command,"START_CIRCUIT")?"START_TEST":"STOP_TEST",request_sequence,100,duration,
          "FORWARD",ADS_Protocol_Now(protocol),&reason);
      else reason="MALFORMED_ARGUMENTS";
    }
    ADS_Protocol_CircuitResult(protocol,request_sequence,accepted,reason); return;
  }
  if (!strcmp(command,"EMERGENCY_STOP") && protocol->circuit_test)
    ADS_Test_Fault(protocol->circuit_test,ADS_Protocol_Now(protocol),"EMERGENCY_STOP");
  if (strcmp(command, "GET_STATUS") == 0)
  {
    ADS_Protocol_SendStatus(protocol, request_sequence);
  }
  else if ((strcmp(command, "GET_CAPABILITIES") == 0 || !strcmp(command,"GET_DEVICE_INFO")))
  {
    ADS_Protocol_SendCapabilities(protocol, request_sequence);
  }
  else if (strcmp(command, "GET_FAULTS") == 0)
  {
    if(protocol->motor_test) {
      ADS_Protocol_MotorResult(protocol,request_sequence,1,protocol->motor_test->reason,"ack"); return;
    }
    ADS_Protocol_SendAck(protocol, request_sequence,
                         protocol->safety_state == ADS_PROTOCOL_SAFE_IDLE ?
                         "{\"faults\":[],\"state\":\"SAFE_IDLE\"}" :
                         "{\"faults\":[\"COMMUNICATION_TIMEOUT\"],\"state\":\"COMMUNICATION_TIMEOUT\"}");
  }
  else if ((strcmp(command, "READ_MEASUREMENTS") == 0 || !strcmp(command,"GET_SENSOR_DATA")))
  {
    ADS_Protocol_SendMeasurements(protocol, request_sequence);
  }
  else if (ADS_Protocol_IsControlCommand(command))
  {
    if(protocol->motor_test) {
      const char *reason="MALFORMED_ARGUMENTS";
      uint32_t pwm=0,duration=0;
      char direction[16]="";
      int accepted;
      int valid=1;
      protocol->motor_test->operator_confirmation=0;
      if(!strcmp(command,"ARM_TEST") || !strcmp(command,"CLEAR_FAULTS")) {
        const char *confirmation=ADS_Protocol_FindValue(frame,"\"supervised_confirmed\"");
        protocol->motor_test->operator_confirmation=confirmation && !strncmp(confirmation,"true",4);
      }
      if(!strcmp(command,"START_TEST") || !strcmp(command,"SET_PWM"))
        valid=ADS_Protocol_ReadUint32(frame,"\"pwm_percent\"",&pwm);
      if(!strcmp(command,"START_TEST"))
        valid=valid && ADS_Protocol_ReadUint32(frame,"\"duration_ms\"",&duration) &&
          ADS_Protocol_ReadString(frame,"\"direction\"",direction,sizeof(direction));
      if(valid) accepted=ADS_Test_Command(protocol->motor_test,command,request_sequence,pwm,duration,
                                          direction,ADS_Protocol_Now(protocol),&reason);
      else accepted=0;
      ADS_Protocol_MotorResult(protocol,request_sequence,accepted,reason,"ack");
      ADS_Protocol_EmitMotorEvents(protocol);
      return;
    }
    /* Stop requests always attempt shutdown, but cannot claim physical success
     * while relay operation is unverified. Never clear a latched timeout. */
    if ((strcmp(command, "STOP_MOTOR") == 0 || strcmp(command, "STOP_TEST") == 0) && protocol->stop != NULL)
      protocol->stop(protocol->callback_context);
    ADS_Protocol_SendError(protocol, request_sequence, "CONTROL_DISABLED",
                           "Motor outputs are disabled pending verification");
  }
  else
  {
    ADS_Protocol_SendError(protocol, request_sequence, "UNSUPPORTED_COMMAND",
                           "Command is not supported by this firmware");
  }
}

void ADS_Protocol_SetHeartbeatCallback(ADS_Protocol *protocol, ADS_HeartbeatFn heartbeat)
{
  if (protocol != NULL) protocol->heartbeat = heartbeat;
}

void ADS_Protocol_Init(ADS_Protocol *protocol,
                       ADS_ProtocolTransmitFn transmit,
                       ADS_ProtocolTickFn tick,
                       void *callback_context)
{
  if (protocol == NULL)
  {
    return;
  }
  memset(protocol, 0, sizeof(*protocol));
  protocol->transmit = transmit;
  protocol->tick = tick;
  protocol->callback_context = callback_context;
  protocol->last_valid_request_ms = ADS_Protocol_Now(protocol);
  protocol->safety_state = ADS_PROTOCOL_SAFE_IDLE;
}

void ADS_Protocol_ProcessByte(ADS_Protocol *protocol, uint8_t byte)
{
  if (protocol == NULL)
  {
    return;
  }
  if (byte == 0U) { protocol->receive_overflow = 1U; return; }
  if (byte == '\r')
  {
    return;
  }
  if (byte == '\n')
  {
    if (protocol->receive_overflow != 0U)
    {
      ADS_Protocol_SendError(protocol, 0U, "FRAME_TOO_LARGE",
                             "Frame exceeds firmware receive limit");
    }
    else if (protocol->receive_length > 0U)
    {
      protocol->receive_buffer[protocol->receive_length] = '\0';
      size_t n=protocol->receive_length;
      int protected_frame=n>=9 && protocol->receive_buffer[n-9]=='*';
      int valid=!protocol->require_crc && !protected_frame;
      if(protected_frame) {
        uint32_t expected=0; valid=1;
        for(size_t i=n-8;i<n;i++) {
          unsigned char ch=(unsigned char)protocol->receive_buffer[i];
          if(!isxdigit(ch)) { valid=0; break; }
          expected=(expected<<4)|(isdigit(ch)?(unsigned)(ch-'0'):(unsigned)(tolower(ch)-'a'+10));
        }
        n-=9; protocol->receive_buffer[n]=0;
        valid=valid && ADS_CRC32((const uint8_t *)protocol->receive_buffer,n)==expected;
      }
      if(!valid || n>ADS_PROTOCOL_MAX_FRAME_BYTES) {
        if(protocol->motor_test) ADS_Test_Fault(protocol->motor_test,ADS_Protocol_Now(protocol),"PROTOCOL_INTEGRITY_FAULT");
        ADS_Protocol_SendError(protocol,0,"CRC32_REQUIRED_OR_INVALID","Frame integrity check failed");
      } else ADS_Protocol_HandleFrame(protocol, protocol->receive_buffer);
    }
    protocol->receive_length = 0U;
    protocol->receive_overflow = 0U;
    return;
  }
  if (protocol->receive_overflow != 0U)
  {
    return;
  }
  if (protocol->receive_length >= ADS_PROTOCOL_MAX_FRAME_BYTES + (protocol->require_crc ? 9U : 0U))
  {
    protocol->receive_overflow = 1U;
    return;
  }
  protocol->receive_buffer[protocol->receive_length++] = (char)byte;
}

void ADS_Protocol_Poll(ADS_Protocol *protocol)
{
  if (protocol == NULL)
  {
    return;
  }
  if(protocol->circuit_test) ADS_Test_Poll(protocol->circuit_test,ADS_Protocol_Now(protocol));
  if(protocol->motor_test) {
    ADS_Test_Poll(protocol->motor_test,ADS_Protocol_Now(protocol));
    protocol->safety_state=protocol->motor_test->locked ? ADS_PROTOCOL_COMMUNICATION_TIMEOUT : ADS_PROTOCOL_SAFE_IDLE;
    ADS_Protocol_EmitMotorEvents(protocol); return;
  }
  if ((uint32_t)(ADS_Protocol_Now(protocol) -
                 protocol->last_valid_request_ms) >=
      ADS_PROTOCOL_HEARTBEAT_TIMEOUT_MS)
  {
    protocol->safety_state = ADS_PROTOCOL_COMMUNICATION_TIMEOUT;
    if (protocol->stop != NULL) protocol->stop(protocol->callback_context);
  }
}

ADS_ProtocolSafetyState ADS_Protocol_GetSafetyState(
    const ADS_Protocol *protocol)
{
  return protocol == NULL ? ADS_PROTOCOL_COMMUNICATION_TIMEOUT
                          : protocol->safety_state;
}
