"""Read-only SQLite health inspection for Habitat workspaces."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .storage_migrations import SCHEMA_VERSION, required_schema_issues


def inspect_connection(conn: sqlite3.Connection) -> dict:
    integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    foreign_key_violations = [
        dict(row) for row in conn.execute("PRAGMA foreign_key_check")
    ]
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        meta_version = row[0] if row else None
    except sqlite3.OperationalError:
        meta_version = None
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    missing_columns = required_schema_issues(conn)
    schema_ok = (
        meta_version == str(SCHEMA_VERSION)
        and user_version == SCHEMA_VERSION
        and not missing_columns
    )
    return {
        "ok": integrity == ["ok"] and not foreign_key_violations and schema_ok,
        "schema": {
            "expected_version": SCHEMA_VERSION,
            "meta_version": meta_version,
            "user_version": user_version,
            "missing_columns": missing_columns,
        },
        "sqlite": {
            "integrity_check": integrity,
            "foreign_key_violations": foreign_key_violations,
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        },
    }


def inspect_database(db_path: Path) -> dict:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return inspect_connection(conn)
    finally:
        conn.close()
