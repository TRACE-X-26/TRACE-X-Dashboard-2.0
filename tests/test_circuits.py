import unittest

from diagnostic_platform.circuits import CircuitDiagnosticService


class CircuitDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CircuitDiagnosticService()

    def test_healthy_circuit_passes_all_test_points(self) -> None:
        report = self.service.run("12V-LOAD", "DIAGNOSE", "healthy")
        self.assertEqual(report["condition"], "HEALTHY")
        self.assertTrue(all(step["result"] == "PASS" for step in report["steps"]))

    def test_blown_fuse_is_located_after_supply_input(self) -> None:
        report = self.service.run("12V-LOAD", "DIAGNOSE", "blown_fuse")
        steps = {step["point_id"]: step for step in report["steps"]}
        self.assertEqual(report["condition"], "FAULT")
        self.assertEqual(steps["TP1"]["result"], "PASS")
        self.assertEqual(steps["TP2"]["result"], "FAIL")
        self.assertIn("fuse", report["conclusion"].lower())

    def test_learn_mode_creates_baseline_used_by_diagnosis(self) -> None:
        learned = self.service.run("12V-LOAD", "LEARN", "shorted_load")
        self.assertEqual(learned["scenario"], "healthy")
        self.assertEqual(learned["condition"], "LEARNED")
        diagnosed = self.service.run("12V-LOAD", "DIAGNOSE", "healthy")
        self.assertTrue(diagnosed["uses_learned_baseline"])


if __name__ == "__main__":
    unittest.main()
