"""Small, explicit compatibility repairs for Habitat SQLite workspaces."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType

from .sql_safety import quote_identifier


SCHEMA_VERSION = 22

_ADDITIVE_COLUMNS = MappingProxyType({
    "files": MappingProxyType({
        "indexed_bytes": "INTEGER NOT NULL DEFAULT 0",
        "index_truncated": "INTEGER NOT NULL DEFAULT 0",
        "parse_complete": "INTEGER NOT NULL DEFAULT 1",
    }),
    "context_faults": MappingProxyType({
        "authority_bytes_read": "INTEGER NOT NULL DEFAULT 0",
    }),
})

_REQUIRED_COLUMNS = MappingProxyType({
    "files": frozenset({
        "id", "path", "language", "size", "digest", "mtime_ns",
        "indexed_bytes", "index_truncated", "parse_complete",
    }),
    "context_faults": frozenset({
        "seq", "handle", "page_id", "object_id", "path", "source_bytes",
        "authority_bytes_read", "revision", "episode_id", "fetched_at",
    }),
})

_ADDITIVE_TABLES = frozenset(_ADDITIVE_COLUMNS)
_REQUIRED_TABLES = frozenset(_REQUIRED_COLUMNS)


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

    base_target = db_path.with_name(f"{db_path.name}.pre-migration-v{source_version}")
    with NamedTemporaryFile(
        dir=db_path.parent,
        prefix=f".{base_target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        destination = sqlite3.connect(str(temporary))
        try:
            conn.backup(destination)
        finally:
            destination.close()
        digest = _file_sha256(temporary)
        target = base_target
        if target.exists():
            if _file_sha256(target) == digest:
                return target
            target = base_target.with_name(f"{base_target.name}.{digest}")
            if target.exists():
                if _file_sha256(target) == digest:
                    return target
                raise RuntimeError("pre-migration backup digest collision")
        try:
            os.link(temporary, target)
        except FileExistsError:
            if _file_sha256(target) != digest:
                raise RuntimeError("pre-migration backup target changed concurrently")
        return target
    finally:
        temporary.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repair_additive_columns(conn: sqlite3.Connection) -> None:
    """Bring legacy tables forward before their version marker is recorded."""

    for issue in additive_schema_issues(conn):
        table, column = issue.split(".", 1)
        table_name = quote_identifier(table, _ADDITIVE_TABLES)
        column_name = quote_identifier(column, frozenset(_ADDITIVE_COLUMNS[table]))
        definition = _ADDITIVE_COLUMNS[table][column]
        conn.execute("ALTER TABLE " + table_name + " ADD COLUMN " + column_name + " " + definition)


def additive_schema_issues(conn: sqlite3.Connection) -> list[str]:
    """Return additive columns missing from a partially migrated workspace."""

    issues: list[str] = []
    for table, columns in _ADDITIVE_COLUMNS.items():
        table_name = quote_identifier(table, _ADDITIVE_TABLES)
        present = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(" + table_name + ")").fetchall()
        }
        issues.extend(f"{table}.{name}" for name in columns if name not in present)
    return issues


def required_schema_issues(conn: sqlite3.Connection) -> list[str]:
    """Return structural columns that must exist before recording the schema version."""

    issues: list[str] = []
    for table, required in _REQUIRED_COLUMNS.items():
        table_name = quote_identifier(table, _REQUIRED_TABLES)
        present = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(" + table_name + ")").fetchall()
        }
        issues.extend(f"{table}.{name}" for name in sorted(required - present))
    return issues


def verify_required_structure(conn: sqlite3.Connection) -> None:
    issues = required_schema_issues(conn)
    if issues:
        raise RuntimeError(f"Habitat schema verification failed: {issues}")
