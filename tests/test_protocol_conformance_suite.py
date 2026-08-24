import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.run_protocol_conformance_suite import normalize_protocol_conformance_report


class ProtocolConformanceSuiteTests(unittest.TestCase):
    def test_report_binds_fixture_and_outcomes_to_the_candidate_commit(self):
        report = normalize_protocol_conformance_report(
            source_commit="a" * 40,
            fixture_bytes=b'{"cases":[]}',
            scenarios={"adversarial-transport": True, "oversize-rejection": True},
        )

        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual(hashlib.sha256(b'{"cases":[]}').hexdigest(), report["fixture_sha256"])
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_an_unbound_candidate_identity(self):
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_protocol_conformance_report(
                source_commit="invalid",
                fixture_bytes=b"{}",
                scenarios={},
            )


if __name__ == "__main__":
    unittest.main()
