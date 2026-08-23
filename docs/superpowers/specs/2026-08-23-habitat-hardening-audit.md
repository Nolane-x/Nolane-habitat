# Nolane Habitat Comprehensive Hardening Audit

- **Audit date:** 2026-08-23
- **Audited commit:** `7c74cfeb0869528fee9f61038e70fe1d13609dfe`
- **Release identity:** `0.1.0-alpha.18` / Python package `0.1.0a18`
- **Primary environment:** Windows, Python 3.14, Node syntax checker, SQLite WAL
**Change boundary:** diagnostic probes used temporary workspaces and databases. No product source was changed during the audit.

## Executive conclusion

Habitat's current workspace is structurally healthy and the direct test suite passes, but the persistence layer has two release-blocking truth-integrity defects:

1. a structurally old SQLite database can be labeled schema version 22 without being migrated; and
2. a failed refresh can leave partial index changes in an open transaction that an unrelated JSON save later commits without advancing the workspace revision.

The Windows test-matrix runner also has a reproducible infrastructure failure when a descendant process retains a shard log handle. The remaining findings are documentation drift, concentrated complexity, silent exception handling, and missing continuous quality gates. Static-analysis SQL and chmod alerts were manually rejected as false positives; no verified SQL injection was found.

## Product truths under test

The audit treated these as Habitat's critical obligations:

- The authoritative source tree and its derived semantic state must never disagree silently.
- A revision identifier must bind one coherent database state, not a partial refresh.
- A reported schema version must describe the database structure that is actually present.
- Failed mutations, refreshes, migrations, and test shards must end in an explicit, diagnosable state.
- MCP, protocol, Observatory, and release documentation must describe the shipped surface accurately.
- Quality gates must distinguish a product failure from a scanner false positive or test-infrastructure failure.

## Evidence classes

- **Verified defect:** reproduced on the audited commit with an observed outcome that contradicts a product obligation.
- **Candidate risk:** supported by static or structural evidence, but not yet reproduced as a user-visible failure.
- **Rejected signal:** investigated alert whose proposed mechanism does not apply.
- **Verified healthy:** a bounded check passed; it is not a universal proof outside the stated scope.

## Findings

| ID | Priority | Classification | Finding | Evidence and impact |
|---|---:|---|---|---|
| DB-001 | P0 | Verified defect | Schema version can be advanced without structural migration | A temporary database containing an old `files` table was opened through `Store`. Habitat wrote `schema_version=22`, left `indexed_bytes`, `index_truncated`, and `parse_complete` absent, then `upsert_file` failed with `OperationalError: table files has no column named indexed_bytes`. Existing workspaces can therefore be reported current while unusable. |
| TX-001 | P0 | Verified defect | Failed refresh can later be committed as a partial, revision-incoherent state | A two-file temporary workspace was refreshed with an injected failure after persisting `a.py`. The connection remained in a transaction and saw the new digest; another connection still saw the old state. `save_json("sessions", ...)` then committed the changed digest while the head revision remained unchanged. This violates revision binding and can poison subsequent reads. |
| TST-001 | P1 | Verified defect | Parallel test matrix can crash during Windows cleanup | `tools/run_test_matrix.py --mode shard --workers 2` raised `PermissionError [WinError 32]` while `TemporaryDirectory` removed `stderr.log`. The cleanup exception occurs outside `run_group`'s `try`, so the future raises, the matrix aborts, and no reliable result bundle is produced. |
| DOC-001 | P2 | Verified defect | Current-surface documentation still identifies alpha.17 | `docs/AGENT-PROTOCOL.md`, `docs/IMPLEMENTATION-STATUS.md`, `docs/LIMITATIONS.md`, and `docs/control/CAPABILITY-DIAGNOSIS.md` present themselves as current alpha.17 documents in an alpha.18 release. Historical research/release plans that mention alpha.17 are valid and must remain historical. |
| ARCH-001 | P1 | Candidate risk | Core control paths are concentrated in very large, complex functions and files | `workspace.py` is 3,134 lines and `storage.py` is 1,329 lines. Graph analysis reports `HabitatProtocol._dispatch` at cyclomatic 162, `ObservatoryReadModel.snapshot` at cyclomatic 77/cognitive 145, and `MutationEngine._normalize_operations` at cyclomatic 29/cognitive 95. These are regression multipliers, not independently verified failures. |
| ERR-001 | P1 | Candidate risk | Silent exception handling can hide degraded cleanup or provider state | CodeQL reported 38 empty `except` handlers in product/tool code, concentrated in `source_bridge.py`, `workspace.py`, `observatory.py`, `mutation.py`, and execution/provider paths. Some are intentional best-effort cleanup, but the current shape makes intended suppression indistinguishable from lost error evidence. |
| QA-001 | P1 | Verified gap | The repository has no committed CI workflow or repository-owned static-analysis policy | No `.github` workflow, coverage configuration, Semgrep configuration, Ruff configuration, or CodeQL workflow was present. Local checks exist, but the only matrix runner is affected by TST-001. Release confidence therefore depends on a maintainer's machine and manual command selection. |
| SEC-001 | P2 | Coverage gap | JavaScript static-analysis coverage is incomplete | Semgrep parsed approximately 99.9% of 56 files but recorded five scanner errors, including timeouts on large Python/JavaScript targets and one parser disagreement in `observatory_assets/app.js`. Node accepted the JavaScript syntax. The gaps require tuned, repository-owned scans rather than a security claim. |

## Causal analysis

### DB-001 — false schema truth

`Store._init_schema` uses `CREATE TABLE IF NOT EXISTS`. SQLite does not add newly declared columns to an existing table. Habitat explicitly repairs only `context_faults.authority_bytes_read`, then unconditionally writes `SCHEMA_VERSION` and commits. The version marker is therefore an assertion without a structural postcondition.

The fix must not merely add the three reproduced columns. It must introduce ordered, idempotent migrations plus a structural verifier, because a database already mislabeled as 22 cannot be trusted by version number alone.

### TX-001 — transaction ownership leak

`HabitatWorkspace.refresh` performs many writes and commits only in `_finalize_refresh`, but the refresh boundary has no rollback on exception. `Store.save_json` owns an unconditional commit. When an earlier operation fails, later code using the same connection can accidentally commit the abandoned refresh.

The fix must establish one explicit top-level transaction owner, support nested savepoints, remove commits from low-level helpers, and prove rollback with fault injection. Adding a single `rollback()` in one exception handler would leave the same class of bug in `refresh_paths`, mutation recovery, and other multi-record flows.

### TST-001 — cleanup outside the error boundary

`run_group` opens a `TemporaryDirectory` before its `try`. A browser, provider, or language-service descendant can retain an inherited log handle on Windows. `TemporaryDirectory.__exit__` then raises after `run_group` has prepared its result, and the exception escapes the future. The runner needs process-tree ownership and durable per-run artifacts; cleanup failure must be represented as infrastructure evidence rather than destroying the matrix report.

## Verified healthy checks

| Check | Result | Bound |
|---|---|---|
| Direct unit-test discovery | 285 tests passed; 35 skipped; 528.116 seconds | Windows/Python 3.14 and locally available optional providers only |
| Python bytecode compilation | Passed for `habitat`, `tests`, and `tools` | Syntax/import compilation, not behavioral proof |
| Dependency consistency | `pip check` reported no broken requirements | Current virtual environment only |
| Observatory JavaScript syntax | `node --check habitat/observatory_assets/app.js` passed | Syntax only, not browser behavior |
| MCP entry point | `python -m habitat.mcp_adapter --help` exited successfully | Startup/help path only |
| CodeQL | 131/131 Python files scanned; 152 quality/security results, 77 in product/tools | No verified product SQL injection or critical taint flow; findings still require triage |
| Current workspace SQLite | `integrity_check=ok`, zero `foreign_key_check` rows, WAL, schema metadata 22 | One current alpha.18 workspace; does not validate legacy upgrades |
| Git hygiene | `git diff --check` clean before planning documents | Audited commit only |

## Static-analysis triage

### Semgrep

The broad Semgrep pass produced 20 findings and five scanner errors.

- Nineteen SQL alerts were rejected after source inspection. Values use SQLite placeholders; interpolated table names are checked against `_JSON_TABLES`; clause fragments and placeholder lists come from fixed internal definitions.
- The file-permission alert on `chmod(..., 0o700)` was rejected because `0700` is restrictive, not world-readable.
- The five scanner errors remain a coverage gap. They must not be converted into either a vulnerability claim or a clean-security claim.

### CodeQL

The Python security-and-quality suite completed over 131 Python files. No product SQL-injection result was emitted. Most product/tool results were maintainability signals:

- 38 empty exception handlers;
- 16 unused imports;
- 8 unused local variables;
- runtime/lazy cyclic-import warnings around workspace, Observatory, and residency;
- two mixed-return warnings in Observatory helpers.

The import-cycle warnings were not reproduced as startup failures and remain candidates. Security examples under `benchmarks/` intentionally contain sensitive-data and permission patterns and must be excluded or explicitly modeled in production security gates.

## Coverage and remaining unknowns

The audit covered repository structure, current and legacy SQLite behavior, refresh failure behavior, direct tests, matrix-runner behavior, Python/JavaScript syntax, package dependency health, version drift, static analysis, and one live Habitat database.

The following remain unknown until dedicated environments exist:

- Linux and macOS filesystem, process-group, and packaging behavior;
- Python 3.10 through 3.13 compatibility after the alpha.18 changes;
- sustained multi-process writer contention and crash/power-loss recovery;
- large-repository memory and latency behavior;
- live Playwright/browser behavior across Chromium versions;
- remote or mirror backend failure modes beyond local fixtures;
- full Codex MCP stdio lifecycle under repeated connect/disconnect and long-running sessions;
- security behavior for untrusted repositories, which the current trusted-local execution profile does not claim to sandbox.

## Priority policy

- **P0 — release blocker:** DB-001 and TX-001. Do not ship a durability-focused release without migration and transaction fault-injection proofs.
- **P1 — high:** TST-001, ARCH-001, ERR-001, and QA-001. Complete these before expanding the public method surface.
- **P2 — planned:** DOC-001, SEC-001, performance budgets, platform expansion, and release automation.

## Exit criteria for the hardening program

The program is complete only when all of these are true:

1. Every supported legacy fixture migrates idempotently, passes structural verification, `integrity_check`, and `foreign_key_check`, and can execute a write/read/reopen cycle.
2. Injected failures in refresh, targeted refresh, mutation apply, rollback, and migration leave no visible or later-committable partial state.
3. The test matrix always writes a machine-readable report on Windows and Linux, including infrastructure failures and retained diagnostics.
4. Protocol and Observatory refactors preserve every public response envelope and current schema contract.
5. CI enforces tests, package smoke tests, JavaScript syntax, repository-owned static analysis, and release identity consistency.
6. Current documentation derives its version from the release source of truth; historical documents remain explicitly historical.
7. A release admission report records passed gates, skipped capabilities, scanner coverage, artifact hashes, and unresolved bounded risks.
