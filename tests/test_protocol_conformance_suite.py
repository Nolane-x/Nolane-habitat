import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.run_protocol_conformance_suite import normalize_protocol_conformance_report


class ProtocolConformanceSuiteTests(unittest.TestCase):
    def test_report_directly_replays_every_fixture_case(self):
        fixture_bytes = json.dumps(
            {
                "schema": 1,
                "protocol": "habitat.agent.v1alpha2",
                "cases": [
                    {"id": "non-object", "raw": "[]", "error_code": "INVALID_REQUEST"},
                    {
                        "id": "duplicate-key",
                        "raw": '{"id":1,"id":2,"method":"protocol.capabilities","params":{}}',
                        "error_code": "INVALID_JSON",
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
        self.assertEqual(2, report["executed_cases"])
        self.assertEqual(
            [
                {
                    "id": "non-object",
                    "expected_error_code": "INVALID_REQUEST",
                    "observed_error_code": "INVALID_REQUEST",
                    "passed": True,
                },
                {
                    "id": "duplicate-key",
                    "expected_error_code": "INVALID_JSON",
                    "observed_error_code": "INVALID_JSON",
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
                        {"id": "same", "raw": "[]", "error_code": "INVALID_REQUEST"},
                        {"id": "same", "raw": "{}", "error_code": "INVALID_REQUEST"},
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

    def test_report_rejects_an_unbound_candidate_identity(self):
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_protocol_conformance_report(
                source_commit="invalid",
                fixture_bytes=b"{}",
            )


if __name__ == "__main__":
    unittest.main()
