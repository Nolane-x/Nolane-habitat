# Research sources and design consequences — alpha.12

## Kiali Topology
Source: Kiali official topology documentation.

Observed principle: topology becomes substantially more useful when real traffic, health and configuration are combined, and motion corresponds to traffic behavior.

Habitat consequence: event particles/pulses correspond to admitted agent/runtime/effect/dataflow activity rather than fake terminal output.

## Grafana Node Graph
Source: Grafana official Node Graph documentation.

Observed principle: layered/force/grid layouts have different scale characteristics; larger graphs can require different layout strategies.

Habitat consequence: current bounded hundreds-of-node Observatory remains Canvas2D; migration to a GPU renderer is triggered by measured graph/frame pressure rather than fashion.

## Sigma.js
Source: Sigma.js official renderer documentation.

Observed principle: WebGL is appropriate for higher-scale graph rendering and custom node/edge programs.

Habitat consequence: Sigma-class WebGL is a credible future renderer if Observatory node/edge counts exceed Canvas admission limits.

## PixiJS
Source: PixiJS official renderer documentation.

Observed principle: GPU WebGL/WebGPU scene rendering is suitable for high-motion visual systems.

Habitat consequence: Pixi-class rendering remains a future option for dense particles/world layers, not an alpha.12 dependency.

## OpenTelemetry
Source: OpenTelemetry official semantic-conventions documentation.

Observed principle: traces, logs, metrics, services, HTTP, database and messaging signals benefit from shared semantic naming.

Habitat consequence: Runtime Twin accepts OTel-shaped records and links them to Habitat revision/path/symbol provenance when available; observed telemetry remains distinct from causal proof.

## MCP 2026-07-28
Source: Model Context Protocol official 2026-07-28 release announcement.

Observed principle: the MCP core is stateless and requests should be self-describing/routable.

Habitat consequence: explicit `agent_id` application state is retained; Habitat does not depend on a transport process as an implicit agent session.
