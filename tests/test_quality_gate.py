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

    def test_quality_gate_blocks_scanner_evidence_for_a_different_commit(self):
        report = evaluate_quality_gate(
            identity={"ok": True},
            matrix={"statuses": {"passed": 7, "failed": 0, "timeout": 0, "infra-error": 0}},
            scanners={
                "semgrep": {
                    "scanner": "semgrep",
                    "source_commit": "b" * 40,
                    "findings": 0,
                    "errors": 0,
                    "status": "passed",
                    "report_sha256": "c" * 64,
                }
            },
            required_scanners=("semgrep",),
            expected_commit="a" * 40,
        )

        self.assertFalse(report["ok"])
        self.assertIn("scanner:semgrep:source-commit-mismatch", report["failed_gates"])

    def test_quality_gate_becomes_commit_bound_evidence_when_requested(self):
        commit = "a" * 40
        scanner = {
            "scanner": "semgrep",
            "source_commit": commit,
            "findings": 0,
            "errors": 0,
            "status": "passed",
        }
        import hashlib
        import json

        scanner["report_sha256"] = hashlib.sha256(
            json.dumps(scanner, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        report = evaluate_quality_gate(
            identity={"ok": True},
            matrix={"statuses": {"passed": 7, "failed": 0, "timeout": 0, "infra-error": 0}},
            scanners={"semgrep": scanner},
            required_scanners=("semgrep",),
            expected_commit=commit,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(commit, report["source_commit"])
        self.assertEqual("passed", report["status"])
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
