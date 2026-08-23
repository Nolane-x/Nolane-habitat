import tempfile
import unittest
from pathlib import Path

from habitat.storage import Store


class StorageRecoveryTests(unittest.TestCase):
    def test_nested_atomic_failure_reopens_at_the_last_committed_state(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "habitat.sqlite3"
            store = Store(db_path)
            try:
                store.set_meta("recovery-probe", "stable")
                with self.assertRaisesRegex(RuntimeError, "injected nested failure"):
                    with store.atomic():
                        store.set_meta("recovery-probe", "outer")
                        with store.atomic():
                            store.set_meta("recovery-probe", "inner")
                            raise RuntimeError("injected nested failure")
            finally:
                store.close()

            reopened = Store(db_path)
            try:
                report = reopened.doctor()
                self.assertEqual("stable", reopened.get_meta("recovery-probe"))
            finally:
                reopened.close()

        self.assertTrue(report["ok"])
        self.assertEqual(["ok"], report["sqlite"]["integrity_check"])
        self.assertEqual([], report["sqlite"]["foreign_key_violations"])
