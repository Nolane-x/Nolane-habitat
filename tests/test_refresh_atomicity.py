import sqlite3
import tempfile
import unittest
from pathlib import Path

if __package__:
    from .support import WorkspaceTemporaryDirectory
else:
    from support import WorkspaceTemporaryDirectory

from habitat.model import FileRecord
from habitat.storage import Store


class RefreshAtomicityTests(unittest.TestCase):
    def test_failed_refresh_cannot_be_committed_by_a_later_write(self):
        with WorkspaceTemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            module = source / "module.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            workspace = td.create_workspace(source, root / "habitat")
            workspace.enter()
            before_revision = workspace.revision
            before_digest = workspace.store.file_by_path("module.py")["digest"]
            module.write_text("VALUE = 2\n", encoding="utf-8")

            persist = workspace._persist_compiled

            def fail_after_persist(compiled):
                persist(compiled)
                raise RuntimeError("injected refresh failure")

            workspace._persist_compiled = fail_after_persist
            with self.assertRaisesRegex(RuntimeError, "injected"):
                workspace.refresh("atomicity-test")

            workspace.store.save_json("runs", "independent-write", {"ok": True})
            external = sqlite3.connect(workspace.store.db_path)
            try:
                digest = external.execute(
                    "SELECT digest FROM files WHERE path = 'module.py'"
                ).fetchone()[0]
                self.assertEqual(before_digest, digest)
            finally:
                external.close()
            self.assertEqual(before_revision, workspace.store.head_revision())

    def test_base_exception_rolls_back_before_any_later_commit(self):
        class Cancellation(BaseException):
            pass

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "habitat.sqlite3"
            store = Store(db_path)
            try:
                with self.assertRaises(Cancellation):
                    with store.atomic():
                        store.upsert_file(
                            FileRecord("file:cancelled", "cancelled.py", "python", 1, "digest", 1)
                        )
                        raise Cancellation()
                store.save_json("runs", "later-write", {"ok": True})
                external = sqlite3.connect(db_path)
                try:
                    count = external.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                finally:
                    external.close()
            finally:
                store.close()

        self.assertEqual(0, count)
