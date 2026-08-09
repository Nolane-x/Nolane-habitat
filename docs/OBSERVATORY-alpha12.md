# Habitat Observatory — alpha.12 cinematic machine world

## Purpose

The Observatory is a realtime **spectator window into the world an AI agent is inhabiting**. Humans watch; agents act.

It intentionally contains no source editor, prompt box, run button, approval button, shell input or mutation API.

## Visual model

The renderer is designed to feel like a living cybernetic system rather than a conventional SaaS dashboard or fake hacker terminal. Dark space is filled by real topology and event motion:

- agents are stable luminous anchors;
- source/symbol nodes form one region of the world;
- static Effect and Dataflow evidence use dedicated neon lanes;
- Runtime Twin/service/database/route observations form a separate observed-runtime region;
- hypotheses, contradictions, invariants, evidence and Project Memory form cognitive/provenance regions;
- counterfactual worlds appear as alternative-world nodes;
- recent activity causes pulses, tracer comets, camera focus and failure shock waves.

Animation is driven by actual Habitat state/activity. Decorative starfield/scanline ambience may move continuously, but the UI does not invent tool calls, files, failures or reasoning text.

## Human-visible cognition

The Observatory may display task summaries, explicit hypotheses, assumptions, unknowns, contradictions, confidence annotations, cognitive-plan recommendations, memory and evidence.

Raw private chain-of-thought is deliberately absent.

## Transport and authority

- loopback-only HTTP;
- `/api/snapshot`, `/api/activity`, `/api/health` and `/events` SSE;
- observer requests use independent SQLite `mode=ro` and `PRAGMA query_only=ON` connections;
- HTTP mutation verbs return `405 observer-read-only`;
- loss of UI/SSE cannot fail an agent mutation or verification.

## Alpha.12 live demo

`reports/OBSERVATORY-alpha12.png` is rendered from the exact snapshot of a demo workspace containing three agents, two counterfactual worlds, static effects/dataflows, Runtime Twin spans, service/database topology, project entities, hypotheses/epistemic state, memory, a promoted transaction, targeted verification and actual browser UI click/assert activity.

The release environment currently falls back to rendering the already-fetched live snapshot through the same production HTML/CSS/JS when a fresh headless Chromium process cannot navigate the loopback URL reliably. The report records the screenshot source explicitly; no mock snapshot is substituted.

## Scaling frontier

The current read model intentionally bounds graph output. Canvas2D keeps the delivery self-contained and performs adequately at the admitted hundreds-of-node scale. If production snapshots cross the measured threshold where frame time/interaction quality degrades, a GPU/WebGL renderer such as Sigma/Pixi-class infrastructure should be admission-tested rather than adopted pre-emptively.
