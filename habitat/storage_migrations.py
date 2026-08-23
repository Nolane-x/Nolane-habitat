"""Small, explicit compatibility repairs for Habitat SQLite workspaces."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 22

_ADDITIVE_COLUMNS = {
    "files": {
        "indexed_bytes": "INTEGER NOT NULL DEFAULT 0",
        "index_truncated": "INTEGER NOT NULL DEFAULT 0",
        "parse_complete": "INTEGER NOT NULL DEFAULT 1",
    },
    "context_faults": {
        "authority_bytes_read": "INTEGER NOT NULL DEFAULT 0",
    },
}

_REQUIRED_COLUMNS = {
    "files": {
        "id", "path", "language", "size", "digest", "mtime_ns",
        "indexed_bytes", "index_truncated", "parse_complete",
    },
    "context_faults": {
        "seq", "handle", "page_id", "object_id", "path", "source_bytes",
        "authority_bytes_read", "revision", "episode_id", "fetched_at",
    },
}


def preflight_schema_version(conn: sqlite3.Connection) -> None:
    """Refuse a workspace produced by a newer Habitat before mutating it."""

    versions = [conn.execute("PRAGMA user_version").fetchone()[0]]
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if has_meta:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row:
            try:
                versions.append(int(row[0]))
            except (TypeError, ValueError):
                raise RuntimeError("Workspace schema version marker is invalid.") from None
    newer_version = max(versions)
    if newer_version > SCHEMA_VERSION:
        raise RuntimeError(
            "Workspace schema version "
            f"{newer_version} is newer than this Habitat build ({SCHEMA_VERSION})."
        )


def migration_backup_version(conn: sqlite3.Connection) -> int | None:
    """Return the legacy version that must be backed up before repair, if any."""

    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if not has_meta:
        return None
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    if not row:
        return None
    try:
        meta_version = int(row[0])
    except (TypeError, ValueError):
        return None
    if max(user_version, meta_version) < SCHEMA_VERSION or required_schema_issues(conn):
        return max(user_version, meta_version)
    return None


def create_pre_migration_backup(
    conn: sqlite3.Connection, db_path: Path, source_version: int
) -> Path:
    """Atomically retain the original SQLite database before a compatibility repair."""

    target = db_path.with_name(f"{db_path.name}.pre-migration-v{source_version}")
    if target.exists():
        return target
    temporary = target.with_name(f"{target.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    destination = sqlite3.connect(str(temporary))
    try:
        conn.backup(destination)
    finally:
        destination.close()
    temporary.replace(target)
    return target


def repair_additive_columns(conn: sqlite3.Connection) -> None:
    """Bring legacy tables forward before their version marker is recorded."""

    for issue in additive_schema_issues(conn):
        table, column = issue.split(".", 1)
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {_ADDITIVE_COLUMNS[table][column]}")


def additive_schema_issues(conn: sqlite3.Connection) -> list[str]:
    """Return additive columns missing from a partially migrated workspace."""

    issues: list[str] = []
    for table, columns in _ADDITIVE_COLUMNS.items():
        present = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        issues.extend(f"{table}.{name}" for name in columns if name not in present)
    return issues


def required_schema_issues(conn: sqlite3.Connection) -> list[str]:
    """Return structural columns that must exist before recording the schema version."""

    issues: list[str] = []
    for table, required in _REQUIRED_COLUMNS.items():
        present = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        issues.extend(f"{table}.{name}" for name in sorted(required - present))
    return issues


def verify_required_structure(conn: sqlite3.Connection) -> None:
    issues = required_schema_issues(conn)
    if issues:
        raise RuntimeError(f"Habitat schema verification failed: {issues}")
