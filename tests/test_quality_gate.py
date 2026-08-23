import unittest

from tools.quality_gate import evaluate_quality_gate


class QualityGateTests(unittest.TestCase):
    def test_quality_gate_accepts_complete_passing_evidence(self):
        report = evaluate_quality_gate(
            identity={"ok": True},
            matrix={"statuses": {"passed": 7, "failed": 0, "timeout": 0, "infra-error": 0}},
            scanners={"semgrep": {"errors": [], "results": []}},
            required_scanners=("semgrep",),
        )

        self.assertTrue(report["ok"])
        self.assertEqual([], report["failed_gates"])

    def test_quality_gate_blocks_when_required_scanner_evidence_is_missing(self):
        report = evaluate_quality_gate(
            identity={"ok": True},
            matrix={"statuses": {"passed": 7, "failed": 0, "timeout": 0, "infra-error": 0}},
            scanners={},
            required_scanners=("semgrep",),
        )

        self.assertFalse(report["ok"])
        self.assertIn("scanner:semgrep:missing", report["failed_gates"])


if __name__ == "__main__":
    unittest.main()
