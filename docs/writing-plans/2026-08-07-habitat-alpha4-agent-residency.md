# Nolane Habitat alpha.4 — Resident Agent Workspace Implementation Plan

Release target: `0.1.0-alpha.4`  
Date: 2026-08-07  
Status: implementation complete candidate; final admission depends on packaged-artifact verification.

This plan applies the Nolane AGI Cognitive System method as an engineering discipline: **charter → capability diagnosis → rival beliefs → discriminating probes → implementation → evidence → unknown-unknown audit → admission/reject/quarantine**. Code existence is not admission evidence.

## 1. Charter

### Goal

Make Habitat behave less like a semantic search service an agent repeatedly visits and more like a **persistent project environment in which an agent maintains a small, valid working set**. Reduce unnecessary semantic recomputation and repeated rediscovery without allowing caches, memory, watcher metadata or summaries to become false authority.

### Protected invariants

1. Canonical project files remain source truth.
2. Semantic/index/residency state is derivative and rebuildable.
3. Exact source is not copied into resident memory at rest.
4. Residency may bias attention only when evidence is fresh and task-relevant.
5. Pinned evidence is never silently evicted.
6. Checkpoint continuation is denied/reclassified when environment/provider bindings drift.
7. Resolver caches must invalidate on semantic candidate-surface changes, not merely source digests.
8. Telemetry must never alter the measured agent result.
9. Generic shell remains absent from the normal agent protocol.
10. Plumbing byte/call metrics must not be mislabeled as model-token or capability results.

### Non-goals

- no desktop/OS automation;
- no production hostile-code sandbox;
- no universal Tree-sitter/LSP/SCIP implementation;
- no full React/Vue/Svelte runtime provenance oracle;
- no claim of lower token usage or higher coding success without a same-model A/B;
- no claim that TypeScript whole-project semantics are node-incremental after JS/TS edits.

## 2. Entry capability diagnosis

Alpha.3 already provided live candidate synchronization, graph-delta persistence, provider-domain caches, revision-bound context refresh/materialization, affected tests, transactional mutation and runtime semantic UI.

The strongest remaining problems were:

- graph persistence was incremental, but base semantic resolution still lacked explicit per-source dirty partitions;
- an agent could materialize context but had no durable working set across subsequent tasks/turns;
- checkpoint/resume bound resident digests but did not yet include a first-class residency model and provider-state continuation policy;
- TSX UI ownership connected elements to components but not directly to static event handlers;
- benchmark plumbing lacked protocol-level instrumentation of calls/bytes/exact-source exposure.

## 3. Belief state with rival hypotheses

### B1 — Per-source relation partitions can reduce semantic work without stale edges

**Hypothesis:** relation resolution can be cached per semantic source using unresolved facts plus the subset of the candidate index that can affect those facts.

**Rival:** body/source changes or new duplicate declarations can leave cached resolution stale.

**Discriminating probes:**

- body-only edit with identical outbound semantic facts → own partition should be reused;
- adding a duplicate declaration that changes a call candidate surface → dependent caller partition must be recomputed and its relation trust/results updated.

**Kill criterion:** any candidate-surface change leaves an old precise edge admitted.

**Status:** retained after regression probes.

### B2 — Persistent residency can reduce rediscovery without becoming stale memory authority

**Hypothesis:** storing semantic object identity/provenance/relevance is enough to preserve working context while exact source remains page-in-only.

**Rival:** stale resident objects or task carryover bias context toward the wrong subsystem.

**Discriminating probes:**

- source edit marks resident object stale and excludes exact-source materialization;
- unrelated task must not receive resident boost merely because an auth object was seen earlier;
- fresh relevant resident object may receive a bounded prior.

**Kill criterion:** stale source is returned as current exact evidence, or unrelated residency dominates a new task.

**Status:** retained with fresh+task-relevant gating.

### B3 — Capacity policy must fail visibly under pinned overcommit

**Hypothesis:** pins can protect high-value resident objects without hidden policy violations.

**Rival:** automatic eviction silently discards a pinned object or pretends capacity is satisfied.

**Probe:** configure capacity below number/estimated bytes of pinned residents.

**Required result:** preserve pins and report `overcommitted=true` with reason.

**Status:** retained.

### B4 — Checkpoint is an environment binding, not a summary

**Hypothesis:** revision + provider fingerprint + event cursor + resident digests can discriminate safe direct resume from selective revalidation/reorientation.

**Rival:** a narrative checkpoint gives false continuity after source/provider changes.

**Probe sequence:** unchanged workspace → unrelated file edit → resident source edit.

**Expected modes:** `direct → selective-revalidate → reorient`.

**Status:** retained.

### B5 — Static JSX handlers are useful UI source evidence when trust is bounded

**Hypothesis:** `onClick={handleSave}` can connect a unique semantic UI anchor to a parser-visible handler.

**Rival:** generated/duplicated/rewritten handler ownership makes the link misleading.

**Kill criterion:** ambiguous anchors/handler targets are promoted to unique semantic proof.

**Status:** retained as bounded parser/semantic evidence only.

### B6 — Protocol tracing can support future A/B evidence without perturbing execution

**Hypothesis:** request/response/exact-source byte and call measurements can be captured transparently.

**Rival:** telemetry failures alter result behavior or instrumentation is mistaken for token measurement.

**Probe:** force trace recorder to raise while performing a normal query.

**Required result:** query result remains unchanged; report boundary states bytes ≠ model tokens.

**Status:** retained.

## 4. Implementation milestones

### M1 — Resolver index and relation partitions

Files:
- `habitat/compiler.py`
- `habitat/semantic/project.py`

Postconditions:
- no-op refresh recomputes zero base partitions;
- body-only edits with stable outbound facts recompute zero relation partitions;
- new candidate declarations invalidate only affected partitions;
- old relation rows are removed/changed correctly through set-diff graph sync.

### M2 — Persistent Context Residency

Files:
- `habitat/residency.py`
- `habitat/storage.py`
- `habitat/workspace.py`

Methods:
- `workspace.context.residency.configure`
- `...admit`
- `...status`
- `...materialize`
- `...touch`
- `...pin`
- `...evict`

Postconditions:
- resident database contains no copied exact source body;
- staleness is digest-visible;
- materialization page-ins exact symbol source only under budget;
- eviction preserves pins and reports overcommit when necessary.

### M3 — Residency-aware Context Compiler

The Context Compiler may use fresh residency as a bounded attention prior only after independent task relevance is established.

Verifier:
- follow-up task in same subsystem can expose `resident` lane;
- unrelated billing task does not pull an auth resident solely because it is remembered.

### M4 — Provenance-bound checkpoint/resume

Checkpoint binds:
- revision/root digest;
- compiler/provider fingerprint;
- event cursor;
- residents with path/digest/kind/pin/relevance;
- next action and invalidation conditions.

Verifier:
- unchanged → `direct`;
- unrelated revision change with residents fresh → `selective-revalidate`;
- resident digest or provider identity drift → `reorient`.

### M5 — UI event-handler semantic path

Files:
- `habitat/semantic/typescript.py`
- `habitat/compiler.py`
- `habitat/workspace.py`

Postcondition on supported static TSX fixture:

```text
component → renders → ui-anchor → handles_event → handler symbol
```

Runtime source hint may expose handler only when anchor/edge evidence is sufficiently unambiguous.

### M6 — Protocol instrumentation

Files:
- `habitat/storage.py`
- `habitat/workspace.py`
- `habitat/protocol.py`

Methods:
- `workspace.trace.start`
- `workspace.trace.status`
- `workspace.trace.stop`

Metrics:
- call count/method distribution;
- request/response bytes;
- exact-source bytes;
- duration;
- revisions.

Telemetry failure must not change the operation response.

### M7 — Schemas and protocol contract

Files:
- `schemas/context-residency.schema.json`
- `schemas/agent-trace.schema.json`
- `docs/AGENT-PROTOCOL.md`

The wire envelope remains `habitat.agent.v1alpha2`; alpha.4 methods are compatible additions rather than a renamed protocol generation.

### M8 — End-to-end demo

Required sequence:

```text
folder
→ ingest/orient
→ admit residency
→ bounded resident materialization
→ trace follow-up access
→ semantic source mutation
→ observe stale resident
→ refresh/re-admit
→ targeted verification
→ runtime UI + handler source evidence
→ warm semantic refresh
→ checkpoint/resume evidence
```

### M9 — Supplied AGI ZIP stress

Corpus: supplied `Nolane-AGI-Cognitive-System-4.0.0(1).zip`.

Required evidence:
- cold ingest succeeds;
- warm file compiler reuse is complete;
- warm base relation partitions recompute zero;
- documentation edit does not dirty base resolver partitions;
- a Python body-only edit with stable outbound facts does not cause unnecessary partition recomputation;
- provider-domain boundaries remain disclosed.

### M10 — Benchmark instrumentation harness

`benchmarks/alpha4_trace_benchmark.py` compares disclosed filesystem plumbing with Habitat protocol plumbing and captures first-class trace metrics.

This is **not** the same-model agent A/B. It may establish instrumentation correctness and warm-access plumbing differences only.

### M11 — Unknown-unknown probes

Mandatory alpha.4 probes:
- resolver candidate-surface expansion;
- pinned capacity overcommit;
- stale resident exact-source exclusion;
- unrelated residency contamination;
- telemetry recorder failure;
- invalid optional protocol parameter types;
- provider/toolchain fingerprint drift from earlier checkpoints;
- metadata-preserving source edits from alpha.3;
- duplicate JSX anchors and browser lifecycle collisions from earlier checkpoints.

## 5. Failures/corrections discovered during alpha.4

### F1 — Alpha.3 regression encoded a now-obsolete cache expectation

An old test expected every Python edit to miss the base semantic domain. Per-source partitions made a body-only edit legitimately reusable. The test contract was updated only after verifying relation correctness; it was not weakened to hide a failure.

### F2 — Residency test assumed orientation selected exactly one object

Orientation correctly selected both file/symbol context. The harness assumption was wrong. The invariant was rewritten to inspect absence of copied exact-source fields rather than exact object cardinality.

### F3 — “No source at rest” check confused provenance fields with source payload

A draft assertion matched keys such as `source_digest`/`source_bytes_estimate` and incorrectly treated them as copied source. The verifier was corrected to detect an exact `source` payload field.

### F4 — Relation partition fingerprint originally included source digest

That made a body-only edit dirty its own partition even when unresolved semantic facts were identical. The digest was removed from relation-partition identity; compiler/provider version remains a separate invalidation boundary. A regression locks zero recomputation for same-outbound-fact edits.

### F5 — Structural implementation bonus admitted unrelated helper symbols

The first protocol trace benchmark selected billing/noise helpers for a credential task because function/class shape received an implementation bonus without any matching task concept. Correction: structural/task-class/trust promotion now requires at least one strong content/path concept match. Regression: a specific credential task over a 20-noise-file fixture must select no noise paths; regenerated 120-noise benchmark selects only the correct subsystem.

## 6. Admission gates

Alpha.4 may be admitted only if:

1. all legacy + alpha.4 unit/adversarial tests pass;
2. compileall passes;
3. every schema/report parses;
4. alpha.4 vertical demo passes;
5. supplied AGI ZIP stress passes;
6. trace benchmark runs and the report preserves the no-token-claim boundary;
7. README quick-start matches executable CLI behavior;
8. package/version identity is alpha.4 everywhere in current release surfaces;
9. delivery manifest independently verifies missing/extra/hash/root-hash state;
10. ZIP integrity passes;
11. clean-extracted final artifact reruns tests/demo/stress/benchmark;
12. isolated package import reports `habitat.__version__ == 0.1.0-alpha.4`.

## 7. Claim boundary

Alpha.4 is allowed to claim bounded evidence for:
- per-source base relation partitions and dirty-closure behavior;
- persistent source-free semantic residency with visible staleness/overcommit;
- residency-aware bounded context continuity;
- provenance-bound resume classification;
- static TSX event-handler source evidence on supported fixtures;
- protocol-level plumbing instrumentation.

Alpha.4 is **not** allowed to claim:
- lower LLM token cost;
- higher coding-task success;
- fully incremental TypeScript whole-project semantics;
- universal framework runtime ownership;
- production hostile-code isolation;
- AGI capability.

## 8. Frontier after admission

- content-addressed/Merkle source partitioning for very large repositories;
- syntax-node incremental Tree-sitter provider when dependency is actually available;
- LSP/SCIP provider lanes with explicit toolchain/index fingerprints;
- dependency-partitioned TypeScript semantic state;
- resident working-set policy learned/evaluated under real task trajectories;
- same-model repeated-run agent A/B harness;
- multiprocess workspace lease/transaction coordinator;
- bundler/source-map-aware React/Vue/Svelte runtime provenance.
