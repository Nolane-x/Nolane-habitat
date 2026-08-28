from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from habitat.storage import Store, _index_terms


_REPOSITORY_ACCESSORS = (
    "_symbols_repository",
    "_relations_repository",
    "_runtime_repository",
    "_evidence_repository",
    "_experimentation_repository",
    "_learning_repository",
)

_DOMAIN_TABLES = (
    "meta",
    "symbols",
    "relations",
    "runtime_events",
    "evidence",
    "hypotheses",
    "experiments",
    "context_feedback",
    "epistemic_items",
    "project_memories",
)


class StoreRepositoryOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "habitat.db"
        self.store = Store(self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def _snapshot(self) -> dict:
        user_version = int(self.store.conn.execute("PRAGMA user_version").fetchone()[0])
        row_counts = {
            table: int(self.store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _DOMAIN_TABLES
        }
        return {
            "user_version": user_version,
            "in_transaction": bool(self.store.conn.in_transaction),
            "total_changes": int(self.store.conn.total_changes),
            "row_counts": row_counts,
        }

    def test_repository_accessors_are_lazy_stable_and_side_effect_free(self) -> None:
        before = self._snapshot()

        for name in _REPOSITORY_ACCESSORS:
            accessor = getattr(self.store, name, None)
            self.assertTrue(callable(accessor), f"Store must expose repository accessor {name}")
            first = accessor()
            second = accessor()
            self.assertIs(first, second, f"{name} must return one stable repository instance")
            self.assertIs(first.owner, self.store, f"{name} repository must retain its owning Store")

        self.assertEqual(self._snapshot(), before)

    def test_repository_instances_are_not_eagerly_created(self) -> None:
        repository_state = {
            key: value
            for key, value in vars(self.store).items()
            if "repository" in key
        }
        self.assertEqual(repository_state, {})

    def test_index_terms_characterization_is_preserved_before_helper_move(self) -> None:
        self.assertEqual(
            _index_terms("fooBar_baz-qux 12 x HTTPRequest_v2-test"),
            ["bar", "baz", "foo", "httprequest", "qux", "test", "v2"],
        )
        self.assertEqual(_index_terms("A 1 _ -"), [])
        self.assertEqual(_index_terms("alpha alpha ALPHA"), ["alpha"])


if __name__ == "__main__":
    unittest.main()
