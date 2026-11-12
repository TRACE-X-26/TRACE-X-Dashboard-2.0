#ifndef ADS_PROTOCOL_H
#define ADS_PROTOCOL_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>
#include "ads_test.h"

#define ADS_PROTOCOL_VERSION 1U
#define ADS_PROTOCOL_MAX_FRAME_BYTES 512U
#define ADS_PROTOCOL_HEARTBEAT_TIMEOUT_MS 2000U

/* Set to 1 only for the pre-Phase-2 plain-text banner behavior. */
#define ADS_PROTOCOL_LEGACY_BANNER_ENABLED 0U

typedef int (*ADS_ProtocolTransmitFn)(const uint8_t *data, size_t length,
                                      void *context);
typedef uint32_t (*ADS_ProtocolTickFn)(void *context);

/* Order: voltage, current, power, temperature, RPM. Fixed point in 1/1000 unit.
 * Acquisition must be nonblocking and mark missing/stale/CRC-failed data invalid. */
typedef struct { int32_t milli_value; uint32_t timestamp_ms; uint8_t valid; } ADS_Sample;
typedef struct {
  uint32_t sample_sequence, electrical_sequence, electrical_started_ms, electrical_completed_ms;
  uint32_t encoder_started_ms, encoder_completed_ms, temperature_started_ms, temperature_completed_ms;
  uint8_t voltage_current_calibrated, encoder_calibrated, temperature_calibrated;
  const char *encoder_direction;
} ADS_MeasurementInfo;
typedef struct {
  ADS_Sample samples[3]; /* voltage V, current A, calculated power W */
  uint32_t sequence, started_ms, completed_ms;
  uint8_t address, connected, configured, calibrated;
  const char *status;
} ADS_ElectricalBranch;
typedef void (*ADS_BranchesFn)(ADS_ElectricalBranch branches[2], void *);
typedef void (*ADS_InfoFn)(ADS_MeasurementInfo *, void *);
typedef void (*ADS_AcquireFn)(ADS_Sample samples[5], void *context);
typedef void (*ADS_StopFn)(void *context);
typedef void (*ADS_HeartbeatFn)(uint32_t now_ms, void *context);

typedef enum
{
  ADS_PROTOCOL_SAFE_IDLE = 0,
  ADS_PROTOCOL_COMMUNICATION_TIMEOUT
} ADS_ProtocolSafetyState;

typedef struct
{
  char receive_buffer[ADS_PROTOCOL_MAX_FRAME_BYTES + 10U];
  size_t receive_length;
  uint32_t transmit_sequence;
  uint32_t last_valid_request_ms;
  uint8_t receive_overflow;
  uint8_t require_crc;
  uint8_t has_received_request;
  ADS_ProtocolSafetyState safety_state;
  ADS_Test *motor_test;
  ADS_Test *circuit_test;
  uint32_t sent_start_event, sent_stop_event;
  ADS_InfoFn info;
  ADS_BranchesFn branches;
  ADS_AcquireFn acquire;
  ADS_StopFn stop;
  ADS_HeartbeatFn heartbeat;
  ADS_ProtocolTransmitFn transmit;
  ADS_ProtocolTickFn tick;
  void *callback_context;
} ADS_Protocol;

void ADS_Protocol_Init(ADS_Protocol *protocol,
                       ADS_ProtocolTransmitFn transmit,
                       ADS_ProtocolTickFn tick,
                       void *callback_context);
void ADS_Protocol_SetBranches(ADS_Protocol *, ADS_BranchesFn);
void ADS_Protocol_SetHardwareCallbacks(ADS_Protocol *protocol, ADS_AcquireFn acquire, ADS_StopFn stop);
void ADS_Protocol_SetMotorTest(ADS_Protocol *, ADS_Test *);
void ADS_Protocol_SetCircuitTest(ADS_Protocol *, ADS_Test *);
void ADS_Protocol_SetMeasurementInfo(ADS_Protocol *, ADS_InfoFn);
void ADS_Protocol_EmitMotorEvents(ADS_Protocol *);
void ADS_Protocol_SetHeartbeatCallback(ADS_Protocol *protocol, ADS_HeartbeatFn heartbeat);
void ADS_Protocol_ProcessByte(ADS_Protocol *protocol, uint8_t byte);
void ADS_Protocol_Poll(ADS_Protocol *protocol);
ADS_ProtocolSafetyState ADS_Protocol_GetSafetyState(
    const ADS_Protocol *protocol);

#ifdef __cplusplus
}
#endif

#endif /* ADS_PROTOCOL_H */
