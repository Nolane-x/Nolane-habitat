from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.run_foundation_convergence_closure import build_certification_report


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "FOUNDATION-CONVERGENCE-CLOSURE.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SOURCE_COMMIT = "a" * 40


class FoundationConvergenceActiveCertificationTests(unittest.TestCase):
    def test_active_certification_binds_exact_commit_manifest_and_all_criteria(self):
        calls: list[tuple[str, ...]] = []

        def fake_runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
            self.assertEqual(ROOT, cwd)
            self.assertEqual(SOURCE_COMMIT, env["HABITAT_SOURCE_COMMIT"])
            calls.append(tuple(argv))
            return 0, "verified\n", ""

        with TemporaryDirectory() as tmp:
            report = build_certification_report(
                ROOT,
                source_commit=SOURCE_COMMIT,
                manifest_path=MANIFEST,
                artifact_dir=Path(tmp),
                command_runner=fake_runner,
                checkout_commit=SOURCE_COMMIT,
            )

        self.assertEqual(1, report["schema"])
        self.assertEqual("foundation-convergence-certification", report["suite"])
        self.assertEqual(SOURCE_COMMIT, report["source_commit"])
        self.assertEqual(SOURCE_COMMIT, report["checkout_commit"])
        self.assertRegex(report["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("passed", report["status"])
        self.assertEqual(12, report["criteria_total"])
        self.assertEqual(12, report["criteria_verified"])
        self.assertEqual([], report["failed_criterion_ids"])
        self.assertEqual(list(range(1, 13)), [item["id"] for item in report["criteria"]])
        self.assertTrue(all(item["status"] == "passed" for item in report["criteria"]))
        self.assertGreaterEqual(len(calls), 12)
        self.assertTrue(all(call[0] for call in calls))
        self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_failed_verification_fails_only_affected_criterion_and_global_status(self):
        def fake_runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
            joined = " ".join(argv)
            if "test_truth_authority" in joined:
                return 1, "", "authority proof failed"
            return 0, "verified", ""

        with TemporaryDirectory() as tmp:
            report = build_certification_report(
                ROOT,
                source_commit=SOURCE_COMMIT,
                manifest_path=MANIFEST,
                artifact_dir=Path(tmp),
                command_runner=fake_runner,
                checkout_commit=SOURCE_COMMIT,
            )

        self.assertEqual("failed", report["status"])
        self.assertIn(4, report["failed_criterion_ids"])
        self.assertIn(11, report["failed_criterion_ids"])
        by_id = {item["id"]: item for item in report["criteria"]}
        self.assertEqual("failed", by_id[4]["status"])
        self.assertEqual("failed", by_id[11]["status"])
        self.assertEqual("passed", by_id[3]["status"])

    def test_checkout_commit_mismatch_is_rejected_before_any_verification_runs(self):
        calls: list[list[str]] = []

        def fake_runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
            calls.append(argv)
            return 0, "", ""

        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "checkout commit"):
                build_certification_report(
                    ROOT,
                    source_commit=SOURCE_COMMIT,
                    manifest_path=MANIFEST,
                    artifact_dir=Path(tmp),
                    command_runner=fake_runner,
                    checkout_commit="b" * 40,
                )
        self.assertEqual([], calls)

    def test_ci_gates_and_uploads_active_closure_report(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Certify Foundation Convergence evidence", workflow)
        self.assertIn(
            "python tools/run_foundation_convergence_closure.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/foundation-convergence-closure.json",
            workflow,
        )
        self.assertIn("path: .test-artifacts/", workflow)

    def test_manifest_declares_non_shell_verification_for_every_criterion(self):
        import json

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(list(range(1, 13)), [item["id"] for item in manifest["criteria"]])
        for item in manifest["criteria"]:
            commands = item["verification"]
            self.assertTrue(commands, f"criterion {item['id']} needs active verification")
            for command in commands:
                self.assertIsInstance(command, list)
                self.assertGreaterEqual(len(command), 2)
                self.assertEqual("python", command[0])
                self.assertTrue(all(isinstance(part, str) and part for part in command))
                joined = " ".join(command)
                self.assertFalse(re.search(r"(?:&&|\|\||;|`|\$\()", joined), joined)


if __name__ == "__main__":
    unittest.main()
