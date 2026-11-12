#include "ads_test.h"
#include <string.h>
#define HEARTBEAT_MS 2000U
static void shutdown(ADS_Test *t, uint32_t now, const char *reason, int lock)
{
  /* Every exit, including repeated cancellation, uses the same physical stop. */
  if (t->stop) t->stop(t->context);
  if(t->power_requested) t->stopped_ms=now;
  if (t->running) {
    t->stopped_ms = now;
    t->stop_event_seq = ++t->event_seq;
  }
  t->running = 0; t->armed = 0; t->applied_pwm = 0; t->supervised_confirmed=0;t->power_requested=0;
  if (lock) t->locked = 1;
  t->state = t->locked ? "LOCKOUT" : "STOPPED";
  t->reason = reason;
}
void ADS_Test_Init(ADS_Test *t, uint32_t pwm, uint32_t duration, int enabled,
                   ADS_TestReadyFn ready, ADS_TestStartFn start, ADS_TestStopFn stop, void *ctx)
{
  memset(t, 0, sizeof(*t));
  t->fixed_pwm = pwm; t->max_duration_ms = duration;
  t->output_enabled = enabled && pwm > 0 && pwm <= 100 && duration > 0 && duration <= 30000;
  t->ready = ready; t->start = start; t->stop = stop; t->context = ctx;
  t->disabled_reason="CONTROL_DISABLED";
  t->state = "DISARMED"; t->reason = "ARM_REQUIRED";
  if (stop) stop(ctx);
}
void ADS_Test_Poll(ADS_Test *t, uint32_t now)
{
  if ((t->armed || t->running) &&
      (!t->heartbeat_seen || (uint32_t)(now-t->last_heartbeat_ms) >= HEARTBEAT_MS))
    shutdown(t, now, "HEARTBEAT_LOSS", 1);
  else if (t->running && (uint32_t)(now-t->started_ms) >= t->duration_ms)
    shutdown(t, now, "COMPLETED", 0);
  else if ((t->running || t->armed) && (!t->ready || !t->ready(t->context)))
    shutdown(t, now, "INTERLOCK_OR_SENSOR_FAULT", 1);
  if(t->armed && t->power_requested) {
    int state=t->power_state?t->power_state(t->context):0;
    if(state==2) t->state="POWER_READY";
    else if(state!=1) shutdown(t,now,"POWER_CHECK_FAILED",1);
  }
}
void ADS_Test_Heartbeat(ADS_Test *t, uint32_t now)
{
  ADS_Test_Poll(t, now); /* A late heartbeat cannot conceal an expired run deadline. */
  t->heartbeat_seen = 1; t->last_heartbeat_ms = now; t->heartbeat_generation++;
}
void ADS_Test_Fault(ADS_Test *t, uint32_t now, const char *reason)
{ shutdown(t, now, reason, 1); }
int ADS_Test_Command(ADS_Test *t, const char *command, uint32_t seq, uint32_t pwm,
                     uint32_t duration, const char *direction, uint32_t now, const char **reason)
{
  uint8_t confirmation=t->operator_confirmation; t->operator_confirmation=0;
  ADS_Test_Poll(t, now);
  *reason = "NONE";
  if (!strcmp(command,"EMERGENCY_STOP")) {
    shutdown(t,now,"EMERGENCY_STOP",1); return 1;
  }
  if (!strcmp(command,"CLEAR_FAULTS")) command="ARM_TEST";
  /* STOP is always acted on, even for an old/repeated request or disabled build. */
  if (!strcmp(command,"STOP_TEST") || !strcmp(command,"STOP_MOTOR")) {
    if (t->running || t->armed) shutdown(t,now,t->locked?t->reason:"CANCELLED",0);
    else if (t->stop) t->stop(t->context);
    if (!t->has_control_seq || seq > t->last_control_seq) t->last_control_seq = seq;
    t->has_control_seq = 1;
    return 1;
  }
  if (t->has_control_seq && seq <= t->last_control_seq) { *reason="DUPLICATE_OR_OLD_REQUEST"; return 0; }
  t->last_control_seq=seq; t->has_control_seq=1;
  if (!strcmp(command,"START_TEST") || !strcmp(command,"SET_PWM")) t->requested_pwm=pwm;
  if (!t->output_enabled) { *reason=t->disabled_reason; return 0; }
  if (!strcmp(command,"ARM_TEST")) {
    if (t->running || t->power_requested) { *reason="RUNNING_OR_POWER_CHECK_ACTIVE"; return 0; }
    if (t->supervised_required && !confirmation) { *reason="SUPERVISED_OPERATOR_CONFIRMATION_REQUIRED"; return 0; }
    if (!t->heartbeat_seen || (uint32_t)(now-t->last_heartbeat_ms)>=HEARTBEAT_MS ||
        t->heartbeat_generation == t->arm_generation) { *reason="FRESH_HEARTBEAT_REQUIRED"; return 0; }
    if (!t->ready || !t->ready(t->context)) { *reason="INTERLOCK_OR_SENSOR_FAULT"; return 0; }
    if (t->arm && !t->arm(t->context)) { *reason="REARM_INTERLOCK"; return 0; }
    t->supervised_confirmed=t->supervised_required && confirmation;
    t->locked=0; t->armed=1; t->state="ARMED"; t->reason="NONE";
    t->arm_generation=t->heartbeat_generation;
    return 1;
  }
  if (!strcmp(command,"PREPARE_TEST_POWER")) {
    if(!t->power_required || !t->armed || t->running || t->locked || t->power_requested) { *reason="ARM_REQUIRED_OR_POWER_CHECK_ACTIVE";return 0; }
    if(!t->prepare_power || !t->prepare_power(t->context)) {
      shutdown(t,now,"POWER_CHECK_START_FAILED",1);*reason="POWER_CHECK_START_FAILED";return 0;
    }
    t->power_requested=1;t->power_started_ms=now;t->state="POWER_CHECK";return 1;
  }
  if (!strcmp(command,"SET_DIRECTION")) { *reason=t->running ? "DIRECTION_CHANGE_WHILE_ACTIVE" : "FIXED_DIRECTION_ONLY"; return 0; }
  if (!strcmp(command,"SET_PWM")) {
    t->requested_pwm=pwm;
    if (!t->armed || t->running || t->locked) { *reason="ARM_REQUIRED_OR_RUNNING"; return 0; }
    if (pwm != t->fixed_pwm) { *reason="PWM_OUT_OF_RANGE"; return 0; }
    /* Staging only: applied PWM stays zero until START_TEST succeeds. */
    return 1;
  }
  if (!strcmp(command,"START_TEST")) {
    t->requested_pwm=pwm;
    if (t->locked || !t->armed || t->running) { *reason="ARM_REQUIRED_OR_RUNNING"; return 0; }
    if (t->supervised_required && !t->supervised_confirmed) { *reason="SUPERVISED_OPERATOR_CONFIRMATION_REQUIRED"; return 0; }
    if(t->power_required && (!t->power_requested || strcmp(t->state,"POWER_READY"))) { *reason="POWER_CHECK_REQUIRED";return 0; }
    if (pwm!=t->fixed_pwm) { *reason="PWM_OUT_OF_RANGE"; return 0; }
    if (!duration || duration>t->max_duration_ms) { *reason="DURATION_OUT_OF_RANGE"; return 0; }
    if (!direction || strcmp(direction,"FORWARD")) { *reason="FIXED_DIRECTION_ONLY"; return 0; }
    if (!t->ready || !t->ready(t->context)) { *reason="INTERLOCK_OR_SENSOR_FAULT"; return 0; }
    if (!t->start || !t->start(pwm,duration,t->context)) {
      shutdown(t,now,"OUTPUT_START_FAILED",1); *reason="OUTPUT_START_FAILED"; return 0;
    }
    t->run_id=seq; t->stopped_ms=0; t->started_ms=now; t->duration_ms=duration;
    t->running=1; t->armed=0; t->applied_pwm=pwm;
    t->state="RUNNING"; t->reason="NONE"; t->start_event_seq=++t->event_seq;
    return 1;
  }
  *reason="UNSUPPORTED_COMMAND"; return 0;
}
