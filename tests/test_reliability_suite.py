import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.run_reliability_suite import normalize_reliability_report


class ReliabilitySuiteTests(unittest.TestCase):
    def test_report_binds_executed_fault_points_to_the_candidate(self):
        report = normalize_reliability_report(
            source_commit="a" * 40,
            executed_fault_points=(
                "semantic.shutdown.before_close",
                "storage.atomic.after_begin",
                "storage.atomic.before_commit",
            ),
            failures=(),
        )

        self.assertEqual("a" * 40, report["source_commit"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual(
            [
                "semantic.shutdown.before_close",
                "storage.atomic.after_begin",
                "storage.atomic.before_commit",
            ],
            report["executed_fault_points"],
        )
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_an_unbound_candidate_identity(self):
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_reliability_report(
                source_commit="not-a-commit",
                executed_fault_points=("storage.atomic.after_begin",),
                failures=(),
            )

    def test_suite_script_runs_from_a_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "faults.json"
            repository = Path(__file__).parents[1]

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/run_reliability_suite.py",
                    "--source-commit",
                    "a" * 40,
                    "--out",
                    str(output),
                ],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("passed", report["status"])
            self.assertEqual("a" * 40, report["source_commit"])
