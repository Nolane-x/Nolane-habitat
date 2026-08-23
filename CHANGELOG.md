# Changelog

## 0.1.0-alpha.19 — 2026-08-23

- Added structural SQLite migration verification, safe pre-migration backups, and explicit rejection of malformed or newer workspace schema markers.
- Made deep and targeted refresh operations atomic, including rollback on task cancellation before later persistence can commit abandoned state.
- Added a read-only `habitat doctor <workspace>` health report for schema, integrity, foreign-key, and WAL state.
- Made test-matrix cleanup failures structured CI evidence and made JSON report output create its artifact directory and replace atomically.
- Added a checked release-identity command to keep runtime, package metadata, changelog, and current Codex documentation aligned.
- Added a truthful execution-capability report to `enter` and `habitat capabilities`, with fail-closed checks for unverified containment.
- Added a dry-run release-promotion gate that always writes a machine-readable verdict and never tags or publishes artifacts.
- Added a release-manifest builder that derives SHA-256 evidence and artifact bindings directly from supplied files.
- Made capability discovery report malformed npm manifests explicitly and avoid timing-dependent full imports when probing Python module presence.

## 0.1.0-alpha.18 — 2026-08-09

- Added portable Codex distribution with the `nolane-habitat` plugin, marketplace entry, operator skill, and maintainer skill.
- Added a concise Codex integration guide, contributor guidance, and a product-focused quick-start README.
- Added Windows-safe transaction journal directories while preserving transaction identity in journal records.
- Retried transient Windows sharing violations during atomic source replacement and retained same-directory atomic replacement semantics.
- Made repeated CSS selectors produce distinct, source-anchored symbols so complete UI asset trees ingest into a workspace.
- Made the balanced test suite close Habitat workspaces before temporary-directory cleanup on Windows.
- Made benchmark agent and evaluator commands preserve Windows path separators with `shell=False` execution.
- Added `pytest` to the development extra so execution verification capability is available in a standard development environment.

## 0.1.0-alpha.17 — 2026-08-08

- Stability/completion pass only: no new subsystem.
- Hardened runtime UI identity against duplicate IDs/test IDs, unsafe selector characters and project-supplied handle spoofing.
- Bounded noisy-page console/network buffers with explicit dropped-event accounting.
- Added fail-fast viewport/action-value validation and closed the browser context/page creation cleanup gap.
- Made observer frame public state atomic across the raw-CDP worker.
- Rebuilt Observatory Operator projection from a dedicated UI-event window with direct open-receipt recovery; stream-epoch changes now reset counters correctly.
- Added portable SQLite read-only file URIs plus real IPv6 loopback server/URL support.
- Source atomic writes now use unique same-directory temporary files to avoid same-PID writer collision; descriptor ownership is separated for temp-file and directory fsync so concurrent writers cannot trigger an fd-reuse/double-close race.
- Observatory frontend respects transport poll hints instead of polling snapshot fallback at live-CDP cadence.
- Corrected the alpha.16 continuous-stream test contract: the live head may advance after an action receipt while the exact action-boundary frame remains addressable in the bounded ring.
- Synchronized current installation/protocol/status/limitations documentation.

## 0.1.0-alpha.16 — 2026-08-08

- Upgraded AI Operator to a continuous raw-CDP WebSocket screencast on supported Chromium hosts; frame delivery continues while the sync Playwright thread is idle.
- Added explicit transport ladder: `cdp-websocket-live` → `cdp-screencast-cooperative` → `snapshot-fallback`, with mode/epoch/sequence exposed to Observatory instead of overstating guarantees.
- Added collision-resistant Windows-safe session frame keys, bounded versioned frame ring, atomic metadata publication and session-generation invalidation.
- Hardened lifecycle: continuous stream registry is drained on forced shared-browser shutdown; live pixels are deleted on close and crash-left ephemeral frames are cleaned at runtime start.
- Hardened privacy across DOM/ARIA/inline-handler/console/URL surfaces; sensitive typing no longer publishes secret length.
- Hardened the new DevTools attack surface: loopback-only bind, exact WebSocket origin, and browser routing that denies project-page access to the privileged debug port even with external traffic enabled.
- Removed literal NUL separators from Observatory JavaScript so source remains text-tooling friendly.
- Added alpha.16 forensic/continuous-stream regression coverage and updated runtime UI schema/documentation.


## 0.1.0-alpha.15 — 2026-08-08

### AI Operator Observatory
- Added an observer-only AI Operator cockpit that mirrors the authoritative Habitat Playwright viewport inside the existing Observatory, including localhost/project pages, without creating a divergent iframe browser state.
- Added a synthetic Nolane AI cursor driven by the real semantic target bounding box, with target brackets, click pulse, typing trail, visible-intent trace and exact viewport coordinate projection.
- Added WORLD / AI OPERATOR / SPLIT observer modes while preserving the no-mutation Observatory boundary; the mode tabs only change local visualization.
- Added browser-style session chrome plus action telemetry for DOM delta, network, console, layout, URL, frame sequence and semantic handle.
- Added action-start receipts before execution so cursor motion can precede the actual click/fill/press visualization, followed by authoritative post-action frame receipts.

### Corrected / hardened
- Live observer frames are written atomically per session and served by a read-only `/api/ui-frame` endpoint; Observatory HTTP threads never call thread-affine Playwright objects.
- Observer frame filenames now sanitize semantic session IDs for Windows compatibility.
- Sensitive password/secret/token/payment-like values are redacted before activity persistence while retaining only safe length/target metadata.
- Pixel frames are explicitly observer evidence only; semantic/runtime assertions remain the verification oracle.
- Restored the historical spectator-only HTML contract by implementing visualization selectors as non-form tab surfaces rather than `<button>`, `<input>` or `<form>` controls.

### Claim boundary
- The cursor is a deterministic visualization of Habitat's semantic browser action target, not OS-level mouse capture.
- The viewport mirror updates at explicit browser observation/action boundaries; alpha.15 is not a full remote-desktop/video stream.

## 0.1.0-alpha.14 — 2026-08-08

### Added / deepened
- Durable Executive Trajectory controller with explicit OBSERVE/UPDATE/DIAGNOSE/RETRIEVE/COMPOSE/DISPATCH/VERIFY/REFLECT/RECOVER/CONTINUE/CLOSE phases.
- Enforced phase-sequence validator, hard step/failure/strategy-switch budgets, and explicit failed/abandoned stop lifecycle.
- Hierarchical milestone DAGs with dependencies, postconditions, priority, verifier references and rollback notes.
- Tamper-evident per-trajectory event hash chains and explicit strategy generation/history.
- Structural strategy switching for stale state, contradiction pressure, verifier gaps, repeated failures and verification failure, including anti-cosmetic fallback when the preferred recovery family equals the current family.
- Failure preservation into provenance-bound Project Memory negative records.
- Fail-closed semantic completion gate over milestone state, verifier artifacts, revision freshness, contradictions, coordination invalidations, invariant verification and trajectory integrity.
- Executive Trajectory/Milestone nodes in the Observatory read model and cinematic graph.
- Manifest schema 10 plus machine-readable executive trajectory, milestone and plan schemas.

### Corrected / hardened
- Structured verifier failures now override a zero process exit code instead of being admitted as success.
- Revision-tagged verifier artifacts are rejected when stale; execution and verification receipts now persist the exact `workspace_revision` observed at run time so real old receipts cannot be replayed after source mutation.
- Executive assurance reads the complete event chain instead of silently truncating at 1,000 events; tampering beyond ordinal 1,000 is therefore still detected.
- Manifest schema 9 remains backward-compatible; `executive_trajectory` is mandatory only for schema 10.
- Shared Playwright browser lifetime now uses workspace leases/refcount; closing the final BrowserRuntime drains the driver immediately instead of leaving short-lived test/CLI processes hanging.
- Current implementation-status, limitations and capability-admission documents are synchronized with the release instead of reporting alpha.11/alpha.9 state.
- Delivery packaging now excludes transient `build/` and `*.egg-info` trees in addition to caches/`dist`, and deterministic ZIP metadata is aligned to the alpha.14 release date.

### Claim boundary
- Executive control is an observable orchestration/assurance mechanism, not access to private model reasoning and not a claim of AGI.
- Verifier admission proves only the explicitly represented receipt/evidence contract at the bound workspace revision; universal correctness still requires domain-appropriate independent oracles.

## 0.1.0-alpha.13 — 2026-08-08

### Added / deepened
- Cognitive resilience analysis for visible-operation loop risk, epistemic pressure and aggregate world health.
- Per-agent Observatory health for stale read-set notifications, loop risk, leases and private residency.
- Context refetch/thrash and authority-I/O amplification accounting.
- Runtime-support correlation for Effect/Dataflow facts with strict same-revision provenance and stronger exact-symbol support.
- DAP reconnect replay identity when a stable debug session identity exists.
- Resumable SSE (`Last-Event-ID`), sequence bounds and retention-gap recovery.
- Adaptive Observatory LOD/clustering, disclosed hidden counts, focus hysteresis, agent trails, temporal heat and event-rate-aware animation.

### Corrected / hardened
- Runtime event persistence is append-only; future direct storage callers cannot overwrite observed history via `INSERT OR REPLACE`.
- Conflicting runtime IDs compare full durable provenance; exact duplicate replay emits no second activity event.
- Telemetry is redacted/bounded before persistence, including DAP sibling `name/value` secret structures; batches above 2,000 records fail instead of silently truncating.
- Counterfactual verification binds overlay generation; changed overlays stale prior results and failed verified worlds cannot be promoted.
- Same-revision memory echoes are suppressed without erasing cross-revision historical memory.
- Observatory static assets no longer send duplicate HTTP responses; core DB frames use one read transaction and external projections disclose their weaker consistency boundary.
- Manifest schema 9, Observatory v2 fields and alpha.13 context-efficiency metrics are admitted by machine-readable schemas.
- Bounded failed-test name lists expose total/truncation metadata and preserve aggregate omitted-failure evidence.

### Evidence
- 240/240 historical + alpha.13 tests pass across completed process shards on the source tree.
- Supplied Nolane AGI corpus: 251 files, 865 symbols, 4,351 occurrences, 29,012 Effect facts and 35,809 Dataflow facts; ordinary warm reconcile hashes zero files.
- Alpha.13 cinematic demo: deliberately surfaces context thrash, loop risk, stale agent cognition, failed counterfactual promotion, Runtime secret redaction and bounded graph projection while preserving canonical verification.

## 0.1.0-alpha.12 — 2026-08-07

- Added revision-bound static Effect Twin and intra-file Dataflow Twin with explicit provider/trust boundaries.
- Added observed Runtime Topology and selected Project World graph providers.
- Added Counterfactual Worlds: fork/apply/evaluate/compare/disposable-copy verify/promote/discard.
- Added ordinal cognitive director (`workspace.cognition.plan`) for stale state, contradictions, experiments, unknowns and assumptions.
- Redesigned Habitat Observatory as a cinematic realtime machine-world: multi-layer neon topology, pulses, tracers, auto-camera, agent orbits and Effect/Dataflow/Runtime signal lanes, while remaining strictly observer-only.
- Added realtime activity events for browser/UI runtime actions.
- Fixed multi-agent invalidation notification ID collisions and same-agent/same-path deduplication.
- Fixed a corpus-discovered Python AugAssign Dataflow persistence bug where metadata could be bound as the trust field.
- Hardened test-matrix shard definitions for alpha.12 and documented host-sensitive combined-run lifecycle variance.
- Supplied-corpus stress: 251 files, 865 symbols, 4,351 occurrences, 29,012 static effect facts and 35,809 dataflow facts; ordinary warm reconcile hashes zero files.

## 0.1.0-alpha.11 — 2026-08-07

### Added
- observer-only realtime **Habitat Observatory**: loopback HTTP/SSE, automatic agent-server/MCP startup, black multicolor topology UI, agent rail, project world, cognitive state, memory/evidence/runtime panels and activity stream;
- separate query-only SQLite observer read model so human visualization cannot share the authoritative control-plane connection;
- append-only activity nervous system with domain-level events below MCP/adapter wrappers;
- explicit MCP `agent_id` handles compatible with the 2026-07-28 stateless-core direction while preserving the compact 12-tool catalog;
- Epistemic Runtime records for facts/assumptions/unknowns/contradictions/constraints/predictions plus bounded cognition-next and unknown-unknown probes;
- Runtime Twin ingestion for OpenTelemetry-shaped spans/logs/metrics and DAP events with revision/path/symbol provenance linkage;
- Semantic Provider Fabric capability reporting for Tree-sitter/LSP/SCIP/native providers without false active-provider claims;
- provenance-bound Project Memory separate from Context Residency: semantic, episodic, procedural, failure, decision and experiment memory with agent scope, evidence links, supersession and invalidation;
- alpha.11 schemas, live screenshot evidence, supplied-AGI stress, architecture/research/agent-integration documentation and 198-test regression matrix.

### Corrected during implementation
- threaded Observatory initially reused the Workspace SQLite connection and failed cross-thread; replaced with per-request read-only/query-only connections rather than disabling SQLite thread checks;
- first MCP portability attempt would have expanded the compact catalog with a separate attach tool; identity minting was folded into `habitat_start_task`;
- Observatory initially showed only activity after browser connect; bounded recent-event replay was added to the initial snapshot;
- Project Memory recall initially risked private-memory leakage through an overly broad store query; agent recall now returns shared memory plus that agent's private memory only;
- alpha.11 AGI stress harness incorrectly passed `agent_id` to `context_fetch_pages`; the harness was corrected to the Workspace contract and the failed run is preserved in self-audit;
- direct Chromium loopback navigation is blocked by policy in this release environment; screenshot verifier falls back to the exact live snapshot rendered by the same UI assets, never mock fixture data.

### Claim boundary
- the Observatory is a spectator UI, not an IDE/terminal/human control plane;
- no raw private model chain-of-thought is collected or displayed;
- Runtime Twin telemetry correlation is not complete causal proof;
- Tree-sitter/LSP/SCIP capability discovery does not mean those providers are installed or used;
- alpha.11 does not establish AGI capability or model-quality superiority.

## 0.1.0-alpha.10 — 2026-08-07

### Added
- optional Bubblewrap filesystem/network containment provider with real host capability probe and fail-closed `filesystem-contained` configuration;
- agent read-set observation ledger, invalidation notifications and selective revalidation;
- path-scoped optimistic transaction rebase with exact touched-path/destination preconditions;
- agent-private residency plus private hypothesis belief views over shared project hypotheses;
- host approval tokens, path-scoped approval policy and mutation policy preflight without side effects;
- cognitive-state retention planning/compaction, private-agent forgetting and POSIX state permission hardening;
- project invariant registry and evidence/verifier/contradiction links;
- Git branch/worktree/conflict/commit-impact cognition and lock-aware direct dependency world;
- bounded world summary and explicit scoped repository-guidance discovery without automatic context injection;
- same-model A/B harness v3 comparability gate requiring observed model/scaffold identity and independent evaluator for strong evidence readiness;
- alpha.10 schemas, demo/stress harnesses and adversarial regressions.

### Corrected / hardened
- disjoint project revision changes no longer reject a transaction solely because global revision changed; touched-path drift still fails closed;
- an agent with pending observed-source invalidation cannot commit until it explicitly performs selective revalidation;
- weak derived/heuristic semantic edges are capped during graph propagation instead of accumulating into unsupported high-confidence context;
- Bubblewrap presence alone is not treated as a sandbox: a minimal namespace/mount execution must succeed before the provider is admitted;
- agent-private cognitive deletion does not erase shared revisions/transactions/evidence provenance;
- repository guidance is discoverable but not implicitly injected, reducing instruction/context pollution risk;
- release identity is locked across `VERSION`, runtime `__version__` and PEP 440 package metadata.

### Claim boundary
- full sandbox availability is host/provider specific and is false on hosts where the configured Bubblewrap profile cannot be executed;
- no Firecracker/microVM, production Cloudflare Computer backend, distributed consensus or universal language precision is claimed;
- belief/invariant/uncertainty annotations remain explicit non-probabilistic/non-formal cognition scaffolds;
- A/B infrastructure does not establish coding superiority without a real controlled experiment and evaluator.


## 0.1.0-alpha.9 — 2026-08-07

### Added
- versioned operator policy service for source read/edit, execution and external-browser decisions;
- Linux `network-contained` execution profile with user/network namespaces, finite resource limits and secret-like environment scrubbing, explicitly not a filesystem sandbox;
- agent sessions, per-agent context-utility namespace, path leases and transaction ownership enforcement;
- Git temporal cognition (`status`, `history`, `blame`, line provenance);
- direct Python/Node/Maven dependency-manifest cognition and lockfile presence;
- correlation-aware hypothesis evidence assessment with source-group diminishing returns;
- MCP-session agent identity propagation through the existing compact 12-tool catalog;
- executable same-model A/B orchestration harness that requires external agents/evaluator and does not synthesize success.

### Corrected / hardened
- policy/lease/ownership checks occur before consequential source or execution side effects;
- untrusted policy refuses providers that do not claim full filesystem sandboxing;
- agent-specific utility cannot contaminate another agent's ranking prior;
- correlated repeated receipts from one provider do not count as independent consensus;
- detached execution source mutation remains fail-closed;
- alpha.9 benchmark/demo scripts run directly from a checkout/delivery root without requiring caller `PYTHONPATH`.

### Claim boundary / still open
- `network-contained` is partial containment, not hostile-code production sandboxing;
- leases are local SQLite coordination, not distributed consensus/CRDT/semantic merge;
- dependency cognition is direct-manifest only, not transitive resolution or API compatibility;
- evidence assessment is heuristic and explicitly not calibrated probability;
- the A/B harness is infrastructure only; no same-model coding-superiority result is claimed.

## 0.1.0-alpha.8 — 2026-08-07

### Added
- integrity-assisted perception reconciliation and explicit deep integrity scrub boundary;
- sparse authoritative line-range source reads with separate model-visible/authority I/O accounting;
- `.gitignore`/`.habitatignore` source admission, narrowed hard-ignore policy and self-index prevention;
- write-ahead local transaction journal with startup recovery;
- CRLF + executable-mode preservation and first-class create/delete/move file mutation operations;
- Unicode-aware task tokenization and persistent symbol-term inverted index;
- coherent multi-concept confidence support and strict budget/type validation;
- bounded execution capture, total stdout/stderr accounting, secret redaction, environment fingerprint and project Python environment discovery;
- browser external-network deny-by-default;
- revision-bound hypothesis/evidence/experiment cognition layer and schemas;
- alpha.8 adversarial regression, >1 MB sparse-I/O demo and supplied-AGI-ZIP stress harness.

### Corrected from the alpha.6 audit
- same-size/restored-mtime edits can no longer remain silently stale on POSIX ordinary reconcile; Windows deliberately deep-verifies until a stronger native change-feed exists;
- Context VM no longer reads a complete source file merely to return one exact symbol page;
- stale context feedback and stale-context episode start are rejected;
- invalid/missing/completed episodes are validated before transaction/test side effects;
- resolved/full-suite evidence is scope-aware rather than globally over-resolved;
- mutation no longer normalizes CRLF or strips ordinary mode bits;
- local interrupted transactions have WAL/startup recovery rather than exception-only rollback;
- unique project-wide bare Python names no longer create false cross-file call edges without binding/import evidence;
- output cap is now a capture-memory boundary rather than post-`communicate()` truncation;
- ignored/private files and Habitat's own state no longer enter the source index by default;
- managed single-file workspace reuse requires explicit reset and does not retain old source/cognitive identity;
- high-level MCP mutation distinguishes successful commit from post-commit verification error;
- truthy-string booleans are rejected instead of Python-coerced;
- non-UTF8 text is labeled lossy rather than claimed byte-exact.

### Claim boundary / still open
- local execution remains unsandboxed; hostile-repository confinement is not solved;
- local WAL recovery is not distributed ACID/2PC;
- enterprise retention/encryption/secret-state governance is incomplete;
- multi-agent concurrency/leases/merge semantics remain incomplete;
- Java and many other languages remain below Python/TypeScript semantic precision;
- hypothesis confidence is an agent belief annotation, not calibrated probability;
- no same-model Habitat-vs-normal-tools coding-superiority claim is admitted.

## 0.1.0-alpha.7 — 2026-08-07

### Added
- composable `SourceAuthority` + `ExecutionProvider` substrate beneath the compatibility `ProjectBackend`;
- authority/executor identity in checkpoints and execution receipts;
- fail-closed detached-executor source-mutation guard;
- persistent TypeScript LanguageService process with dirty-partition traversal and explicit host lifecycle;
- bounded Jedi Project LRU plus persistent semantic output partitions;
- line-budget `workspace.explore` semantic-region API that reads zero exact source bytes during exploration;
- context page-fault ledger and explicit utilization/efficiency reporting;
- cross-revision workflow causal graph;
- host-level idempotent runtime-service shutdown.

### Corrected during implementation
- preserved legacy `source_authority` manifest semantics while adding independent provider fields;
- rejected unbounded Jedi workspace-lifetime retention after lifecycle stress;
- fixed persistent TypeScript stdio cleanup and shared runtime shutdown;
- kept external test-runner latency variance visible instead of relabeling timeouts as passes.

### Claim boundary
- line/source-byte metrics are not token metrics;
- workflow causal edges are provenance, not complete program causality;
- no production Cloudflare Computer adapter or same-model coding-success superiority was claimed.

## 0.1.0-alpha.6 — 2026-08-07

### Added
- pluggable ProjectBackend source/execution substrate with explicit authority/materialization identity;
- backward-compatible local backend plus DirectoryMirrorBackend remote-like contract double;
- authoritative exact-source routing for inspection, context paging, Residency and mutation;
- targeted known-path backend/workspace hydration without whole-project enumeration;
- backend/execution provenance on discovered capabilities and structured execution receipts;
- bounded task-conditioned context utility feedback that cannot create candidates or alter source trust;
- selective next-page planning with no-gold abstention and source-byte/page budgets;
- append-only work episodes linking context, transaction, revision, verification, checkpoint and outcome;
- backend identity binding in checkpoint/resume and optional active-episode checkpoint binding;
- local-vs-mirror semantic equivalence benchmark and alpha.6 AGI corpus stress harness;
- alpha.6 architecture/research/writing-plan/admission documentation.

### Corrected during implementation
- alpha.5 workspace-manifest schema initially rejected alpha.6 backend metadata; schema 3 was added while preserving schema-2 compatibility;
- mirror source-drift probe expected a late page digest fault, but backend reconciliation correctly invalidated the context earlier; the verifier now asserts the stronger `context-revision-stale` behavior;
- Context Residency still estimated symbol bytes through the compiler mirror; exact source estimation now routes through backend authority;
- backend-equivalence harness assumed nonexistent Store convenience APIs and then wrong occurrence column names; harness now uses the actual storage contract;
- first targeted-refresh refactor accidentally attached targeted metrics to deep refresh and referenced `normalized`; release tests caught the NameError and the paths were separated;
- targeted refresh still enumerated the compiler mirror even after backend targeted hydration; it now resolves only the supplied candidate paths.

### Claim boundary
- alpha.6 proves backend separation/equivalence only on local and directory-mirror fixtures;
- no Cloudflare Computer network adapter or production remote synchronization is claimed;
- context feedback is a bounded attention prior, not learning at model weights or source authority;
- source-byte/page/benchmark metrics remain deterministic plumbing evidence, not token or coding-superiority claims.

## 0.1.0-alpha.5 — 2026-08-07

### Added
- static Python/Jedi precision provider with exact call-site evidence, provider-ranked occurrences and per-source semantic partitions;
- dirty-source TypeScript semantic traversal partitions over a whole-project Program/TypeChecker;
- calibrated Context Compiler concept coverage, explicit low-confidence abstention and no-gold retrieval behavior;
- virtual context address space with revision/digest-bound source pages, explicit page faults and byte-budgeted prefetch;
- content-addressed Merkle project snapshots/diffs derived from already-admitted source digests without rereading source bytes;
- first-class active/resolved runtime and test evidence integrated into live task context without contaminating source authority;
- fail-closed Python/Jedi project-wide semantic rename staged as exact digest-bound identifier spans;
- semantic runtime UI assertions over DOM/accessibility/runtime state with explicit oracle/screenshot disclosure;
- optional compact MCP adapter targeting the 2026-07-28 protocol line while keeping Habitat core protocol-independent;
- 200-distractor context-precision harness plus supplied-AGI-ZIP stress and end-to-end alpha.5 demo.

### Corrected during implementation
- resolved evidence was still reachable through lexical FTS; live retrieval now gates evidence on active state;
- an early Jedi overlay removed weaker parser call facts for an entire caller instead of only a proven call-site; supersession is now exact-site scoped;
- equal-trust occurrence dedup could retain the generic linker over Jedi/TypeScript semantic providers; precise providers now win deterministic ties;
- Python/TypeScript provider API-surface identities were initially too sensitive to body text; body-only changes now preserve unrelated partitions while public surface changes expand invalidation;
- a no-gold AGI query was initially overconfident because one common term ("matrix") matched the corpus; confidence now requires independent concept coverage;
- concept coverage originally undercounted identifier morphology such as credential/credentials and validation/validate; indexed fuzzy identifier evidence now supports those concepts without reading source;
- virtual page faults originally reconciled the whole workspace per page; the workspace now reconciles once and each page validates the exact bytes it reads;
- benchmark/release harness key and command-composition errors were kept visible and corrected instead of reusing stale reports.

### Still not claimed
- universal LLM token/cost reduction or coding-success uplift;
- fully persistent/incremental TypeScript language-service state;
- universal Java/LSP/SCIP semantic precision;
- production hostile-code isolation;
- framework-complete UI provenance;
- real MCP runtime admission on a host without the optional SDK;
- AGI capability.

## 0.1.0-alpha.4 — 2026-08-07

### Added
- per-source base semantic relation partitions keyed by unresolved facts and relevant candidate-resolution surfaces;
- dirty-closure behavior where candidate-surface changes invalidate affected reverse partitions;
- persistent Context Residency storing semantic references/provenance without copied exact source bodies;
- residency freshness, pinning, explicit eviction, visible overcommit and bounded source page-in;
- fresh/task-relevant resident objects as a bounded Context Compiler continuity prior;
- stronger checkpoint/resume binding to source revision/root, compiler/provider identity, event cursor and resident state;
- `direct`, `selective-revalidate` and `reorient` resume modes;
- TSX/JSX static event-handler extraction plus `handles_event` semantic edges and runtime handler source hints;
- protocol trace sessions measuring calls, duration, request/response bytes and exact-source bytes;
- alpha.4 schemas, end-to-end demo, AGI-ZIP stress harness and trace benchmark harness.

### Corrected during implementation
- removed source digest from relation-partition fingerprint after proving it caused unnecessary body-only recomputation; compiler/provider identity remains a separate invalidation boundary;
- updated a legacy alpha.3 regression whose expectation encoded the old coarse semantic-cache behavior;
- corrected residency verifiers that confused provenance fields with copied source payload and assumed unstable orientation cardinality;
- added fail-closed validation for optional alpha.4 object/session parameters;
- made telemetry explicitly non-authoritative and regression-tested recorder failure;
- made pinned-capacity violations explicit instead of silently evicting a pin.

### Still not claimed
- lower LLM token usage or higher coding success;
- fully incremental TypeScript Program/TypeChecker state after JS/TS edits;
- universal framework/runtime source ownership;
- production hostile-code isolation;
- AGI capability.

## 0.1.0-alpha.3 — 2026-08-07

### Added
- provider-domain semantic caches so unrelated documentation/Python edits can reuse the TypeScript whole-project semantic domain;
- relation/occurrence set-diff persistence with explicit graph-delta receipts;
- targeted ordinary reconcile that hashes only metadata-identified candidates;
- process-local observation-only source watcher with foreground semantic admission;
- explicit separation between watcher acceleration and deep-hash mutation integrity;
- immutable context-handle refresh with retained/added/removed/missing object deltas;
- bounded Context Materializer with exact symbol-body source budgeting and explicit omissions;
- batch semantic inspection;
- TSX/JSX literal `id`/`data-testid` UI semantic anchors plus component `renders` relations;
- runtime DOM→JSX/component ownership candidates with trust downgrade on ambiguity;
- deterministic navigation-plumbing A/B harness and a separate controlled same-model agent benchmark contract;
- alpha.3 architecture, writing plan, capability diagnosis, stress/demo evidence and AGI-method audit.

### Corrected during implementation
- Alpha.2 per-file reuse was not equivalent to incremental graph persistence; global relation/occurrence replacement was replaced with set-diff synchronization.
- Root-wide semantic invalidation unnecessarily reran TypeScript analysis for unrelated edits; provider-relevant domain digests now gate reuse.
- A watcher could have been mistaken for an integrity oracle despite metadata-preserving edits; mutation preflight remains deep-content-hash authoritative and is adversarially tested.
- JSX elements carrying the same `id` and `data-testid` initially emitted duplicate stable semantic IDs; parser output now deduplicates the anchor/line identity.
- The navigation benchmark initially failed by treating `sqlite3.Row` as a dict with `.get()`; the harness now uses the storage contract and failure remains recorded in self-audit.
- Repeated `orient→inspect` calls still preserved some human-style navigation overhead; Context Materializer now packages bounded symbol bodies in one revision-bound receipt rather than dumping whole files.

### Evidence boundary
- Included tests/demo/stress establish the bounded synchronization, cache, graph-delta, context and UI-source mechanisms on the included fixtures.
- The navigation-plumbing comparison is deterministic engineering evidence, not an LLM-agent benchmark.
- No token-reduction, universal speedup, coding-success uplift, production sandbox or framework-complete UI ownership claim is admitted.

## 0.1.0-alpha.2 — 2026-08-07

### Added
- semantic trust grade and first-class definition/call/import occurrences;
- Python project linker for qualified imports, aliases, relative imports and call targets without importing/executing project code;
- TypeScript whole-project `Program` + `TypeChecker` linker with compiler-resolved imports/calls and cacheable project-semantic output;
- semantic suppression of same-callsite ambiguous TypeScript fallback edges when the compiler resolves a declaration;
- append-only workspace event journal and revision diff API;
- affected-test graph with evidence paths and targeted Python verification execution;
- Context Compiler V3 trust distribution and compact decision packet;
- runtime browser event-listener instrumentation that maps external JS handler registrations back to source;
- semantic HTML anchors for `id`, `data-testid`, and stable form-control `name`;
- process-shared Playwright/Chromium engine so multiple Habitat workspaces do not invalidate one another;
- provider report exposing Tree-sitter/LSP/SCIP gaps rather than pretending those lanes are active;
- alpha.2 schemas, demo, AGI-ZIP stress evidence and detailed implementation plan.

### Corrected during implementation
- Python module-symbol indexes duplicated a top-level symbol under identical name/qname keys, making a qualified call look ambiguous; the index is now deduplicated and regression-tested.
- TypeScript compiler-semantic edges originally coexisted with incorrect heuristic same-name targets from the same callsite; semantic callsite evidence now suppresses those weaker alternatives.
- Context graph roots could reinforce themselves through A→B→A traversal; graph evidence now compounds across distinct roots but not self-cycles.
- Test source text could seed implementation graph expansion and reinforce unrelated same-name functions; implementation graph expansion now begins from production roots and discovers tests downstream.
- A full-suite run exposed Playwright sync-driver collisions across workspaces that individual UI tests missed; browser engine lifetime is now process-shared while contexts remain workspace-scoped.
- Alpha.1-style compiler caches lacked a semantic artifact version/fingerprint; alpha.2 now treats them as stale, recompiles once, and fingerprints provider/toolchain identity before reuse.
- Project-semantic cache reuse originally considered source/root identity but not current provider fingerprint; toolchain/provider drift now invalidates the cache even when source bytes are unchanged.
- Direct benchmark execution initially failed because `benchmarks/` became Python's import root; benchmark scripts now self-bootstrap the delivery root and are verified from an extracted release.
- Release CLI smoke exposed stale README syntax (`ingest --workspace`) that did not match the actual `create SOURCE WORKSPACE` operator CLI; quick-start commands now match the executable parser.

### Evidence boundary
- Controlled fixtures demonstrate stronger supported Python/TypeScript cross-file semantics, event receipts, affected-test selection, targeted Python verification and runtime JS handler source hints.
- AGI-ZIP stress demonstrates per-file recompile/cache behavior on that corpus.
- No claim is made for universal code understanding, universal token reduction, full LSP/SCIP coverage, production sandbox isolation or framework-complete UI source mapping.

## 0.1.0-alpha.1 — 2026-08-07

### Added
- per-file incremental compile cache and deep-hash refresh reuse;
- semantic provider contract and TypeScript compiler-API parser/diagnostic provider;
- first-class diagnostic objects;
- Context Compiler V2 with task classification, multi-lane candidates, bounded graph expansion, diversity caps and paging handles;
- bounded exact source paging;
- semantic symbol-source transaction primitive, staged unified diff, multi-file preflight and semantic diff receipt;
- toolchain fingerprints and structured test result normalization;
- source→test relation and verification plan;
- runtime Playwright/Chromium semantic UI with project-resource routing, ARIA, DOM state, layout, events, semantic actions/deltas and optional screenshots;
- initial runtime UI→HTML/CSS source hints;
- persistent task checkpoint/resume invalidation;
- protocol capability negotiation and new alpha.1 methods.

### Corrected during implementation
- Context V2 initially allowed a superficial lexical `login` hit to outrank `validate_credentials`; scoring was changed to reward multi-concept structural coverage and the regression is tested.
- Initial browser provider attempted localhost/file navigation and hit environment policy `ERR_BLOCKED_BY_ADMINISTRATOR`; project HTML/resource loading was redesigned around `set_content` + intercepted `habitat.local` resource fulfillment instead of weakening the test.
- Alpha.0 `refresh()` reparsed the complete repository. Alpha.1 now caches per-file compiler facts and reparses only changed digests.

### Still not claimed
- production sandboxing;
- LSP/SCIP whole-program semantic precision;
- framework-level UI→component mapping;
- measured LLM token savings or task-success uplift.

## 0.1.0-alpha.0
- Initial executable vertical slice: ingestion, semantic twin, Context Compiler alpha, typed execution, transactional text mutation, static semantic HTML and NDJSON protocol.
