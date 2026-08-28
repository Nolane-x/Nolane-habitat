# Foundation Convergence Wave 3 — Core Decomposition Design

## Status

Approved roadmap slice under `docs/design/FOUNDATION-CONVERGENCE.md`.

This document defines the bounded structural migration for Wave 3. It is not permission for a repository-wide rewrite.

## Problem

Three central files currently aggregate too many independent responsibilities:

1. `HabitatWorkspace` exposes source indexing, querying, mutation, runtime, semantic, cognition, execution, and observational surfaces.
2. `Store` owns SQLite lifecycle/recovery **and** domain-specific persistence logic for symbols, relations, runtime, evidence, experimentation, and learning.
3. `HabitatProtocol._dispatch()` is a long ordered chain of method-name conditionals that mixes registry, validation, dispatch, and workspace invocation.

The project already has stable public contracts and substantial recovery/compatibility evidence. Wave 3 must reduce structural coupling without changing those contracts.

## Goals

Wave 3 MUST:

- introduce explicit internal workspace service boundaries;
- introduce explicit Store domain repository boundaries;
- introduce an operation registry that replaces monolithic protocol routing;
- preserve all existing public `HabitatWorkspace`, `Store`, and protocol contracts;
- preserve source authority, transaction semantics, recovery behavior, and protocol error mapping;
- remain additive/migratory: old public entry points delegate through the new boundaries while clients remain unchanged;
- keep each migration slice independently testable and mergeable.

## Non-goals

Wave 3 MUST NOT:

- redesign the external protocol;
- rename public protocol methods;
- change protocol response/error shapes;
- change SQLite schema or migration version;
- change source-authority or Truth/Evidence rules;
- change compiler/provider selection or semantic admission;
- rewrite `_workspace_core.py` wholesale;
- move database connection lifecycle out of `Store`;
- introduce a dependency-injection framework;
- create plugin discovery or dynamic code loading;
- alter MCP behavior;
- perform Wave 4 Benchmark Lab work.

## Migration strategy

Wave 3 is implemented as three sequential, separately certified slices.

### Slice A — Workspace service facades

Create focused internal services:

- `IndexService`
- `QueryService`
- `TransactionService`
- `RuntimeService`

`HabitatWorkspace` remains the public compatibility object. Selected public methods become thin delegators to these services. The services call the existing implementation explicitly, initially through `_CoreHabitatWorkspace` methods or narrow workspace primitives. This avoids recursive delegation and allows code to move later without contract changes.

The first migration MUST NOT physically split the 250K+ byte `_workspace_core.py`. It establishes stable seams before code motion.

### Slice B — Store domain repositories

Create repositories for:

- symbols;
- relations;
- runtime;
- evidence;
- experimentation;
- learning.

`Store` retains:

- SQLite connection ownership;
- migrations/schema validation;
- backup/recovery;
- atomic transaction ownership;
- durability settings;
- health/doctor functions.

Repositories receive the Store-owned connection through a narrow owner reference. Existing `Store` methods remain public compatibility methods and delegate to repositories. No repository may call `sqlite3.connect`, close the connection, alter PRAGMAs, run migrations, or independently commit when the legacy Store operation is expected to participate in an enclosing `Store.atomic()` transaction.

### Slice C — Operation Registry

Create a static, deterministic operation registry under `habitat/operations/`.

Every protocol method has one descriptor containing at minimum:

- exact protocol method name;
- handler callable;
- read-only classification;
- stable registration order.

`HabitatProtocol.METHODS` becomes a projection of the registry rather than a separately maintained list.

`HabitatProtocol._dispatch()` becomes registry lookup + handler invocation. Parameter validation remains explicit and existing helper semantics (`_required`, `_optional`, `_int`, `_float`, `_bool`) remain unchanged.

Unknown methods MUST still raise the same `KeyError("unknown method: ...")` boundary consumed by `handle()`.

The registry is static Python construction, not runtime plugin discovery.

## Slice A details — workspace services

### Service ownership

`HabitatWorkspace` lazily constructs one instance of each service and owns their lifetime. Services do not own Store/backend/browser/LSP/SCIP lifecycles.

Recommended private attributes:

- `_index_service`
- `_query_service`
- `_transaction_service`
- `_runtime_service`

Recommended accessors:

- `_indexing()`
- `_queries()`
- `_transactions()`
- `_runtime()`

These are internal compatibility seams, not new protocol methods.

### Initial delegated method set

The initial service migration is deliberately bounded to high-value, stable methods whose current implementation exists on `_CoreHabitatWorkspace`:

**IndexService**
- `refresh(reason="refresh")`
- `refresh_paths(paths, reason="targeted-refresh")`
- `reconcile()`

**QueryService**
- `query(query, limit=20)`
- `inspect_snapshot(object_id, include_source="none")`
- `inspect_many(object_ids, include_source="none", max_objects=50)`
- `references_snapshot(object_id, limit=200)`
- `read_source(path, start_line=1, max_lines=200)`

**TransactionService**
- `change_plan(operations)`
- `stage_change(...)`
- `stage_symbol_change(...)`
- `stage_symbol_rename(...)`
- `commit_change(...)`
- `rollback_change(...)`

**RuntimeService**
- `runtime_ingest(...)`
- `runtime_timeline(...)`
- `runtime_topology(...)`

If an exact legacy signature differs, the service and delegating wrapper MUST preserve the existing signature verbatim rather than normalize it for aesthetic consistency.

### No hidden semantic work

Services MUST NOT add implicit `refresh()`, `reconcile()`, semantic provider execution, truth projection, LSP/SCIP activation, or background work. A service delegates the same operation the caller requested.

### Recursion prevention

When a public `HabitatWorkspace` wrapper delegates to a service, the service must invoke the pre-decomposition implementation explicitly through `_CoreHabitatWorkspace.<method>(workspace, ...)` unless the implementation has already moved into the service. Calling `workspace.<same_method>()` from that service is forbidden.

## Slice B details — repositories

### Repository rule

A repository groups persistence behavior by domain, not by SQL primitive.

Each repository:

- receives the owning `Store` instance;
- accesses `owner.conn` only through that owner relationship;
- contains domain SQL and row shaping;
- does not own schema/lifecycle/recovery;
- may use Store utility functions that are not domain-specific.

### Compatibility delegation

For every migrated method:

```python
class Store:
    def all_symbols(self):
        return self.symbols.all()
```

The legacy method remains callable. Existing workspace/protocol code does not need a flag day.

### Commit semantics

Repository extraction must preserve exact legacy commit behavior. Where a legacy method intentionally commits, the repository implementation may do so. Where it relies on `Store.atomic()`, extraction must not introduce a new commit.

A later wave may rationalize transaction boundaries; Wave 3 only preserves them.

## Slice C details — operation registry

### Descriptor

The descriptor is immutable and deterministic. It does not contain model confidence, authorization policy, or execution side effects.

Conceptual shape:

```python
@dataclass(frozen=True)
class OperationDescriptor:
    name: str
    handler: Callable[[HabitatProtocol, dict[str, Any]], Any]
    read_only: bool = False
```

### Registry invariants

- duplicate names are rejected during construction;
- order is stable and equals the current `METHODS` order;
- every listed method has exactly one handler;
- every read-only method is registered as such;
- `protocol.capabilities` reports the registry method list;
- telemetry/activity classification continues to use the same read-only semantics;
- registration itself performs no workspace work.

### Migration shape

Handlers can initially be small functions that contain the exact former `if m == ...` body. They are then grouped into focused modules only if doing so improves reviewability without changing behavior.

## Compatibility invariants

Across all Wave 3 slices:

1. Public Python API signatures remain stable.
2. Protocol method order remains stable.
3. Protocol success/error JSON shapes remain stable.
4. Unknown protocol method behavior remains stable.
5. Read-only protocol calls remain observational and do not emit activity solely because of observation.
6. Store schema version and database structure remain unchanged.
7. Existing persisted workspaces open without migration caused by Wave 3.
8. Mutation/recovery semantics remain unchanged.
9. Semantic provider admission and source authority remain unchanged.
10. No service/repository/registry constructor performs hidden source/runtime work.

## Dependency direction

Allowed direction:

```text
Protocol -> Operation Registry -> HabitatWorkspace public API
HabitatWorkspace -> Services -> _CoreHabitatWorkspace / narrow primitives
_CoreHabitatWorkspace -> Store compatibility API
Store compatibility API -> Domain Repositories -> Store-owned connection
```

Forbidden cycles:

- repositories importing workspace/protocol;
- services importing protocol;
- operation registry importing Store/repositories;
- repositories constructing services;
- services constructing protocol instances.

## Failure policy

Wave 3 is structural. If delegation changes an exception type, error message relied on by compatibility tests, transaction outcome, revision behavior, activity behavior, or database recovery outcome, that is a regression and must be fixed at the new boundary rather than accepted as cleanup.

## Testing strategy

Every slice uses RED → GREEN TDD.

### Slice A tests

Characterize:

- service objects are lazy and stable per workspace;
- public wrappers call the intended service exactly once;
- service direct calls match legacy `_CoreHabitatWorkspace` behavior;
- no recursive delegation;
- no hidden semantic/LSP/SCIP activation;
- current mutation authority/recovery tests remain green.

### Slice B tests

For every repository family:

- compatibility method and repository method return equivalent rows/results;
- writes are visible through the old Store API and vice versa;
- nested atomic rollback remains atomic;
- no schema/user_version change;
- fork/recovery/doctor behavior remains unchanged.

### Slice C tests

Characterize:

- registry name order equals the pre-migration `METHODS` list exactly;
- duplicate registration fails;
- registry covers all methods exactly once;
- read-only classification is identical;
- representative success and validation/error responses are byte/shape compatible;
- unknown methods preserve error behavior;
- registry construction causes no workspace activity.

## Certification gate

Each slice requires exact-head:

- full Ubuntu/Windows × Python 3.10/3.14 Habitat CI;
- protocol conformance;
- database and source-mutation recovery evidence;
- reproducibility and distributable artifact verification;
- Semgrep policy;
- CodeQL;
- changed-file boundary audit;
- no unresolved review threads.

Wave 3 is complete only after all three slices are merged into `main` and `main` is verified to contain them in sequence.
