# Habitat Alpha.6 Architecture — Backend Substrate and Cognitive Continuity

## System boundary

```text
                  ordinary project authority
                           │
                    ProjectBackend
             ┌─────────────┼─────────────┐
             │             │             │
          read/write    reconcile      execute
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                  materialized source view
                           │
                           ▼
                    Semantic Compiler
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           symbols      relations    evidence
              │            │            │
              └────────────┼────────────┘
                           ▼
                    Context Compiler
                           │
             ┌─────────────┼──────────────┐
             ▼             ▼              ▼
       virtual pages   residency     utility prior
             │             │              │
             └─────────────┼──────────────┘
                           ▼
                       AI agent
                           │
                 transaction / verify
                           │
                           ▼
                    ProjectBackend
```

The Semantic Twin is explicitly **derived**. Backend authority is canonical.

## Backend contract

`ProjectBackend` exposes:

- `info` — backend identity/capability/provenance;
- `materialized_root` — compiler view;
- `reconcile(paths?)` — hydrate source authority into compiler view;
- `read_bytes` / `write_bytes` / `is_file` — exact canonical source operations;
- `discover_capabilities` — typed executable capabilities;
- `run` — execution returning a typed receipt.

Alpha.6 implementations:

### LocalProjectBackend

Authority == materialized source. Existing linked-folder/managed-ZIP behavior remains compatible.

### DirectoryMirrorBackend

Authority and compiler mirror are separate directories. It proves the abstraction without pretending to implement a network/cloud backend.

Full reconcile enumerates the authority. Targeted reconcile with candidate paths does **not** enumerate the whole authority; it hydrates only those paths. A real remote adapter can map a change feed onto this path.

## Backend provenance

`BackendInfo` declares backend id, kind, authority, authoritative/materialized roots, execution kind, watch capability and supported operations.

`ExecutionReceipt` now carries:

- `backend_id`;
- `execution_backend`.

A passing test without execution placement provenance is considered incomplete evidence for a multi-backend future.

## Context utility

Agent/harness feedback may label a candidate `used` or `unhelpful`. Utility is indexed by object + task terms and applied only to candidates that already have independent evidence.

Invariants:

- no candidate creation from feedback;
- bounded score adjustment;
- utility never changes source trust grade;
- source/evidence/semantic lanes remain authoritative for facts;
- utility is an attention prior only.

## Next-page planning

`workspace.context.plan_next` ranks not-yet-fetched virtual pages under source-byte/page budgets.

Low-confidence/no-gold contexts return `abstain-or-broaden-query` and zero source-byte reads. The planner may not pick a best-looking page merely to fill budget.

## Causal work episodes

A work episode binds:

```text
task
  ↓
context handle
  ↓
transaction staged
  ↓
transaction committed / revision
  ↓
verification receipt / evidence
  ↓
episode outcome
```

Checkpoints may bind an active episode and emit a `checkpoint-created` link. This enables continuation/handoff with executable provenance rather than narrative-only memory.

`workspace.causality.explain` reports these workflow links. Its scope explicitly does not claim full program causality.

## Checkpoint binding

Alpha.6 checkpoint state includes backend identity/binding in addition to revision, Merkle root, compiler/provider fingerprint, event cursor and residents.

Resume policy:

- same source/provider/backend → `direct`;
- unrelated revision drift with fresh residents → `selective-revalidate`;
- resident/provider/backend identity drift → `reorient`.

## Cloudflare Computer compatibility direction

A future adapter can map:

```text
Cloudflare workspace filesystem → ProjectBackend source authority
workspace runtime              → capability execution
Durable workspace identity     → backend binding
Habitat compiler mirror        → local/ephemeral semantic materialization
```

No Cloudflare-specific adapter is claimed in alpha.6. The contract-double exists to make such an adapter possible without changing Habitat cognition semantics.
