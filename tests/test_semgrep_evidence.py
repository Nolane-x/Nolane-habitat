from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from tools.run_semgrep import main, normalize_semgrep_report


class SemgrepEvidenceTests(unittest.TestCase):
    def test_normalized_report_binds_ruleset_target_and_candidate_commit(self) -> None:
        report = normalize_semgrep_report(
            {"results": [{"check_id": "rule", "path": "workflow.yml"}], "errors": []},
            ruleset="p/github-actions",
            source_commit="a" * 40,
            target=".github",
        )

        self.assertEqual("semgrep", report["scanner"])
        self.assertEqual("p/github-actions", report["ruleset"])
        self.assertEqual("a" * 40, report["source_commit"])
        self.assertEqual(".github", report["target"])
        self.assertEqual(1, report["findings"])
        self.assertEqual("failed", report["status"])
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_normalized_report_is_passing_only_without_findings_or_errors(self) -> None:
        report = normalize_semgrep_report(
            {"results": [], "errors": []},
            ruleset="p/github-actions",
            source_commit="b" * 40,
            target=".github",
        )

        self.assertEqual("passed", report["status"])
        self.assertEqual(0, report["findings"])
        self.assertEqual(0, report["errors"])

    def test_normalized_report_rejects_an_invalid_candidate_commit(self) -> None:
        with self.assertRaisesRegex(ValueError, "40-character lowercase SHA"):
            normalize_semgrep_report(
                {"results": [], "errors": []},
                ruleset="p/github-actions",
                source_commit="not-a-commit",
                target=".github",
            )

    def test_missing_semgrep_writes_failed_evidence_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "semgrep.json"
            with patch("tools.run_semgrep.subprocess.run", side_effect=FileNotFoundError):
                result = main([
                    "--source-commit", "c" * 40,
                    "--out", str(output),
                ])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(1, result)
            self.assertEqual("failed", report["status"])
            self.assertGreater(report["errors"], 0)

    def test_runner_uses_the_isolated_semgrep_executable_from_its_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "semgrep.json"
            with (
                patch.dict(
                    "tools.run_semgrep.os.environ",
                    {"HABITAT_SEMGREP_EXECUTABLE": "isolated-semgrep"},
                ),
                patch(
                    "tools.run_semgrep.subprocess.run",
                    return_value=CompletedProcess(
                        args=[], returncode=0, stdout='{"results": [], "errors": []}'
                    ),
                ) as run,
            ):
                result = main([
                    "--source-commit", "d" * 40,
                    "--out", str(output),
                ])

            self.assertEqual(0, result)
            self.assertEqual("isolated-semgrep", run.call_args.args[0][0])


if __name__ == "__main__":
    unittest.main()
