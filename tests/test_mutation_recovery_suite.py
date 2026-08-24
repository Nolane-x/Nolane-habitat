import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.run_mutation_recovery_suite import normalize_mutation_recovery_report


class MutationRecoverySuiteTests(unittest.TestCase):
    def test_report_is_hash_bound_to_commit_and_recovery_outcomes(self):
        report = normalize_mutation_recovery_report(
            source_commit="a" * 40,
            scenarios={
                "text-interruption": True,
                "structural-interruption": True,
            },
        )

        self.assertEqual("a" * 40, report["source_commit"])
        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["failures"])
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_an_unbound_candidate_identity(self):
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_mutation_recovery_report(
                source_commit="not-a-commit",
                scenarios={"text-interruption": True},
            )

    def test_suite_script_runs_from_a_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "mutation-recovery.json"
            repository = Path(__file__).parents[1]

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/run_mutation_recovery_suite.py",
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


if __name__ == "__main__":
    unittest.main()
