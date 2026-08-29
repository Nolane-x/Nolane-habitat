# Foundation Convergence Wave 3C — Operation Registry Implementation Plan

> **Status:** implementation plan for the final Wave 3 slice.
>
> **Base:** `main@8bbe11b8897367989d24ce88ffefe55311874dd5`
>
> **Canonical design:** `docs/superpowers/specs/2026-08-28-core-decomposition-design.md`

## Goal

Replace `HabitatProtocol._dispatch()`'s 162-branch monolithic router with one immutable, deterministic static operation registry while preserving the protocol byte/shape contract, public method order, validation helpers, telemetry/activity classification, and workspace semantics exactly.

This slice is structural only. It does not introduce dynamic plugins, new methods, new authorization rules, new protocol fields, or handler behavior cleanup.

## Baseline facts that must remain true

The exact Slice C base has:

- protocol version `habitat.agent.v1alpha2`;
- 162 entries in `HabitatProtocol.METHODS`;
- 162 unique method names;
- 162 `_dispatch()` branches covering those names exactly once;
- five declared read-only methods: `protocol.capabilities`, `workspace.inspect`, `workspace.inspect.batch`, `workspace.references`, and `workspace.source.read`;
- `_dispatch()` branch order is **not** identical to `METHODS` order.

That final point is a compatibility trap: registry order must be built from the existing `METHODS` order, not from lexical order and not from the old `if`-branch order.

## Hard boundaries

Expected changed files:

- `docs/superpowers/plans/2026-08-29-operation-registry.md`
- `habitat/operation_registry.py` (new)
- `habitat/protocol.py`
- `tests/test_operation_registry.py` (new)
- `tests/test_protocol_conformance.py` only if a missing compatibility characterization cannot be expressed cleanly in the focused test file.

Do not change unless a proven blocker requires it:

- workspace/core/services;
- Store/repositories/schema/migrations;
- truth/semantic/provider code;
- MCP adapter wire behavior;
- server transport;
- compiler selection;
- workflows/recovery tooling;
- protocol version.

## Architecture

### `OperationDescriptor`

Use a frozen dataclass with the conceptual contract from the design:

```python
@dataclass(frozen=True)
class OperationDescriptor:
    name: str
    handler: Callable[[HabitatProtocol, dict[str, Any]], Any]
    read_only: bool = False
```

Runtime imports must not create a protocol/registry cycle. `HabitatProtocol` may be referenced only under `TYPE_CHECKING` in the registry module.

### `OperationRegistry`

The registry is constructed once from an ordered tuple of descriptors.

Required properties:

- duplicate descriptor names raise during construction;
- order is insertion order and deterministic;
- names are exposed as an immutable tuple;
- read-only names are exposed as a frozen set;
- lookup has no workspace side effects;
- no `register()`, mutation API, entry-point discovery, import scanning, environment loading, or plugin behavior exists.

### Static handler table

Each of the 162 former `_dispatch()` bodies becomes a small top-level handler in `habitat/operation_registry.py`.

Handlers may call:

- `protocol.workspace.<existing public method>`;
- existing protocol validation helpers (`_required`, `_optional`, `_int`, `_bool`, `_float`);
- protocol constants only where required for exact legacy output.

The static descriptor tuple is ordered according to the pre-migration `METHODS` list, even where old `_dispatch()` branch order differed.

`protocol.capabilities` must report the registry-derived method list in the exact legacy order.

### `HabitatProtocol`

Preserve compatibility attributes:

```python
METHODS = list(OPERATION_REGISTRY.names)
READ_ONLY_METHODS = OPERATION_REGISTRY.read_only_names
```

`_dispatch()` becomes a narrow registry lookup. A missing descriptor must raise exactly `KeyError(f"unknown method: {method}")`.

Activity and trace classification must obtain read-only semantics from registry metadata while preserving legacy special-prefix exclusions exactly.

## Task 1 — Registry kernel (RED → GREEN)

### RED

Create `tests/test_operation_registry.py` with focused kernel tests:

1. `OperationDescriptor` is frozen.
2. Registry preserves descriptor insertion order.
3. Duplicate names fail deterministically.
4. Lookup returns the exact descriptor or `None`.
5. Names are immutable.
6. Read-only names are immutable.
7. There is no runtime registration/mutation API.

Run the focused test on the RED commit and verify the failure is specifically because `habitat.operation_registry` does not exist.

### GREEN

Create only the generic immutable registry kernel in `habitat/operation_registry.py`.

Do **not** wire `HabitatProtocol` yet. Verify focused tests GREEN and run compile.

## Task 2 — Static 162-operation table (RED → GREEN)

### RED characterization

Add tests that capture the exact pre-migration surface as explicit constants in the test:

- exact ordered tuple of all 162 method names;
- exact five read-only names;
- 162 total / 162 unique;
- registry has exactly one descriptor per expected method;
- descriptor order equals the explicit baseline method tuple;
- read-only classification equals the explicit baseline set;
- each descriptor has a callable handler;
- importing/constructing the registry performs no workspace work.

Do not derive the expected order from `HabitatProtocol.METHODS` in this test; that would allow both sides to drift together.

### GREEN

Move the exact former branch bodies into static top-level handlers and construct the ordered descriptor tuple.

Generation may be used as a local mechanical aid, but no generator or dynamic discovery ships in the repository.

Before commit, mechanically prove:

- former dispatch branch names = registry handler names as sets;
- registry order = legacy `METHODS` order;
- no duplicate handlers/descriptors;
- all five and only five legacy read-only methods are marked read-only.

At this task boundary `HabitatProtocol` may still dispatch through the old router; the registry itself must already be complete and behavior-capable.

## Task 3 — Route protocol through registry (RED → GREEN)

### RED

Add routing tests that fail while the monolithic router is still authoritative:

- patch a registry descriptor handler at the test seam and prove `_dispatch()` delegates through registry lookup rather than an `if` chain;
- unknown method preserves exact `KeyError("unknown method: ...")` behavior before `handle()` translation;
- `protocol.capabilities` returns the exact explicit 162-method baseline order;
- `HabitatProtocol.METHODS` remains a list for public compatibility;
- `READ_ONLY_METHODS` retains membership semantics.

Do not add a public registry mutation API.

### GREEN

Wire `HabitatProtocol` to the static registry and delete all 162 routing branches.

Keep unchanged:

- JSON parser and transport validation;
- `_required`, `_optional`, `_int`, `_bool`, `_float`;
- `_error()`;
- exception translation in `handle()`;
- protocol version.

Verify focused registry + protocol tests GREEN.

## Task 4 — Read-only telemetry/activity equivalence (RED → GREEN)

### RED

Characterize representative calls using a lightweight fake workspace or mocks:

- each of the five read-only methods emits neither `tool.started`/`tool.completed` activity nor trace-call telemetry solely due to observation;
- ordinary non-read-only methods still produce activity and trace telemetry;
- `workspace.activity.*` and `workspace.observatory.*` retain their activity exclusion;
- `workspace.trace.*` retains both activity and trace-control exclusions exactly;
- unknown methods retain legacy activity/trace behavior as currently produced by `handle()`.

The test must use registry metadata as the intended source of truth without changing externally visible responses.

### GREEN

Replace direct classification dependence on the legacy handwritten set with descriptor metadata while preserving the compatibility `READ_ONLY_METHODS` attribute.

Do not broaden the five-method read-only set in Wave 3.

## Task 5 — Compatibility corpus and structural audit

Run focused and existing protocol tests, including:

- `tests.test_operation_registry`
- `tests.test_protocol_conformance`
- public compatibility tests
- representative alpha tests that assert `HabitatProtocol.METHODS`

Add focused exact-response tests if needed for:

- success response shape;
- missing required parameter -> `INVALID_PARAMS`;
- wrong parameter type -> `INVALID_PARAMS`;
- unknown method -> `NOT_FOUND`;
- exact error message/details shape.

Structural checks:

- 162 exact names;
- no duplicates;
- registry import performs no workspace/runtime I/O;
- no registry -> Store/repository import;
- no dynamic registration/discovery;
- `habitat/protocol.py` no longer contains `if m == ...` routing;
- `METHODS` order unchanged;
- protocol version unchanged.

## Task 6 — Exact-head certification and merge

On the final candidate SHA:

1. Audit changed filenames against the allowed boundary.
2. Verify no main/head drift.
3. Require Habitat CI on the exact SHA across Ubuntu/Windows × Python 3.10/3.14.
4. Require all substantive release gates: compile, release identity, full regression, isolated regression, public compatibility, protocol conformance, DB recovery, source-mutation recovery, fault injection, independent-checkout reproducibility, distributable artifacts, Semgrep, and quality evidence/upload.
5. Require CodeQL Python and JavaScript/TypeScript.
6. Audit PR reviews and unresolved threads.
7. Merge with `expected_head_sha=<final candidate>`.
8. Verify PR merged/closed and `main` equals the returned merge commit.

Because the connected GitHub Mark-Ready mutation is known to be broken, open the Slice C PR as **non-draft** from the start. This changes no verification standard.

## Wave 3 completion condition

Wave 3 is complete only when Slice A is present in `main`, Slice B merge `8bbe11b8897367989d24ce88ffefe55311874dd5` is an ancestor, this Slice C is merged after Slice B, the exact merge commit on `main` is verified, and every Slice C exact-head certification gate is green.

After that, proceed automatically to Wave 4 Benchmark Lab according to Foundation Convergence without asking for an additional approval checkpoint.
