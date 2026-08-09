# Nolane Habitat — Master Implementation Plan

> **Execution rule:** Work task-by-task. Every checked implementation task must have executable evidence. Every precision upgrade must preserve source authority, trust grades and rollback. Do not promote a heuristic into an exact semantic claim because it performs well on examples.

**Goal:** Build a project cognition substrate where an agent works through semantic objects/actions/state rather than repeatedly reconstructing project meaning from file trees, terminal presentation and screenshots.

**Architecture:** Canonical normal source tree + rebuildable semantic twin + task Context Compiler + typed agent protocol + transactional source mutation + capability-bound execution + semantic UI surface + verification receipts.

**Current delivery:** `0.1.0-alpha.1`, adding incremental compile reuse, Context Compiler V2, semantic mutation, structured test evidence, runtime browser semantics and resumable task state.

## Global gates

- [x] Source files remain canonical.
- [x] No project code execution during indexing.
- [x] Semantic objects carry trust grades/source anchors where available.
- [x] Agent protocol has no generic shell method.
- [x] Mutation reconciles external source before commit.
- [x] Index truncation is explicit.
- [x] Search index avoids a second full source copy on supported SQLite.
- [ ] Hardened process isolation exists before untrusted automated execution is called safe.
- [ ] Same-model benchmark exists before token-efficiency claims.
- [ ] Runtime UI + visual oracle exists before broad UI-understanding claims.

---

## Task 1 — Freeze charter and contradiction set

**Files**
- `docs/control/CHARTER.md`
- `docs/control/CAPABILITY-DIAGNOSIS.md`
- `docs/control/UNKNOWN-UNKNOWNS.md`

**Postconditions**
- [x] Objective and non-goals are separable.
- [x] Source authority is explicit.
- [x] “AI-native” is defined by typed state/action rather than LLM-callability.
- [x] Stop/redesign conditions are stated.

**Verifier**
- Documentation self-audit; no claim of AGI, token savings, complete UI understanding or sandboxing.

---

## Task 2 — Source Bridge foundation

**Files**
- `habitat/source_bridge.py`
- `tests/test_source_bridge.py`

**Interfaces**
- `prepare_source(source, habitat_dir)`
- `safe_extract_zip(zip, destination, limits)`
- `snapshot_metadata(root)`
- `atomic_write(path, bytes)`

**Work**
- [x] linked folder mode.
- [x] managed ZIP mode.
- [x] managed loose-file code path.
- [x] path traversal rejection.
- [x] archive symlink rejection.
- [x] special-file rejection.
- [x] uncompressed-size/file-count/compression-ratio limits.
- [x] atomic replace primitive.
- [x] dedicated loose-file regression test.
- [ ] Windows ACL/readonly test matrix.
- [ ] hard-link policy.

**Exit evidence**
- Source Bridge adversarial tests green.

---

## Task 3 — Persistent revision model

**Files**
- `habitat/model.py`
- `habitat/storage.py`
- `habitat/workspace.py`

**Interfaces**
- `Revision`
- `workspace.refresh(reason)`
- `workspace.reconcile()`

**Work**
- [x] file SHA-256 digest.
- [x] deterministic root-content digest.
- [x] parent revision link.
- [x] changed-path list.
- [x] metadata fast reconciliation on normal agent access.
- [x] per-file compile cache; deep refresh reparses only changed digests.
- [ ] inter-process source lease.
- [ ] Merkle subtree digests for huge repositories.
- [ ] persistent watcher event journal.

**Failure probes**
- [x] external edit before next query.
- [x] external edit after transaction stage.
- [ ] same-size + restored-mtime content mutation.

---

## Task 4 — Storage that does not clone the project

**Files**
- `habitat/storage.py`
- `tests/test_storage.py`

**Work**
- [x] SQLite metadata/object store.
- [x] relation indexes.
- [x] FTS5 lexical lane.
- [x] contentless FTS when supported.
- [x] exact source remains outside DB.
- [x] search metadata maps rowid -> semantic object.
- [ ] schema migration runner.
- [ ] DB corruption/rebuild command.
- [ ] storage-overhead benchmark across representative repos.

**Postcondition**
- The database can be deleted and rebuilt without losing project source.

---

## Task 5 — Syntax Compiler alpha

**Files**
- `habitat/compiler.py`
- `tests/test_compiler.py`
- `tests/test_large_file_coverage.py`

**Work**
- [x] Python AST classes/functions/methods/docstrings/call-name edges.
- [x] conservative JS/TS function/class extraction.
- [x] conservative Java class/method extraction.
- [x] HTML id objects.
- [x] trust grades.
- [x] large-file parse/index coverage state.
- [ ] Tree-sitter provider interface.
- [ ] Tree-sitter Python/JS/TS/Java/HTML/CSS adapters.
- [ ] incremental tree edits.
- [ ] syntax diagnostic object table.

**Invariant**
- JS/TS/Java alpha extraction remains `heuristic` until a precise provider supplies stronger evidence.

---

## Task 6 — Semantic Compiler precision lane

**Planned files**
- `habitat/semantic/base.py`
- `habitat/semantic/lsp.py`
- `habitat/semantic/python.py`
- `habitat/semantic/typescript.py`
- `habitat/semantic/java.py`
- `tests/test_semantic_*`

**Work**
- [x] generic semantic provider/result contract; definition/reference/type precision remains future LSP work.
- [ ] capability probe for language servers.
- [ ] Python LSP adapter.
- [x] TypeScript compiler-API parser/diagnostic adapter (syntax precision only; LSP/type-checker references remain future work).
- [ ] Java LSP adapter.
- [ ] optional SCIP import.
- [ ] provenance grade per relation edge.
- [ ] timeout/crash isolation.

**Exit postcondition**
A symbol inspection can distinguish exact references supplied by a semantic provider from heuristic edges.

---

## Task 7 — Context Compiler V1

**Files**
- current alpha: `habitat/workspace.py`
- planned: split into `habitat/context/*`

**Work**
- [x] bounded object budget.
- [x] lexical candidate lane.
- [x] deterministic fuzzy identifier lane.
- [x] code-vs-UI task intent bias.
- [x] bounded one-hop graph expansion.
- [x] uncertainty for heuristic/coverage loss.
- [x] regression: `validate_credentials` ranks before `login-form` for implementation task.
- [x] separate task-class model.
- [x] test + diagnostic candidate lanes; history lane remains pending.
- [x] diversity caps by path/object class.
- [x] context paging handles with revision-stale detection.
- [x] bounded two-hop partial dependency graph expansion.
- [ ] optional embeddings lane + ablation.
- [ ] missed-dependency benchmark.

**Verifier**
Compare first-correct-location rate and irrelevant bytes/tokens against plain file search.

---

## Task 8 — Exact source inspection

**Files**
- `habitat/workspace.py`

**Work**
- [x] semantic object inspection.
- [x] source anchor path/start/end/digest/revision.
- [x] symbol-body source range.
- [x] relation visibility.
- [x] range paging for text source.
- [ ] raw-byte handle for non-UTF8 source.
- [ ] source-anchor re-resolution after symbol move/rename.

---

## Task 9 — Agent Protocol V1 alpha

**Files**
- `habitat/protocol.py`
- `habitat/server.py`
- `docs/AGENT-PROTOCOL.md`
- `tests/test_protocol.py`

**Methods**
- [x] `workspace.enter`
- [x] `workspace.refresh`
- [x] `workspace.orient`
- [x] `workspace.query`
- [x] `workspace.inspect`
- [x] `workspace.change.stage`
- [x] `workspace.change.commit`
- [x] `workspace.change.rollback`
- [x] `action.run`
- [x] `ui.observe`
- [x] typed success/error envelope.
- [x] NDJSON stdio transport.
- [x] unknown `shell.exec` rejected.
- [x] protocol capability negotiation.
- [ ] HTTP transport.
- [ ] MCP adapter.
- [ ] A2A adapter if useful; never core dependency.

---

## Task 10 — Transactional Mutation V1 alpha

**Files**
- `habitat/mutation.py`
- `tests/test_workspace.py`

**Work**
- [x] stage transaction.
- [x] base revision binding.
- [x] optional exact digest precondition.
- [x] unique-match text replacement.
- [x] atomic canonical-source write.
- [x] backup.
- [x] commit.
- [x] automatic rollback on partial failure.
- [x] explicit rollback if no newer source work.
- [x] stale external edit fails commit.
- [ ] AST/symbol-body patch.
- [x] multi-file mutation preflight before first canonical write.
- [x] post-commit semantic symbol-ID diff.
- [ ] formatter integration as typed post-action.
- [ ] merge/rebase conflict strategy.

---

## Task 11 — Execution Capability Catalog

**Files**
- `habitat/execution.py`
- `tests/test_capabilities.py`

**Work**
- [x] Python unittest discovery.
- [x] pytest availability probe.
- [x] npm script manifest discovery.
- [x] Maven/Gradle discovery.
- [x] availability + reason instead of fake capability.
- [ ] project-runtime environment resolver.
- [ ] per-capability authority policy.
- [x] toolchain version fingerprint.
- [ ] service/start/stop capability objects.

---

## Task 12 — Structured Execution Provider

**Files**
- `habitat/execution.py`
- `tests/test_execution.py`

**Work**
- [x] program+args, `shell=False`.
- [x] cwd bound to source root.
- [x] timeout.
- [x] bounded stdout/stderr.
- [x] exit code.
- [x] changed-path readback.
- [x] run receipt persistence.
- [ ] sandbox provider contract.
- [ ] network/filesystem policy.
- [x] POSIX process-group termination on timeout; full cross-platform parity remains pending.
- [ ] resource quotas.
- [x] structured test-output normalization; build normalization remains pending.

**Important:** Local provider is not a sandbox.

---

## Task 13 — Test Intelligence

**Planned files**
- `habitat/tests_intelligence/*`

**Work**
- [x] pytest structured summary adapter (stdout parser; JSON plugin not required).
- [x] unittest parser.
- [x] Jest/Vitest summary adapter.
- [ ] Maven/Gradle/JUnit adapter.
- [ ] test object identity.
- [x] source->test structural relation from test-like imports.
- [ ] affected-test selection.
- [ ] failure history and flaky-state tracking.
- [ ] minimal justified verification set.

---

## Task 14 — UI Semantic Surface alpha

**Files**
- `habitat/ui_semantic.py`
- `tests/test_workspace.py`

**Work**
- [x] static HTML parser.
- [x] role inference.
- [x] name/attributes/text.
- [x] stable per-file element handles.
- [x] explicit limitation list.
- [ ] CSS rule/style relation layer.
- [ ] form labels via `for` and accessible-name algorithm.
- [x] post-commit semantic symbol-ID diff.

---

## Task 15 — Runtime Web UI Surface

**Planned files**
- `habitat/ui/browser_provider.py`
- `habitat/ui/dom_projection.py`
- `habitat/ui/actions.py`
- `habitat/ui/layout.py`

**Work**
- [x] headless Chromium provider with system-browser capability probe.
- [x] ARIA snapshot.
- [x] runtime DOM semantic projection.
- [x] layout rectangles/visibility/enabled state.
- [x] console/network resource events.
- [x] runtime semantic handles stable within browser session where possible.
- [x] click/fill/select/check/press by semantic handle.
- [x] optional screenshot as secondary oracle.
- [x] overflow + viewport-clipping detectors; overlap detector remains future work.
- [ ] visual regression path.

---

## Task 16 — UI-to-source graph

**Work**
- [ ] route -> page/component relation.
- [x] DOM ID -> HTML source hint; framework component ownership remains future work.
- [x] CSS selector candidate -> source anchor (heuristic).
- [ ] source-map integration.
- [ ] UI failure -> candidate source slice.
- [ ] patch -> rerender -> semantic+visual diff verification loop.

---

## Task 17 — Persistent living state

**Work**
- [x] persistent task session/checkpoint object.
- [x] active task + revision; charter digest remains pending.
- [x] resident semantic object set; warm/cold tiers remain pending.
- [ ] active transaction/run/service/UI surface.
- [x] checkpoint and resume.
- [x] stale/missing resident-object detection; automatic re-resolution remains pending.
- [x] digest-based resident-object invalidation predicate.

**Exit postcondition**
A new agent process resumes a prior task without repeating repository discovery unless the source revision invalidates the saved context.

---

## Task 18 — Benchmark harness

**Current**
- [x] byte/latency plumbing seed.
- [x] stress run on supplied AGI ZIP.
- [ ] LLM/token-aware harness.

**Baselines**
- [ ] file/list/grep/read/shell baseline.
- [ ] repo-map baseline.
- [ ] semantic-symbol baseline.
- [ ] Habitat full stack.

**Controls**
- [ ] same model.
- [ ] same source revision.
- [ ] same task.
- [ ] same token/cost budget.
- [ ] repeated trials.
- [ ] cold and warm indexing costs reported separately.

**Metrics**
- task success;
- first-correct-location;
- navigation calls;
- whole-file reads;
- model input/source/irrelevant tokens;
- latency/cost;
- stale-context errors;
- regressions;
- UI success;
- resume overhead.

---

## Task 19 — Hardening

- [x] ZIP traversal/symlink/size controls.
- [x] source prose treated as indexed data, not instructions.
- [ ] watcher races.
- [ ] multi-process leases.
- [ ] DB crash recovery.
- [ ] malicious language-server output.
- [ ] malicious compiler/build output.
- [ ] sandbox escape testing.
- [ ] huge monorepo stress corpus.
- [ ] Unicode/path edge cases on Windows/macOS/Linux source files (without expanding product scope to desktop automation).

---

## Task 20 — V1 packaging and external adapters

- [ ] stable schema migration policy.
- [ ] Python SDK.
- [ ] TypeScript SDK.
- [ ] MCP adapter.
- [ ] human inspector GUI only after core metrics justify it.
- [ ] export/rebuild tooling.
- [ ] benchmark report.
- [ ] complete threat model.
- [ ] deterministic full-source delivery archive.

## Promotion rule

Do not advance a version because the file count increased. Promote only when a defined postcondition gains new executable evidence and protected invariants remain green.
