# SELF AUDIT — Nolane Habitat 0.1.0-alpha.13

Alpha.13 deliberately used Nolane AGI-style command attacks against the seams of the alpha.12 system. This file preserves failed probes and corrected beliefs; it is not a success-only release note.

## Findings admitted and corrected

### A13-F01 — Runtime history could be overwritten by a future direct Store caller
- **Observation:** Workspace guarded duplicate runtime IDs, but `Store.append_runtime_event()` still used `INSERT OR REPLACE`.
- **Risk:** a future caller bypassing Workspace collision checks could rewrite an observed historical event.
- **Correction:** runtime event persistence is now plain `INSERT`; collision/replay semantics live above it and SQLite remains a final fail-closed boundary.
- **Verifier:** `test_runtime_store_is_append_only_and_dap_reconnect_replay_is_idempotent`.

### A13-F02 — DAP reconnect identity was not replay-safe
- **Observation:** DAP event IDs included current receive time. Replayed `session + seq` events could create distinct observations.
- **Rival design rejected:** make every DAP `seq` globally unique. DAP sequence alone is not a cross-session identity.
- **Correction:** when a session/process/episode/agent identity and `seq` exist, replay identity is `session + seq + event`; receive time is not part of duplicate equivalence. Without a session identity, Habitat says `replay_identity=unavailable` and does not fake deduplication.
- **Verifier:** two DAP replay tests in alpha.13.

### A13-F03 — Counterfactual verification could become stale without being obvious
- **Observation:** verification originally did not bind overlay generation.
- **Correction:** `overlay_generation` / `verified_generation`; any new patch turns passed/failed verification into `stale`.
- **Verifier:** stale-generation regression.

### A13-F04 — A fresh *failed* counterfactual world could still promote
- **Observation:** alpha.12 promotion rejected stale verification but not fresh failed verification.
- **Risk:** agent can run the verifier, observe failure, then still promote the failed world.
- **Correction:** if a world has been verified, promotion requires `passed + fresh`. Never-verified promotion remains compatible with older explicit policy.
- **Verifier:** `test_failed_counterfactual_verification_blocks_promotion`.

### A13-F05 — Runtime collision equality was too narrow
- **Observation:** duplicate checks did not originally cover all durable provenance dimensions.
- **Correction:** status/path/symbol/agent/episode/duration/source plus trace/span/name/revision/attributes are compared; conflicting IDs fail closed.
- **Verifier:** `test_runtime_collision_compares_full_durable_provenance`.

### A13-F06 — Telemetry redaction by key is insufficient for debugger variables
- **Observation:** DAP often encodes a secret as `{name:"API_KEY", value:"..."}`; `value` is not itself a sensitive key.
- **Correction:** structural sibling-name/value redaction plus key/value regexes, opaque token patterns, depth/list/dict/string bounds.
- **Verifier:** DAP structural secret regression and cinematic demo secret absence.

### A13-F07 — Runtime batch slicing could silently lose events
- **Observation:** bounded ingestion using the first 2,000 records would make dropped telemetry look absent.
- **Correction:** batches above 2,000 fail with an instruction to split the batch; no silent telemetry loss.
- **Verifier:** alpha.13 batch regression.

### A13-F08 — Same-revision project-memory echo can self-reinforce retrieval
- **Observation:** identical memory statements could accumulate repeatedly without new world evidence.
- **Correction:** exact same-revision/kind/scope/agent memory echoes return the existing record and emit `memory.echo-suppressed`; the same statement after a new revision is allowed as historical memory.
- **Verifier:** same-revision and cross-revision memory regressions + AGI stress.

### A13-F09 — Context page faults did not expose refetch/thrash amplification
- **Observation:** model-visible source bytes alone hide repeated page faults and authority I/O.
- **Correction:** unique/duplicate page faults, refetch ratio and authority-I/O amplification are first-class metrics and schemas.
- **Verifier:** context-efficiency regression + cinematic demo deliberate 0.5 refetch ratio.

### A13-F10 — Environment-visible cognitive loops were not surfaced
- **Observation:** an agent could repeatedly call the same Habitat operation without admitted progress while the world still looked healthy.
- **Correction:** bounded loop detector over *visible Habitat operations only*; world/cognition health and Observatory agent chips surface risk. No private model reasoning is inspected.
- **Verifier:** explicit loop tests and cinematic demo (9 repeated inspect operations → HIGH risk).

### A13-F11 — Invariant verifier query used wrong relation names during alpha.13 implementation
- **Observation:** new health code queried `verifies/verified-by`; actual invariant link relation is `verifier`.
- **Correction:** cognition and observer health use the canonical relation.
- **Verifier:** `test_invariant_verifier_link_clears_verifier_gap`.

### A13-F12 — Observatory asset handler wrote the HTTP response twice
- **Observation:** static asset path in alpha.12 duplicated header/body work.
- **Correction:** one header/body write.
- **Verifier:** observer asset response regression.

### A13-F13 — Observer snapshot consistency claim was too strong
- **Observation:** SQLite rows are coherent in a read transaction, but Project World includes filesystem-backed projection outside that DB snapshot.
- **Correction:** output distinguishes `snapshot_consistency=sqlite-read-transaction` from `external_projection_consistency=revision-bound-best-effort` until a backend supplies a snapshot token.
- **Verifier:** consistency-claim regression.

### A13-F14 — SSE reconnect had no resume/gap semantics
- **Observation:** observer reconnect could miss retained events and still look live.
- **Correction:** `Last-Event-ID`, sequence bounds, replay cursor, retention-gap event and client resnapshot.
- **Verifier:** SSE resume/gap regression.

### A13-F15 — Cross-thread observer test initially violated the real writer topology
- **Observation:** test tried to write through the same thread-bound Workspace connection from another thread.
- **Correction:** preserved SQLite writer thread boundary; concurrent writer opens a separate Workspace/control connection while observer uses separate query-only readers.
- **Verifier:** concurrent observer/writer regression.

### A13-F16 — Large observer graph was silently truncated
- **Observation:** alpha.12 client hard-capped nodes/edges without visually explaining omitted world state.
- **Correction:** server `graph_sampling` disclosure plus client adaptive focus+context LOD and cluster nodes (`SYMBOL × N`, etc.). Hot/agent/hypothesis/evidence/runtime/failure nodes are prioritized.
- **Verifier:** adaptive-LOD regression and >120-symbol cinematic demo.

### A13-F17 — Event storms could thrash camera and DOM
- **Observation:** every small event could compete for camera focus; activity rows were repeatedly rebuilt.
- **Correction:** event priority + focus hysteresis, capped tracers/bursts, dense-graph physics throttling, requestAnimationFrame activity batching, reduced-motion degradation.
- **Verifier:** asset contract tests + cinematic demo.

### A13-F18 — Dataflow runtime support was too path-oriented
- **Observation:** path correlation alone can visually over-strengthen a static fact.
- **Correction:** only same-revision observations support current static facts; exact symbol match is strong, path-only is weak; static support is never called causality.
- **Verifier:** revision-bound Effect/Dataflow runtime-support regression.

### A13-F19 — Effect Twin schema did not match its own wire response
- **Observation:** API emits `effects`; alpha.12 JSON Schema required `facts`.
- **Correction:** schema follows the real wire contract and adds runtime-support annotations.
- **Verifier:** schema parse/contract gate.

### A13-F20 — Manifest schema lagged writer schema 9 / Observatory v2
- **Observation:** first historical shard rejected a valid alpha.13 manifest; after admitting schema 9 it still rejected `cinematic-realtime-world-v2`, `sse-resumable`, `snapshot_consistency`, `adaptive_lod`.
- **Correction:** additive schema compatibility; older enum values remain allowed.
- **Verifier:** alpha.1 schema contract now passes.

### A13-F21 — Context-efficiency schema lagged new micro-depth metrics
- **Observation:** alpha.7 public contract rejected `unique_page_faults`, `duplicate_page_faults`, `refetch_ratio`, `authority_io_amplification`.
- **Correction:** additive schema update, no removal of legacy fields.
- **Verifier:** alpha.7 schema contract now passes.

### A13-F22 — Bounded failed-test names were not explicitly disclosed
- **Observation:** structured test normalization retained at most 100 failed names.
- **Risk:** an agent can mistake a bounded list for the complete set.
- **Correction:** `failed_tests_total` + `failed_tests_truncated`; evidence recording adds an aggregate omitted-failures record.
- **Verifier:** failed-test bounding regression.

### A13-F23 — Cinematic demo appeared to hang while screenshot was still being acquired
- **Observation:** one tool invocation hit the outer runner timeout after report output. A faulthandler probe showed the main thread waiting in the Chromium screenshot subprocess, not stuck in Habitat world mutation; observer threads were waiting normally.
- **Correction:** release evidence distinguishes screenshot acquisition latency from runtime lifecycle. Subsequent instrumented demo exits cleanly and records whether capture is live HTTP or exact-live-snapshot fallback.
- **Verifier:** `DEMO-EVIDENCE-alpha13.json` + screenshot source metadata.

## Open findings / deliberately not over-claimed

- External filesystem Project World projection still lacks a backend snapshot token.
- DAP replay without stable session/process/agent/episode identity cannot be deduplicated safely.
- Loop/pressure/thrash scores are heuristics and need real-agent calibration.
- Static Effect/Dataflow + Runtime support is not causal inference or dynamic taint proof.
- Canvas2D remains the admitted renderer; GPU/WebGL migration awaits measured frame-time pressure.
- Same-model Habitat-vs-filesystem product-quality A/B remains separate from mechanism evidence.
