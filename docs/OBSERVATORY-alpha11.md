# Habitat Observatory — alpha.11

## Purpose

The Observatory exists for one reason: let a human **watch** an AI agent inhabit Nolane Habitat in real time.

It is deliberately not an IDE and not a terminal. A human cannot edit source, run tests, approve mutations, steer agents, or send prompts from this surface.

## What appears live

- agents and their public task/status metadata;
- current revision and episodes;
- project files/symbol topology;
- active hypotheses and confidence annotations;
- explicit assumptions, unknowns and contradictions;
- hot Context VM residents and durable Project Memory;
- evidence/test status;
- Runtime Twin spans/logs/metrics/debug events;
- transaction/source-change/verification timeline;
- multi-agent coordination and invalidation events;
- semantic/cognitive/runtime world-map pulses.

The screen uses activity summaries and environment records. Raw private chain-of-thought is intentionally absent.

## Transport

- loopback-only HTTP server;
- initial `/api/snapshot` read model;
- `/events` Server-Sent Events stream;
- `/api/activity?since=<seq>` replay;
- periodic snapshot refresh for eventual visual convergence;
- all mutation HTTP verbs return 405.

## Read model

The observer does not share the Workspace's SQLite connection. Every request opens a short-lived read-only/query-only connection. This prevents a rendering thread from becoming a concurrency participant in the control plane.

## Visual language

The alpha.11 renderer intentionally borrows the useful *ideas* of observability topology products without copying a normal ops dashboard:

- nodes encode different world types using distinct colors;
- runtime/cognitive activity causes transient pulses;
- graph edges are faint until activity makes nearby nodes salient;
- agent identities remain visible as stable anchors;
- failures/contradictions use warmer colors;
- the timeline runs continuously like an event stream, but it is not terminal output.

The resulting feel is closer to watching a living distributed system than using an editor.

## Auto-start

The standard agent server and MCP CLI auto-start the Observatory. Browser auto-open can be disabled while retaining the observer server.

## Screenshot evidence

`reports/OBSERVATORY-alpha11.png` is rendered from a real demo workspace containing two agents, real semantic objects, hypotheses, runtime observations, context residents, project memories, a committed mutation and a passing verification. In the release environment direct loopback Chromium navigation may be administratively blocked, so the benchmark falls back to rendering the exact already-fetched live snapshot through the same HTML/CSS/JS instead of substituting mock data.
