import tempfile
import unittest
from pathlib import Path

from habitat.mutation import MutationEngine
from habitat.workspace import HabitatWorkspace


class MutationRecoveryTests(unittest.TestCase):
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
