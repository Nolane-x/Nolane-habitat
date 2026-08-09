# Research notes — alpha.12

Alpha.12 used current observability/graph/runtime standards as reference points, not templates to copy.

## Kiali topology
Kiali demonstrates a useful principle: combine topology, telemetry, health and traffic animation so motion corresponds to real request behavior. Habitat applies the principle to agent/project cognition rather than service-mesh operations.

## Grafana Node Graph
Grafana's node graph distinguishes layered/force/grid layouts and notes scale trade-offs around larger graphs. Habitat uses this as support for keeping a bounded Canvas renderer at the current scale and treating GPU migration as an evidence-triggered decision.

## Sigma.js / PixiJS
Sigma uses WebGL for graph rendering and Pixi provides GPU renderer infrastructure. They are credible future options if the Observatory must render thousands of continuously animated entities, but alpha.12 avoids a frontend dependency/build pipeline before scale evidence requires it.

## OpenTelemetry
OpenTelemetry semantic conventions provide common naming across traces, logs, metrics, services, HTTP, database and messaging signals. Habitat's Runtime Twin accepts an OTel-shaped ingress to reduce vendor coupling while retaining a strict boundary: telemetry is observed evidence, not causal proof.

## MCP 2026-07-28
MCP's stateless protocol core reinforces Habitat's explicit-agent-handle design. Agent identity belongs in application state/request context rather than an assumed long-lived transport session.

## Design consequence
The Observatory should look intense because the **world is active**, not because the interface fabricates terminal output. Event particles, pulses, camera focus and graph layers therefore bind to real Habitat entities/events wherever possible.
