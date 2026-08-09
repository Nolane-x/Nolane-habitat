# Nolane Habitat 0.1.0-alpha.0 — Executable Vertical Slice Plan

> **Planning discipline:** This plan is an executable control artifact, not a promise of capability. Each milestone has falsifiable postconditions, explicit unknowns, rollback, and verification. Source files remain canonical truth; all semantic state is derived.

## Goal

Prove or falsify the core Habitat thesis on a narrow implementation:

> An agent can ingest a normal folder/ZIP/file, receive a compact structured orientation to a task, inspect exact source by semantic handle, mutate source transactionally, execute project capabilities without a terminal interface, observe HTML UI semantically, and keep the external source tree synchronized.

## Non-goals for alpha.0

- No desktop/OS automation.
- No claim of instant/full understanding.
- No LLM-generated architecture summaries.
- No vector-only retrieval.
- No full Tree-sitter/LSP integration yet; interfaces must leave room for them.
- No JavaScript runtime browser observation yet; static HTML semantics only.
- No container/network sandbox guarantee.
- No multi-agent orchestration.
- No proprietary workspace bundle as source of truth.

## Protected invariants

1. Source bytes outrank derived state.
2. Project code is never executed during indexing.
3. ZIP imports reject traversal and archive symlinks.
4. Mutation requires a workspace revision and supports rollback on failure.
5. A structured execution receipt records argv, cwd, timeout, exit code, output, and changed paths.
6. Semantic claims expose trust grade (`exact`, `parser`, `heuristic`, `derived`).
7. Unsupported precision is reported as an unknown instead of silently upgraded.

## Capability diagnosis

| Requirement | alpha.0 mechanism | Evidence target | Gap / fallback |
|---|---|---|---|
| Folder/ZIP/file ingest | Source Bridge | deterministic tests | symlink handling conservative |
| Persistent project state | SQLite | round-trip tests | no graph DB |
| Python structure | stdlib AST | exact location tests | decorators/types only partially modeled |
| JS/TS/Java structure | conservative regex | trust=heuristic | future Tree-sitter/LSP |
| Retrieval | SQLite FTS5 + 1-hop graph | task-orient tests | no semantic embeddings |
| Exact inspection | source range handle | line-level tests | UTF-8 replacement for display only |
| Mutation | digest/revision guarded replace | conflict/rollback tests | symbol rewrite later |
| Execution | subprocess program+args | receipt tests | not a security sandbox |
| UI | semantic static HTML parser | accessible element tests | no runtime DOM/layout yet |
| Sync | direct canonical source writes + refresh | external edit tests | polling API, no daemon watcher yet |

## Architecture decision records for this slice

### ADR-A0-001 — Python standard library first

**Decision:** Keep alpha.0 dependency-free.

**Reason:** We need to test the abstraction before paying integration complexity for Tree-sitter, LSP, browser drivers, graph DBs, or embedding models.

**Invalidation condition:** If the prototype cannot represent enough structure to measure the workflow, add one precise parser/provider rather than broad dependencies.

### ADR-A0-002 — SQLite is the semantic state store

**Decision:** Store files, symbols, relations, revisions, runs and transactions in SQLite; use FTS5 when available.

**Reason:** Durable, inspectable, transactional, zero service dependency, sufficient for alpha graph traversal.

**Invalidation condition:** Benchmarks demonstrate query/update limits that cannot be addressed with schema/index changes.

### ADR-A0-003 — Source tree is canonical

**Decision:** Habitat mutates real linked/managed source files atomically, then recompiles derived state.

**Reason:** Human tools, compilers and version control continue to work normally; Habitat is disposable/rebuildable.

### ADR-A0-004 — Terminal is implementation detail

**Decision:** Agent-facing execution is `run(capability)` returning a typed receipt. The implementation may use subprocess underneath.

**Reason:** Hiding the terminal UI is useful only if state and postconditions become structured; merely wrapping shell text is insufficient.

### ADR-A0-005 — UI semantics start static, not fake-dynamic

**Decision:** Parse static HTML into typed UI elements now and explicitly label missing JS/layout/runtime semantics.

**Reason:** A partial truthful sensor is preferable to pretending we implemented a browser intelligence layer.

## Milestone M0 — Contract and schemas

**Postconditions**
- Scope/non-scope and source authority are machine/human documented.
- Core record types exist for file, symbol, relation, revision, context, transaction and run receipt.
- Every derived symbol has a source path/range and trust grade.

**Verification**
- Schema smoke tests.
- Self-audit that no documentation claims runtime browser/LSP precision in alpha.0.

## Milestone M1 — Source Bridge

**Build**
- `prepare_source()` for linked folders, managed ZIP imports, managed loose files.
- ZIP path traversal and symlink rejection.
- Atomic write primitive.
- Source snapshot metadata.

**Tests**
- folder import;
- ZIP import;
- traversal archive blocked;
- external edit detected after refresh;
- managed loose file preserved.

**Rollback**
- Source Bridge is isolated from semantic compiler; can replace archive strategy without DB migration.

## Milestone M2 — Semantic Twin Core

**Build**
- SQLite schema;
- file inventory/digests;
- Python AST extractor;
- conservative JS/TS/Java/HTML extraction;
- relation resolver;
- revision chain;
- FTS search.

**Postconditions**
- `enter()` returns revision, language mix, file/symbol counts and discovered execution capabilities.
- Python symbols are exact-parser backed.
- Non-Python heuristic extraction never masquerades as exact semantics.

## Milestone M3 — Context Compiler alpha

**Build**
- task token normalization;
- indexed candidate retrieval;
- bounded one-hop relation expansion;
- object budget;
- uncertainty emission;
- exact-source handles.

**Postcondition**
- A task such as “where is login validation implemented?” returns relevant objects without first opening whole files.

**Failure probes**
- ambiguous symbol names;
- no match;
- heuristic-only match;
- irrelevant high-frequency README text.

## Milestone M4 — Transactional mutation

**Build**
- staged transaction identity;
- base revision validation;
- optional exact source digest precondition;
- unique-match replace operation;
- atomic file write;
- backup + rollback;
- refresh after commit.

**Postconditions**
- Mutation is visible immediately in canonical external source.
- Stale transaction fails instead of overwriting newer external work.

## Milestone M5 — Structured execution

**Build**
- capability discovery from project manifests;
- `run_action(program,args)` with `shell=False`;
- timeout;
- bounded stdout/stderr;
- changed-file read-back;
- persistent run receipt.

**Important limitation**
This is an execution abstraction, not yet a hardened sandbox. Agent-facing API is AI-native; security isolation remains future work.

## Milestone M6 — Semantic HTML observation

**Build**
- HTML parser;
- role/name/attributes/text extraction;
- stable per-file UI handles;
- explicit limitations block.

**Postcondition**
- Agent can reason about forms/buttons/inputs/headings without reading raw HTML first.

**Not yet proven**
- visual correctness;
- runtime framework state;
- computed styles/layout;
- network/console events.

## Milestone M7 — Benchmark harness seed

Create small tasks comparing:

A. direct file scan baseline;
B. Habitat orient + inspect.

Measure at minimum:
- number of whole-file reads;
- bytes returned to caller;
- correctness of first relevant object;
- cold indexing cost;
- warm orientation latency.

Do **not** claim token reduction until the caller is an LLM/tokenizer-aware harness.

## Alpha.0 completion gate

Alpha.0 may be called a *working research prototype* only if all are true:

- [x] all unit/adversarial tests pass;
- [x] source/ZIP/file import works;
- [x] external edit + refresh changes revision;
- [x] task orientation returns source-backed objects;
- [x] exact symbol source can be inspected without whole-file read;
- [x] guarded mutation synchronizes to source;
- [x] stale mutation is rejected;
- [x] structured test/program execution returns receipt;
- [x] semantic HTML observation works;
- [x] benchmark seed runs reproducibly;
- [x] limitations document remains explicit.

## Next plan only after alpha.0 evidence

If alpha.0 validates the abstraction, alpha.1 should prioritize **precision upgrades**, not feature count:

1. Tree-sitter provider interface + incremental parse;
2. Python/TypeScript language-server adapters;
3. precise reference/definition relations;
4. file watcher daemon with debounce/reconciliation;
5. structured diagnostics/test adapters;
6. headless Chromium semantic runtime surface;
7. task-specific retrieval benchmark against plain grep/read and repo-map baselines.

If alpha.0 fails to reduce reconstruction work, redesign Context Compiler/object granularity before adding these layers.
