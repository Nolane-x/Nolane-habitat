# Writing Plan — Habitat alpha.6 Backend Substrate + Cognitive Loop

Status: implemented / admission pending final artifact gate.

## Charter

Evolve Habitat so that project authority/execution can move without moving cognition semantics. Strengthen long-horizon context behavior at the same time.

### Protected invariants

1. Canonical project bytes remain authority.
2. Semantic Twin remains rebuildable/derived.
3. Exact source must be authority-backed.
4. Unsupported precision fails closed.
5. Context feedback cannot become source truth.
6. Low-confidence retrieval may abstain rather than spend source budget.
7. Consequential mutations deep-reconcile before trust-sensitive commit.
8. Execution evidence records backend provenance.
9. Checkpoint continuation is conditional on environment identity.

## Beliefs and rival hypotheses

### B1 — backend separation can preserve semantic equivalence

Rival: separating authority/mirror changes symbol identity or retrieval ordering.

Probe: same fixture under local and directory-mirror backends; compare symbols, relations, occurrences, context result, canonical mutation and verification.

Kill criterion: any unexplained semantic divergence.

### B2 — known changed paths can avoid remote O(project) listing

Rival: targeted refresh still secretly enumerates source/mirror.

Probe: external single-file authority edit + `refresh_paths([path])`; backend receipt must report targeted/no-enumeration and one path considered.

### B3 — feedback improves attention without inventing relevance

Rival: repeated feedback becomes self-fulfilling pseudo-truth.

Probe: only already-ranked candidates may receive utility; outside IDs fail; adjustment remains bounded.

### B4 — no-gold should stop page faults

Rival: planner always fills a source budget.

Probe: no-gold task; zero planned source pages and zero source bytes.

### B5 — checkpoint must bind backend identity

Rival: source backend changes but narrative state is reused.

Probe: mutate manifest backend identity; resume must `reorient`.

### B6 — long-horizon work needs causal workflow state

Rival: narrative checkpoint is enough.

Probe: episode links context, transaction, revision, verification, checkpoint and close status.

## Milestones

### M1 — backend contract
- abstract backend identity/source/execution surface;
- local backend migration compatibility;
- mirror contract double.

### M2 — authority-safe exact source
- inspect/source paging/residency/mutation route exact bytes through backend;
- no direct compiler-mirror shortcut for exact evidence.

### M3 — targeted backend hydration
- known candidate paths hydrate without backend whole-project enumeration;
- workspace targeted refresh also avoids project listing.

### M4 — execution provenance
- capabilities identify backend/execution placement;
- receipts carry backend id and execution backend.

### M5 — bounded context utility
- used/unhelpful feedback;
- task-term utility table;
- bounded prior only over independent candidates.

### M6 — selective next-page planner
- source-byte/page budget;
- diversity/cost ranking;
- no-gold abstention.

### M7 — work episode ledger
- context / transaction / revision / verification / outcome links;
- causality explanation with explicit scope boundary.

### M8 — checkpoint/episode/backend binding
- backend identity and active episode persisted;
- resume mode reacts to drift.

### M9 — backend equivalence benchmark
- same semantic answers under local/mirror;
- same canonical mutation result;
- different execution provenance allowed/required.

### M10 — AGI corpus stress
- warm compiler/provider partition reuse preserved;
- planner/feedback/no-gold behavior measured.

### M11 — release admission
- full suite;
- compileall;
- docs/schema/quick-start;
- clean ZIP independent manifest verification;
- rerun demo/equivalence/stress from extracted final artifact.

## Failure ledger to preserve

- old workspace-manifest schema rejected alpha.6 backend object until schema was made backward-compatible;
- mirror page-fault probe expected a late digest fault, but backend reconciliation invalidated the context earlier (`context-revision-stale`); test updated to the stronger invariant;
- backend-equivalence harness called nonexistent `Store.all_relations`; harness corrected to the actual storage contract;
- harness then assumed occurrence columns named `line/column/symbol_id`; corrected to `start_line/start_column/target_id`;
- targeted-refresh patch accidentally inserted targeted metrics into deep refresh, causing `NameError: normalized`; corrected and regression-tested.

## Claim boundary

Alpha.6 may claim:

- executable backend separation on local/directory-mirror fixtures;
- semantic equivalence on the bundled fixture;
- backend-bound execution receipts;
- targeted no-enumeration hydration when exact paths are supplied;
- bounded context utility and no-gold page abstention;
- causal workflow episode/checkpoint provenance.

Alpha.6 may **not** claim:

- Cloudflare Computer integration;
- production remote synchronization;
- model token savings;
- coding-success superiority;
- learned optimal retrieval;
- complete program causality;
- AGI capability.
