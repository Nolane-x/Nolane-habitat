# Observatory Projection Cleanup — Design Specification

**Status:** Wave 7 implementation design for Foundation Convergence  
**Baseline:** Wave 6 merge `863457c9f2f7f073b3126a23c4d3f77f33712b68`  
**Master plan:** `docs/design/FOUNDATION-CONVERGENCE.md` — Wave 7

## 1. Objective

Wave 7 makes Habitat's Observatory an explicit, independently disable-able projection layer over existing durable/runtime truth. It separates the read-only observability core from the HTTP/cinematic frontend, removes the Observatory's remaining durable write on startup, and adds descriptive cost evidence for headless projection versus frontend/server use.

This wave does **not** treat visual sophistication as architectural progress and does not claim performance superiority from the cost measurements.

## 2. Existing architecture and defects

The alpha.19-compatible Observatory already has strong pieces worth preserving:

- `ObservatoryReadModel` opens `habitat.sqlite3` through SQLite URI `mode=ro` and `PRAGMA query_only=ON`;
- snapshots are reconstructed from canonical Store rows, source/backend metadata, and bounded runtime/UI artifacts rather than from a second Observatory database;
- HTTP mutation verbs fail closed;
- the HTTP server binds loopback only;
- `habitat/server.py` already supports `--no-observatory`;
- cinematic assets already live under `habitat/observatory_assets/`.

But `habitat/observatory.py` currently combines four responsibilities in one module:

1. durable/read-only projection (`ObservatoryReadModel`);
2. HTTP/SSE transport;
3. static/cinematic frontend delivery;
4. CLI/server lifecycle.

A correctness defect also remains: `ObservatoryServer.start()` calls `workspace.activity_emit("observatory.started", ...)`. Merely starting an observer therefore changes the authoritative SQLite state. Existing request-level read-only tests snapshot the database *after* server startup and do not detect that mutation.

## 3. Target structure

### 3.1 Observability Core

Create `habitat/observability.py` as the frontend-independent projection core.

It owns:

- `ObservatoryReadModel`;
- revision/activity read projection;
- coherent snapshot reconstruction;
- privacy-safe operator/frame metadata projection;
- no HTTP server, browser launch, asset loading, sockets, or frontend state;
- no mutation API and no writable Store connection.

The core remains a projection over the existing workspace SQLite/source/runtime artifacts. It does not create a database, cache database, journal, or alternate source of truth.

`ObservatoryReadModel` remains import-compatible from `habitat.observatory` through a re-export during this convergence series.

### 3.2 Cinematic Frontend / Transport

Create `habitat/observatory_frontend.py` for the current HTTP/SSE/static/cinematic adapter.

It owns:

- `_Handler`;
- loopback HTTP server classes;
- `ObservatoryServer`;
- static asset delivery;
- `/api/*`, `/events`, and UI-frame transport;
- optional browser opening.

It consumes an `ObservatoryReadModel`; it does not own source/runtime truth.

`habitat/observatory.py` becomes a compatibility facade/CLI entry point that re-exports the established Observatory names and lazily composes the frontend adapter. Existing URLs, protocol method names, CLI name, asset paths, and serialized snapshot schema remain compatible.

### 3.3 Startup must be state-neutral

Starting or stopping `ObservatoryServer` must not call any durable workspace mutation method. In particular, remove the `workspace.activity_emit("observatory.started", ...)` write.

Server status is process-local ephemeral state exposed by `ObservatoryServer.status()` and `/api/health`; it is not an authoritative domain event.

The hard test boundary is:

```text
SQLite dump before Observatory construction/start
== SQLite dump after start/status/GET/HEAD/stop
```

for an otherwise quiescent workspace.

### 3.4 Independent disable/headless mode

Do not invent a second configuration system. Preserve the existing `habitat-agent-server --no-observatory` switch and the existing manifest compatibility fields.

Wave 7 must prove:

- workspace create/open/enter and protocol serving work when the frontend is never imported or started;
- `--no-observatory` never calls `workspace.observatory_start()`;
- core projection can be used directly without importing `habitat.observatory_frontend`;
- disabling the frontend does not disable source authority, protocol, runtime, Learning Plane, or execution behavior.

Default agent-server behavior is not changed in this wave; only independence and state neutrality are strengthened.

## 4. Projection authority and privacy invariants

The following are constitutional for this wave:

- Observatory is observer-only and has no mutation authority.
- Canonical source files and the existing Store remain truth.
- No Observatory-owned durable database is introduced.
- HTTP remains GET/HEAD-only for successful observer operations; mutation methods fail closed.
- Read model SQLite connections remain `mode=ro` and `query_only`.
- UI frame transport returns only already-produced privacy-safe frame artifacts/metadata and does not acquire browser action authority.
- Raw private chain-of-thought is neither required nor surfaced.
- Frontend animation/layout/camera state never feeds back into Truth, Cognitive, Action, or Learning planes.

## 5. Cost evidence

Add a dedicated benchmark/measurement surface rather than automatic runtime telemetry.

Create `benchmarks/observatory_projection_costs.py` with deterministic JSON output fields for a supplied workspace:

- source commit / workspace revision where available;
- `headless_projection_wall_ms`;
- `headless_projection_bytes` (canonical compact JSON bytes of one snapshot);
- `frontend_start_wall_ms` when explicitly requested, otherwise `null`;
- `frontend_health_wall_ms` when explicitly requested, otherwise `null`;
- whether frontend was included;
- claim boundary.

Rules:

- measurements are descriptive observations, not pass/fail performance thresholds;
- missing/unavailable frontend measurements serialize as `null`, never zero;
- measurements must not mutate workspace state;
- the benchmark does not write its measurements into Habitat SQLite;
- no mean/aggregate superiority claim is emitted by the runtime.

Tests validate schema, non-negative measured values, `null` semantics, and state neutrality; they do not assert machine-specific timing thresholds.

## 6. Compatibility boundary

Wave 7 preserves:

- `habitat.observatory.ObservatoryReadModel` import;
- `habitat.observatory.ObservatoryServer` import;
- `habitat.observatory.start_observatory`;
- existing Observatory URL paths and JSON shapes;
- `workspace.observatory.start/status` protocol methods;
- 12-tool MCP surface;
- `habitat-agent-server --no-observatory`;
- packaged `observatory_assets`;
- alpha.19 workspace/schema compatibility.

No protocol method is removed or renamed.

## 7. Fault closure

Machine evidence must cover at least:

1. server construction/start/status/GET/HEAD/stop leaves authoritative SQLite unchanged;
2. POST/PUT/PATCH/DELETE remain rejected and cannot mutate state;
3. importing/using Observability Core does not import the frontend module;
4. headless agent-server mode never starts the Observatory and still serves core protocol behavior;
5. core projection does not create a second database or write cache;
6. snapshot/front-end compatibility remains intact after module separation;
7. cost measurement is non-mutating and uses `null` for unavailable frontend fields;
8. no Wave 7 claim equates cinematic growth with cognitive/architectural improvement.

## 8. Exit criteria

Wave 7 is complete only when:

- Observability Core is separated from cinematic frontend/transport;
- Observatory startup is durably state-neutral;
- frontend can be independently disabled without breaking core behavior;
- headless/runtime cost evidence exists with honest missing-value semantics;
- existing Observatory/protocol/MCP compatibility remains green;
- no second truth store exists;
- exact-final Ubuntu/Windows × Python 3.10/3.14 CI succeeds;
- CodeQL, compatibility, recovery, fault injection, reproducibility, distribution, and Semgrep gates succeed;
- review/thread/comment and changed-file boundary audits are clean;
- `main` has no drift immediately before exact-head merge.

**Claim boundary:** Wave 7 proves projection separation, observer-only state neutrality, frontend independence, and descriptive runtime-cost measurement. It does not prove that cinematic rendering improves reasoning quality, model capability, or task success.
