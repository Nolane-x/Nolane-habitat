# Nolane Habitat alpha.12 architecture

## Thesis

Alpha.12 turns the alpha.11 realtime spectator surface into a deeper **cinematic machine-world observatory** while expanding the world model underneath it. The UI remains disposable and read-only; agents still act through Habitat's API/NDJSON/MCP control plane.

```text
                 CODEX / CLAUDE / CUSTOM AGENT
                            │
                      MCP / NDJSON / API
                            │
                            ▼
                     HABITAT CONTROL PLANE
                            │
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
   Semantic Twin       Epistemic state      Transactions
        │                   │                    │
        ├────────────┬──────┴──────┬─────────────┤
        ▼            ▼             ▼             ▼
   Effect Twin   Dataflow Twin  Runtime Twin  Project World
        │            │             │             │
        └────────────┴──────┬──────┴─────────────┘
                            ▼
                    Machine World Read Model
                            │
                     SQLite query-only
                            │
                         HTTP + SSE
                            │
                            ▼
                    HABITAT OBSERVATORY
                    human spectator only
```

## Evidence planes

### Semantic Twin
Definitions, symbols, references, calls/imports and diagnostics. Derived from source; never canonical truth.

### Effect Twin
Revision-bound static effect facts such as READS, WRITES, RETURNS, THROWS, AUTHORIZES, DB-QUERY, NETWORK-REQUEST, EMITS and RECEIVES. Python AST evidence is parser-trust; JavaScript/TypeScript pattern lanes are explicitly heuristic.

### Dataflow Twin
Bounded intra-file static dataflow facts: assignment, argument-to-call, call-result, return-flow and condition-flow. Runtime references may be correlated by admitted path provenance. Correlation does **not** prove dynamic value identity or causality.

### Runtime Twin
Observed OTel/DAP-shaped spans/logs/metrics/debug events. Runtime topology links service, route, database, messaging, source and parent-child span relationships. It is evidence about observed executions, not proof of all possible executions.

### Project World
Selected repository manifests/configuration are compiled into package/build/CI/API/database/infrastructure nodes and edges. This is deliberately incomplete and provider-scoped.

### Counterfactual Worlds
An agent may fork a revision-bound overlay, stage alternative source changes, compile/evaluate Effect/Dataflow facts in isolation, verify inside a disposable project copy, compare alternatives, and only then promote through the normal transactional mutation path. Disposable-copy verification protects canonical bytes but is **not** a hostile-code sandbox.

## Cognitive director

`workspace.cognition.plan` ranks explicit environment operations using ordinal information gain, decision sensitivity and cost. It prioritizes stale-world revalidation, contradictions, discriminating experiments, unknowns and assumptions before mutation. The score is not calibrated expected utility and is not hidden chain-of-thought.

## Realtime nervous system

Domain boundaries emit best-effort activity events. UI/browser actions now emit their own events so the Observatory can show an agent opening a runtime, clicking/filling/asserting, faulting context pages, creating worlds, mutating files, verifying, receiving invalidation and updating memory.

Observer failures never change control-plane results.

## Cinematic Observatory

The alpha.12 renderer is self-contained Canvas2D with no frontend build or CDN dependency. The renderer uses:

- a dominant topology field instead of a terminal-like layout;
- type-cluster anchors for agent/source/runtime/effect/dataflow/world nodes;
- event-driven node pulses and shock flashes;
- moving tracer particles on runtime/effect/dataflow/call/dependency edges;
- agent orbit rings and automatic camera focus on recent activity;
- a top HUD for event rate, node count, Effect/Dataflow/Runtime signals;
- current cognitive director, epistemic debt, working memory, durable project memory, evidence/runtime lane and activity rail;
- no buttons/forms/inputs and no human mutation endpoint.

Canvas2D is an evidence-based alpha.12 choice: current admitted visual snapshots are bounded to hundreds of nodes. A WebGL renderer remains a scale-triggered frontier rather than an unconditional dependency.

## Multi-agent coordination correction

Alpha.12 found and fixed a real notification collision. Multiple observations by the same agent for different objects on one path now deduplicate into one path invalidation per causing transaction/revision. Notification identity includes agent/path/cause rather than colliding across observers.

## Claim boundaries

Alpha.12 may claim distinct static semantic/effect/dataflow evidence, observed runtime topology, selected project-world entities, isolated counterfactual overlays and a realtime read-only human spectator surface.

Alpha.12 may **not** claim whole-program dataflow proof, causal inference, complete deployment/runtime truth, all-language semantic parity, production hostile-code isolation, or that the Observatory reveals private model chain-of-thought.
