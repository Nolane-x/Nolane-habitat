# Habitat 0.1.0-alpha.20 Limitations and Claim Boundary

## Executive Trajectory is control architecture, not hidden reasoning
Alpha.14 records observable work products: goals, milestones, phases, receipts, failures, strategy changes and completion gates. It does not request, store or expose a model's raw private chain-of-thought. A trajectory is therefore an auditable execution/control record, not a transcript of internal cognition.

## Executive resource accounting has explicit authority boundaries
Executive Trajectory hard-enforces step count, failed-step count, strategy-switch count, and Habitat-measured host wall time. Declared tool-call, input-token, output-token and compute-time limits are enforced only from validated provider-reported usage receipts that carry non-empty provider/receipt identities and become part of the executive event hash chain. Those provider values are not independently verified by Habitat and must not be treated as authoritative billing telemetry. Host wall-clock accounting is also not a distributed monotonic-clock guarantee. Unknown extension budget keys remain explicit under `unmetered` rather than being silently treated as measured zero consumption.

## Phase control is explicit and conservative
Control-step phase skipping is rejected. Auxiliary milestone records can still be written without pretending to advance the control phase. Successful CLOSE requires a current successful control VERIFY followed by REFLECT/CONTINUE; failure/abandon uses a separate explicit stop path and does not claim successful completion.

## Strategy switching is bounded
The current classifier maps explicit symptoms such as stale observations, contradictions, verifier gaps, repeated failures and failed verification to a small strategy family. This is useful anti-stagnation control, but it is heuristic rather than a learned optimal meta-controller.

## Verification is only as strong as the admitted oracle
An admitted run/evidence/experiment artifact can establish that its represented verifier succeeded at the bound workspace revision. It cannot establish universal correctness outside that contract. High-impact domains need independent, domain-appropriate oracles and potentially multiple non-correlated verifiers.

## Revision freshness is explicit, not magical
Habitat-owned execution and verification receipts persist the `workspace_revision` observed at execution time. Revision-tagged verifier artifacts are rejected when stale and successful VERIFY events become stale after workspace revision changes. External systems with weak or missing revision provenance cannot gain stronger guarantees merely by being ingested into Habitat.

## Assurance history is unbounded by UI projection limits
Completion/hash verification reads the complete executive event chain. Callers may request bounded event projections for UI/inspection, but those limits are not reused by the assurance path; otherwise events after a display cap could escape integrity verification.

## Completion gates can be conservative
Open contradictions, stale agent notifications, missing critical invariant verifiers, milestone failures, dependency defects or trajectory-chain corruption block closure. This fail-closed behavior may require explicit cleanup/resolution even when a human believes the task is already finished.

## AI Operator cursor is a semantic visualization, not OS mouse capture
Alpha.15 derives cursor position from the target element rectangle observed in the real Playwright page. The Observatory animates a synthetic pointer toward that coordinate. This is intentionally deterministic and inspectable, but it is not a recording of an operating-system cursor or hidden model motor intent.

## Operator frames are visual mirrors, not verification oracles
Habitat can continuously mirror the controlled Chromium page through a loopback CDP WebSocket. Semantic/accessibility/runtime assertions still decide pass/fail; pixels never become verification evidence. Browser throttling, host policy or missing optional transport can reduce cadence, in which case the reported mode falls back to cooperative CDP or snapshots. This is not an OS-level remote desktop guarantee.

## Localhost visibility follows the AI browser session
If the agent opens a loopback URL, the Observatory mirrors the same browser page instead of constructing a second iframe state. Continuous mode uses a temporary DevTools endpoint bound to `127.0.0.1` with an exact WebSocket origin; project-page routes explicitly deny that privileged port. The endpoint exists only while the shared Chromium runtime is alive.

## Typed-value visibility is privacy filtered
Non-sensitive fill/press values may be shown to explain an action. Sensitive fields redact values and do not publish their length. Alpha.16/17 additionally scrubs ARIA snapshots, inline-handler text, console assignments, common bearer credentials and credential-bearing URL query/fragment values. Detection is still heuristic: applications should not place secrets into arbitrary labels or non-secret DOM text.

## Observatory is intentionally not a control surface
The realtime UI is for human spectators. It exposes no mutation HTTP verbs and no terminal/editor controls. Agent/control-plane operation must remain independent of browser/SSE availability.

## Shared browser lifecycle is process-scoped but leased
Browser engine reuse remains process-shared for efficiency, while each BrowserRuntime holds a lease. Closing the final lease drains Playwright immediately. An abrupt host kill can still bypass normal cleanup, so host-level shutdown remains best-effort and idempotent.

## UI event capture is bounded
Console and network events are bounded between observations. When a page emits more events than the buffer can retain, Habitat reports drop counts rather than pretending the returned tail is complete. This protects long-running sessions from unbounded observer memory while keeping the loss explicit.

## Semantic UI handles are runtime identities, not project authority
Habitat overwrites project-supplied `data-nolane-habitat-handle` values and allocates unique per-page identities. Duplicate DOM IDs/test IDs receive unique suffixes. Handles remain runtime/session-local and should not be persisted as cross-session source identities.

## Runtime Twin is observed telemetry, not causal proof
OpenTelemetry-shaped spans/logs/metrics and DAP events can be linked to source when provenance permits. Correlation and linkage are not proof of causality, and missing telemetry is not proof that behavior did not occur.

## Semantic precision is uneven
Python and TypeScript have the strongest shipped semantic lanes. Tree-sitter/LSP/SCIP are capability/provider surfaces, not universal compiler-grade precision for every language and framework.

## Project Memory can be stale
Memory records bind revision/provenance/evidence and can be invalidated or superseded. Recalling a memory never makes it canonical source truth. Alpha.14 intentionally preserves negative/failure memory rather than silently deleting unsuccessful paths.

## Execution security remains provider dependent
Policy/containment boundaries are inherited. A successful local capability probe is not a universal hostile-code security proof; alpha.17 does not claim Firecracker/microVM isolation on every host.

## Performance and test process
Some historical combined test matrices can exceed an external runner wall clock even when independent shards finish. Alpha.17 evidence should distinguish completed PASS/FAIL shards from runner timeouts rather than relabeling timeouts as successes.

## Scale-memory evidence is process-level, not allocation attribution
The deterministic scale harness can carry OS-observed peak resident-set size reported by the canonical Foundation baseline collector. The default scale path runs each cycle in a fresh child process so one cycle's lifetime peak cannot leak into another, and missing/unsupported probes remain `None`. The value is still the peak RSS of the whole benchmark process lifetime, not a proof of the bytes allocated by cold ingest, reconcile, orientation, or Habitat alone. It varies with Python, loaded providers, libraries, host policy and runner image.

## Measurement-environment matching narrows claims but does not prove host equivalence
The Foundation baseline emits a normalized comparison record containing OS/release, machine architecture, Python implementation/version and logical CPU count. Scale evidence binds a SHA-256 fingerprint of that record and rejects mixed-environment cycles; operational SLO conversion fails closed when current/baseline evidence lacks a comparable environment or the fingerprints differ. This prevents obvious cross-OS, cross-Python or cross-machine-class comparisons from silently becoming one claim. It does not capture every variable that can affect performance: CPU model/frequency, memory topology, virtualization, power state, background load, filesystem/cache state and installed semantic-provider behavior may still differ. A matching fingerprint is therefore necessary evidence scope, not proof of physical-host equivalence. A separately curated production baseline under controlled conditions is still required before this evidence can participate in a production SLO or performance-comparison claim.

## Model-quality boundary
Habitat supplies world-model, memory, planning, verification and coordination affordances. It does not establish that an arbitrary model becomes AGI or that coding success is superior to ordinary repository tooling without controlled same-model/scaffold/evaluator experiments.
