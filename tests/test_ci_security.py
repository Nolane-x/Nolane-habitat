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


if __name__ == "__main__":
    unittest.main()
