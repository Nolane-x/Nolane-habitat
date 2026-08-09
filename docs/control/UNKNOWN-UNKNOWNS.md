# Unknown-Unknown Frontier — alpha.4

This file preserves unresolved hazards and newly discovered false assumptions. Missing hazards are not evidence of safety.

## Newly discovered/corrected during alpha.4

### File-level incrementality still allowed unnecessary relation work
Alpha.3 reused file compilers and diff-persisted graph rows, but base relation resolution did not expose per-source dirty partitions. Alpha.4 introduces source partitions keyed by unresolved semantic facts and relevant candidate surfaces.

### Source digest was too coarse for relation-partition identity
The first partition fingerprint included the source digest. A body-only edit therefore dirtied a relation partition even though outbound semantic facts had not changed. The digest was removed from relation-partition identity; compiler/provider/cache versions remain separate invalidation boundaries. Regression evidence requires zero partition recomputation for identical outbound facts.

### “Persistent context” can become confirmation bias
A resident working set can save rediscovery but can also pull stale or irrelevant historical objects into a new task. Alpha.4 gates residency prior on both source freshness and current-task relevance. This is still a heuristic policy and needs real-model trajectory evaluation.

### Pinned working memory can exceed capacity
Silently evicting pins would violate user/agent intent; silently ignoring capacity would falsify resource accounting. Alpha.4 chooses visible overcommit: pins remain and the capacity receipt reports the violated bound.

### Provenance field names are not source copies
An early verifier treated `source_digest` and `source_bytes_estimate` as if they were copied source payloads. The invariant was refined: residency may store provenance/estimates but must not persist exact source bodies.

### Orientation cardinality is not stable
A draft residency test assumed one selected semantic object. Context Compiler correctly selected both file and symbol evidence. Tests now verify invariants rather than overfitting an incidental ranking/cardinality.

### Telemetry can perturb the system it measures
If trace recording raises, the agent operation must still succeed/fail according to its own behavior. Alpha.4 catches instrumentation failure outside the operation result path and has an adversarial regression.

### Checkpoint narrative alone is unsafe continuity
A task note can sound valid while source/provider state has changed. Alpha.4 binds revision/root/provider/event/resident evidence and classifies resume rather than blindly continuing.

## Open frontier

### TypeScript semantic incrementality remains coarse
A JS/TS edit still reruns TypeScript Program/TypeChecker semantics. Per-source base relation partitioning does not solve TypeScript incremental project-state reuse.

### Resolver partitions may miss unconventional candidate surfaces
Dynamic imports, registries, decorators, reflection, generated code and runtime dispatch can alter effective resolution without appearing in current static unresolved facts. Trust remains bounded.

### Residency policy may fail under long-horizon task switching
Recency/relevance/pinning is a hand-designed policy. Unknown failure modes include thrashing, excessive pinning, stale-but-frequently-touched objects and correlated retrieval bias.

### Event cursor is not an external-world checkpoint
The journal covers Habitat/source observations, not every backend process, remote API, browser world, database or service. Resume modes are project-workspace continuation classes, not full environment restoration.

### UI handler mapping is not runtime proof
A static `onClick={handler}` path can be transformed/wrapped/delegated by frameworks/builds. Source maps, SSR/hydration, portals, Vue/Svelte and generated handlers need separate evidence lanes.

### Trace bytes can be gamed by API shape
A lower byte count can coexist with worse decisions, more hidden preprocessing or lower success. Benchmark admission must include task outcomes, ingest cost and raw trajectories, not optimize trace numbers alone.

### Very large repositories may change the economics
SQLite/FTS and in-memory resolver indexes are sufficient for current stress fixtures but may behave differently on million-file monorepos. Merkle/path partitions, streaming indexes and memory bounds remain unproven.

### Multiprocess concurrency remains unmodeled
Two Habitat processes sharing one canonical source root can race. A process-local watcher and SQLite transaction are not a distributed lease/commit protocol.

## Alpha.5 discoveries

- **Resolved evidence through historical FTS:** append-only search history could reintroduce a resolved test failure. Live retrieval now explicitly checks evidence `active` state.
- **Over-broad precision supersession:** resolving one Jedi call initially removed every weak call edge from the same source function. Supersession is now call-site-line scoped.
- **Provider cache over-invalidation:** including one-line function bodies inside TypeScript/Python API-surface signatures made body-only changes look like API changes. Surface identity now focuses on definition/import resolution identity.
- **No-gold false confidence:** a multi-concept nonsense query became high-confidence on the AGI corpus because one common word matched. Confidence now includes concept coverage and can recommend abstention.
- **Per-page reconcile tax:** virtual page faults initially invoked source reconcile again for every fetched page. Fetch now validates the exact backing bytes directly after one workspace reconciliation.
- **MCP environment ambiguity:** adapter code existed while the release host lacked the real SDK. Runtime capability is explicitly separated from adapter contract verification.

These are retained as regression targets; they are not removed from the project history merely because the current implementation passes.

## Alpha.6 discoveries and open frontier

### Backend abstraction can leak through innocent source reads
Context Residency still estimated symbol source size by reading the compiler mirror directly. That was safe only while authority == mirror. Alpha.6 routes this exact-source access through backend authority and treats direct mirror source reads as an abstraction violation.

### A remote-like backend can still hide O(project) work
The first mirror implementation supported `reconcile(paths)` but still constructed whole authority/mirror maps. Alpha.6 now has a targeted/no-enumeration path when exact candidates are supplied. Full reconcile remains O(project) and is explicitly not production-remote-ready.

### Workspace targeted refresh can reintroduce the same listing tax
Even after targeted backend hydration, `refresh_paths` originally enumerated the entire materialized root. It now resolves only validated candidate paths. A future adapter still needs a trustworthy path-change source.

### Early invalidation is preferable to late source drift
A mirror page-fault failure probe expected digest drift during the fault. Authority reconcile advanced the workspace revision first, so the context was rejected as revision-stale. The stronger early invalidation is retained.

### Backend identity is part of cognition continuity
A checkpoint valid for one source/execution authority may be unsafe under another even when visible files look identical. Alpha.6 binds backend identity and forces reorientation on drift.

### Feedback is vulnerable to long-horizon bias
Bounded utility cannot invent candidates, but repeated feedback can still make an already-supported candidate systematically easier/harder to retrieve. Alpha.6 has no automatic credit assignment from successful tests and does not claim the policy learns optimal context.

### Workflow causality is not program causality
The episode ledger answers “which task/context/transaction/verification produced this workspace change?” It does not answer arbitrary semantic causal questions about runtime behavior. The API reports this scope explicitly.

### Remote execution may expose multiple runtime choices
Cloud-like systems may expose container/isolate/JS or other runtimes concurrently. Alpha.6 records selected execution provenance but does not let the model choose arbitrary runtime identifiers. A future execution policy must preserve typed capability constraints.

### Source authority and execution provider may eventually need independent composition
`ProjectBackend` currently groups source authority and execution placement. This is sufficient for local/mirror fixtures and maps naturally to computer-style backends, but future deployments may want local source with remote execution or vice versa. Split composition remains an architectural frontier, not a hidden assumption.
