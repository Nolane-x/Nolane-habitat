# Nolane Habitat alpha.5 — Deep Evolution Architecture

## Thesis

Habitat is not a prettier file browser for agents. Its alpha.5 architecture treats an ordinary project as a **versioned semantic address space** whose source files remain canonical authority while agents operate on derived, typed, provenance-bound state.

```text
canonical folder / ZIP / loose source
             │
             ▼
     content-hashed source bridge
             │
             ├───────────────┐
             ▼               ▼
  incremental compiler   Merkle state
             │               │
             ▼               │
  semantic provider domains  │
  ├─ Python AST               │
  ├─ Python Jedi partitions  │
  ├─ TS Program + dirty scan │
  └─ explicit weak fallback  │
             │               │
             ▼               │
 symbols / relations / occurrences / diagnostics
             │
             ├── runtime + verification evidence
             ├── task retrieval + calibrated abstention
             ├── context virtual address space
             ├── resident working set
             ├── transactional mutation / semantic rename
             ├── affected-test verification
             └── semantic UI runtime/assertions
                           │
                           ▼
                         agent
```

## A. Authority and trust lanes

Alpha.5 preserves five trust grades:

- `exact`: fact bounded to canonical bytes/runtime receipt;
- `semantic`: language/runtime provider resolved a relationship inside a declared boundary;
- `parser`: syntax observation;
- `derived`: deterministic structural inference;
- `heuristic`: candidate requiring verification.

The SQLite twin, Merkle objects, context packets, evidence records and residency are all derivative. None outrank canonical project bytes.

## B. Precision provider partitions

### Python

The Python precision overlay uses Jedi as a **static** provider. Project modules are never imported or executed during indexing.

Each Python source owns a precision partition. Cache admission binds:

```text
source digest
+ provider identity/version
+ provider schema
+ conservative Python API/import surface digest
```

A body-only change normally dirties one source partition. A definition/import surface change invalidates every partition that could have observed a different resolution surface. Alpha.5 deliberately chooses conservative global surface invalidation over unsound local reuse.

A semantic call supersedes weaker parser call edges only at the **same proven call-site line**. Resolving one call inside a function may not erase unresolved evidence at another call site.

### TypeScript / JavaScript

TypeScript still constructs a whole-project `Program`/`TypeChecker` when a provider run is needed because target resolution is project-sensitive. However, semantic traversal/output is partitioned by dirty source paths:

```text
no JS/TS dirty          -> provider process not invoked
body-only one-file edit -> Program available, scan one source partition
API/import surface edit -> conservatively scan all TS/JS partitions
```

This is not claimed to be a persistent in-process TypeScript incremental compiler. It is a real reduction in semantic traversal/output work with a conservative project-resolution boundary.

## C. Calibrated task retrieval

A high lexical score is not sufficient evidence of task coverage. Alpha.5 computes:

- top candidate score;
- independent evidence lanes;
- indexed concept coverage across task concepts;
- retrieval confidence: `low | medium | high`;
- `abstention_recommended`.

A multi-concept query that matches one common word but lacks the remaining concepts is low-confidence. High-level adapters suppress automatic exact-source prefetch when abstention is recommended.

This is intentionally a retrieval confidence signal, not a probability that the agent will solve the task.

## D. Context virtual memory

A context handle maps relevant objects to virtual pages:

```text
ctx://<handle>/<page-id>
```

Pages contain metadata eagerly but not copied source. Fetchable pages are symbol bodies or bounded diagnostic windows. File objects remain metadata-only to prevent whole-file dumping under a different name.

Exact source page fault:

1. validate context revision;
2. validate stored source digest;
3. read backing bytes directly;
4. hash those same bytes to detect race/drift;
5. slice exact source range;
6. enforce exact byte budget;
7. return `authority=exact-source`.

Fault reasons remain explicit (`unknown-page`, `metadata-only-page`, `byte-budget`, digest drift, stale context).

## E. Content-addressed project state

Merkle state is constructed from digests already computed by the source bridge. Building or querying Merkle state reads **zero additional source bytes**.

It provides:

- revision root hash;
- subtree identity;
- hash-pruned revision diff;
- added/deleted/modified paths;
- exact one-to-one content rename detection;
- checkpoint project-state binding.

The Merkle store is not a second source store: leaf values contain identity/digest/size metadata, not duplicated project bytes.

## F. Runtime and verification evidence

A failed structured verification can produce first-class `test-failure` evidence with:

- originating revision;
- path/test identity where resolvable;
- run/capability receipt;
- severity/trust;
- active/resolved state.

Active evidence participates in task retrieval. Resolved evidence remains auditable in storage/FTS history but is explicitly excluded from live lexical retrieval.

A passing targeted verification resolves failures only for selected tests. A passing full suite may resolve the full active test-failure set.

## G. Semantic mutation and rename

### Symbol-body mutation

Existing symbol-body replacement remains digest-bound, previewed, transactional and rollback-capable.

### Python semantic rename

Alpha.5 introduces provider-proven project rename:

```text
symbol ID
  -> Jedi exact definition anchor
  -> project references
  -> exact identifier spans
  -> per-file source digests
  -> staged multi-file transaction
  -> atomic commit + semantic refresh
```

The rename intentionally preserves local aliases such as:

```python
from auth import validate_credentials as check
# rename source API -> verify_credentials
# local alias `check` remains `check`
```

Rename fails closed when:

- symbol is outside supported Python/Jedi precision boundary;
- identifier is invalid;
- one exact definition anchor cannot be proven;
- a referenced source is not indexed;
- an outside-project reference is reported;
- any backing digest drifts after staging.

## H. AI-native UI verification

Runtime UI assertions operate on semantic browser state. Assertions can address a semantic handle or role/name and check count, visibility, enabled/checked state, value, text, or containment.

The returned oracle explicitly states that DOM/accessibility/runtime state was used and `screenshot_used=false`. Pixel evidence remains an optional secondary oracle for visual defects.

Static JSX ownership and event-handler hints remain bounded by their parser/runtime provenance; build transforms can make ownership ambiguous.

## I. MCP adapter boundary

The internal `habitat.agent.v1alpha2` protocol remains the core interface. Alpha.5 adds an **optional** MCP adapter targeting the 2026-07-28 MCP specification and SDK v2 contract.

Only 12 high-level tools are exposed. The large internal primitive set is deliberately not mirrored 1:1 into MCP because tool-selection context is itself an attention cost.

Core Habitat has zero MCP dependency. If the SDK is absent, the adapter fails with an explicit optional-dependency error. The alpha.5 release environment verifies the adapter with an SDK contract double; a real MCP SDK runtime is a separate environment-bound capability and is not claimed when the package is absent.

## J. Admission boundary

Alpha.5 may claim only what its executable evidence supports:

- deterministic project ingestion and synchronization;
- semantic precision improvements within provider boundaries;
- partition reuse/recomputation metrics;
- exact-source byte budgets observed by Habitat;
- no-gold retrieval abstention on tested fixtures;
- structured mutation/test/UI/evidence behavior.

It may **not** infer from those results:

- universal token savings;
- model reasoning improvement;
- coding success-rate superiority;
- universal repository retrieval superiority;
- AGI capability.
