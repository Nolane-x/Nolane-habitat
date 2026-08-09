# Alpha.14 Architecture — Executive Trajectory

## Why this layer exists
Alpha.12/13 gave Habitat a rich world model and resilience diagnostics, but `cognition.plan` remained a bounded next-action heuristic. Long-running work still lacked one durable object tying goal decomposition, verifier state, failures, strategy changes and closure together. Alpha.14 introduces that missing control object without pretending to inspect model internals.

## AGI-system principles adopted
The design was informed by Nolane-AGI Cognitive System 4.0 material, especially `V4-ARCHITECTURE.md`, `AGI-SYSTEM-RESEARCH.md`, `nolane-agi-world-model`, `nolane-agi-hierarchical-planning`, `nolane-agi-strategy-switching`, `nolane-agi-memory-retrieval`, and `nolane-agi-memory-consolidation`.

The architectural translations are:

1. **World state is a versioned candidate, not truth.** Executive verification is bound to Habitat revision when provenance exists; source changes stale prior completion evidence.
2. **Long-horizon goals require hierarchy.** Milestones have explicit postconditions and dependencies rather than one flat prompt-plan.
3. **Failure must change control structure.** Failed verification and repeated non-progress can cause a strategy-family switch instead of more of the same action.
4. **Negative evidence is first-class memory.** Failed/inconclusive steps are persisted with trajectory/event provenance.
5. **Completion is an assurance decision.** CLOSE is gated by verifier admission, revision freshness, contradiction state, coordination invalidations, invariant coverage and trajectory integrity.
6. **Observable cognition must not become CoT surveillance.** Habitat stores explicit task/control artifacts only.

## Data model

### `executive_trajectories`
Durable goal/control envelope: goal, owner agent/episode, base revision, status, current strategy, strategy generation, budget, metrics and outcome.

### `executive_milestones`
Hierarchical work units: title, explicit postcondition, priority, dependencies, verifier reference, rollback note, base revision and result.

### `executive_events`
Append-only executive events with ordinal, phase, operation, status, revision, reference, structured data, previous hash and record hash.

Each event hash commits to the previous hash plus canonical event content. Assurance always validates the complete chain; bounded projections are inspection/UI-only, so tail events beyond 1,000 records cannot fall outside integrity checking. This detects local history modification; it is tamper-evident, not externally notarized.

## Control phases

`OBSERVE -> UPDATE -> DIAGNOSE -> RETRIEVE -> COMPOSE -> DISPATCH -> VERIFY -> REFLECT/RECOVER -> CONTINUE -> CLOSE`

Habitat does not force an LLM to reveal reasoning for these phases. A client records only explicit operations and artifacts that matter to control and assurance. Alpha.14 validates the control-step sequence: direct phase skipping is rejected; failed/inconclusive control steps route to RECOVER; successful closure requires current VERIFY evidence and a subsequent REFLECT/CONTINUE state. Milestone bookkeeping is auxiliary and cannot impersonate control-phase advancement.

## Strategy families
- `direct-analysis`
- `reframe`
- `causal-intervention`
- `rival-hypothesis`
- `external-oracle`
- `dependency-replan`
- `scope-reduction`

The classifier deliberately changes the *kind* of next attempt under recognized failure classes. It is deterministic and auditable, not claimed to be globally optimal.

## Budget and stop control
The trajectory budget hard-enforces `max_steps`, `max_failed_steps`, and `max_strategy_switches`. Declared budget fields outside those meters remain visible but are explicitly labeled unmetered. Once a hard budget is exhausted, further `executive.advance` calls fail closed; the controller exposes `workspace.executive.stop` to terminate as `failed` or `abandoned` with a durable reason instead of silently looping.

When a failure requires adaptation and the diagnosed recovery family equals the current strategy, a structural fallback family is selected. Reusing the same family under a different label is not admitted as a strategy switch.

## Verifier admission
For a high/critical milestone to pass, `verifier_ref` must resolve to a known Habitat artifact:
- execution receipt/run;
- evidence record; or
- completed experiment.

Structured run failure overrides process exit-code success. Habitat-owned execution/verification receipts persist the `workspace_revision` observed at execution time, and any revision-carrying artifact must match the current workspace revision at admission time.

## Completion gate
CLOSE is blocked by any of:
- invalid executive event hash chain;
- milestone dependency cycle/missing dependency;
- unsatisfied high/critical postcondition milestone;
- missing or unsuccessful high/critical verifier;
- pending stale-observation notification for the owning agent;
- unresolved contradiction;
- critical/error project invariant without verifier linkage;
- missing VERIFY event when milestones exist;
- successful VERIFY event from an older workspace revision.

This is intentionally conservative. It proves that Habitat's explicit closure contract is satisfied, not that every possible program behavior is correct.

## Observatory integration
The read-only Observatory projects trajectories and milestones as world nodes and exposes active strategy in cognitive/director panels. Human spectators can inspect what the agent is doing at the control-artifact level without gaining mutation controls or raw private chain-of-thought.

## Compatibility
- Store schema: 22.
- Workspace manifest: 10 with `world_model.executive_trajectory=true`.
- Manifest schema retains validation compatibility for schema 9 workspaces.
- Wire protocol remains `habitat.agent.v1alpha2`; alpha.14 adds methods without needlessly renaming the compatible envelope.
