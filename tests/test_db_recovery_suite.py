import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.run_db_recovery_suite import normalize_db_recovery_report


class DatabaseRecoverySuiteTests(unittest.TestCase):
    def test_report_is_hash_bound_to_commit_and_scenario_outcomes(self):
        report = normalize_db_recovery_report(
            source_commit="a" * 40,
            sqlite_version="3.46.1",
            scenarios={
                "contention": True,
                "migration_rollback": True,
                "nested_rollback_reopen": True,
            },
        )

        self.assertEqual("a" * 40, report["source_commit"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_a_commit_that_cannot_identify_a_candidate(self):
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_db_recovery_report(
                source_commit="not-a-commit",
                sqlite_version="3.46.1",
                scenarios={"contention": True},
            )

    def test_suite_script_runs_from_a_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "db-recovery.json"
            repository = Path(__file__).parents[1]

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/run_db_recovery_suite.py",
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
