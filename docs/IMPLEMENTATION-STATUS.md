# Implementation Status — 0.1.0-alpha.20

## Implemented and executable

### 0.1.0-alpha.20 Foundation Convergence closure
- the post-alpha.19 Foundation Convergence implementation series is complete under the repository-defined 12-criterion active certification manifest; the original architecture proposal remains historical design provenance rather than self-certifying completion evidence;
- release identity now includes the release-admission manifest command, so a stale release-runbook version fails the same machine gate as stale package/runtime/plugin/current-document identity;
- exact-commit CI evidence remains the authority for closure; descriptive benchmark/scale observations are not promoted into production-performance claims without an independent matching baseline.

### Agent substrate and source authority
- folder / ZIP / loose-file ingestion with ordinary canonical project bytes as source authority;
- independent SourceAuthority + ExecutionProvider beneath the backend compatibility facade;
- JSON stdio agent server, direct protocol embedding, optional MCP adapter, explicit agent handles;
- policy, approvals, path leases, read-set invalidation, selective revalidation and optimistic transaction controls.

### Cognitive project world
- Semantic Twin plus sparse Context VM, exact-source paging, evidence, hypotheses/experiments, work episodes and invariants;
- Effect Twin, Dataflow Twin, Runtime Twin, Project World and revision-bound Counterfactual Worlds;
- Epistemic Runtime for facts/assumptions/unknowns/contradictions/constraints/predictions;
- Project Memory distinct from context residency, including semantic/episodic/procedural/failure/decision/experiment records;
- alpha.13 loop/context-thrash/epistemic-pressure and world-health diagnostics over observable Habitat operations.

### Alpha.17 stability completion
- UI semantic handles are allocated from an internal per-page WeakMap, overwrite project-supplied handle attributes, preserve readable unique-id handles where possible, encode unsafe ID characters, and suffix duplicate IDs/test IDs rather than becoming ambiguous;
- console/network observation buffers are bounded between observations and report dropped event counts instead of allowing a noisy page to grow memory without limit;
- UI viewport/action inputs fail fast, context/page creation lives entirely inside the cleanup boundary, and observer frame tuples are read under the same session lock used by the CDP publisher;
- Observatory operator reconstruction has a dedicated durable UI-event window and direct open-receipt recovery, so unrelated machine-world activity cannot evict the active browser projection;
- stream epoch changes reset frame/stream monotonic counters rather than maxing a new generation against an old one;
- Observatory read-only SQLite connections use portable file URIs and `::1` now uses a real IPv6 HTTP server with a bracketed URL;
- source-authority atomic writes use unique same-directory temporary files, preserving atomic replace semantics under same-process concurrency;
- current installation/protocol/release documentation is synchronized with the shipped release.

### Alpha.16 AI Operator observability
- continuous loopback CDP WebSocket mirror on supported Chromium hosts, with cooperative-CDP and snapshot fallbacks reported explicitly;
- authoritative per-session observer frames still originate from the exact page controlled by `ui.runtime.*`;
- collision-resistant session frame keys, monotonically increasing versioned frame sequence and a bounded six-frame ephemeral ring, separate from explicit assertion screenshots;
- semantic action preview includes handle, role/name, target rectangle, normalized/absolute pointer coordinates and viewport geometry;
- privacy filter redacts password/secret/token/payment-like values across DOM, ARIA, inline handlers, console text and credential-bearing URLs before public persistence/display;
- continuous transport binds DevTools to loopback with exact allowed origin and browser routing denies project-page access to that privileged port;
- action completion receipt includes DOM delta counts, console/network counts, layout diagnostics, resulting URL and frame sequence;
- Observatory reconstructs active operator state only from durable activity receipts and serves frame bytes read-only, avoiding cross-thread Playwright calls;
- WORLD / AI OPERATOR / SPLIT cinematic modes with simulated AI cursor, click pulse, target brackets, typing visualization and operator timeline;
- UI activity automatically focuses the operator viewport unless the human temporarily selected another visualization mode;
- viewport pixels remain an observer mirror, never a pass/fail oracle.

### Alpha.14 Executive Trajectory
- durable trajectory records for long-horizon work with explicit goal, agent/episode binding, strategy generation, budgets and metrics;
- hash-chained append-only executive events across OBSERVE/UPDATE/DIAGNOSE/RETRIEVE/COMPOSE/DISPATCH/VERIFY/REFLECT/RECOVER/CONTINUE/CLOSE;
- enforced control-phase sequence with explicit recovery after failed/inconclusive control steps and reflection before successful closure;
- hard metering for `max_steps`, `max_failed_steps`, `max_strategy_switches`, and Habitat-measured `max_wall_time_ms`;
- fail-closed provider-reported accounting for `max_tool_calls`, `max_input_tokens`, `max_output_tokens`, and `max_compute_ms`: every admitted control step under those limits carries a validated provider/receipt identity in the hash-chained event record, while the reported usage values are not independently verified by Habitat;
- provider receipt replay is rejected before event/metric mutation, and provider-metered totals are re-derived from the complete executive event history rather than trusted from mutable counters;
- unknown extension budget keys remain explicit under `unmetered` instead of being interpreted as measured zero consumption;
- explicit failed/abandoned stop termination remains available after budget exhaustion;
- hierarchical milestones with dependency DAG, explicit postconditions, priority, verifier linkage and rollback notes;
- structural strategy families: direct analysis, reframe, causal intervention, rival hypothesis, external oracle, dependency replan and scope reduction; repeated failure cannot be admitted as a cosmetic switch to the same family;
- failed/inconclusive steps are preserved as provenance-bound failure memory;
- high/critical milestone verification is fail-closed: invented verifier IDs, failed receipts, contradictory structured failure, and revision-stale verifier artifacts are rejected; real run/verify receipts persist their observed `workspace_revision`;
- assurance validates the complete executive event chain rather than a bounded 1,000-event projection, so long-horizon tail tampering cannot be hidden by UI-style limits;
- completion gate checks trajectory integrity, dependency defects, critical postconditions, verifier status, current revision, pending agent invalidations, unresolved contradictions and critical invariant-verifier gaps.

### Runtime and observability
- Runtime Twin ingestion for normalized OpenTelemetry-shaped span/log/metric records and DAP events;
- append-only activity nervous system and resumable SSE with retention-gap signaling;
- read-only loopback Habitat Observatory using a separate SQLite query-only read model;
- cinematic graph includes Executive Trajectory and Milestone entities, active strategy and executive counts without exposing raw private chain-of-thought;
- process-shared Playwright runtime uses explicit leases so the final workspace close drains the browser driver deterministically;
- adaptive LOD/clustering, focus hysteresis, temporal heat and agent trails remain inherited from alpha.13;
- operational SLO admission uses immutable profiles/samples, preserves unavailable measurements as `None`, fails closed on missing or insufficient evidence, and emits deterministic commit-bound reports only when externally measured samples are explicitly supplied;
- deterministic scale evidence reuses the canonical Foundation baseline lifecycle over generated fixtures, binds multi-cycle raw observations to a source commit and workload fingerprint, runs the default collector in a fresh child process per cycle, and admits only explicit collector-reported peak RSS in bytes with measurement method/scope provenance; each default baseline also reports a normalized measurement environment (OS/release, machine architecture, Python implementation/version and logical CPU count), scale evidence binds its fingerprint, mixed environments across cycles fail closed, and SLO conversion requires an independent workload- and environment-matching baseline.

### Machine contracts
- workspace manifest schema 10 advertises `world_model.executive_trajectory=true`;
- schema 9 remains backward-validation-compatible;
- dedicated schemas exist for executive trajectory, milestone and plan plus alpha.14 world-health / Observatory additions;
- executive trajectory schema documents measured/provider-reported budget-state accounting while preserving historical compatibility through optional additions and `additionalProperties`;
- storage schema is 22 with durable executive tables.

## Partial / bounded
- strategy selection/switching is deterministic heuristic diagnosis over explicit Habitat state, not learned meta-reasoning;
- provider-reported tool/token/compute usage is governed and hash-chained but is not independently verified billing truth; Habitat-measured wall time is host wall-clock evidence, not a distributed monotonic-clock guarantee;
- a verifier artifact proves only the represented receipt/evidence contract; universal program correctness still requires domain-appropriate independent oracles;
- milestone postconditions are explicit strings plus verifier linkage, not a general theorem prover;
- Semantic Fabric discovers/report providers, but Tree-sitter/LSP/SCIP are not universally active with equal precision;
- Runtime Twin is normalized ingress, not a full OTLP Collector or universal debugger orchestrator;
- Project Memory retrieval and cognitive planning are bounded heuristics and never source truth;
- full hostile-code isolation remains provider/host dependent; unsupported containment must not be described as a production sandbox;
- non-Python/TypeScript semantic precision and live production-world cognition remain uneven;
- deterministic scale evidence records OS-reported peak RSS for the fresh benchmark process where the host probe is supported, but that value is a process-lifetime peak rather than per-operation allocation attribution; its environment fingerprint prevents obvious cross-environment SLO joins but is only a declared comparison class, not proof that two physical hosts have identical hardware/load characteristics. A separately curated production baseline remains absent, so CI scale artifacts remain descriptive/non-gating and do not establish production SLO compliance or performance superiority.

## Not implemented / not claimed
- raw model chain-of-thought capture/display;
- AGI capability or AGI-quality superiority;
- universal causal inference from telemetry;
- universal language/compiler precision;
- production distributed consensus for multi-agent mutation;
- hostile-code microVM safety on every host;
- automatic proof that all software behavior is correct;
- same-model Habitat-vs-filesystem superiority without controlled external experiments.
