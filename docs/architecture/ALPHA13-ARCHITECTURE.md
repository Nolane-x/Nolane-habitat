# Alpha.13 Architecture — Micro-depth Resilience and Truthful Observatory

Alpha.13 does not add another giant world model. It attacks the seams between existing worlds where a long-running agent can continue operating while its interpretation silently drifts.

## 1. Truth planes remain distinct

- **Semantic / Effect / Dataflow**: static provider evidence.
- **Runtime Twin**: observed telemetry with source/revision provenance.
- **Counterfactual World**: overlay-local alternative state.
- **Canonical Source**: authoritative committed project bytes.
- **Observer projection**: bounded human view, never an authority surface.

Runtime correlation can annotate a static fact as observed-supported only at the same revision. Exact symbol provenance is stronger than path-only provenance. Neither creates causal proof.

## 2. Resilience invariants

1. Runtime event IDs are append-only. Replays are idempotent only when durable provenance agrees.
2. Debug replay identity is stable only when a session identity exists; otherwise replay identity is explicitly unavailable.
3. Counterfactual verification is generation-bound. Any overlay edit stales the result. A verified-failed world cannot promote.
4. Same-revision memory echoes do not amplify attention indefinitely; later revisions may preserve the same statement as historical memory.
5. A bounded list must disclose truncation/omissions whenever the omission can affect cognition.
6. Human-observer transport failure must not affect the agent/control-plane result.
7. The observer core is one SQLite read transaction; external filesystem projections remain revision-bound best effort until the backend supplies a snapshot token.

## 3. Cognitive health

`workspace.cognition.health` and `workspace.world.health` surface environmental debt:

- repeated visible operations without admitted progress;
- pending stale-source invalidations;
- explicit contradictions/unknowns/assumptions;
- critical invariants without verifier links;
- stale/failed counterfactual verification;
- context page refetch/thrash and authority-I/O amplification.

These are metacognitive environment signals, not access to hidden chain-of-thought and not calibrated probabilities.

## 4. Observatory v2

The human UI remains observer-only. Alpha.13 adds:

- resumable SSE with `Last-Event-ID` and retention-gap events;
- adaptive LOD with hot/important-node retention and cluster nodes for omitted low-value state;
- `visible / total` disclosure rather than silent truncation;
- agent trajectory trails, temporal heat, priority/hysteresis camera focus;
- runtime/effect/dataflow particle density tied to admitted event/edge data;
- per-agent stale/loop/lease health chips;
- frame-batched activity rendering and reduced-motion degradation.

Canvas2D remains intentionally self-contained at the current admitted scale. WebGL/Sigma/Pixi is a benchmark-triggered migration, not a prestige dependency.

## 5. Open boundaries

- External Project World projection has no backend snapshot token yet.
- DAP events without a stable session identity cannot be safely deduplicated across reconnects.
- Loop/thrash/pressure heuristics need calibration against real agent trajectories.
- Runtime correlation is not dynamic taint/value-flow or causal inference.
- Observatory GPU migration requires measured frame-time pressure at larger live graphs.
