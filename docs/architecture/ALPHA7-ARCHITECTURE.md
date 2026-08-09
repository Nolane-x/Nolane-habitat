# Habitat alpha.7 Architecture — Composable Substrate + Explorer/Solver Boundary

## Thesis
Habitat is a project cognition substrate, not a virtual computer. Alpha.7 separates canonical source authority from execution placement and adds a bounded explorer/solver boundary so an agent can localize code without faulting source bytes into reasoning context.

## Substrate

```text
SourceAuthority                 ExecutionProvider
  read/write/reconcile             discover/run
          \                         /
           \                       /
             CompositeProjectBackend
                      |
              compiler materialization
                      |
                 Semantic Twin
```

The compatibility `ProjectBackend` façade remains so alpha.0–alpha.6 callers keep working. Manifest schema 4 preserves legacy `source_authority` while adding explicit `source_authority_provider` and `execution_provider` bindings.

A detached executor may execute observation/test workloads. If it mutates project paths while its execution root is not canonical authority, Habitat fails closed until an explicit durable write-back bridge exists.

## Persistent semantic services

TypeScript uses a process-persistent LanguageService within a bounded host pool. It preserves Program/document-registry state and traverses only dirty source partitions when the public resolution surface permits.

Python/Jedi retains semantic *output partitions* and a bounded four-Project LRU. An initial unbounded workspace-lifetime Project cache was rejected because callers from earlier releases were not required to close workspaces, creating hidden lifecycle pressure. Provider persistence is admitted only when boundedness and cleanup are explicit.

## Explorer / solver separation

`workspace.explore(task, line_budget, max_regions, context_budget)` emits ranked semantic regions:
- path and exact line interval;
- symbol/diagnostic identity;
- trust and evidence lane;
- no exact source bytes.

Low-confidence/no-gold tasks abstain rather than selecting least-bad code. The resulting context handle can then be passed to Context VM page planning/faulting. This keeps exploratory metadata separate from exact solver source.

## Context utilization ledger

Every exact-source page fault records handle/page/object/path/bytes/revision/episode. Explicit `used` and `unhelpful` feedback can then produce a context-efficiency report. Unrated objects are not assumed useless, and source bytes are never presented as tokens.

## Cross-revision work provenance

`causal_edges` forms a bounded workflow graph across:

```text
context -> episode -> transaction -> revision -> verification run -> evidence
```

This supports audit/handoff questions without claiming full program causality.

## Runtime lifecycle

Global optional services are independently drainable via `shutdown_runtime_services()`:
- TypeScript LanguageService pool;
- bounded Jedi Project cache;
- shared Chromium/Playwright engine.

Cleanup is idempotent and registered for process exit. This preserves backward compatibility with early callers that did not need to close every workspace.

## Trust boundary
- canonical bytes: SourceAuthority;
- semantic objects: derived, provider/trust annotated;
- execution receipts: bind source authority id and execution provider id;
- explorer regions: orientation evidence, not source authority;
- causal graph: recorded workflow provenance only.
