# Habitat Observatory alpha.13

The Observatory is a human spectator window into the machine world. It is not an IDE, terminal, prompt surface, approval console or mutation API.

## What the screen means

- **Agent chips**: explicit agent session + environmental health (`active`, `stale`, `loop-risk`).
- **World map**: bounded focus+context projection of semantic, effect, dataflow, runtime, project, epistemic, memory and counterfactual entities.
- **Motion**: event/edge-derived pulses and particles. No fake hacker text is generated.
- **Health HUD**: world/loop/context-thrash/LOD status.
- **Activity**: structured agent/world events, never raw private model chain-of-thought.

## Truthfulness rules

- hidden graph state is disclosed through sampling/LOD counts;
- runtime support colors do not turn static edges into causal proof;
- SSE reconnect gaps trigger resnapshot rather than silently skipping state;
- telemetry sensitive values are redacted before they can reach the UI;
- HTTP mutation verbs remain rejected.
