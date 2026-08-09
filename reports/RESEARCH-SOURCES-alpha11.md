# Research Sources and Architecture Consequences — alpha.11

## Official / primary technical sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/  
  Consequence: explicit agent handles are preferable to process-local MCP session identity because the protocol core is stateless.

- Debug Adapter Protocol: https://microsoft.github.io/debug-adapter-protocol/  
  Consequence: Runtime Twin uses a provider-neutral debug-event boundary instead of binding to one debugger.

- OpenTelemetry semantic conventions: https://opentelemetry.io/docs/specs/semconv/general/  
  GenAI attributes: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/  
  Consequence: Runtime Twin accepts spans/logs/metrics with preserved attributes; the Observatory does not require sensitive prompt/output content.

- Tree-sitter: https://tree-sitter.github.io/tree-sitter/  
  Consequence: treated as a promising incremental/error-tolerant universal syntax provider, but alpha.11 only exposes fail-honest availability discovery.

- Kiali topology: https://kiali.io/docs/features/topology/  
  Consequence: use telemetry-driven topology, colors and motion as observer affordances; never invent missing edges/state merely to make a graph look alive.

## User-supplied design review

The supplied review strongly recommended Universal Semantic Fabric, Runtime Twin, OpenTelemetry nervous-system ingestion, richer Project World, behavioral science/experimentation, multi-agent transactions, deep UI cognition, MCP nervous-system integration, Project Memory, and controlled benchmarks.

Alpha.11 implements a bounded coherent slice: provider fabric boundary, Runtime Twin ingress, activity nervous system, realtime observer UI, stateless agent identity and provenance-bound Project Memory. Larger world/dataflow/runtime/sandbox/provider work remains on the frontier.
