import os
import tempfile
import unittest
from pathlib import Path

from habitat.mutation import TransactionConflict
from habitat.workspace import HabitatWorkspace


@unittest.skipUnless(os.name == "nt", "Win32 path alias semantics")
class WindowsPathIdentityTests(unittest.TestCase):
    def test_file_aliases_cannot_bypass_an_exact_deny(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            protected = project / "VERSION"
            protected.write_text("0.1.0-alpha.19\n", encoding="utf-8")
            self.assertTrue((project / "VERSION.").samefile(protected))
            self.assertTrue((project / "version").samefile(protected))
            self.assertTrue((project / "VERSION::$DATA").samefile(protected))
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update(
                    {
                        "source": {"edit": ["**"], "deny": ["VERSION"]},
                        "structural_mutation": {"approval_required": False},
                    }
                )

                case_decision = workspace.policy_evaluate("edit", path="version")[
                    "decision"
                ]
                self.assertFalse(case_decision["allowed"])
                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "replace_text",
                                "path": "version",
                                "old": "alpha.19",
                                "new": "alpha.20",
                            }
                        ]
                    )
                for unsafe_alias in ("VERSION.", "VERSION::$DATA"):
                    with self.subTest(unsafe_alias=unsafe_alias):
                        with self.assertRaises(ValueError):
                            workspace.stage_change(
                                [
                                    {
                                        "op": "replace_text",
                                        "path": unsafe_alias,
                                        "old": "alpha.19",
                                        "new": "alpha.20",
                                    }
                                ]
                            )

                self.assertEqual(
                    "0.1.0-alpha.19\n", protected.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    0,
                    workspace.store.conn.execute(
                        "SELECT COUNT(*) FROM transactions"
                    ).fetchone()[0],
                )
            finally:
                workspace.close()

    def test_case_aliases_share_one_path_lease_identity(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "VERSION").write_text(
                "0.1.0-alpha.19\n", encoding="utf-8"
            )
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                first_agent = workspace.agent_open("first")["id"]
                second_agent = workspace.agent_open("second")["id"]
                transaction = workspace.stage_change(
                    [
                        {
                            "op": "replace_text",
                            "path": "VERSION",
                            "old": "alpha.19",
                            "new": "alpha.20",
                        }
                    ],
                    agent_id=first_agent,
                )

                self.assertEqual(["version"], transaction["lease_resources"])
                with self.assertRaises(TransactionConflict):
                    workspace.stage_change(
                        [
                            {
                                "op": "replace_text",
                                "path": "version",
                                "old": "alpha.19",
                                "new": "alpha.21",
                            }
                        ],
                        agent_id=second_agent,
                    )
                for unsafe_alias in ("VERSION.", "VERSION::$DATA"):
                    with self.subTest(unsafe_alias=unsafe_alias):
                        with self.assertRaises(ValueError):
                            workspace.lease_acquire(
                                second_agent, "path", unsafe_alias
                            )
            finally:
                workspace.close()


if __name__ == "__main__":
    unittest.main()
