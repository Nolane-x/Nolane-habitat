# Nolane Habitat Comprehensive Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Habitat's persisted world model transactionally truthful, safely upgradeable, continuously verified, and easier to evolve without changing its public protocol surface.

**Architecture:** Stabilize SQLite first with structural migrations and explicit transaction ownership, then extract high-risk refresh, protocol, and Observatory responsibilities behind compatibility façades. Add fault-injection, cross-platform, static-analysis, MCP lifecycle, and release-admission gates around the preserved public contracts.

**Tech Stack:** Python 3.10+, SQLite/WAL, `unittest`, MCP Python SDK, vanilla JavaScript Observatory, Semgrep, CodeQL, GitHub Actions, setuptools.

**Spec:** `docs/superpowers/specs/2026-08-23-habitat-hardening-audit.md`

**Production-grade companion design:** `docs/superpowers/specs/2026-08-23-habitat-production-grade-evolution-design.md`

## Global Constraints

- Preserve the `habitat.agent.v1alpha2` wire envelope, existing MCP tool names, JSON schemas, CLI entry points, and Observatory read-only policy.
- Use red-green-refactor for every defect. A reproduced failure must exist before its implementation change.
- Run migration and fault-injection tests only against temporary copies or fixtures. Never experiment on a user's only Habitat database.
- Make exactly one layer own each commit or rollback. Low-level storage helpers must not commit implicitly.
- Treat `meta.schema_version` as untrusted until the database passes structural verification.
- Keep public README claims positive and verified. Put technical boundaries in versioned engineering documents instead of implying unsupported capability.
- Do not combine architectural extraction with behavior changes. First lock public behavior with characterization tests, then move code, then simplify.
- Keep each task independently revertible and commit it after its focused verification passes.
- A skipped optional-provider test is acceptable only when the report records the missing capability and the required release tier does not mandate it.

---

## Delivery sequence

| Phase | Tasks | Release rule |
|---|---|---|
| A — Truth integrity | 1–3 | DB-001 and TX-001 must be closed before any new feature work or release candidate. |
| B — Reliable verification | 4–5 | Matrix, version, and documentation gates must produce deterministic artifacts. |
| C — Regression surface reduction | 6–9 | Public behavior remains byte/schema compatible while complexity and silent failures are reduced. |
| D — Continuous admission | 10–12 | Cross-platform CI, stress tests, MCP lifecycle, and release evidence become mandatory. |

## Program portfolio and dependency gates

This plan is the Truth Core and Architecture Hardening branch of a larger production-grade program. It intentionally does not mix semantic-policy experiments, privacy controls, Observatory UX work, or supply-chain promotion into the same review units.

| Branch | Plan | May begin | Blocks |
|---|---|---|---|
| Truth Core and architecture | this plan | immediately | every state-mutating branch until Tasks 1–3 pass |
| Intelligence and agent evolution | `docs/superpowers/plans/2026-08-23-habitat-intelligence-and-agent-evolution.md` | read-only fixture construction may start immediately; state integration begins after Tasks 1–3 | beta readiness and skill/policy promotion |
| Security, scale, and operations | `docs/superpowers/plans/2026-08-23-habitat-security-scale-and-operations.md` | threat model and CI scaffolding may start immediately; state integration begins after Tasks 1–3 | production candidate promotion |

### Non-negotiable program gates

- No new public feature work while DB-001 or TX-001 is open.
- No beta-readiness claim without sealed semantic/context holdouts, provenance, memory invalidation, and cross-agent isolation.
- No production-candidate claim without fault/SLO evidence, privacy verification, scale profiles, SBOM, reproducible artifacts, and rollback evidence.
- No skill or ranking-policy promotion without frozen Teacher, isolated Student, independent Judge, paired trials, ablations, and zero protected-dimension regression.
- No calendar or marketing milestone overrides a failed evidence gate.

### Program scorecard

| Dimension | Required result |
|---|---:|
| Revision coherence after injected failures | 100% |
| Supported legacy migration fixtures | 100% |
| Parsed symbol precision / recall | at least 97% / 95% |
| Static relation precision / recall | at least 95% / 90% |
| Stale-fact invalidation and context budget compliance | 100% |
| Cross-agent private-state isolation | 100% |
| Repeated MCP lifecycle | at least 100/100 |
| Protected regressions admitted during evolution | 0 |
| Distributed artifacts covered by hashes/SBOM/provenance | 100% |

### Safe execution waves

| Wave | Required work | Exit gate |
|---|---|---|
| 0 | Comprehensive Tasks 1–3 | migrations, transactions, doctor, and recovery tests green |
| 1 | Comprehensive Tasks 4–9; Intelligence Tasks 1–6; Security/Operations Tasks 1–4 | deterministic verification, provenance/memory/coordination, boundaries/privacy/faults green |
| 2 | Comprehensive Tasks 10–12; Intelligence Task 7; Security/Operations Tasks 5–6 | CI/release-check foundation, Codex bootstrap, Observatory, and scale profiles green |
| 3 | Intelligence Task 8; Security/Operations Tasks 7–8 | independent evolution admission, reproducible artifacts, canary and rollback evidence green |

Within a wave, parallel work is allowed only when files do not overlap. Changes to `habitat/storage.py`, `habitat/workspace.py`, `tools/release_check.py`, or plugin skills are serialized and reviewed against all previously landed contracts.

## Task 1: Introduce structural SQLite migrations

**Files:**

- Create: `habitat/storage_migrations.py`
- Modify: `habitat/storage.py`
- Create: `tests/test_storage_migrations.py`
- Modify: `tests/test_storage.py`

**Acceptance:** Opening every supported legacy fixture either migrates it to a structurally valid version 22 database or fails before changing its version marker. Opening a database already mislabeled as 22 repairs supported drift or emits an explicit incompatibility error. A second open is idempotent.

- [ ] Add the exact DB-001 reproducer as a failing test.

```python
import sqlite3
import tempfile
import unittest
from pathlib import Path

from habitat.model import FileRecord
from habitat.storage import Store


class StorageMigrationTests(unittest.TestCase):
    def test_old_files_table_is_migrated_before_version_is_advanced(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "legacy.sqlite3"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '1');
                CREATE TABLE files(
                  id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL,
                  language TEXT NOT NULL, size INTEGER NOT NULL,
                  digest TEXT NOT NULL, mtime_ns INTEGER NOT NULL
                );
                """
            )
            conn.commit()
            conn.close()

            store = Store(db)
            try:
                columns = {
                    row["name"]
                    for row in store.conn.execute("PRAGMA table_info(files)")
                }
                self.assertTrue(
                    {"indexed_bytes", "index_truncated", "parse_complete"} <= columns
                )
                store.upsert_file(
                    FileRecord("f1", "a.py", "python", 1, "d", 1)
                )
                version = store.conn.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0]
                self.assertEqual("22", version)
            finally:
                store.close()
```

- [ ] Run `python -m unittest -v tests.test_storage_migrations.StorageMigrationTests.test_old_files_table_is_migrated_before_version_is_advanced` and confirm it fails with the missing `indexed_bytes` column on the unmodified implementation.
- [ ] Define a canonical structural manifest and ordered migration registry in `habitat/storage_migrations.py`.

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable


TARGET_SCHEMA_VERSION = 22


@dataclass(frozen=True)
class Migration:
    from_version: int
    to_version: int
    apply: Callable[[sqlite3.Connection], None]


REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "files": frozenset({
        "id", "path", "language", "size", "digest", "mtime_ns",
        "indexed_bytes", "index_truncated", "parse_complete",
    }),
    "context_faults": frozenset({
        "seq", "handle", "page_id", "object_id", "path", "source_bytes",
        "authority_bytes_read", "revision", "episode_id", "fetched_at",
    }),
}


def table_columns(conn: sqlite3.Connection, table: str) -> frozenset[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return frozenset(str(row[1]) for row in rows)


def verify_required_structure(conn: sqlite3.Connection) -> None:
    missing = {
        table: sorted(columns - table_columns(conn, table))
        for table, columns in REQUIRED_COLUMNS.items()
        if columns - table_columns(conn, table)
    }
    if missing:
        raise RuntimeError(f"Habitat schema verification failed: {missing}")
```

- [ ] Move `SCHEMA_VERSION` to the migration module and re-export it from `storage.py` for compatibility.
- [ ] Encode every structural change represented by supported shipped schema versions. Use idempotent column/table/index checks before each SQLite DDL statement.
- [ ] Run all migrations inside one `BEGIN IMMEDIATE` transaction. Set both `PRAGMA user_version` and `meta.schema_version` only after `verify_required_structure`, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check` pass.
- [ ] Add tests for a correctly labeled current database, a falsely labeled version 22 database, a future version 23 rejection, interrupted migration rollback, and double-open idempotence.
- [ ] Run `python -m unittest -v tests.test_storage_migrations tests.test_storage` and confirm all tests pass.
- [ ] Run `python -m unittest discover -s tests -p "test_*.py"` and confirm the full suite passes.
- [ ] Commit with `fix(storage): add verified structural migrations`.

## Task 2: Make refresh and storage transactions atomic

**Files:**

- Modify: `habitat/storage.py`
- Modify: `habitat/workspace.py`
- Modify: `habitat/mutation.py`
- Create: `tests/test_refresh_atomicity.py`
- Create: `tests/test_mutation_atomicity.py`

**Acceptance:** Any exception during deep refresh, targeted refresh, mutation apply, mutation rollback, or JSON persistence rolls back all database changes owned by that operation. No later operation can commit abandoned writes, and the revision always describes the visible file/index state.

- [ ] Add a failing test that persists one changed file, injects an exception, calls `save_json`, reopens the database, and proves that the changed digest did not leak.

```python
def test_failed_refresh_cannot_be_committed_by_later_json_save(self) -> None:
    ws, source, habitat = self.make_workspace({
        "a.py": "VALUE = 1\n",
        "b.py": "VALUE = 1\n",
    })
    self.addCleanup(ws.close)
    old_revision = ws.revision
    old_digest = ws.store.file_by_path("a.py")["digest"]
    (source / "a.py").write_text("VALUE = 2\n", encoding="utf-8")

    original = ws._persist_compiled
    def fail_after_write(compiled):
        original(compiled)
        raise RuntimeError("injected refresh failure")
    ws._persist_compiled = fail_after_write

    with self.assertRaisesRegex(RuntimeError, "injected refresh failure"):
        ws.refresh("fault-injection")

    ws.store.save_json("sessions", "probe", {"ok": True})
    ws.close()
    ws = HabitatWorkspace(habitat)
    self.assertEqual(old_revision, ws.revision)
    self.assertEqual(old_digest, ws.store.file_by_path("a.py")["digest"])
```

- [ ] Run the single test and confirm the old implementation leaks the new digest while retaining the old revision.
- [ ] Add nested transaction ownership to `Store` with outer `BEGIN IMMEDIATE` and inner savepoints.

```python
from contextlib import contextmanager
from collections.abc import Iterator


@contextmanager
def transaction(self, name: str = "store") -> Iterator[None]:
    depth = self._transaction_depth
    savepoint = f"habitat_{depth}"
    self._transaction_depth += 1
    try:
        if depth == 0:
            self.conn.execute("BEGIN IMMEDIATE")
        else:
            self.conn.execute(f"SAVEPOINT {savepoint}")
        yield
        if depth == 0:
            self.conn.commit()
        else:
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except BaseException:
        if depth == 0:
            self.conn.rollback()
        else:
            self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    finally:
        self._transaction_depth -= 1
```

- [ ] Initialize `_transaction_depth = 0` in `Store.__init__` and reject concurrent use of one `Store` object from multiple threads rather than sharing transaction depth unsafely.
- [ ] Remove unconditional commits from `save_json` and every low-level write helper. Preserve `Store.commit()` only as a compatibility boundary with an explicit deprecation path.
- [ ] Wrap `refresh`, `refresh_paths`, top-level mutation apply, rollback, and recovery workflows in `with self.store.transaction("operation-name"):`.
- [ ] Add fault injection after file upsert, symbol replacement, relation sync, revision insertion, event append, and source-fingerprint update. Assert both same-connection and reopened-database state match the pre-operation snapshot.
- [ ] Add a nested-savepoint test proving an inner rollback does not discard an outer caller's independent valid write.
- [ ] Run `python -m unittest -v tests.test_refresh_atomicity tests.test_mutation_atomicity` and confirm all tests pass.
- [ ] Run the full test suite and `python -m compileall -q habitat tests tools`.
- [ ] Commit with `fix(storage): enforce atomic workspace operations`.

## Task 3: Add database recovery, contention, and health checks

**Files:**

- Modify: `habitat/storage.py`
- Create: `habitat/database_health.py`
- Create: `tests/test_database_health.py`
- Modify: `habitat/cli.py`
- Modify: `docs/CODEX-INTEGRATION.md`

**Acceptance:** Habitat can inspect a workspace database without mutating it, reports schema/integrity/foreign-key/WAL status, creates a safe pre-migration backup, and handles bounded writer contention with a clear error instead of a partial state.

- [ ] Add failing tests for a foreign-key violation, malformed schema metadata, a locked writer, and a backup/restore cycle.
- [ ] Implement a read-only health report with stable keys.

```python
from dataclasses import dataclass, asdict
import sqlite3


@dataclass(frozen=True)
class DatabaseHealth:
    integrity: str
    foreign_key_violations: int
    journal_mode: str
    user_version: int
    meta_version: int | None
    structure_valid: bool

    def as_dict(self) -> dict:
        return asdict(self)


def inspect_database(conn: sqlite3.Connection) -> DatabaseHealth:
    integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    row = conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()
    meta_version = int(row[0]) if row is not None else None
    return DatabaseHealth(
        integrity=integrity,
        foreign_key_violations=violations,
        journal_mode=journal_mode,
        user_version=user_version,
        meta_version=meta_version,
        structure_valid=integrity == "ok" and violations == 0,
    )
```

- [ ] Configure `PRAGMA busy_timeout=5000`, `PRAGMA foreign_keys=ON`, and the documented WAL/synchronous policy on every connection.
- [ ] Before a migration, use SQLite's online backup API to create `habitat.sqlite3.pre-migration-v<source>` in the workspace state directory. Write through a temporary backup path and atomically replace the final backup.
- [ ] Add `habitat doctor <workspace>` with `--json` and `--repair-schema`. The default path is read-only; `--repair-schema` requires an explicit flag and reports the backup path.
- [ ] Add contention tests with two independent connections: one writer holds `BEGIN IMMEDIATE`, the other times out cleanly, and neither leaves a partial revision.
- [ ] Run `python -m unittest -v tests.test_database_health tests.test_storage_migrations tests.test_refresh_atomicity`.
- [ ] Run `python -m habitat.cli doctor <temporary-workspace> --json` in a test and validate the JSON schema.
- [ ] Commit with `feat(storage): add database health and recovery checks`.

## Task 4: Make the test matrix deterministic on Windows and Linux

**Files:**

- Modify: `tools/run_test_matrix.py`
- Create: `tests/test_test_matrix.py`
- Modify: `pyproject.toml`

**Acceptance:** Every invocation writes its JSON report even when a shard times out, a worker raises, a descendant retains a log handle, or artifact cleanup fails. The exit code is nonzero for test or infrastructure failure and zero only when every required shard passes.

- [ ] Add a Windows regression test that keeps a shard log open past worker return and proves the runner emits an `infra-error` row instead of raising from `TemporaryDirectory.__exit__`.
- [ ] Add a cross-platform test where a shard spawns a long-lived child and verify the runner terminates the owned process tree.
- [ ] Move logs to a durable per-run artifact directory supplied by `--artifact-dir`; default to a unique directory under the output report's parent.

```python
@dataclass(frozen=True)
class ShardResult:
    group: str
    status: str
    returncode: int | None
    tests: int | None
    wall_ms: float
    stdout_path: str
    stderr_path: str
    error: str | None = None
```

- [ ] Introduce platform-specific process-tree ownership: POSIX process groups and a Windows Job Object configured with kill-on-close. Keep the implementation in `tools/run_test_matrix.py` so the product has no new runtime dependency.
- [ ] Catch exceptions at both the worker boundary and the `Future.result()` boundary. Convert each exception into one complete `ShardResult`.
- [ ] Write the final JSON to a temporary sibling and atomically replace `--out`, even when results include failures.
- [ ] Add a deterministic cleanup phase with bounded retry. A cleanup failure is recorded in `cleanup_errors` and never destroys the primary report.
- [ ] Run `python -m unittest -v tests.test_test_matrix` on Windows.
- [ ] Run `python tools/run_test_matrix.py --mode shard --workers 2 --timeout 180 --out .test-artifacts/matrix.json` and require a complete report.
- [ ] Run the same command on Ubuntu CI before closing this task.
- [ ] Commit with `fix(testing): make shard matrix process-safe`.

## Task 5: Enforce release identity and documentation truth

**Files:**

- Create: `tools/check_release_identity.py`
- Create: `tests/test_release_identity.py`
- Modify: `docs/AGENT-PROTOCOL.md`
- Modify: `docs/IMPLEMENTATION-STATUS.md`
- Modify: `docs/LIMITATIONS.md`
- Modify: `docs/control/CAPABILITY-DIAGNOSIS.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Acceptance:** One machine-readable release identity drives current documentation checks. Historical documents may mention older versions; current-surface documents cannot. README claims are backed by executable checks or clearly scoped descriptions.

- [ ] Add a failing test proving the current-surface documents reject `0.1.0-alpha.17` when `VERSION` is alpha.18.
- [ ] Implement a checker with an explicit current-document allowlist and historical-document exclusions.

```python
CURRENT_DOCUMENTS = (
    "README.md",
    "docs/AGENT-PROTOCOL.md",
    "docs/IMPLEMENTATION-STATUS.md",
    "docs/LIMITATIONS.md",
    "docs/control/CAPABILITY-DIAGNOSIS.md",
)


def release_identities(version: str) -> tuple[str, str]:
    tag = version.strip()
    package = tag.removeprefix("v").replace("-alpha.", "a")
    return tag, package
```

- [ ] Verify `VERSION`, `pyproject.toml`, `habitat.__version__`, plugin manifest version, changelog heading, and current-document headings in one command.
- [ ] Update current documents to alpha.18 while leaving alpha.17 research notes and the alpha.18 release plan historically intact.
- [ ] Keep README focused on verified benefits, quick setup, MCP/Codex connection, and observable outcomes. Link technical claim boundaries instead of listing speculative capabilities.
- [ ] Run `python tools/check_release_identity.py` and `python -m unittest -v tests.test_release_identity`.
- [ ] Commit with `docs: synchronize alpha18 product truth`.

## Task 6: Replace monolithic protocol dispatch with typed handler registries

**Files:**

- Create: `habitat/protocol_handlers/__init__.py`
- Create: `habitat/protocol_handlers/workspace.py`
- Create: `habitat/protocol_handlers/context.py`
- Create: `habitat/protocol_handlers/mutation.py`
- Create: `habitat/protocol_handlers/runtime.py`
- Create: `habitat/protocol_handlers/cognition.py`
- Modify: `habitat/protocol.py`
- Create: `tests/test_protocol_characterization.py`
- Modify: `tests/test_protocol.py`

**Acceptance:** Every existing method returns the same success/error envelope and schema-visible fields. Unknown-method and invalid-parameter behavior remains unchanged. No handler contains unrelated method families, and `_dispatch` becomes a registry lookup plus the existing shared envelope logic.

- [ ] Generate characterization cases from the current protocol schema: one valid request and one invalid request for every public method.
- [ ] Snapshot normalized envelopes with volatile revision/time/ID fields removed by the test normalizer; do not snapshot raw unstable values.
- [ ] Define the handler interface and registry.

```python
from collections.abc import Callable, Mapping
from typing import Any

Handler = Callable[[Mapping[str, Any]], dict[str, Any]]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def add(self, method: str, handler: Handler) -> None:
        if method in self._handlers:
            raise ValueError(f"duplicate protocol method: {method}")
        self._handlers[method] = handler

    def resolve(self, method: str) -> Handler | None:
        return self._handlers.get(method)
```

- [ ] Move one method family at a time. Preserve each existing branch body before simplifying any code.
- [ ] Keep authorization, revision checks, tracing, response-size accounting, and error translation in the protocol façade where they apply to all handlers.
- [ ] Run `python -m unittest -v tests.test_protocol_characterization tests.test_protocol` after each family move.
- [ ] Add a test that registry keys exactly equal the method names exposed by the protocol schema.
- [ ] Run the full suite and compare MCP `tools/list` output before and after the refactor.
- [ ] Commit with `refactor(protocol): split dispatch into method families`.

## Task 7: Decompose Observatory snapshots without weakening consistency

**Files:**

- Create: `habitat/observatory_read_model.py`
- Modify: `habitat/observatory.py`
- Modify: `habitat/observatory_assets/app.js`
- Create: `tests/test_observatory_snapshot_consistency.py`
- Create: `tests/test_observatory.py`

**Acceptance:** A snapshot is built from one SQLite read transaction, preserves the current JSON schema and SSE resume behavior, and remains valid while a writer commits concurrently. The HTTP layer performs routing/serialization only.

- [ ] Add golden schema tests for empty, active, degraded-provider, and concurrent-write snapshots.
- [ ] Add a concurrency test that pauses snapshot projection after reading the head revision, commits a writer transaction, resumes projection, and proves every projected object still belongs to the captured revision.
- [ ] Extract immutable projection context and focused builders.

```python
from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class SnapshotContext:
    revision: str
    generated_at: str
    sequence: int


class ObservatoryReadModel:
    def snapshot(self) -> dict:
        with self._read_transaction() as conn:
            context = self._context(conn)
            return {
                "schema": "habitat.observatory.snapshot.v2",
                "context": context.__dict__,
                "workspace": self._workspace(conn, context),
                "agents": self._agents(conn, context),
                "activity": self._activity(conn, context),
                "world": self._world(conn, context),
            }
```

- [ ] Split workspace, agent, activity, world, runtime, and UI projections into private methods with no HTTP dependencies.
- [ ] Keep `Observatory._Handler.do_GET` limited to route validation, ETag/SSE headers, serialization, and bounded error responses.
- [ ] Add JavaScript fixture tests for snapshot compatibility, reconnect sequence handling, and missing optional sections.
- [ ] Run `python -m unittest -v tests.test_observatory_snapshot_consistency tests.test_observatory` and `node --check habitat/observatory_assets/app.js`.
- [ ] Commit with `refactor(observatory): isolate consistent read projections`.

## Task 8: Extract refresh coordination from the workspace façade

**Files:**

- Create: `habitat/refresh.py`
- Modify: `habitat/workspace.py`
- Create: `tests/test_refresh_service.py`
- Modify: `tests/test_workspace.py`
- Modify: `tests/test_alpha3_live_workspace.py`

**Acceptance:** `HabitatWorkspace.refresh` and `refresh_paths` retain signatures and response shapes but delegate scanning, cache decisions, persistence, semantic finalization, and I/O accounting to a focused coordinator. Transaction ownership from Task 2 remains at the operation boundary.

- [ ] Lock deep and targeted refresh behavior with characterization tests for create, modify, delete, metadata-preserving modification, ignored files, backend reconcile, cache hit, and provider failure.
- [ ] Define an immutable request/result boundary.

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RefreshRequest:
    reason: str
    mode: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshMetrics:
    hashed_files: int = 0
    hash_bytes_read: int = 0
    compiler_input_bytes_minimum: int = 0
    index_bytes_written: int = 0


@dataclass(frozen=True)
class RefreshResult:
    payload: dict
    metrics: RefreshMetrics = field(default_factory=RefreshMetrics)
```

- [ ] Move only refresh-related private methods into `RefreshCoordinator`. Inject the store, backend, compiler functions, effect/dataflow compilers, and clock as constructor dependencies.
- [ ] Leave compatibility wrappers on `HabitatWorkspace`; callers and protocol handlers must not import the coordinator directly.
- [ ] Make the coordinator return data and let the workspace façade emit cross-cutting activity/tracing only once.
- [ ] Run refresh tests plus the Task 2 fault-injection suite after every extraction step.
- [ ] Require `workspace.py` to fall below 2,500 lines in this task without moving unrelated code or changing public behavior.
- [ ] Commit with `refactor(workspace): extract refresh coordinator`.

## Task 9: Replace silent failures with an explicit exception policy

**Files:**

- Create: `habitat/error_policy.py`
- Modify: `habitat/source_bridge.py`
- Modify: `habitat/mutation.py`
- Modify: `habitat/execution.py`
- Modify: `habitat/observatory.py`
- Modify: `habitat/protocol.py`
- Modify: `habitat/workspace.py`
- Create: `tests/test_error_policy.py`

**Acceptance:** Every suppressed exception is narrow, documented by category, and observable through debug logging or structured activity evidence. State-integrity failures are never suppressed. Cleanup remains best effort without masking the primary exception.

- [ ] Classify each of the 38 CodeQL empty-except results as benign absence, best-effort cleanup, optional-provider degradation, or integrity-critical failure.
- [ ] Add a small helper that preserves the primary exception while recording cleanup failure.

```python
from collections.abc import Callable
import logging


def best_effort_cleanup(
    action: Callable[[], None],
    *,
    operation: str,
    logger: logging.Logger,
) -> str | None:
    try:
        action()
        return None
    except (FileNotFoundError, ProcessLookupError) as exc:
        logger.debug("cleanup already complete: %s", operation, exc_info=exc)
        return None
    except OSError as exc:
        logger.warning("cleanup failed: %s: %s", operation, exc)
        return f"{type(exc).__name__}: {exc}"
```

- [ ] Replace broad `except Exception: pass` only where the classified contract permits suppression. Re-raise integrity, authorization, persistence, and revision errors.
- [ ] Add fault-injection tests for atomic file replacement, mutation rollback, provider shutdown, Observatory disconnect, and protocol trace cleanup. Assert the primary exception is unchanged and cleanup evidence is retained.
- [ ] Re-run CodeQL. Require zero `py/empty-except` findings in `habitat/` and document any narrowly justified suppression rule in `.github/codeql/`.
- [ ] Run the full test suite.
- [ ] Commit with `refactor(errors): make degraded cleanup observable`.

## Task 10: Add repository-owned continuous quality gates

**Files:**

- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/codeql.yml`
- Create: `.semgrep.yml`
- Modify: `pyproject.toml`
- Create: `tools/quality_gate.py`
- Create: `tests/test_quality_gate.py`

**Acceptance:** Pull requests run deterministic Windows and Ubuntu checks, a Python version matrix, package smoke installation, JavaScript syntax, tests, coverage, Semgrep, and CodeQL. Generated reports are uploaded even on failure.

- [ ] Add `coverage[toml]`, `ruff`, and `semgrep` to the development extra with bounded compatible versions. Configure Ruff for syntax, imports, and high-confidence correctness rules before enabling style rules.
- [ ] Add coverage configuration for branch coverage over `habitat/`, excluding benchmark and generated asset fixtures. Start with a measured baseline gate and ratchet it upward; the gate may never be reduced in the same change that loses coverage.
- [ ] Create a CI matrix with `windows-latest` and `ubuntu-latest`, Python 3.10 and 3.14, plus one full optional-provider job.

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ['3.10', '3.14']
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install -U pip
      - run: python -m pip install -e ".[dev,mcp,python-semantic]"
      - run: python -m compileall -q habitat tests tools
      - run: python tools/check_release_identity.py
      - run: python tools/run_test_matrix.py --mode shard --workers 2 --timeout 240 --out .test-artifacts/matrix.json
```

- [ ] Configure Semgrep to exclude `.venv`, worktrees, generated artifacts, benchmark security examples, and packaged copies. Add repository rules for dynamic SQLite identifiers, missing transaction wrappers, and broad silent exceptions.
- [ ] Configure CodeQL for Python and JavaScript with separate invocations and explicit benchmark exclusions so example vulnerabilities do not dilute product findings.
- [ ] Implement `tools/quality_gate.py` to merge test, coverage, Semgrep, CodeQL, identity, and package-smoke summaries into `.test-artifacts/quality-gate.json`.
- [ ] Add `workflow_dispatch` and artifact upload with `if: always()` for every report.
- [ ] Run the workflow locally where possible and validate both GitHub workflow files with a YAML parser test.
- [ ] Commit with `ci: add cross-platform quality admission`.

## Task 11: Add state-machine, concurrency, and performance regression tests

**Files:**

- Create: `tests/test_workspace_state_machine.py`
- Create: `tests/test_sqlite_concurrency.py`
- Create: `tests/test_long_lived_resources.py`
- Create: `benchmarks/hardening_baseline.py`
- Create: `tools/check_performance_budget.py`

**Acceptance:** Deterministic generated traces cover workspace lifecycle transitions, concurrent readers/writers, crash recovery, and repeated open/close behavior. Performance gates use relative work/latency budgets and detect large regressions without depending on one machine's absolute speed.

- [ ] Build a deterministic lifecycle model with states `absent`, `ready`, `refreshing`, `staged`, `committed`, `rolled_back`, and `closed`. Generate seeded action sequences and compare filesystem bytes, database head, and visible file digests after every action.
- [ ] Add transition invariants.

```python
def assert_revision_coherent(testcase, ws) -> None:
    rows = ws.store.all_files()
    digest = root_digest((row["path"], row["digest"]) for row in rows)
    head = ws.store.revision(ws.revision)
    testcase.assertEqual(head["root_digest"], digest)
    testcase.assertFalse(ws.store.conn.in_transaction)
```

- [ ] Exercise two readers during one writer transaction and two competing writers with bounded timeouts. Assert readers see complete old or complete new snapshots, never a mixture.
- [ ] Inject process termination after migration backup, after DDL, after file indexing, and before revision commit using subprocess fixtures. Reopen and require either complete rollback or successful recovery.
- [ ] Run 100 create/open/refresh/close cycles and record process handles, child processes, temporary directories, and SQLite connections. Require no monotonically growing resource count and no locked workspace deletion after close.
- [ ] Benchmark cold ingest, unchanged deep refresh, one-file targeted refresh, context compile, and Observatory snapshot over a generated 1,000-file project.
- [ ] Gate relative invariants: unchanged refresh compiles zero files; targeted refresh considers no more than the requested paths plus declared semantic dependents; a new change may not regress median latency or peak memory by more than 20% against the committed platform baseline without an approved benchmark note.
- [ ] Store benchmark inputs and summary JSON, not generated source trees or databases.
- [ ] Commit with `test: add lifecycle and durability stress coverage`.

## Task 12: Prove Codex/MCP lifecycle and automate release admission

**Files:**

- Create: `tests/test_mcp_stdio_e2e.py`
- Create: `tests/test_codex_plugin_contract.py`
- Create: `tools/release_check.py`
- Modify: `plugins/nolane-habitat/.codex-plugin/plugin.json`
- Modify: `plugins/nolane-habitat/skills/nolane-habitat/SKILL.md`
- Modify: `plugins/nolane-habitat/skills/nolane-habitat-maintainer/SKILL.md`
- Modify: `docs/CODEX-INTEGRATION.md`
- Modify: `CHANGELOG.md`

**Acceptance:** A fresh subprocess can initialize the MCP server, list the expected compact tool surface, open a temporary Habitat workspace, orient, inspect context, execute a governed read-only flow, close cleanly, and reconnect without orphaned processes or locked SQLite files. One release command produces a signed-off admission report and artifact hashes.

- [ ] Use Context7 to verify the installed MCP SDK's current stdio client API before implementing the test.
- [ ] Add an end-to-end lifecycle test using the SDK client.

```python
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpStdioEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_list_orient_and_close(self) -> None:
        params = StdioServerParameters(
            command="python",
            args=["-m", "habitat.mcp_adapter", "--workspace", self.workspace],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                self.assertEqual(12, len(tools.tools))
                result = await session.call_tool(
                    "habitat_orient",
                    {"task": "inspect workspace integrity", "budget": 8},
                )
                self.assertFalse(result.isError)
```

- [ ] Assert a second connection reuses the workspace safely, the Observatory auto-start policy remains bounded to loopback, and server close releases database and browser/provider handles.
- [ ] Validate plugin manifest paths, version, MCP command, both skill frontmatters, and skill references against files in the packaged plugin.
- [ ] Implement `tools/release_check.py` to run identity, migration fixtures, transaction fault injection, test matrix, package build/install smoke, plugin validation, MCP E2E, JavaScript syntax, Semgrep, and CodeQL summary ingestion.
- [ ] Emit `dist/release-admission.json` containing commit, version, platform, test counts, skips, scanner coverage/errors, database migration fixtures, artifact SHA-256 hashes, and unresolved bounded risks.
- [ ] Make release creation fail when DB-001/TX-001 regressions, required platform jobs, artifact hashes, current-document identity, or MCP lifecycle checks are missing.
- [ ] Update maintainer skills so future Codex agents run `habitat doctor`, transaction fault tests, and `tools/release_check.py` before proposing a release.
- [ ] Run `python tools/release_check.py --candidate` twice from clean checkouts and compare deterministic fields.
- [ ] Commit with `release: require Habitat admission evidence`.

---

## Final verification checklist

- [ ] `python -m compileall -q habitat tests tools`
- [ ] `python -m unittest discover -s tests -p "test_*.py"`
- [ ] `python tools/run_test_matrix.py --mode shard --workers 2 --timeout 240 --out .test-artifacts/matrix.json`
- [ ] `python tools/check_release_identity.py`
- [ ] `python tools/quality_gate.py --out .test-artifacts/quality-gate.json`
- [ ] `python tools/release_check.py --candidate`
- [ ] `node --check habitat/observatory_assets/app.js`
- [ ] `python -m habitat.mcp_adapter --help`
- [ ] `python -m pip check`
- [ ] `git diff --check`
- [ ] Confirm Windows and Ubuntu required CI jobs are green.
- [ ] Confirm migration backups restore and all supported legacy fixtures reopen.
- [ ] Confirm no failed operation leaves `conn.in_transaction` true.
- [ ] Confirm current docs show alpha.18 and historical alpha.17 documents are labeled historical.
- [ ] Confirm release-admission JSON records all skips, scanner errors, and bounded unknowns.

## Completion definition

This hardening branch is complete when Tasks 1–12 are committed in order, all final checks pass from a clean checkout, the release-admission artifact is reproducible, and no P0/P1 finding in the audit remains open without an explicit rejected-evidence record.

The production-grade Habitat program is complete only when this branch and both companion plans pass their own completion definitions, the program scorecard is green, all promotion evidence is hash-bound to the same source commit, and residual risks remain visible in the promotion verdict.
