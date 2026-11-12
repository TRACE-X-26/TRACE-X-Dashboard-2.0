import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import api.main as api_main


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_database = api_main.DATABASE_PATH
        api_main.DATABASE_PATH = Path(self.tempdir.name) / "api-test.db"
        self.client_context = TestClient(api_main.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        api_main.DATABASE_PATH = self.original_database
        self.tempdir.cleanup()

    def test_health_and_default_profile(self) -> None:
        health = self.client.get("/api/health").json()
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["stm32_connected"])
        profiles = self.client.get("/api/profiles").json()
        self.assertEqual(profiles[0]["device_id"], "MOTOR-001")

    def test_simulated_hardware_interface_is_explicitly_labeled(self) -> None:
        status = self.client.get("/api/hardware/status").json()
        capabilities = self.client.get("/api/hardware/capabilities").json()
        measurements = self.client.get("/api/hardware/measurements").json()
        self.assertEqual(status["source"], "SIMULATION")
        self.assertEqual(capabilities["source"], "SIMULATION")
        self.assertFalse(capabilities["hardware_verified"])
        self.assertEqual(measurements["source"], "SIMULATION")
        self.assertIsNone(measurements["rpm"])

    def test_websocket_streams_and_persists_test(self) -> None:
        with self.client.websocket_connect("/ws/tests") as socket:
            socket.send_json(
                {"device_id": "MOTOR-001", "scenario": "overloaded", "samples": 5, "interval_ms": 0}
            )
            messages = []
            while True:
                message = socket.receive_json()
                messages.append(message)
                if message["type"] == "completed":
                    break
        self.assertEqual(messages[0]["type"], "started")
        self.assertEqual(sum(m["type"] == "measurement" for m in messages), 5)
        first_measurement = next(m for m in messages if m["type"] == "measurement")
        self.assertEqual(first_measurement["source"], "SIMULATION")
        self.assertEqual(first_measurement["measurement_envelopes"][0]["quality"], "GOOD")
        self.assertEqual(messages[-1]["report"]["condition"], "WARNING")
        sessions = self.client.get("/api/sessions").json()
        self.assertEqual(sessions[0]["sample_count"], 5)

    def test_completed_session_can_create_baseline(self) -> None:
        with self.client.websocket_connect("/ws/tests") as socket:
            socket.send_json(
                {"device_id": "MOTOR-001", "scenario": "healthy", "samples": 5, "interval_ms": 0}
            )
            session_id = None
            while True:
                message = socket.receive_json()
                if message["type"] == "completed":
                    session_id = message["session_id"]
                    break
        response = self.client.post(f"/api/sessions/{session_id}/baseline")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["sample_count"], 5)
        baselines = self.client.get("/api/baselines").json()
        self.assertEqual(baselines[0]["device_id"], "MOTOR-001")

    def test_motor_control_endpoint_returns_acknowledgments(self) -> None:
        self.client.post("/api/motor/commands", json={
            "command_id": "cleanup", "action": "disable"
        })
        rejected = self.client.post("/api/motor/commands", json={
            "command_id": "unsafe", "action": "set_pwm", "value": 50
        }).json()
        self.assertFalse(rejected["accepted"])
        enabled = self.client.post("/api/motor/commands", json={
            "command_id": "enable-1", "action": "enable"
        }).json()
        self.assertTrue(enabled["accepted"])
        status = self.client.get("/api/motor/status").json()
        self.assertTrue(status["state"]["enabled"])
        self.assertEqual(status["mode"], "simulation")
        self.client.post("/api/motor/commands", json={
            "command_id": "cleanup-2", "action": "disable"
        })

    def test_multimeter_endpoint_exposes_hardware_channels(self) -> None:
        response = self.client.get("/api/multimeter/readings")
        self.assertEqual(response.status_code, 200)
        channels = {item["channel"] for item in response.json()["channels"]}
        self.assertIn("motor_current", channels)
        self.assertIn("circuit_voltage", channels)
        self.assertNotIn("temperature", channels)

    def test_backend_owned_motor_sequence_can_be_cancelled(self) -> None:
        started = self.client.post("/api/motor/sequences/pwm-ramp").json()
        self.assertTrue(started["accepted"])
        cancelled = self.client.post("/api/motor/sequences/cancel").json()
        self.assertIn("disabled", cancelled["message"])
        status = self.client.get("/api/motor/status").json()
        self.assertFalse(status["state"]["enabled"])
        self.assertFalse(status["sequence"]["running"])
        events = self.client.get("/api/events").json()
        self.assertTrue(any(event["event_type"] == "MOTOR_SEQUENCE_CANCELLED" for event in events))

    def test_guided_circuit_diagnostic_reports_fault(self) -> None:
        profiles = self.client.get("/api/circuits/profiles").json()
        self.assertEqual(profiles["profiles"][0]["profile_id"], "12V-LOAD")
        report = self.client.post("/api/circuits/run", json={
            "profile_id": "12V-LOAD",
            "mode": "DIAGNOSE",
            "scenario": "shorted_load",
        }).json()
        self.assertEqual(report["condition"], "FAULT")
        self.assertTrue(any(step["result"] == "FAIL" for step in report["steps"]))


if __name__ == "__main__":
    unittest.main()
