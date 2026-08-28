# Wave 3 Workspace Service Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish stable `IndexService`, `QueryService`, `TransactionService`, and `RuntimeService` seams behind the existing `HabitatWorkspace` public API without changing observable behavior.

**Architecture:** `HabitatWorkspace` remains the public compatibility object. It lazily owns four focused service objects; public methods delegate into them. Services call the pre-decomposition `_CoreHabitatWorkspace` implementation explicitly, preventing recursive wrapper calls and avoiding a physical `_workspace_core.py` rewrite in this slice.

**Tech Stack:** Python 3.10+, stdlib `dataclasses`/typing, `unittest`, existing Habitat GitHub Actions matrix.

**Spec:** `docs/superpowers/specs/2026-08-28-core-decomposition-design.md`

## Global Constraints

- No SQLite schema or migration changes.
- No `_workspace_core.py` edits in this slice.
- No protocol/MCP method or response changes.
- No source-authority, Truth/Evidence, semantic admission, compiler selection, workflow, or recovery changes.
- Service construction performs no source/runtime work.
- Existing public method signatures and exceptions remain stable.
- Every production change follows a RED test-only commit/run first.

---

## File map

Create:

- `habitat/services/__init__.py` — public internal exports for four services.
- `habitat/services/index.py` — refresh/reconcile delegation.
- `habitat/services/query.py` — read/query delegation.
- `habitat/services/transaction.py` — mutation delegation plus existing categorical symbol-anchor authority guard.
- `habitat/services/runtime.py` — runtime evidence/timeline/topology delegation.
- `tests/test_workspace_services.py` — service lifetime, routing, recursion, and side-effect boundaries.

Modify:

- `habitat/workspace.py` — lazy service accessors and public compatibility wrappers; move current `stage_change` authority guard into `TransactionService`.

Must not modify:

- `habitat/_workspace_core.py`
- `habitat/storage.py`
- `habitat/protocol.py`
- `habitat/mcp_adapter.py`
- `.github/workflows/*`

---

### Task 1: Lazy service ownership

**Files:**
- Create: `tests/test_workspace_services.py`
- Create: `habitat/services/__init__.py`
- Create: `habitat/services/index.py`
- Create: `habitat/services/query.py`
- Create: `habitat/services/transaction.py`
- Create: `habitat/services/runtime.py`
- Modify: `habitat/workspace.py`

**Interfaces:**
- Produces: `HabitatWorkspace._indexing() -> IndexService`
- Produces: `HabitatWorkspace._queries() -> QueryService`
- Produces: `HabitatWorkspace._transactions() -> TransactionService`
- Produces: `HabitatWorkspace._runtime() -> RuntimeService`

- [ ] **Step 1: Write RED tests for lazy construction**

Create a workspace fixture, close it, then reopen with `HabitatWorkspace(habitat_dir)` so no initial refresh creates services. Assert service private attributes are absent or `None`, then call each accessor twice and assert object identity is stable. Patch service constructors and assert constructing/accessing services does not invoke `refresh`, `reconcile`, semantic comparison, LSP, or SCIP activation.

Representative contract:

```python
ws = HabitatWorkspace(habitat_dir)
self.assertIs(ws._indexing(), ws._indexing())
self.assertIs(ws._queries(), ws._queries())
self.assertIs(ws._transactions(), ws._transactions())
self.assertIs(ws._runtime(), ws._runtime())
self.assertIsNone(getattr(ws, "_lsp_runtime_manager", None))
self.assertIsNone(getattr(ws, "_scip_runtime_manager", None))
```

- [ ] **Step 2: Run full regression on test-only head**

Expected new failures: missing `habitat.services` and/or missing workspace accessors. Existing tests must not introduce unrelated failures.

- [ ] **Step 3: Implement minimal lazy services**

Each service is a small class holding `workspace`. It performs no work in `__init__`. Add workspace accessors using `getattr` so `_CoreHabitatWorkspace.__init__` need not change:

```python
def _indexing(self) -> IndexService:
    service = getattr(self, "_index_service", None)
    if service is None:
        service = IndexService(self)
        self._index_service = service
    return service
```

Repeat for query/transaction/runtime.

- [ ] **Step 4: Run focused tests and full regression**

Expected: new service-lifetime tests pass with no legacy regression.

- [ ] **Step 5: Commit**

Commit message: `refactor: add lazy workspace service seams`

---

### Task 2: IndexService delegation

**Files:**
- Modify: `tests/test_workspace_services.py`
- Modify: `habitat/services/index.py`
- Modify: `habitat/workspace.py`

**Interfaces:**
- `IndexService.refresh(reason: str = "refresh") -> dict`
- `IndexService.refresh_paths(paths: list[str], reason: str = "targeted-refresh") -> dict`
- `IndexService.reconcile() -> dict`
- Public `HabitatWorkspace.refresh`, `refresh_paths`, `reconcile` retain exact legacy signatures.

- [ ] **Step 1: Write RED routing tests**

Patch `IndexService.refresh`, `refresh_paths`, and `reconcile` to return sentinels. Call the public workspace methods and assert each service method is called exactly once with exact arguments.

Also patch `_CoreHabitatWorkspace.refresh` and call `ws._indexing().refresh("x")`; assert the core implementation is called with the workspace and reason exactly once. This catches accidental `workspace.refresh()` recursion inside the service.

- [ ] **Step 2: Run test-only RED head**

Expected failures: current public methods still resolve directly to `_CoreHabitatWorkspace`, so patched service methods are not called.

- [ ] **Step 3: Implement routing**

`IndexService` invokes `_CoreHabitatWorkspace.refresh(self.workspace, ...)`, `refresh_paths(...)`, and `reconcile(...)`. Add thin public wrappers in `habitat/workspace.py` delegating to `_indexing()`.

- [ ] **Step 4: Verify GREEN**

Run focused tests plus full regression. Existing source mutation/recovery tests must remain green because the decorated core refresh methods still execute unchanged.

- [ ] **Step 5: Commit**

Commit message: `refactor: route workspace indexing through IndexService`

---

### Task 3: QueryService delegation

**Files:**
- Modify: `tests/test_workspace_services.py`
- Modify: `habitat/services/query.py`
- Modify: `habitat/workspace.py`

**Interfaces:**
- `query(query: str, limit: int = 20) -> list[dict]`
- `inspect_snapshot(object_id: str, include_source: str = "none") -> dict`
- `inspect_many(object_ids: list[str], include_source: str = "none", max_objects: int = 50) -> dict`
- `references_snapshot(object_id: str, limit: int = 200) -> dict`
- `read_source(path: str, start_line: int = 1, max_lines: int = 200) -> dict`

- [ ] **Step 1: Write RED routing/recursion tests**

For each public method, patch the corresponding `QueryService` method to return a distinct sentinel and assert public routing is exact. Separately patch `_CoreHabitatWorkspace.<method>` and call the service directly to prove it calls the core implementation rather than the public wrapper.

- [ ] **Step 2: Run test-only RED head**

Expected: public methods bypass QueryService.

- [ ] **Step 3: Implement QueryService and wrappers**

Use explicit `_CoreHabitatWorkspace.<method>(self.workspace, ...)` calls. Do not add reconcile calls in the service; methods that historically reconcile already do so inside their core implementation.

- [ ] **Step 4: Verify GREEN**

Run focused tests and full suite. Protocol read-only/activity conformance must remain green.

- [ ] **Step 5: Commit**

Commit message: `refactor: route workspace queries through QueryService`

---

### Task 4: TransactionService delegation and authority guard migration

**Files:**
- Modify: `tests/test_workspace_services.py`
- Modify: `habitat/services/transaction.py`
- Modify: `habitat/workspace.py`
- Existing characterization: `tests/test_truth_mutation_authority.py`

**Interfaces:**
- `change_plan(operations: list[dict]) -> dict`
- `stage_change(operations, episode_id=None, agent_id=None, lease_ttl_s=120.0, approval_id=None) -> dict`
- `stage_symbol_change(symbol_id, new_source, episode_id=None, agent_id=None) -> dict`
- `stage_symbol_rename(symbol_id, new_name, episode_id=None, agent_id=None) -> dict`
- `commit_change(txid, agent_id=None) -> dict`
- `rollback_change(txid, agent_id=None) -> dict`

- [ ] **Step 1: Write RED service-enforcement tests**

Patch `TransactionService.stage_change` and assert public `ws.stage_change()` routes to it exactly once. Patch `habitat.services.transaction.operation_allows_evidence` false for an exact symbol anchor and assert the service raises the same `TransactionConflict` boundary used today. Patch it true for semantic trust and assert execution is delegated into the existing core transaction checks.

- [ ] **Step 2: Run RED**

Expected: public `stage_change` still owns authority logic and does not route through TransactionService.

- [ ] **Step 3: Move authority decision into TransactionService**

Move, without semantic changes, the existing categorical `replace_symbol_source` loop from `habitat/workspace.py` into `TransactionService.stage_change`; then call `_CoreHabitatWorkspace.stage_change(...)`.

Route the other transaction public methods through the service. For `stage_symbol_change`/`stage_symbol_rename`, invoke the matching core method explicitly and rely on its existing calls/validation. Avoid copying mutation engine logic.

- [ ] **Step 4: Verify GREEN**

Run:

- new workspace-service tests;
- `tests/test_truth_mutation_authority.py`;
- source-mutation recovery tests;
- full suite.

Exact exception messages and staged transaction shapes must remain unchanged.

- [ ] **Step 5: Commit**

Commit message: `refactor: route workspace mutations through TransactionService`

---

### Task 5: RuntimeService delegation

**Files:**
- Modify: `tests/test_workspace_services.py`
- Modify: `habitat/services/runtime.py`
- Modify: `habitat/workspace.py`

**Interfaces:**
- Preserve exact current signatures for `runtime_ingest`, `runtime_timeline`, and `runtime_topology` as defined in `_CoreHabitatWorkspace`.

- [ ] **Step 1: Write RED routing tests**

Patch each RuntimeService method and assert the workspace method routes exactly once. Patch the matching core implementation and call service methods directly to prove explicit core delegation.

- [ ] **Step 2: Run RED**

Expected: current inherited methods bypass RuntimeService.

- [ ] **Step 3: Implement runtime routing**

Copy no runtime normalization/persistence logic. RuntimeService delegates to the existing core methods with exact keyword semantics.

- [ ] **Step 4: Verify GREEN**

Run focused runtime tests and full regression.

- [ ] **Step 5: Commit**

Commit message: `refactor: route runtime operations through RuntimeService`

---

### Task 6: Slice A compatibility and boundary certification

**Files:**
- Modify only tests if a missing characterization is discovered.

- [ ] **Step 1: Audit changed filenames**

Reject the candidate if it contains `_workspace_core.py`, storage, protocol/MCP, workflows, or recovery modules.

- [ ] **Step 2: Run exact-head Habitat CI**

Require success for Ubuntu/Windows × Python 3.10/3.14 including full regression, compatibility, protocol conformance, DB/source-mutation recovery, fault injection, reproducibility, distributable artifacts, and Semgrep.

- [ ] **Step 3: Run exact-head CodeQL**

Require success on the same head SHA.

- [ ] **Step 4: Review PR threads and head/base drift**

Require no unresolved review threads, unchanged exact head, and no unexpected base drift.

- [ ] **Step 5: Merge with expected-head guard**

Merge only the certified SHA into `main`, then verify `main` contains the merge commit.

- [ ] **Step 6: Begin Slice B from the new `main`**

Create a fresh Store Repository branch only after Slice A is merged.
