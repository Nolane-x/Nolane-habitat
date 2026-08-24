from __future__ import annotations

import re
import unittest
from pathlib import Path


class CiSecurityTests(unittest.TestCase):
    def test_pull_request_release_evidence_binds_to_the_head_commit(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn(
            "HABITAT_SOURCE_COMMIT: ${{ github.event.pull_request.head.sha || github.sha }}",
            workflow,
        )
        self.assertEqual(
            workflow.count("ref: ${{ env.HABITAT_SOURCE_COMMIT }}"),
            3,
        )
        self.assertNotIn("--source-commit ${{ github.sha }}", workflow)
        self.assertNotIn("ref: ${{ github.sha }}", workflow)

    def test_workflow_actions_are_pinned_to_immutable_commits(self) -> None:
        root = Path(__file__).parents[1]
        workflows = (root / ".github" / "workflows" / "ci.yml", root / ".github" / "workflows" / "codeql.yml")

        for workflow in workflows:
            actions = re.findall(r"^\s*(?:-\s+)?uses:\s+[^@\s]+@([^\s#]+)", workflow.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertTrue(actions, f"no actions found in {workflow}")
            for action in actions:
                self.assertRegex(action, r"^[0-9a-f]{40}$", f"mutable action reference in {workflow}: {action}")

    def test_ci_binds_semgrep_evidence_to_the_github_commit(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertNotIn('"semgrep>=', pyproject)
        self.assertIn("python -m venv .semgrep-venv", workflow)
        self.assertIn("HABITAT_SEMGREP_EXECUTABLE", workflow)
        self.assertIn('"$semgrep_python" -m pip install "semgrep==1.168.0"', workflow)
        self.assertIn('semgrep_env_path=".semgrep-venv\\Scripts\\semgrep.exe"', workflow)
        self.assertIn(
            "python tools/run_semgrep.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/semgrep-workflows.json",
            workflow,
        )
        self.assertIn(
            "--scanner semgrep=.test-artifacts/semgrep-workflows.json --require-scanner semgrep --expected-commit ${{ env.HABITAT_SOURCE_COMMIT }}",
            workflow,
        )

    def test_ci_binds_recovery_and_fault_evidence_to_the_github_commit(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn(
            "python tools/run_db_recovery_suite.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/db-recovery.json",
            workflow,
        )
        self.assertIn(
            "python tools/run_mutation_recovery_suite.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/mutation-recovery.json",
            workflow,
        )
        self.assertIn(
            "python tools/run_reliability_suite.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/faults.json",
            workflow,
        )
        self.assertIn(
            "python tools/verify_contracts.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --fixture tests/fixtures/contracts/agent-v1alpha2.json --out .test-artifacts/contract.json",
            workflow,
        )
        self.assertIn(
            "python tools/run_protocol_conformance_suite.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/protocol-conformance.json",
            workflow,
        )
        self.assertIn(
            "python tools/normalize_sdist.py --dist .test-artifacts/dist-first --epoch 0",
            workflow,
        )
        self.assertIn(
            "python tools/normalize_sdist.py --dist .test-artifacts/dist-second --epoch 0",
            workflow,
        )
        self.assertIn(
            "path: .test-artifacts/source-first",
            workflow,
        )
        self.assertIn(
            "path: .test-artifacts/source-second",
            workflow,
        )
        self.assertIn(
            "python tools/verify_reproducible_build.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --first .test-artifacts/dist-first --second .test-artifacts/dist-second --first-source .test-artifacts/source-first --second-source .test-artifacts/source-second --out .test-artifacts/reproducible-build.json",
            workflow,
        )
        self.assertIn(
            "python tools/verify_distribution.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --dist .test-artifacts/dist-first --out .test-artifacts/artifacts.json",
            workflow,
        )

    def test_ci_binds_identity_and_matrix_evidence_to_the_github_commit(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn(
            "python tools/check_release_identity.py --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/identity.json",
            workflow,
        )
        self.assertIn(
            "python tools/run_test_matrix.py --mode shard --workers 1 --timeout 600 --source-commit ${{ env.HABITAT_SOURCE_COMMIT }} --out .test-artifacts/matrix.json",
            workflow,
        )
        self.assertIn("--out .test-artifacts/truth-core.json", workflow)

    def test_ci_installs_the_declared_build_backend_before_no_isolation_build(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn('python -m pip install -U pip "setuptools>=68"', workflow)
        self.assertIn("SOURCE_DATE_EPOCH: \"0\"", workflow)
        self.assertIn("python -m build --no-isolation --outdir ../dist-first", workflow)
        self.assertIn("python -m build --no-isolation --outdir ../dist-second", workflow)
        self.assertIn("working-directory: .test-artifacts/source-first", workflow)
        self.assertIn("working-directory: .test-artifacts/source-second", workflow)


if __name__ == "__main__":
    unittest.main()
