import tempfile
import unittest
from pathlib import Path

from habitat.mutation import MutationEngine, TransactionConflict
from habitat.workspace import HabitatWorkspace


class MutationRecoveryTests(unittest.TestCase):
    def test_canonical_policy_path_blocks_equivalent_git_hook_mutations(self):
        variants = (
            "./.git/hooks/pre-commit",
            ".git//hooks/./pre-commit",
            ".git\\hooks\\pre-commit",
        )
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update(
                    {
                        "source": {"edit": ["**"], "deny": [".git/hooks/pre-commit"]},
                        "structural_mutation": {"approval_required": False},
                    }
                )

                for raw_path in variants:
                    with self.subTest(raw_path=raw_path):
                        decision = workspace.policy_evaluate("edit", path=raw_path)["decision"]
                        self.assertFalse(decision["allowed"])
                        with self.assertRaises(PermissionError):
                            transaction = workspace.stage_change(
                                [
                                    {
                                        "op": "create_file",
                                        "path": raw_path,
                                        "content": "#!/usr/bin/env python\n",
                                        "mode": 0o755,
                                    }
                                ]
                            )
                            workspace.commit_change(transaction["id"])

                self.assertFalse((project / ".git" / "hooks" / "pre-commit").exists())
                self.assertEqual(
                    0,
                    workspace.store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
                )
            finally:
                workspace.close()

    def test_canonical_policy_path_checks_both_move_endpoints(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "blocked.py").write_text("blocked = True\n", encoding="utf-8")
            (project / "safe.py").write_text("safe = True\n", encoding="utf-8")
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update(
                    {
                        "source": {
                            "edit": ["**"],
                            "deny": ["blocked.py", "blocked-target.py"],
                        },
                        "structural_mutation": {"approval_required": False},
                    }
                )

                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "move_file",
                                "from_path": "./blocked.py",
                                "to_path": "out.py",
                            }
                        ]
                    )
                with self.assertRaises(PermissionError):
                    workspace.stage_change(
                        [
                            {
                                "op": "move_file",
                                "from_path": "./safe.py",
                                "to_path": ".\\blocked-target.py",
                            }
                        ]
                    )
            finally:
                workspace.close()

    def test_equivalent_paths_share_one_agent_lease_resource(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "a.py").write_text("value = 1\n", encoding="utf-8")
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                first_agent = workspace.agent_open("first")["id"]
                second_agent = workspace.agent_open("second")["id"]
                transaction = workspace.stage_change(
                    [
                        {
                            "op": "replace_text",
                            "path": ".\\a.py",
                            "old": "value = 1",
                            "new": "value = 2",
                        }
                    ],
                    agent_id=first_agent,
                )
                self.assertEqual("a.py", transaction["operations"][0]["path"])
                self.assertEqual(["a.py"], transaction["lease_resources"])

                with self.assertRaises(TransactionConflict):
                    workspace.stage_change(
                        [
                            {
                                "op": "replace_text",
                                "path": "./a.py",
                                "old": "value = 1",
                                "new": "value = 3",
                            }
                        ],
                        agent_id=second_agent,
                    )
            finally:
                workspace.close()

    def test_rejects_invalid_operations_before_reconciling_or_persisting(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "a.py"
            source.write_text("value = 1\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            try:
                # Deliberately make the source manifest stale. An invalid request must
                # still fail before it can reconcile that drift into SQLite state.
                source.write_text("value = 2\n", encoding="utf-8")
                source_before = source.read_bytes()
                revision_before = workspace.revision
                database_before = "\n".join(workspace.store.conn.iterdump())

                with self.assertRaisesRegex(ValueError, "operations must be a non-empty list"):
                    workspace.stage_change([])

                self.assertEqual(source_before, source.read_bytes())
                self.assertEqual(revision_before, workspace.revision)
                self.assertEqual(database_before, "\n".join(workspace.store.conn.iterdump()))
                self.assertFalse((workspace_path / "transactions").exists())
            finally:
                workspace.close()

    def test_rejects_invalid_payload_before_consuming_approval(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "a.py").write_text("value = 1\n", encoding="utf-8")
            workspace = HabitatWorkspace.create(project, base / "workspace")
            try:
                workspace.policy_update({"structural_mutation": {"approval_required": True}})
                approval = workspace.approval_grant("edit", granted_by="reviewer")

                with self.assertRaisesRegex(ValueError, "create_file requires UTF-8 string content"):
                    workspace.stage_change(
                        [{"op": "create_file", "path": "new.py", "content": 7}],
                        approval_id=approval["id"],
                    )

                consumed_at = workspace.store.conn.execute(
                    "SELECT consumed_at FROM approvals WHERE id=?", (approval["id"],)
                ).fetchone()[0]
                self.assertIsNone(consumed_at)
                self.assertFalse((project / "new.py").exists())
            finally:
                workspace.close()

    def test_reopen_rolls_back_an_interrupted_text_replacement_once(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "a.py"
            source.write_text("value = 1\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            engine = MutationEngine(workspace)
            transaction = engine.begin(
                [{"op": "replace_text", "path": "a.py", "old": "value = 1", "new": "value = 2"}]
            )
            originals, outputs, _ = engine._prepare(transaction.operations)
            journal = {
                "version": engine.JOURNAL_VERSION,
                "transaction_id": transaction.id,
                "base_revision": transaction.base_revision,
                "state": "applying",
                "backup_meta": engine._backup(transaction, originals),
                "applied": [{"op": "write", "path": "a.py"}],
                "created_at": "fixture",
            }
            engine._write_journal(transaction.id, journal)
            workspace.write_source_bytes("a.py", outputs["a.py"])
            workspace.close()

            reopened = HabitatWorkspace(workspace_path)
            try:
                self.assertEqual("value = 1\n", source.read_text(encoding="utf-8"))
                self.assertIn(
                    {"transaction_id": transaction.id, "action": "rolled-back-incomplete-transaction"},
                    reopened.enter()["startup_transaction_recovery"],
                )
            finally:
                reopened.close()

            reopened_again = HabitatWorkspace(workspace_path)
            try:
                self.assertEqual([], reopened_again.enter()["startup_transaction_recovery"])
            finally:
                reopened_again.close()

    def test_reopen_restores_a_partial_structural_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "keep.py").write_text("keep = True\n", encoding="utf-8")
            (project / "delete.py").write_text("delete = True\n", encoding="utf-8")
            workspace_path = base / "workspace"
            workspace = HabitatWorkspace.create(project, workspace_path)
            engine = MutationEngine(workspace)
            transaction = engine.begin(
                [
                    {"op": "create_file", "path": "created.py", "content": "created = True\n"},
                    {"op": "move_file", "from_path": "keep.py", "to_path": "moved.py"},
                    {"op": "delete_file", "path": "delete.py"},
                ]
            )
            originals, outputs, _ = engine._prepare(transaction.operations)
            journal = {
                "version": engine.JOURNAL_VERSION,
                "transaction_id": transaction.id,
                "base_revision": transaction.base_revision,
                "state": "applying",
                "backup_meta": engine._backup(transaction, originals),
                "applied": [
                    {"op": "write", "path": "created.py"},
                    {"op": "move", "from": "keep.py", "to": "moved.py"},
                    {"op": "delete", "path": "delete.py"},
                ],
                "created_at": "fixture",
            }
            engine._write_journal(transaction.id, journal)
            workspace.write_source_bytes("created.py", outputs["created.py"])
            workspace.move_source_file("keep.py", "moved.py")
            workspace.delete_source_file("delete.py")
            workspace.close()

            reopened = HabitatWorkspace(workspace_path)
            try:
                self.assertEqual("keep = True\n", (project / "keep.py").read_text(encoding="utf-8"))
                self.assertEqual("delete = True\n", (project / "delete.py").read_text(encoding="utf-8"))
                self.assertFalse((project / "created.py").exists())
                self.assertFalse((project / "moved.py").exists())
                self.assertIn(
                    {"transaction_id": transaction.id, "action": "rolled-back-incomplete-transaction"},
                    reopened.enter()["startup_transaction_recovery"],
                )
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
