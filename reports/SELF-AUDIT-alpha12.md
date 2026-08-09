# Self Audit — Nolane Habitat 0.1.0-alpha.12

## Admitted progress

Alpha.12 adds five deliberately separate world/evidence planes: Semantic Twin, static Effect Twin, static intra-file Dataflow Twin, observed Runtime Twin/Topology, and selected Project World. Counterfactual Worlds can evaluate alternative source overlays and verify them in a disposable project copy before canonical promotion. The Observatory has been redesigned into a cinematic realtime machine-world while remaining loopback-only and read-only for humans.

## Failures preserved during development

### 1. Multi-agent notification ID collision — CORE
A cinematic three-agent scenario triggered `UNIQUE constraint failed: agent_notifications.id`. One agent could have multiple object observations on the same path and the invalidation loop attempted to persist the same logical path notification more than once.

**Correction:** aggregate observations per `(agent,path)`, use one latest observation, bind identity to agent/path/causing transaction/revision, and deduplicate an already-existing logical invalidation.

**Verifier:** alpha.12 same-agent/same-path multi-observation regression.

### 2. AugAssign Dataflow trust corruption — CORE
The supplied Nolane AGI corpus exposed a Python `AugAssign` path where a metadata dictionary was passed positionally into the `trust` parameter. SQLite correctly rejected the dictionary during persistence.

**Correction:** metadata is keyword-bound; regression asserts `total += delta` persists parser trust and `operator=Add` metadata separately.

**Verifier:** dedicated regression plus supplied-corpus stress rerun.

### 3. Stress report falsely displayed zero Effect/Dataflow facts — EVIDENCE HARNESS
The snapshot APIs use `effects` and `flows`; the first alpha.12 stress harness read `facts`, producing zero in the report while the database actually contained tens of thousands of facts.

**Correction:** harness uses the public output keys and cross-checks world-summary counts.

**Verifier:** rerun reports 29,012 Effect facts and 35,809 Dataflow facts.

### 4. Obsolete historical test module names — RELEASE HARNESS
One manual final shard used old module names and produced four import errors. Those errors were not regressions.

**Correction:** derive current module names from the actual `tests/test_*.py` tree and rerun. The failed harness invocation is not counted.

### 5. Combined matrix invocation remains host-sensitive — TOOLING/LIFECYCLE
All four matrix groups pass independently, but a single orchestrator process running every group sequentially can still experience pathological host/runtime lifetime variance. Pipe inheritance by browser/Node descendants was one observed contributing mechanism; the runner now logs to files and uses process groups, but the combined host behavior is not called solved.

**Admission rule:** only four independently completed shard runs are counted: 66 + 38 + 83 + 26 = 213 tests. Combined incomplete invocations are neither PASS nor FAIL.

### 6. Live-loopback Chromium screenshot fallback — RELEASE ENVIRONMENT
The Observatory itself runs over live HTTP/SSE. On this host a fresh Chromium CLI process is not consistently able to capture the loopback page after other browser/runtime work.

**Correction:** screenshot fallback renders the exact already-fetched live snapshot using the same packaged HTML/CSS/JS. `screenshot.source` is recorded as `live-snapshot-offline-render`; no mock world state is substituted.

### 7. Earlier demo harness contract mistakes — HARNESS
During vertical-slice construction the demo used a wrong invariant keyword, a wrong invariant-link call shape, a stale status wrapper assumption, and an incorrect Project World key. They were corrected to the public API rather than changing core contracts to satisfy the harness.

## Open frontiers

- Effect Twin remains static and language coverage is uneven.
- Dataflow Twin is bounded intra-file evidence, not interprocedural SSA/points-to/taint proof.
- Runtime Twin is observed telemetry, not full causal inference or full OTLP Collector compatibility.
- Project World parses selected manifests/configs; it is not a complete cloud/deployment/production model.
- Counterfactual disposable-copy verification protects canonical source bytes but does not sandbox hostile code.
- Semantic Fabric still reports many provider capabilities without universal admitted Tree-sitter/LSP/SCIP semantics.
- Canvas2D is admitted at the current bounded scale; GPU/WebGL migration is still untested against a production-scale graph.
- Same-model Habitat-vs-filesystem A/B remains evaluation infrastructure, not a demonstrated product-quality win.
- Raw model chain-of-thought remains intentionally absent from Observatory.

## Claim discipline

The alpha.12 UI can be described as realtime/cinematic because it is driven by admitted state/activity and continuously renders motion. It must not be described as showing hidden model thoughts. The world graph can be described as semantic/effect/dataflow/runtime/project evidence; it must not be collapsed into a proven causal model.

### 8. Isolated pip build dependency fetch unavailable — RELEASE ENVIRONMENT
The first RC `pip install --target` smoke failed before building because pip build isolation attempted to obtain `setuptools>=68` from the session's restricted package index, which returned no candidate. The host already contained setuptools 82.0.1.

**Correction:** rerun the artifact packaging smoke with `--no-build-isolation --no-deps`, explicitly using the already-installed build backend. The installed package imported from the isolated target and contained all Observatory assets.

**Claim:** this admits the package metadata/build under the available backend; it does not claim an offline source install can bootstrap build dependencies without a package source.
