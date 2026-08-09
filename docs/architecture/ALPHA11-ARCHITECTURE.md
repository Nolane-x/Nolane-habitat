# Nolane Habitat alpha.11 — Cognitive Observatory Architecture

## Thesis

Alpha.11 keeps Habitat agent-first. The human screen is not an IDE, command center, terminal, or approval console. It is a **read-only observatory** over the world that agents already use through Habitat's protocol/MCP/Workspace APIs.

```text
Codex / Claude Code / custom agent
             │
       MCP / NDJSON / API
             │
             ▼
      HABITAT CONTROL PLANE
  task · context · evidence · mutation
  verification · policy · coordination
             │
             ▼
          WORLD STATE
  Semantic Twin · Context VM · Runtime Twin
  Epistemic Ledger · Project Memory · Activity
             │
             ├────────────► SQLite authoritative derived state
             │
             ▼
      OBSERVATORY READ MODEL
      query-only connection
             │
          HTTP + SSE
             │
             ▼
       HUMAN SPECTATOR UI
       OBSERVER ONLY
```

The Observatory must be disposable: closing it, refreshing it, losing SSE, or failing to render cannot alter an agent operation.

## 1. Agent underlay

Agent control remains model/vendor neutral:

- `habitat-agent-server` — newline-delimited JSON protocol over stdio;
- `habitat-mcp-server` — optional MCP adapter, spec target `2026-07-28`;
- direct `HabitatWorkspace` / `HabitatProtocol` embedding for custom agents.

MCP's 2026 stateless core makes process identity a poor place to keep agent state. Alpha.11 therefore mints an explicit `agent_id` from `habitat_start_task` and lets stateless follow-up requests carry that handle. The compact MCP catalog stays at 12 high-level tools.

## 2. Activity nervous system

`activity_events` is an append-only, monotonic observer journal. Consequential domain boundaries emit best-effort events such as:

- agent connected/disconnected;
- episode started/finished;
- context page fault / feedback;
- memory admitted/evicted/recorded/invalidated;
- hypothesis and experiment transitions;
- transaction staged/committed/rollback;
- source path modified/created/deleted;
- verification started/completed;
- execution started/completed;
- coordination invalidated/revalidated;
- runtime observation received;
- tool started/completed.

Observability is non-authoritative. Emission failure is caught at consequential paths and must not change mutation/verification results.

## 3. Observatory read-model isolation

A naive threaded HTTP observer initially reused the Workspace SQLite connection and triggered SQLite cross-thread errors. Alpha.11 rejects the tempting `check_same_thread=False` shortcut.

Instead each observer request opens a short-lived SQLite connection using:

- `mode=ro`;
- `PRAGMA query_only=ON`;
- no write-capable Workspace object;
- explicit close after request.

The agent/control plane retains its authoritative connection. HTTP `POST`, `PUT`, `PATCH`, and `DELETE` all return `405 observer-read-only`.

## 4. Real-time UI

The browser surface is intentionally spectator-oriented:

- black/high-contrast multicolor topology;
- agent rail with active agents;
- current task/episode/revision;
- hypothesis confidence annotations;
- assumptions/unknowns/contradictions;
- resident Context VM objects;
- provenance-bound Project Memory;
- evidence and Runtime Twin signals;
- semantic/cognitive/runtime world map;
- live activity timeline;
- pulse/highlight when paths/nodes are touched.

It does **not** expose or request raw private model chain-of-thought. It displays environment-visible summaries and explicit cognitive records only.

## 5. Runtime Twin ingress

Alpha.11 adds a normalized observed-runtime plane beside the static Semantic Twin.

Ingress accepts:

- OpenTelemetry-shaped spans;
- OpenTelemetry-shaped logs;
- OpenTelemetry-shaped metrics;
- Debug Adapter Protocol events.

When a runtime observation includes a project path/source line, Habitat attempts to connect it back to a current file/symbol. Runtime observations retain trace/span/parent identities and arbitrary attributes.

```text
observed runtime signal
        │
        ├─ path / line
        ▼
 source range / symbol
        │
        ├─ revision
        ├─ episode
        └─ agent
```

Claim boundary: observed telemetry is stronger than static possibility for that run, but provenance correlation is not a complete causal proof.

## 6. Semantic Provider Fabric

Alpha.11 introduces a provider-independent capability fabric. It can discover/report availability for:

- Tree-sitter syntax substrate;
- LSP servers for supported languages;
- SCIP command/index artifacts;
- existing Habitat native Python/TypeScript semantics.

The fabric deliberately separates **discovered** from **admitted/used**. An unavailable Tree-sitter/LSP/SCIP provider is a visible capability gap, not fake semantic precision.

Agents should consume stable Habitat objects/relations/trust/provenance instead of needing to know whether a relation came from rust-analyzer, pyright, Tree-sitter, SCIP, or another provider.

## 7. Epistemic runtime — Nolane AGI DNA as environment affordance

Nolane AGI is not embedded into Habitat. Its design DNA is expressed as environment primitives:

- explicit `fact`, `assumption`, `unknown`, `contradiction`, `constraint`, `prediction` records;
- revision-bound cognitive state;
- bounded unknown-unknown probes;
- `workspace.cognition.next` that prioritizes invalidation, contradiction, discriminating experiments, unknowns, assumptions, exploration, or action;
- explicit stop/claim boundaries.

This is metacognitive scaffolding for an external model. It is not hidden model reasoning and does not prove AGI capability.

## 8. Project Memory vs Context Residency

Alpha.11 makes the distinction first-class.

### Context Residency
Short-lived working set: what the agent is actively carrying now.

### Project Memory
Provenance-bound remembered claims/events/processes:

- semantic;
- episodic;
- procedural;
- failure;
- decision;
- experiment.

Every Project Memory record binds revision, optional agent/episode, provenance, evidence IDs, confidence annotation, supersession/invalidation state. Recall never promotes a memory into canonical source truth. Private memories are visible only to their owning agent through agent-scoped recall; shared memories are visible to all agents.

## 9. Observatory world map

Nodes can include files, symbols, agents, episodes, hypotheses, epistemic items, project memories, evidence, and runtime observations. Edges include both Semantic Twin relationships and derived provenance relationships such as:

- episode → hypothesis;
- episode → epistemic item;
- agent → private cognitive item;
- episode → runtime observation;
- runtime observation → source symbol;
- memory → supporting evidence.

The map is bounded for rendering and is not the complete project graph.

## 10. Auto-start behavior

`habitat-agent-server` and the MCP CLI auto-start the Observatory by default and may open the browser automatically. Operators may disable either behavior:

```text
--no-observatory
--no-open-observatory
--observatory-port <port>
```

The agent remains fully usable with Observatory disabled.

## Admission boundary

Alpha.11 may claim:

- live observer projection of actual Habitat state;
- observer/control separation;
- query-only read connections;
- monotonic activity events;
- OTel/DAP-shaped runtime ingestion;
- project-memory provenance/invalidation;
- explicit agent handles for stateless MCP follow-up;
- provider-capability discovery.

Alpha.11 may **not** claim:

- all Tree-sitter/LSP/SCIP providers are active;
- full OpenTelemetry Collector/OTLP compatibility;
- DAP debugger orchestration across all runtimes;
- runtime telemetry establishes complete program causality;
- Observatory shows raw model chain-of-thought;
- UI is a human control plane;
- Habitat turns an arbitrary model into AGI.
