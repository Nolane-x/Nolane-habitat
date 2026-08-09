# Writing Plan — alpha.11 Cognitive Observatory

## Charter

Make Habitat usable as an underlay for arbitrary coding agents while giving humans a visually rich, realtime, **read-only** window into that world. Apply Nolane AGI design DNA as environmental affordances: explicit uncertainty, evidence, hypotheses, memory provenance, bounded next-step selection and unknown-unknown probes.

## Protected invariants

1. Canonical source remains source authority.
2. Observatory never becomes a mutation/control plane.
3. Observatory failure cannot fail an agent operation.
4. Raw private model chain-of-thought is never required or exposed.
5. Memory is not truth; runtime correlation is not causal proof.
6. Optional semantic/runtime providers fail honestly when unavailable.
7. MCP tool catalog remains compact.
8. Historical workspace/schema behavior remains readable.

## Beliefs / rival hypotheses

### B1 — observer activity should live below adapter wrappers
Rival: instrument only MCP.
Kill probe: direct Workspace mutation must still appear in activity stream.
Outcome: domain boundary instrumentation retained.

### B2 — a shared SQLite connection is acceptable for the observer thread
Rival: observer needs a separate read model.
Probe: real threaded HTTP snapshot.
Outcome: B2 rejected after SQLite cross-thread failure; query-only per-request connection adopted.

### B3 — Project Memory can reuse Context Residency
Rival: long-term remembered claims need provenance/invalidation independent of hot working-set residency.
Outcome: B3 rejected; separate memory table/API/UI treatment implemented.

### B4 — one MCP process can remain one agent identity
Rival: MCP 2026 stateless routing makes process-local session identity brittle.
Outcome: explicit `agent_id` handle minted by start-task; fallback remains compatibility-only.

### B5 — detected semantic provider means active semantic proof
Rival: discovery and admission/usage are different states.
Outcome: capability fabric reports availability/reason/precision and explicitly avoids active-use claims.

## Milestones

- M1: activity journal + domain instrumentation.
- M2: read-only Observatory HTTP/SSE server.
- M3: realtime black/multicolor visual world map and timeline.
- M4: stateless agent identity path in MCP.
- M5: Epistemic Runtime + cognitive-next / unknown probes.
- M6: Runtime Twin OTel/DAP normalization and source linkage.
- M7: Semantic Provider Fabric capability surface.
- M8: Project Memory with provenance/revision/evidence/supersession.
- M9: historical regression and supplied-AGI stress.
- M10: clean-package admission from final ZIP.

## Unknown-unknown probes

- observer cross-thread/database lifetime;
- browser direct-loopback restrictions in CI;
- SSE reconnect/replay gaps;
- large graph rendering pressure;
- private memory leakage across agents;
- telemetry content sensitivity;
- provider discovery mistaken for semantic admission;
- adapter-only activity blind spots.

## Admission boundary

Alpha.11 is admitted only if:
- all four regression shards complete with no failure/timeout/infra-error;
- observer mutation verbs return 405;
- live demo has multiple agents + real transaction + passing verification + runtime/cognitive state;
- screenshot comes from real live state, not mock fixture data;
- supplied AGI ZIP retains warm incremental behavior and no-gold abstention;
- final package imports as alpha.11 from an isolated target;
- final ZIP passes independent manifest/root-hash verification.
