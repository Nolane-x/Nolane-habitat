# Agent Integration — alpha.11

Habitat is intended to run **under** coding agents. Codex, Claude Code, custom agent loops, or local models should use Habitat as their project substrate rather than making the human Observatory their control path.

## 1. Generic NDJSON stdio

```bash
habitat-agent-server ./.habitat
```

By default this starts the read-only Observatory and prints its URL to **stderr**, preserving stdout for newline-delimited protocol messages.

Disable visual observer:

```bash
habitat-agent-server ./.habitat --no-observatory
```

Keep observer but do not open browser:

```bash
habitat-agent-server ./.habitat --no-open-observatory
```

## 2. MCP

Install the optional MCP dependency:

```bash
pip install "nolane-habitat[mcp]"
```

Then run:

```bash
habitat-mcp-server ./.habitat
```

The adapter targets MCP `2026-07-28`. `habitat_start_task` mints an explicit `agent_id` when the client does not supply one. Stateless follow-up calls should pass the returned handle.

The MCP catalog remains intentionally compact at 12 high-level tools. Habitat's richer internal protocol is not copied one-for-one into tool names because a huge tool catalog would itself become model context/tool-selection overhead.

## 3. Direct embedding

Python agent hosts can instantiate `HabitatWorkspace` or `HabitatProtocol` directly. Domain-level activity instrumentation sits below MCP, so the Observatory still receives transaction, verification, context, memory, and runtime events even when an agent bypasses the MCP adapter.

## 4. Runtime telemetry

External agent/runtime instrumentation may submit OpenTelemetry-shaped span/log/metric records or DAP event objects through `workspace.runtime.ingest`. Habitat preserves provenance and attempts source/symbol linkage when path/line data is present.

## 5. No chain-of-thought dependency

Habitat does not require a model to reveal private chain-of-thought. The Observable cognitive state consists of explicit task/hypothesis/evidence/assumption/unknown/action records that the environment can legitimately store and display.

## 6. Identity model

Shared verified world state and agent-private cognitive state remain distinct. Explicit agent handles are used for private beliefs, memory/utility scope, residency, coordination read-sets and transaction ownership.
