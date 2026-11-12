#ifndef ADS_TEST_H
#define ADS_TEST_H
#include <stdint.h>
/* Portable bounded controller; real outputs are supplied only by a gated board adapter. */
typedef int (*ADS_TestReadyFn)(void *);
typedef int (*ADS_TestStartFn)(uint32_t, uint32_t, void *);
typedef void (*ADS_TestStopFn)(void *);
typedef struct {
  const char *state, *reason, *disabled_reason;
  uint32_t requested_pwm, applied_pwm, run_id, started_ms, stopped_ms, duration_ms;
  uint32_t last_control_seq, last_heartbeat_ms, heartbeat_generation, arm_generation;
  uint32_t event_seq, start_event_seq, stop_event_seq;
  uint32_t fixed_pwm, max_duration_ms, power_started_ms;
  uint8_t output_enabled, heartbeat_seen, armed, running, locked, has_control_seq;
  uint8_t supervised_required, operator_confirmation, supervised_confirmed;
  uint8_t power_feedback_installed, power_feedback_verified;
  ADS_TestReadyFn feedback;
  uint8_t power_required, power_requested;
  ADS_TestReadyFn prepare_power, power_state;
  ADS_TestReadyFn ready, arm;
  ADS_TestStartFn start;
  ADS_TestStopFn stop;
  void *context;
} ADS_Test;
void ADS_Test_Init(ADS_Test *, uint32_t, uint32_t, int, ADS_TestReadyFn,
                   ADS_TestStartFn, ADS_TestStopFn, void *);
void ADS_Test_Heartbeat(ADS_Test *, uint32_t);
void ADS_Test_Poll(ADS_Test *, uint32_t);
void ADS_Test_Fault(ADS_Test *, uint32_t, const char *);
int ADS_Test_Command(ADS_Test *, const char *, uint32_t, uint32_t, uint32_t,
                     const char *, uint32_t, const char **);
#endif
