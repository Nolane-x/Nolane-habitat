# Wave 3 Store Domain Repositories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish explicit `SymbolsRepository`, `RelationsRepository`, `RuntimeRepository`, `EvidenceRepository`, `ExperimentationRepository`, and `LearningRepository` persistence seams behind the existing `Store` API while preserving exact SQLite schema, transaction, commit, recovery, and row-shape behavior.

**Architecture:** `Store` remains the sole owner of SQLite connection lifecycle, schema/migrations, `atomic()`, recovery, durability settings, and health operations. Six focused repositories receive the owning `Store`, use only `owner.conn` plus narrow pre-existing Store utilities, and contain only the domain SQL migrated in this slice. Existing `Store` methods remain compatibility entry points and delegate to one repository method exactly once; no caller outside `Store` is required to change.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`/`json`/typing, `unittest`, existing Habitat GitHub Actions matrix.

**Spec:** `docs/superpowers/specs/2026-08-28-core-decomposition-design.md`

## Global Constraints

- No SQLite schema or migration-version changes.
- `Store` remains the sole owner of `sqlite3.connect`, connection close, PRAGMAs, schema initialization, migrations, backup/recovery, `atomic()`, durability settings, and `doctor()`.
- Repository constructors perform no SQL, commits, migrations, PRAGMA changes, source/runtime work, or background work.
- A repository accesses SQLite only through `self.owner.conn`; no repository stores or creates an independent connection.
- Existing public `Store` method names, signatures, return row shapes, ordering, exceptions, and commit behavior remain stable.
- A legacy method that currently commits must still commit at the same observable boundary after delegation.
- A legacy method that currently does **not** commit must not gain an implicit commit; this is required for enclosing `Store.atomic()` rollback semantics.
- Existing `_TransactionAwareConnection.commit()` suppression inside `Store.atomic()` remains unchanged and is not copied into repositories.
- No `_workspace_core.py`, workspace service, protocol/MCP, semantic admission, source-authority, compiler-selection, workflow, or GitHub Actions changes in this slice.
- Shared Store utilities such as `delete_search`, `index_search`, and `get_meta` remain on `Store` when moving them would broaden the domain boundary or duplicate behavior.
- Every production migration task follows RED test-only evidence before GREEN implementation.

---

## File Map

Create:

- `habitat/repositories/__init__.py` — internal exports for the six repository classes.
- `habitat/repositories/symbols.py` — symbol and symbol-term persistence only.
- `habitat/repositories/relations.py` — semantic relation-edge persistence only.
- `habitat/repositories/runtime.py` — `runtime_events` persistence only.
- `habitat/repositories/evidence.py` — evidence persistence and activation state only.
- `habitat/repositories/experimentation.py` — hypotheses, hypothesis-evidence links, and experiments.
- `habitat/repositories/learning.py` — workspace context feedback/utility, epistemic items, and project memories.
- `tests/test_store_repositories.py` — ownership, routing, row-equivalence, side-effect, commit-parity, and atomicity contracts.

Modify:

- `habitat/storage.py` — lazy repository accessors plus compatibility delegates for the explicitly migrated methods.

Must not modify:

- `habitat/storage_migrations.py`
- `habitat/database_health.py`
- `habitat/_workspace_core.py`
- `habitat/workspace.py`
- `habitat/protocol.py`
- `habitat/mcp_adapter.py`
- `.github/workflows/*`

## Repository Ownership Contract

`Store` lazily owns one stable instance of each repository. Use private accessors rather than eager constructor work:

```python
def _symbols_repository(self) -> SymbolsRepository:
    repository = getattr(self, "_symbols_repository_instance", None)
    if repository is None:
        repository = SymbolsRepository(self)
        self._symbols_repository_instance = repository
    return repository
```

Equivalent accessors:

- `_symbols_repository() -> SymbolsRepository`
- `_relations_repository() -> RelationsRepository`
- `_runtime_repository() -> RuntimeRepository`
- `_evidence_repository() -> EvidenceRepository`
- `_experimentation_repository() -> ExperimentationRepository`
- `_learning_repository() -> LearningRepository`

Repository constructors are deliberately trivial:

```python
class SymbolsRepository:
    def __init__(self, owner: "Store") -> None:
        self.owner = owner
```

Use `TYPE_CHECKING` for the `Store` import so repository modules do not create a runtime import cycle.

## Commit-Parity Rule

Migration must preserve the current behavior method-by-method:

**No implicit commit in migrated method:**

- `replace_symbols_for_file`
- `symbols_matching_terms` (read only)
- `symbol_by_id` (read only)
- `symbols_named` (read only)
- `symbols_for_file` (read only)
- `all_symbols` (read only)
- `replace_relations`
- `sync_relations`
- `relations_for` (read only)
- `incoming_relations` (read only)
- `append_evidence`
- `evidence_by_id` (read only)
- `active_evidence` (read only)
- `active_evidence_ids` (read only)
- `resolve_evidence`
- `evidence_by_ids` (read only)
- context/learning reads and any currently non-committing helper listed below.

**Explicit commit preserved in migrated method:**

- `append_runtime_event`
- `create_hypothesis`
- `update_hypothesis`
- `link_hypothesis_evidence`
- `create_experiment`
- `complete_experiment`
- `record_context_feedback`
- `create_epistemic_item`
- `update_epistemic_item`
- `create_project_memory`
- `update_project_memory`

Inside an enclosing `Store.atomic()`, these calls still rely on `_TransactionAwareConnection.commit()` suppression exactly as today. Repositories must call `self.owner.conn.commit()` where the legacy method did; they must not bypass Store transaction awareness with raw `sqlite3.Connection.commit` or `commit_atomic()`.

---

### Task 1: Repository package and lazy Store ownership

**Files:**
- Create: `habitat/repositories/__init__.py`
- Create: `habitat/repositories/symbols.py`
- Create: `habitat/repositories/relations.py`
- Create: `habitat/repositories/runtime.py`
- Create: `habitat/repositories/evidence.py`
- Create: `habitat/repositories/experimentation.py`
- Create: `habitat/repositories/learning.py`
- Create: `tests/test_store_repositories.py`
- Modify: `habitat/storage.py`

**Interfaces:**
- Produces the six Store accessors named in the Repository Ownership Contract.
- Each repository exposes `.owner` and performs no work in `__init__`.

- [ ] **Step 1: Write RED ownership tests**

Add tests that create a temporary `Store`, patch each repository constructor with a counting wrapper, and assert each accessor is lazy and stable:

```python
self.assertIs(store._symbols_repository(), store._symbols_repository())
self.assertIs(store._relations_repository(), store._relations_repository())
self.assertIs(store._runtime_repository(), store._runtime_repository())
self.assertIs(store._evidence_repository(), store._evidence_repository())
self.assertIs(store._experimentation_repository(), store._experimentation_repository())
self.assertIs(store._learning_repository(), store._learning_repository())
```

Record `PRAGMA user_version`, `store.conn.in_transaction`, and a table-count snapshot before and after accessor construction; assert they are unchanged. Patch `store.conn.commit` with a spy while only constructing/accessing repositories and assert zero calls.

- [ ] **Step 2: Run RED**

Run:

```bash
python -m unittest tests.test_store_repositories -v
```

Expected: failure because `habitat.repositories` and Store repository accessors do not exist. No unrelated test should fail.

- [ ] **Step 3: Implement minimal repository classes and lazy accessors**

Each new repository module contains only its class constructor. Add `habitat/repositories/__init__.py` exports. In `storage.py`, import the six classes and add six lazy accessors using `getattr`; do not touch `Store.__init__`, `_init_schema`, `_complete_schema_initialization`, `_ensure_symbol_terms_index`, `atomic`, `close`, or `doctor`.

- [ ] **Step 4: Verify GREEN and lifecycle boundary**

Run:

```bash
python -m unittest tests.test_store_repositories -v
python -m unittest discover -s tests -v
```

Expected: repository ownership tests pass; full regression has no behavior changes.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: add Store repository seams"
```

---

### Task 2: SymbolsRepository

**Files:**
- Modify: `habitat/repositories/symbols.py`
- Modify: `habitat/storage.py`
- Modify: `tests/test_store_repositories.py`

**Migrated Store interfaces, signatures unchanged:**

```python
replace_symbols_for_file(file_id: str, symbols: Iterable[SymbolRecord]) -> None
symbols_matching_terms(terms: list[str], limit: int = 1000)
symbol_by_id(object_id: str)
symbols_named(name: str)
symbols_for_file(file_id: str)
all_symbols()
```

**Boundary:** `upsert_file`, diagnostics, occurrences, generic FTS/search helpers, compile cache, and `_ensure_symbol_terms_index` remain on `Store` in this slice. `SymbolsRepository.replace_for_file()` may call `owner.delete_search()` and `owner.index_search()` because those are established shared Store utilities. It may delete relation rows for removed symbols exactly as the current method does; ownership of general relation synchronization remains `RelationsRepository`.

- [ ] **Step 1: Write RED routing and direct-equivalence tests**

Patch `SymbolsRepository` methods with sentinels and assert every listed `Store` compatibility method routes exactly once with exact arguments. Add a fixture with two files and symbols; compare rows returned by repository reads against the compatibility Store methods after seeding.

Add a commit-parity test:

```python
with store.atomic():
    store.replace_symbols_for_file(file_id, replacement)
    raise RollbackProbe()
```

After catching `RollbackProbe`, assert original symbol rows and symbol terms remain intact. This proves extraction added no commit.

- [ ] **Step 2: Run RED**

Expected: public Store methods still execute their inline SQL and therefore bypass patched repository methods.

- [ ] **Step 3: Move symbol SQL into SymbolsRepository**

Use methods with domain-oriented names:

```python
replace_for_file(file_id, symbols)
matching_terms(terms, limit=1000)
by_id(object_id)
named(name)
for_file(file_id)
all()
```

Copy SQL and row ordering verbatim. `Store.replace_symbols_for_file` delegates to `.replace_for_file`; the other legacy methods delegate likewise. Preserve the current no-commit behavior.

- [ ] **Step 4: Verify GREEN**

Run the focused repository tests, symbol/search tests, source-mutation/recovery characterization, and full suite. Verify `PRAGMA user_version` is unchanged.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories/symbols.py habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: extract symbol persistence repository"
```

---

### Task 3: RelationsRepository

**Files:**
- Modify: `habitat/repositories/relations.py`
- Modify: `habitat/storage.py`
- Modify: `tests/test_store_repositories.py`

**Migrated Store interfaces:**

```python
replace_relations(relations: Iterable[RelationRecord]) -> None
sync_relations(relations: Iterable[RelationRecord]) -> dict
relations_for(object_id: str)
incoming_relations(object_id: str, kind: str | None = None)
```

- [ ] **Step 1: Write RED relation routing/equivalence tests**

Seed relation rows with distinct `kind`, `trust`, and `evidence`. Assert legacy reads and repository reads return equivalent row tuples and ordering. Patch repository methods and assert Store routes exactly once.

For `sync_relations`, characterize the exact count dictionary keys and values: `inserted`, `updated`, `deleted`, `unchanged`, `total`.

Add nested atomic rollback evidence: replace/sync relation changes inside `Store.atomic()`, raise a sentinel exception, and assert the pre-transaction relation graph is restored.

- [ ] **Step 2: Run RED**

Expected: Store methods bypass `RelationsRepository`.

- [ ] **Step 3: Move relation SQL into RelationsRepository**

Repository methods:

```python
replace(relations)
sync(relations) -> dict
for_object(object_id)
incoming(object_id, kind=None)
```

Copy SQL and set-diff semantics verbatim. Do not add commits to `replace` or `sync`.

- [ ] **Step 4: Verify GREEN**

Run focused relation/repository tests plus full suite and recovery evidence.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories/relations.py habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: extract relation persistence repository"
```

---

### Task 4: RuntimeRepository

**Files:**
- Modify: `habitat/repositories/runtime.py`
- Modify: `habitat/storage.py`
- Modify: `tests/test_store_repositories.py`

**Migrated Store interfaces:**

```python
append_runtime_event(value: dict) -> None
runtime_event(event_id: str)
runtime_events(*, trace_id: str | None = None, agent_id: str | None = None, limit: int = 500)
```

**Boundary:** `events`, `activity_events`, `trace_sessions`, and `trace_calls` remain on `Store` in this slice. They are existing observability/protocol bookkeeping surfaces with separate semantics; moving them is not required to establish the approved `runtime_events` repository seam.

- [ ] **Step 1: Write RED routing, filtering, and commit-parity tests**

Patch `RuntimeRepository` methods and assert legacy methods route exactly once. Seed events for two traces and two agents; compare repository and Store filtering/order.

Characterize explicit commit behavior by inserting through `append_runtime_event` outside `Store.atomic()`, opening a second SQLite connection to the same temporary database, and asserting the row is visible without calling `store.commit()`.

Then prove transaction suppression remains intact by calling `append_runtime_event` inside `Store.atomic()`, raising a sentinel exception, and asserting the row is absent afterward.

- [ ] **Step 2: Run RED**

Expected: Store runtime methods bypass repository.

- [ ] **Step 3: Move `runtime_events` SQL into RuntimeRepository**

Repository methods:

```python
append(value)
by_id(event_id)
list(*, trace_id=None, agent_id=None, limit=500)
```

Preserve JSON serialization defaults, ordering by `started_at DESC`, and `owner.conn.commit()` in `append`.

- [ ] **Step 4: Verify GREEN**

Run focused repository/runtime tests and the full suite.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories/runtime.py habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: extract runtime event repository"
```

---

### Task 5: EvidenceRepository

**Files:**
- Modify: `habitat/repositories/evidence.py`
- Modify: `habitat/storage.py`
- Modify: `tests/test_store_repositories.py`

**Migrated Store interfaces:**

```python
append_evidence(value: dict) -> None
evidence_by_id(evidence_id: str)
active_evidence(kind: str | None = None, limit: int = 500)
active_evidence_ids(*, kind: str | None = None, paths: list[str] | None = None, object_ids: list[str] | None = None, source: str | None = None) -> list[str]
resolve_evidence(*, kind: str | None = None, paths: list[str] | None = None, object_ids: list[str] | None = None, source: str | None = None) -> int
evidence_by_ids(ids: list[str])
```

**Boundary:** Generic search indexing remains Store-owned. `EvidenceRepository.append()` calls `owner.delete_search()` / `owner.index_search()` exactly as the legacy method does.

- [ ] **Step 1: Write RED routing, selector, search-side-effect, and atomic tests**

Cover selectors independently and combined: `kind`, `paths`, `object_ids`, `source`. Verify empty ID input returns `[]`. Verify `resolve_evidence` returns exact affected-row count and does not commit implicitly by rolling it back inside `Store.atomic()`.

For `append_evidence`, verify the evidence row and search document are both created before explicit Store commit in the same connection, and both roll back together when enclosed by `Store.atomic()` and a sentinel exception.

- [ ] **Step 2: Run RED**

Expected: Store methods bypass repository.

- [ ] **Step 3: Move evidence SQL into EvidenceRepository**

Repository methods:

```python
append(value)
by_id(evidence_id)
active(kind=None, limit=500)
active_ids(*, kind=None, paths=None, object_ids=None, source=None)
resolve(*, kind=None, paths=None, object_ids=None, source=None)
by_ids(ids)
```

Copy selector construction, ordering, JSON encoding, default trust/source/severity, and no-commit semantics verbatim.

- [ ] **Step 4: Verify GREEN**

Run focused evidence/repository tests, Truth/Evidence tests, recovery evidence, and full suite.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories/evidence.py habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: extract evidence persistence repository"
```

---

### Task 6: ExperimentationRepository

**Files:**
- Modify: `habitat/repositories/experimentation.py`
- Modify: `habitat/storage.py`
- Modify: `tests/test_store_repositories.py`

**Migrated Store interfaces:**

```python
create_hypothesis(value: dict) -> None
hypothesis(hypothesis_id: str)
hypotheses(episode_id: str | None = None, status: str | None = None, limit: int = 100)
update_hypothesis(hypothesis_id: str, *, status: str | None = None, confidence: float | None = None, updated_at: str) -> None
link_hypothesis_evidence(hypothesis_id: str, evidence_id: str | None, polarity: str, weight: float, note: str | None, revision: str, created_at: str) -> int
hypothesis_evidence(hypothesis_id: str)
hypothesis_evidence_rows(hypothesis_id: str)
create_experiment(value: dict) -> None
experiment(experiment_id: str)
experiments_for_hypothesis(hypothesis_id: str, limit: int = 100)
complete_experiment(experiment_id: str, status: str, result: dict, completed_at: str) -> None
```

**Boundary:** `work_episodes`, `episode_links`, `context_faults`, and `causal_edges` remain Store-owned orchestration/provenance persistence in this bounded extraction. The repository owns only hypotheses, their evidence links, and experiments.

- [ ] **Step 1: Write RED routing, exception, serialization, and atomic tests**

Characterize:
- default hypothesis status/confidence;
- hypothesis query filtering/order;
- `KeyError` for missing hypothesis updates/linking;
- exact float conversion for confidence/weight;
- JSON round-trip for experiment expected/result payloads;
- `KeyError` for completing a missing experiment.

Outside `Store.atomic()`, verify explicit commits make writes visible to a second SQLite connection. Inside `Store.atomic()`, call a committing experiment/hypothesis method then raise a sentinel exception; verify rollback removes the write.

- [ ] **Step 2: Run RED**

Expected: compatibility methods still own inline SQL.

- [ ] **Step 3: Move experimentation SQL into ExperimentationRepository**

Use focused methods mirroring the compatibility surface. `hypothesis_evidence` and `hypothesis_evidence_rows` may both delegate to one repository read because their current SQL and ordering are equivalent, but both Store methods remain callable.

Preserve every existing `owner.conn.commit()` call in write methods.

- [ ] **Step 4: Verify GREEN**

Run focused cognition/experimentation/repository tests, full regression, and DB recovery tests.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories/experimentation.py habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: extract experimentation repository"
```

---

### Task 7: LearningRepository

**Files:**
- Modify: `habitat/repositories/learning.py`
- Modify: `habitat/storage.py`
- Modify: `tests/test_store_repositories.py`

**Migrated Store interfaces:**

```python
record_context_feedback(handle: str, object_id: str, verdict: str, weight: float, task_terms: list[str], revision: str, created_at: str) -> int
context_utility_for(object_id: str, terms: list[str]) -> dict
context_feedback_for_handle(handle: str, limit: int = 500)
create_epistemic_item(value: dict) -> None
epistemic_item(item_id: str)
epistemic_items(*, kind: str | None = None, status: str | None = None, agent_id: str | None = None, limit: int = 200)
update_epistemic_item(item_id: str, *, status: str | None = None, confidence: float | None = None, updated_at: str, provenance: dict | None = None) -> None
create_project_memory(value: dict) -> None
project_memory(memory_id: str)
find_active_memory(kind: str, statement: str, agent_id: str | None, base_revision: str)
project_memories(*, kind: str | None = None, status: str | None = "active", agent_id: str | None = None, limit: int = 200)
update_project_memory(memory_id: str, *, status: str | None = None, confidence: float | None = None, invalidated_by: str | None = None, updated_at: str)
```

**Boundary:** Agent-private learning tables (`agent_context_utility`, `agent_hypothesis_beliefs`) remain with the existing agent-coordination Store surface in this slice. Slice B establishes the workspace-level LearningRepository without absorbing the separate concurrency/isolation subsystem.

- [ ] **Step 1: Write RED validation, weighting, filtering, serialization, and commit tests**

Characterize `record_context_feedback`:
- only `used` / `unhelpful` accepted;
- task terms are deduplicated/sorted;
- utility decay/update equation remains unchanged;
- returned sequence is preserved.

Characterize epistemic/project-memory defaults, filters, `agent_id IS NULL` visibility rules, JSON serialization, and missing-ID `KeyError` behavior.

Use a second SQLite connection to prove the currently committing write methods still commit outside `Store.atomic()`. Use sentinel rollback inside `Store.atomic()` to prove those same commits remain suppressed by `_TransactionAwareConnection` and rollback atomically.

- [ ] **Step 2: Run RED**

Expected: Store methods bypass LearningRepository.

- [ ] **Step 3: Move learning SQL into LearningRepository**

Use repository methods with the same argument semantics. Preserve `json.dumps` options (`sort_keys`, `ensure_ascii`) exactly per existing method; do not normalize them across tables. Preserve current ordering and default status values. Preserve explicit commits only where they already exist.

- [ ] **Step 4: Verify GREEN**

Run focused context-learning/memory/epistemic/repository tests, full regression, and DB recovery evidence.

- [ ] **Step 5: Commit**

```bash
git add habitat/repositories/learning.py habitat/storage.py tests/test_store_repositories.py
git commit -m "refactor: extract learning persistence repository"
```

---

### Task 8: Slice B compatibility, schema, transaction, recovery, and boundary certification

**Files:**
- Modify only `tests/test_store_repositories.py` if a missing characterization is discovered.

- [ ] **Step 1: Run focused repository contract suite**

Run:

```bash
python -m unittest tests.test_store_repositories -v
```

Require all repository ownership, routing, row-equivalence, commit-parity, and rollback tests to pass.

- [ ] **Step 2: Prove schema identity**

In a fresh temporary Store and an existing fixture workspace, record:

```sql
PRAGMA user_version;
SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name;
```

Compare behavior against pre-Slice-B expectations used by existing schema/recovery tests. Slice B must not add/drop/alter a table, index, column, pragma policy, or migration version.

- [ ] **Step 3: Run full local/CI-equivalent regression**

Run full `unittest` discovery. Pay special attention to database recovery, source-mutation recovery, protocol conformance, fault injection, persisted-workspace reopening, and nested atomic rollback tests.

- [ ] **Step 4: Audit changed filenames**

Allowed production paths are only:

- `habitat/repositories/__init__.py`
- `habitat/repositories/symbols.py`
- `habitat/repositories/relations.py`
- `habitat/repositories/runtime.py`
- `habitat/repositories/evidence.py`
- `habitat/repositories/experimentation.py`
- `habitat/repositories/learning.py`
- `habitat/storage.py`

Allowed supporting paths are this plan and repository tests. Reject the candidate if `_workspace_core.py`, workspace services, storage migrations, database health, protocol/MCP, workflows, or unrelated domains changed.

- [ ] **Step 5: Exact-head GitHub certification**

Require on the same final SHA:
- Habitat CI success on Ubuntu/Windows × Python 3.10/3.14;
- full regression;
- public compatibility contract;
- protocol conformance;
- database recovery;
- source-mutation recovery;
- fault injection;
- independent reproducibility builds;
- distributable artifact verification;
- Semgrep policy;
- Habitat CodeQL success.

- [ ] **Step 6: Final PR audit**

Require:
- zero unresolved review threads;
- no unexpected submitted review requesting changes;
- PR head unchanged from certified SHA;
- `main` unchanged from the expected Slice A merge base, or explicitly re-audit/rebase if drift occurred;
- mergeable true.

- [ ] **Step 7: Merge with expected-head guard and verify main**

Merge only the certified SHA. Verify `main` points to the resulting merge commit and that the merge has the Slice A merge commit in ancestry.

- [ ] **Step 8: Begin Slice C only from verified new main**

Create the Operation Registry branch only after Slice B is merged and main is re-read from GitHub.

---

## Self-Review Against the Approved Design

### Spec coverage

- Six required repositories are present as six explicit tasks.
- Store retains connection/schema/migration/recovery/atomic/doctor ownership.
- Legacy Store APIs remain as compatibility delegates.
- No repository creates/closes a connection or changes PRAGMAs/schema.
- Commit semantics are characterized both outside and inside `Store.atomic()`.
- Existing persisted workspace compatibility and recovery are final certification gates.
- No protocol, MCP, source-authority, semantic-admission, compiler-selection, or Wave 4 work is included.

### Deliberate bounded exclusions

The following remain on `Store` because they are not one of the six approved domain seams or would broaden Slice B into adjacent subsystems:
- files and diagnostics;
- occurrences;
- generic FTS/search and compile cache;
- Merkle/project cache/residency;
- trace sessions/calls and generic activity/events;
- work episodes/context faults/causal edges;
- agent isolation/concurrency/approvals/residency;
- executive trajectories/milestones/events;
- effect/dataflow/counterfactual persistence;
- revisions and generic JSON tables.

These exclusions are not deferred implementation promises; they are explicit scope boundaries for this structural slice.

### Placeholder scan

This plan contains no TODO/TBD/"similar to" implementation gaps. Every migrated Store method is named, every repository boundary is explicit, and every task includes RED, GREEN, verification, and commit steps.
