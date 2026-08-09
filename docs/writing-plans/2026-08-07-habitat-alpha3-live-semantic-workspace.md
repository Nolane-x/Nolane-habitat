# Nolane Habitat alpha.3 — Live Semantic Workspace Implementation Plan

Release target: `0.1.0-alpha.3`  
Date: 2026-08-07  
Status: implemented candidate; admission remains conditional on final artifact verification.

This plan is an executable engineering contract. It uses the Nolane AGI Cognitive System method explicitly: charter → capability diagnosis → competing beliefs → discriminating experiments → implementation → semantic proof → unknown-unknown audit → admission gate. A feature is not considered complete because code exists; it is complete only inside the bounded claim supported by a verifier.

## 1. Charter

### Goal

Move Habitat from a persistent semantic index toward a **live agent work surface**. An agent should remain inside one revision-aware semantic environment while external project files change, request task context in bounded packets, inspect exact source only when decision-relevant, and connect runtime UI state back to source candidates without returning to human-style terminal/file-tree/browser workflows.

### Protected invariants

1. Ordinary project files remain canonical source truth.
2. Habitat state remains derived and rebuildable.
3. Metadata watchers are acceleration hints, never integrity authority.
4. Consequential mutation still performs a deep content-hash preflight.
5. No provider may be silently upgraded above its evidence grade.
6. No whole-file source dump is allowed as the default context materialization behavior.
7. Generic shell remains absent from the agent protocol.
8. Benchmark numbers must disclose what they measure and what they do not measure.

### Non-goals for alpha.3

- no Windows/macOS/Linux desktop automation;
- no production hostile-code sandbox;
- no universal LSP/SCIP implementation;
- no Tree-sitter claim when bindings are absent;
- no framework-complete React/Vue/Svelte source-map proof;
- no claim that Habitat reduces LLM tokens or improves coding success without a same-model A/B run.

## 2. Capability diagnosis at entry

Alpha.2 already had per-file compiler reuse, project semantic relations, event journal, affected tests, transaction safety, runtime browser semantics and source hints. The weakest architectural points were:

- ordinary external synchronization still escalated to a deep refresh after any metadata difference;
- semantic graph persistence used full-table replacement even when the graph did not change;
- one root-wide project semantic cache invalidated unrelated provider work;
- event journal had no live observation mechanism;
- stale task context could only be rejected, not refreshed as a delta;
- `orient()` still left the agent with multiple follow-up `inspect` calls;
- framework ownership was limited mostly to HTML anchors and runtime JS listener stacks;
- benchmark evidence did not include an explicit filesystem-vs-Habitat navigation harness.

## 3. Belief state and rivals

### B1 — Targeted reconciliation can reduce ordinary refresh work safely

**Hypothesis:** metadata differences can be treated as candidate paths, with content hashing restricted to those paths during ordinary read-only synchronization.

**Rival:** metadata filtering creates a stale-state hole that can cause unsafe mutation.

**Kill criterion:** if a metadata-preserving edit can survive the mutation preflight and be overwritten, reject targeted reconciliation.

**Resolution:** retained with a strict split: ordinary reconcile is targeted; mutation stage/commit/rollback still uses deep `refresh()` over all project bytes.

### B2 — Provider-domain caches are safer and cheaper than a root-wide semantic cache

**Hypothesis:** Markdown or unrelated language edits should not rerun TypeScript whole-project semantics.

**Rival:** domain partitioning may preserve stale cross-language relations.

**Kill criterion:** a source change that can influence a provider's graph must alter that provider's domain digest or provider fingerprint.

**Resolution:** retained. Base relation domain includes semantic-bearing files; TypeScript domain includes only JS/TS files plus TypeScript provider identity. A compatibility sentinel still forces a conservative miss when provider fingerprint drifts.

### B3 — Diff synchronization is preferable to delete/reinsert graph persistence

**Hypothesis:** relation/occurrence storage can preserve unchanged rows and report exact graph mutations.

**Rival:** set-diff logic can leave stale edges or update evidence incorrectly.

**Kill criterion:** no-op refresh must produce zero inserted/updated/deleted rows, while semantic edits must remove obsolete edges and add new ones.

**Resolution:** retained through `sync_relations` and `sync_occurrences`.

### B4 — A live watcher can exist without making SQLite or compilation concurrent

**Hypothesis:** a background watcher can observe metadata and queue candidates while all source hashing/admission remains on the foreground workspace thread.

**Rival:** background mutation of semantic state introduces races and nondeterministic SQLite access.

**Kill criterion:** watcher thread must never write storage or execute project code.

**Resolution:** retained. `PollingSourceWatcher` is observation-only.

### B5 — Runtime UI can obtain framework-aware ownership hints from JSX anchors

**Hypothesis:** explicit `id`/`data-testid` literals in TSX/JSX can connect a runtime DOM element to a parser-observed component source candidate.

**Rival:** the attribute may be duplicated, rewritten or not represent the runtime owner.

**Kill criterion:** duplicate JSX anchors must never be promoted to unique ownership.

**Resolution:** retained at `parser` trust only when unique; duplicate anchors are `heuristic`. Runtime listener stacks remain independent evidence.

### B6 — Context should be refreshable and materializable, not merely stale/fresh

**Hypothesis:** a revision-bound context handle can be recompiled into a new handle with an explicit object delta, and a bounded materializer can reduce follow-up tool calls without dumping full files.

**Rival:** materialization silently hides omitted source or turns derived context into authority.

**Kill criterion:** byte budget overflow or stale context must be visible; exact source must remain labeled separately from parser/semantic metadata.

**Resolution:** retained.

## 4. Milestones and verifiers

### M1 — Provider-domain semantic cache

Files:
- `habitat/semantic/project.py`

Implementation:
- semantic project version bumped;
- base relation cache keyed by semantic-bearing file digest/provider identity;
- TypeScript whole-project cache keyed only by JS/TS domain digest + TypeScript version/availability;
- alpha.2 compatibility sentinel retained for provider-drift migration behavior.

Postconditions:
- no-op refresh hits all provider domains;
- Markdown-only edit reuses base and TypeScript semantic provider domains;
- Python-only edit reuses TypeScript domain;
- provider fingerprint drift forces a conservative top-level miss.

### M2 — Graph set-diff persistence

Files:
- `habitat/storage.py`

Implementation:
- `sync_relations()`;
- `sync_occurrences()`;
- delta receipt: inserted / updated / deleted / unchanged / total.

Verifier:
- no-op graph refresh changes zero rows;
- existing alpha.2 relation/reference tests remain green.

### M3 — Targeted reconcile

Files:
- `habitat/workspace.py`

Implementation:
- deep `refresh()` retained as integrity mode;
- `refresh_paths()` hashes only candidate files;
- ordinary `reconcile()` compares metadata and calls targeted refresh;
- compiler/provider state fingerprint forces deep refresh when tooling changes.

Verifier:
- one external file edit → one hashed file + one compiled file;
- path traversal rejected;
- metadata-preserving edit is invisible to ordinary metadata reconcile but detected by deep integrity refresh.

### M4 — Source watcher

Files:
- `habitat/watcher.py`;
- `habitat/workspace.py`;
- `habitat/protocol.py`.

Methods:
- `workspace.watch.start`;
- `workspace.watch.poll`;
- `workspace.watch.wait`;
- `workspace.watch.status`;
- `workspace.watch.stop`.

Design constraint:
- watcher thread may only scan `(path,size,mtime)` and queue observations;
- workspace foreground admits candidates and appends a `watch-observation` event.

### M5 — Context delta refresh

Files:
- `habitat/context/compiler.py`;
- `habitat/workspace.py`.

Method:
- `workspace.context.refresh`.

Output:
- old/new revision;
- new context handle;
- retained object IDs;
- added object IDs;
- removed object IDs;
- missing object IDs;
- changed source paths.

### M6 — Bounded Context Materializer

Methods:
- `workspace.context.materialize`;
- `workspace.inspect.batch`.

Rules:
- symbol body exact source may be included under a byte budget;
- file objects are metadata-only by default;
- no whole-file source dump is performed automatically;
- stale handles fail closed to a stale receipt;
- omissions are explicit.

### M7 — JSX/TSX framework ownership lane

Files:
- `habitat/semantic/typescript.py`;
- `habitat/compiler.py`;
- `habitat/workspace.py`.

Mechanism:
- parser records literal JSX `id` / `data-testid` anchors;
- component → UI-element `renders` relation;
- runtime DOM element correlates with unique JSX anchor;
- owner function/class relation added as a source hint;
- duplicate anchors remain heuristic.

### M8 — Navigation plumbing A/B harness

Files:
- `benchmarks/alpha3_navigation_benchmark.py`;
- `benchmarks/AGENT-AB-BENCHMARK-CONTRACT.md`.

The deterministic benchmark compares a disclosed full-text filesystem scan with warm Habitat orientation on a synthetic repository. It records bytes read, API/navigation operations and target presence, but explicitly cannot support LLM/token/coding-success claims.

A separate contract defines the future same-model controlled A/B admission requirements.

### M9 — Supplied AGI ZIP stress

Corpus:
- `Nolane-AGI-Cognitive-System-4.0.0(1).zip`.

Required observations:
- cold ingest succeeds;
- warm deep refresh reuses all file compiler facts;
- no-op semantic graph set-diff mutates zero graph rows;
- documentation-only edit hashes/compiles one candidate and reuses semantic provider domains;
- one Python edit hashes/compiles one candidate.

### M10 — End-to-end live demo

Sequence:

```text
folder
→ ingest
→ orient
→ semantic transaction
→ context.refresh
→ targeted verification
→ watcher documentation edit
→ runtime browser open
→ semantic UI action
→ JSX ownership hint
→ warm refresh
```

### M11 — Unknown-unknown probes

Mandatory probes:
- metadata-preserving external edit;
- duplicate JSX ownership key;
- stale context materialization;
- provider fingerprint drift;
- legacy compile cache migration;
- multi-workspace browser lifecycle;
- direct benchmark execution from source checkout;
- archive traversal/symlink/size attacks from earlier checkpoints.

### M12 — Admission

Alpha.3 may be admitted only when:

1. all legacy + alpha.3 tests pass from the source tree;
2. `compileall` passes;
3. all JSON schemas/reports parse;
4. alpha.3 demo passes;
5. alpha.3 navigation benchmark finds every known target in both disclosed arms;
6. AGI ZIP stress passes;
7. package manifest has no missing, mismatched or unlisted release files;
8. the final ZIP passes integrity check;
9. the ZIP is extracted to a clean directory and the full suite/demo/stress are rerun from that extracted artifact.

## 5. Failures discovered during implementation

### F1 — benchmark harness used mapping API unsupported by `sqlite3.Row`

The first alpha.3 navigation run attempted `.get()` on `sqlite3.Row` and failed. Correction: use the storage contract explicitly (`row['name']`). Regression: benchmark must execute directly before admission.

### F2 — JSX `id` and `data-testid` with the same literal generated a duplicate symbol ID

A TSX element such as `<button id="go" data-testid="go">` produced two parser anchors with the same stable identity. Correction: de-duplicate `(key,line)` parser anchors before persistence. Regression: alpha.3 demo uses exactly this case.

### F3 — metadata watcher cannot be an integrity oracle

A same-size source edit with restored mtime defeats metadata observation by design. Correction was architectural, not cosmetic: ordinary reads may lag, but every consequential mutation still deep-hashes canonical source before staging and commit. Regression test preserves this limitation and safety boundary.

## 6. Claim boundary

Alpha.3 is allowed to claim:

- ordinary metadata-detected edits can be admitted with targeted content hashing;
- no-op graph persistence no longer rewrites unchanged relation/occurrence rows;
- semantic provider work is partitioned by provider domain;
- a live observation watcher exists with a foreground admission boundary;
- context can be revision-refreshed and bounded-materialized;
- explicit JSX anchors provide bounded framework ownership candidates;
- included deterministic plumbing benchmarks execute and disclose their limitations.

Alpha.3 is **not** allowed to claim:

- lower LLM token use;
- higher coding-task success;
- universal repository understanding;
- production sandbox security;
- complete framework source-map ownership;
- full incremental AST/TypeChecker recomputation at syntax-node granularity;
- AGI capability.

## 7. Deferred frontier

Next candidates after alpha.3 admission:

- optional Tree-sitter incremental old-tree provider with capability-attested dependency;
- LSP/SCIP ingestion with provider-specific cache identities;
- Merkle/path partition for very large source roots;
- process lease / multiprocess transaction coordinator;
- React/Vue/Svelte source-map and bundler-aware component ownership;
- safe targeted Jest/Vitest selectors;
- external same-model agent A/B runner;
- sandbox broker integration.
