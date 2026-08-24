import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.run_protocol_conformance_suite import main, normalize_protocol_conformance_report


class ProtocolConformanceSuiteTests(unittest.TestCase):
    def test_report_directly_replays_every_fixture_case(self):
        fixture_bytes = json.dumps(
            {
                "schema": 1,
                "protocol": "habitat.agent.v1alpha2",
                "cases": [
                    {
                        "id": "non-object",
                        "raw": "[]",
                        "expected_kind": "error",
                        "error_code": "INVALID_REQUEST",
                    },
                    {
                        "id": "capabilities",
                        "raw": '{"id":1,"method":"protocol.capabilities","params":{}}',
                        "expected_kind": "success",
                    },
                    {
                        "id": "unknown-method",
                        "raw": '{"id":2,"method":"protocol.not-real","params":{}}',
                        "expected_kind": "error",
                        "error_code": "NOT_FOUND",
                    },
                ],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        report = normalize_protocol_conformance_report(
            source_commit="a" * 40,
            fixture_bytes=fixture_bytes,
        )

        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual(3, report["executed_cases"])
        self.assertEqual(
            [
                {
                    "id": "non-object",
                    "expected_kind": "error",
                    "observed_kind": "error",
                    "expected_error_code": "INVALID_REQUEST",
                    "observed_error_code": "INVALID_REQUEST",
                    "passed": True,
                },
                {
                    "id": "capabilities",
                    "expected_kind": "success",
                    "observed_kind": "success",
                    "expected_error_code": None,
                    "observed_error_code": None,
                    "passed": True,
                },
                {
                    "id": "unknown-method",
                    "expected_kind": "error",
                    "observed_kind": "error",
                    "expected_error_code": "NOT_FOUND",
                    "observed_error_code": "NOT_FOUND",
                    "passed": True,
                },
            ],
            report["case_verdicts"],
        )
        self.assertEqual(hashlib.sha256(fixture_bytes).hexdigest(), report["fixture_sha256"])
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_empty_or_duplicate_case_corpora(self):
        invalid = (
            (
                {"schema": 1, "protocol": "habitat.agent.v1alpha2", "cases": []},
                "non-empty",
            ),
            (
                {
                    "schema": 1,
                    "protocol": "habitat.agent.v1alpha2",
                    "cases": [
                        {"id": "same", "raw": "[]", "expected_kind": "error", "error_code": "INVALID_REQUEST"},
                        {"id": "same", "raw": "{}", "expected_kind": "error", "error_code": "INVALID_REQUEST"},
                    ],
                },
                "unique",
            ),
        )
        for fixture, expected in invalid:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    normalize_protocol_conformance_report(
                        source_commit="a" * 40,
                        fixture_bytes=json.dumps(fixture).encode("utf-8"),
                    )

    def test_suite_main_preserves_protocol_unittest_coverage(self):
        with TemporaryDirectory() as td:
            report_path = Path(td) / "protocol-report.json"

            exit_code = main(
                ["--source-commit", "a" * 40, "--out", str(report_path)]
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(0, exit_code)
            self.assertGreater(report["executed_unittests"], 0)
            self.assertEqual([], report["unittest_failures"])
            self.assertEqual(
                report["executed_unittests"], len(report["unittest_scenarios"])
            )

    def test_report_rejects_an_unbound_candidate_identity(self):
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_protocol_conformance_report(
                source_commit="invalid",
                fixture_bytes=b"{}",
            )


if __name__ == "__main__":
    unittest.main()
