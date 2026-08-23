import tempfile
import unittest
from pathlib import Path

from habitat.storage import Store, StoreBusyError


class StorageContentionTests(unittest.TestCase):
    def test_locked_writer_fails_cleanly_without_leaving_a_transaction_open(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "habitat.sqlite3"
            owner = Store(db_path)
            contender = Store(db_path)
            try:
                owner.conn.execute("BEGIN IMMEDIATE")
                with self.assertRaisesRegex(StoreBusyError, "busy"):
                    with contender.atomic():
                        pass
                self.assertFalse(contender.conn.in_transaction)
            finally:
                if owner.conn.in_transaction:
                    owner.conn.rollback()
                contender.close()
                owner.close()
