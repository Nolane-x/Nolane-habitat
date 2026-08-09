# Alpha.4 Architecture — Resident Agent Workspace

Alpha.4 moves Habitat from a live semantic workspace toward a **resident agent workspace**. The core architectural change is that task-relevant semantic objects can remain as a bounded, provenance-bound working set across successive agent turns without copying source text into a second authority store.

```text
                         CANONICAL PROJECT FILES
                                  │
                     targeted/deep synchronization
                                  │
                    per-file compiler/cache facts
                                  │
                  ┌───────────────┴────────────────┐
                  │                                │
        base semantic resolver             TypeScript domain
        per-source partitions              Program/TypeChecker
                  │                                │
                  └───────────────┬────────────────┘
                                  │
                     relation / occurrence graph
                                  │
               ┌──────────────────┼────────────────────┐
               │                  │                    │
        task context          impact/tests          runtime UI
               │                                       │
       Context Residency                         JSX/runtime hints
               │                                       │
       page-in exact source                component → handler evidence
               │                                       │
               └──────────────────┬────────────────────┘
                                  │
                         checkpoint / resume
                                  │
                           protocol trace
                                  ▼
                                AGENT
```

## 1. Resolver partitions

Alpha.3 persisted graph deltas but the base resolver still conceptually reasoned over a broad semantic domain. Alpha.4 introduces a resolver index plus **per-source relation partitions**.

Each source file with unresolved semantic facts has a partition fingerprint derived from:

- its unresolved outbound facts;
- only the candidate-resolution surface relevant to those facts;
- semantic provider version/identity through the project semantic version boundary.

A source-body edit that does not alter outbound semantic facts therefore does not need to recompute that relation partition. Conversely, adding a new declaration that changes the candidate set for another source invalidates the affected reverse partition.

The partition fingerprint intentionally excludes the source digest itself. Source bytes are already protected by file compiler/cache identity. Including the digest would make body-only edits falsely dirty semantic relation work.

## 2. Context Residency

`ContextResidency` is a persistent semantic working set. It stores:

- object identity;
- kind/path;
- admitted revision and source digest;
- relevance;
- pin state;
- estimated source-body bytes;
- recency/access counters.

It deliberately does **not** store exact source bodies.

```text
resident semantic reference
        │
        ├─ fresh → eligible for task prior / materialization
        ├─ stale → visible but not materialized as current evidence
        └─ missing → visible as invalidated state
```

Exact source is paged from canonical files only during bounded materialization. Eviction prefers stale/missing entries, then least-recent/least-relevant unpinned entries. Pinned entries are never silently evicted. If pins alone exceed configured capacity, Habitat reports `overcommitted=true` rather than violating the policy covertly.

## 3. Residency as an attention prior, not authority

Context Compiler may apply a bounded `resident` lane boost only when the resident object:

1. is still fresh against canonical source digest; and
2. remains independently relevant to the new task.

Residency is therefore a continuity prior, not a reason to drag unrelated historical context into a new task. This is intended to reduce repeated rediscovery while limiting confirmation-bias amplification.

## 4. Provenance-bound checkpoint/resume

A checkpoint binds more than narrative notes. It records:

- source revision/root digest;
- compiler/provider-state fingerprint;
- event-journal cursor;
- resident semantic object IDs and source digests;
- residency configuration;
- next action/notes.

Resume classifies the continuation:

- `direct` — revision/provider/resident bindings remain valid;
- `selective-revalidate` — workspace changed but resident evidence remains fresh;
- `reorient` — resident evidence is stale/missing or provider identity drifted.

A checkpoint is therefore a resumable belief/environment binding, not a free-form summary.

## 5. Framework event-handler evidence

The TypeScript/TSX parser records static JSX handler attributes such as:

```tsx
<button id="save" onClick={handleSave}>Save</button>
```

The semantic graph can represent:

```text
component --renders--> ui-anchor --handles_event--> handleSave
```

Runtime UI source enrichment may expose the handler as `framework-event-handler:click` when the anchor is unique and the parser edge is sufficiently grounded. Ambiguous anchors/handlers degrade trust rather than being promoted to precise ownership.

This is still static framework evidence; it is not universal runtime component provenance.

## 6. Protocol trace instrumentation

Alpha.4 adds bounded trace sessions around agent protocol calls. Trace storage records:

- method;
- success/failure;
- duration;
- request bytes;
- response bytes;
- exact-source bytes returned;
- workspace revision.

Trace control calls are excluded from the measured workload. Telemetry is explicitly **non-authoritative**: trace recording failure must never change the result of the agent operation being measured.

These metrics are benchmark instrumentation, not token counts. They create a reproducible plumbing layer for a future same-model A/B run.

## 7. Remaining semantic boundary

Alpha.4 improves the base relation resolver at partition granularity. The TypeScript whole-project `Program`/`TypeChecker` domain still reruns conservatively after a JS/TS source edit. Habitat therefore does not claim fully incremental whole-project semantics across all providers.
