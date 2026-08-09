# Research Notes — alpha.11

Research was used to constrain architecture, not to manufacture feature claims.

## MCP 2026-07-28

Official MCP release notes describe a stateless protocol core in which requests are self-describing and can land on different server instances. Architecture consequence: Habitat must not equate one MCP server process with durable agent identity. Alpha.11 uses explicit server-minted `agent_id` handles while preserving a compact high-level tool surface.

Source: https://blog.modelcontextprotocol.io/posts/2026-07-28/

## Debug Adapter Protocol

DAP standardizes JSON communication between development tools and debugger adapters and supports multiple runtimes/debuggers. Architecture consequence: Runtime Twin should accept debugger observations through a provider boundary rather than hard-code one debugger. Alpha.11 only normalizes DAP-shaped events; it does not yet orchestrate arbitrary debugger sessions.

Source: https://microsoft.github.io/debug-adapter-protocol/

## OpenTelemetry

OpenTelemetry semantic conventions provide common naming for spans, metrics, logs and events, with GenAI semantic attributes evolving separately. Architecture consequence: Runtime Twin ingress should preserve arbitrary attributes and normalize signal categories instead of inventing a Habitat-only telemetry schema for every runtime. Content-bearing GenAI attributes may contain sensitive data, so alpha.11 does not require or display raw prompts/model chain-of-thought.

Sources:
- https://opentelemetry.io/docs/specs/semconv/general/
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/

## Tree-sitter

Tree-sitter is an incremental parsing library designed to remain useful during syntax errors and supports many languages. Architecture consequence: it is a strong candidate for the universal syntax layer under Habitat's provider-independent objects. Alpha.11 exposes capability discovery but does not claim Tree-sitter is active unless installed/admitted.

Source: https://tree-sitter.github.io/tree-sitter/

## Kiali topology/traffic visualization

Kiali demonstrates useful observability ideas: topology views, telemetry-derived edges, health colors and animated traffic. Architecture consequence for Habitat Observatory: topology should animate *actual observed state*, and missing telemetry must remain visibly missing instead of being invented. Habitat adapts the concept to project/cognitive/runtime nodes rather than service-mesh operations.

Source: https://kiali.io/docs/features/topology/

## User-supplied architecture review

The supplied review proposed Universal Semantic Fabric, Runtime Twin, OpenTelemetry as a nervous system, richer Project World, behavioral experimentation, multi-agent transactions, deep UI cognition, MCP nervous-system integration and provenance-bound Project Memory. Alpha.11 adopts a bounded vertical slice of those ideas rather than claiming the full roadmap is complete.

Adopted now:
- provider capability fabric;
- Runtime Twin ingress;
- activity nervous system;
- observer-only realtime UI;
- explicit stateless agent identity path;
- Project Memory distinct from Context Residency.

Deferred:
- full active LSP/SCIP/Tree-sitter fabric;
- full OTel Collector/OTLP integration;
- debugger session orchestration;
- full dataflow/effect twin;
- production/runtime world across databases/cloud/queues;
- semantic multi-agent branch/merge kernel;
- universal framework component cognition.
