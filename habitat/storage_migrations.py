"""Small, explicit compatibility repairs for Habitat SQLite workspaces."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType

from .sql_safety import quote_identifier


SCHEMA_VERSION = 23

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

_LEARNING_TABLE_DDL = MappingProxyType({
    "learning_policy_versions": """
        CREATE TABLE IF NOT EXISTS learning_policy_versions(
          version TEXT PRIMARY KEY,
          fingerprint TEXT NOT NULL UNIQUE,
          policy_json TEXT NOT NULL,
          parent_version TEXT REFERENCES learning_policy_versions(version),
          created_by TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
    """,
    "learning_candidates": """
        CREATE TABLE IF NOT EXISTS learning_candidates(
          candidate_id TEXT PRIMARY KEY,
          policy_version TEXT NOT NULL REFERENCES learning_policy_versions(version),
          policy_fingerprint TEXT NOT NULL,
          baseline_version TEXT NOT NULL REFERENCES learning_policy_versions(version),
          baseline_fingerprint TEXT NOT NULL,
          generator_id TEXT NOT NULL,
          state TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
    """,
    "learning_outcomes": """
        CREATE TABLE IF NOT EXISTS learning_outcomes(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          candidate_id TEXT NOT NULL REFERENCES learning_candidates(candidate_id),
          policy_version TEXT NOT NULL REFERENCES learning_policy_versions(version),
          task_fingerprint TEXT NOT NULL,
          benchmark_class TEXT NOT NULL,
          provider_fingerprints_json TEXT NOT NULL,
          context_refs_json TEXT NOT NULL,
          action_refs_json TEXT NOT NULL,
          verification_refs_json TEXT NOT NULL,
          independent_outcome_json TEXT NOT NULL,
          resource_metrics_json TEXT NOT NULL,
          errors_json TEXT NOT NULL,
          rollbacks_json TEXT NOT NULL,
          revision TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
    """,
    "learning_evaluations": """
        CREATE TABLE IF NOT EXISTS learning_evaluations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          candidate_id TEXT NOT NULL REFERENCES learning_candidates(candidate_id),
          policy_fingerprint TEXT NOT NULL,
          evaluator_id TEXT NOT NULL,
          heldout_suite_id TEXT NOT NULL,
          baseline_benchmark_fingerprint TEXT NOT NULL,
          candidate_benchmark_fingerprint TEXT NOT NULL,
          improved INTEGER NOT NULL,
          evidence_refs_json TEXT NOT NULL,
          reproduction_tolerance REAL,
          created_at TEXT NOT NULL
        )
    """,
    "learning_activations": """
        CREATE TABLE IF NOT EXISTS learning_activations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          candidate_id TEXT NOT NULL REFERENCES learning_candidates(candidate_id),
          action TEXT NOT NULL,
          previous_version TEXT,
          previous_fingerprint TEXT,
          active_version TEXT NOT NULL REFERENCES learning_policy_versions(version),
          active_fingerprint TEXT NOT NULL,
          evaluation_id INTEGER NOT NULL REFERENCES learning_evaluations(id),
          baseline_benchmark_fingerprint TEXT NOT NULL,
          candidate_benchmark_fingerprint TEXT NOT NULL,
          reproduction_benchmark_fingerprint TEXT,
          reproduction_tolerance REAL,
          created_at TEXT NOT NULL
        )
    """,
    "learning_state": """
        CREATE TABLE IF NOT EXISTS learning_state(
          key TEXT PRIMARY KEY,
          value TEXT,
          updated_at TEXT NOT NULL
        )
    """,
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
    "learning_policy_versions": frozenset({
        "version", "fingerprint", "policy_json", "parent_version", "created_by", "created_at",
    }),
    "learning_candidates": frozenset({
        "candidate_id", "policy_version", "policy_fingerprint", "baseline_version",
        "baseline_fingerprint", "generator_id", "state", "created_at", "updated_at",
    }),
    "learning_outcomes": frozenset({
        "id", "candidate_id", "policy_version", "task_fingerprint", "benchmark_class",
        "provider_fingerprints_json", "context_refs_json", "action_refs_json",
        "verification_refs_json", "independent_outcome_json", "resource_metrics_json",
        "errors_json", "rollbacks_json", "revision", "created_at",
    }),
    "learning_evaluations": frozenset({
        "id", "candidate_id", "policy_fingerprint", "evaluator_id", "heldout_suite_id",
        "baseline_benchmark_fingerprint", "candidate_benchmark_fingerprint", "improved",
        "evidence_refs_json", "reproduction_tolerance", "created_at",
    }),
    "learning_activations": frozenset({
        "id", "candidate_id", "action", "previous_version", "previous_fingerprint",
        "active_version", "active_fingerprint", "evaluation_id",
        "baseline_benchmark_fingerprint", "candidate_benchmark_fingerprint",
        "reproduction_benchmark_fingerprint", "reproduction_tolerance", "created_at",
    }),
    "learning_state": frozenset({"key", "value", "updated_at"}),
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

    for ddl in _LEARNING_TABLE_DDL.values():
        conn.execute(ddl)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_candidates_state "
        "ON learning_candidates(state,updated_at,candidate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_outcomes_candidate "
        "ON learning_outcomes(candidate_id,id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_evaluations_candidate "
        "ON learning_evaluations(candidate_id,id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_activations_candidate "
        "ON learning_activations(candidate_id,id)"
    )
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
