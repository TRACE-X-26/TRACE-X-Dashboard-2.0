#include "ads_protocol.h"

#include <stdio.h>
#include <assert.h>
#include <string.h>

static uint32_t simulated_tick_ms = 100U;

static int capture_transmit(const uint8_t *data, size_t length, void *context)
{
  (void)context;
  return fwrite(data, 1U, length, stdout) == length ? 0 : -1;
}

static uint32_t get_tick(void *context)
{
  (void)context;
  return simulated_tick_ms++;
}

static unsigned stops;
static void stop(void *context) { (void)context; stops++; }
static uint32_t fixed_tick(void *context) { (void)context; return simulated_tick_ms; }
static void acquire(ADS_Sample samples[5], void *context)
{
  (void)context;
  samples[0] = (ADS_Sample){12345, 42, 1};
  samples[1] = (ADS_Sample){-125, 43, 1};
}
int main(int argc, char **argv)
{
  ADS_Protocol protocol;
  int input;

  if (argc > 1 && strcmp(argv[1], "--safety") == 0) {
    ADS_Protocol_Init(&protocol, NULL, fixed_tick, NULL);
    assert(ADS_Protocol_GetSafetyState(&protocol) == ADS_PROTOCOL_SAFE_IDLE);
    ADS_Protocol_SetHardwareCallbacks(&protocol, NULL, stop);
    assert(stops == 1);
    simulated_tick_ms += 1999;
    ADS_Protocol_Poll(&protocol); assert(stops == 1);
    simulated_tick_ms++;
    ADS_Protocol_Poll(&protocol); assert(stops == 2);
    assert(ADS_Protocol_GetSafetyState(&protocol) == ADS_PROTOCOL_COMMUNICATION_TIMEOUT);
    {
      const char *frames[] = {
        "{\"version\":1,\"type\":\"heartbeat\",\"seq\":1,\"device_id\":\"pi\",\"timestamp_ms\":0,\"payload\":{}}\n",
        "{\"version\":1,\"type\":\"command\",\"seq\":2,\"device_id\":\"pi\",\"timestamp_ms\":0,\"payload\":{\"command\":\"START_TEST\",\"arguments\":{}}}\n",
        "{\"version\":1,\"type\":\"command\",\"seq\":3,\"device_id\":\"pi\",\"timestamp_ms\":0,\"payload\":{\"command\":\"STOP_MOTOR\",\"arguments\":{}}}\n"
      };
      for (unsigned repeat = 0; repeat < 3; repeat++) {
        for (unsigned j = 0; j < 3; j++) {
          unsigned before = stops;
          for (const char *p = frames[j]; *p; p++) ADS_Protocol_ProcessByte(&protocol, (uint8_t)*p);
          if (j == 2) assert(stops > before);
          assert(ADS_Protocol_GetSafetyState(&protocol) == ADS_PROTOCOL_COMMUNICATION_TIMEOUT);
        }
      }
    }
    return 0;
  }
  if (argc > 1 && strcmp(argv[1], "--normal-shutdown") == 0) {
    const char *shutdown = "{\"version\":1,\"type\":\"command\",\"seq\":1,\"device_id\":\"pi\",\"timestamp_ms\":0,\"payload\":{\"command\":\"STOP_TEST\",\"arguments\":{}}}\n";
    ADS_Protocol_Init(&protocol, NULL, fixed_tick, NULL);
    ADS_Protocol_SetHardwareCallbacks(&protocol, NULL, stop);
    assert(stops == 1);
    for (unsigned i = 0; i < 4; i++) {
      for (const char *p = shutdown; *p; p++) ADS_Protocol_ProcessByte(&protocol, (uint8_t)*p);
      assert(stops == i + 2);
      assert(ADS_Protocol_GetSafetyState(&protocol) == ADS_PROTOCOL_SAFE_IDLE);
    }
    return 0;
  }
  ADS_Protocol_Init(&protocol, capture_transmit, get_tick, NULL);
  if (argc > 1) ADS_Protocol_SetHardwareCallbacks(&protocol, acquire, NULL);
  while ((input = getchar()) != EOF)
  {
    ADS_Protocol_ProcessByte(&protocol, (uint8_t)input);
  }
  return 0;
}
