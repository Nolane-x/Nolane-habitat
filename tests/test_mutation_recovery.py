import tempfile
import unittest
from pathlib import Path

from habitat.mutation import MutationEngine
from habitat.workspace import HabitatWorkspace


class MutationRecoveryTests(unittest.TestCase):
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
