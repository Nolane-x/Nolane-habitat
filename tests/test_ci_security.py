from __future__ import annotations

import re
import unittest
from pathlib import Path


class CiSecurityTests(unittest.TestCase):
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
            "python tools/run_semgrep.py --source-commit ${{ github.sha }} --out .test-artifacts/semgrep-workflows.json",
            workflow,
        )
        self.assertIn(
            "--scanner semgrep=.test-artifacts/semgrep-workflows.json --require-scanner semgrep --expected-commit ${{ github.sha }}",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
