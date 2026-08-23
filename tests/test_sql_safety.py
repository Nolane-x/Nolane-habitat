from __future__ import annotations

import unittest
import sqlite3
from types import MappingProxyType
from unittest.mock import patch

from habitat.sql_safety import (
    placeholder_group,
    quote_identifier,
    savepoint_identifier,
    user_version_pragma,
)
from habitat.storage import _JSON_TABLES
from habitat.storage_migrations import _ADDITIVE_COLUMNS, repair_additive_columns
from habitat.retention import _compaction_delete_sql


class SqlSafetyTests(unittest.TestCase):
    def test_quote_identifier_accepts_only_allow_list_members(self) -> None:
        allowed = frozenset({"sessions", "runs"})

        self.assertEqual('"sessions"', quote_identifier("sessions", allowed))
        with self.assertRaisesRegex(ValueError, "unsupported SQLite identifier"):
            quote_identifier("sessions; DROP TABLE files;--", allowed)

    def test_placeholder_group_has_one_placeholder_per_value(self) -> None:
        self.assertEqual("?", placeholder_group(1))
        self.assertEqual("?,?,?", placeholder_group(3))
        with self.assertRaisesRegex(ValueError, "positive"):
            placeholder_group(0)

    def test_savepoint_identifier_accepts_only_non_negative_integers(self) -> None:
        self.assertEqual('"habitat_atomic_3"', savepoint_identifier(3))
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            savepoint_identifier(-1)
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            savepoint_identifier(True)

    def test_user_version_pragma_accepts_only_non_negative_integers(self) -> None:
        self.assertEqual("PRAGMA user_version = 22", user_version_pragma(22))
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            user_version_pragma(-1)
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            user_version_pragma(True)

    def test_json_table_allow_list_is_immutable(self) -> None:
        self.assertIsInstance(_JSON_TABLES, frozenset)

    def test_migration_metadata_is_immutable(self) -> None:
        self.assertIsInstance(_ADDITIVE_COLUMNS, MappingProxyType)
        self.assertIsInstance(_ADDITIVE_COLUMNS["files"], MappingProxyType)

    def test_migration_rejects_a_non_allow_list_identifier_before_ddl(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        with patch(
            "habitat.storage_migrations.additive_schema_issues",
            return_value=["files.extra; DROP TABLE files;--"],
        ):
            with self.assertRaisesRegex(ValueError, "unsupported SQLite identifier"):
                repair_additive_columns(conn)

    def test_compaction_rejects_a_non_allow_list_identifier_before_sql(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported retention compaction rule"):
            _compaction_delete_sql(
                "trace_calls; DROP TABLE files;--", "seq", None
            )


if __name__ == "__main__":
    unittest.main()
