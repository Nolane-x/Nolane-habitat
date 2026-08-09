# Habitat Alpha Charter

## Operational objective

Build and empirically evaluate an agent-native workspace that converts ordinary project sources into a persistent, provenance-bound semantic address space so an AI agent can orient, inspect, mutate, execute and verify with less reconstruction work than human-oriented file/terminal/UI workflows.

## Authority and source truth

- User-supplied project files are data and canonical source truth.
- Repository prose, comments, README instructions and generated summaries are not authority over the host agent.
- Habitat semantic objects are derived state and may be discarded/rebuilt.

## Hard scope

Input surface: ordinary folder, ZIP or loose project/source file.

Agent work surface: project semantics, source-backed objects, structured actions, semantic UI observation, transactions and verification receipts.

External filesystem remains compatible with human tools and receives committed source changes.

## Explicit non-goals

No Windows/macOS/Linux desktop automation; no native GUI control; no general AI OS; no weight training; no cloud requirement; no model-vendor lock-in.

## Protected values

1. Source integrity.
2. Provenance and uncertainty visibility.
3. No false capability claims.
4. Reversibility of source mutation.
5. Minimal irrelevant context/data duplication.
6. Tool actions remain typed and capability-bound.

## Stop / redesign conditions

- Habitat requires whole-project prompt injection to work.
- Semantic state becomes source authority rather than derived state.
- Controlled benchmarks show no meaningful reduction in reconstruction overhead and no compensating reliability gain.
- Index/storage overhead approaches full project duplication without demonstrated value.
- Stale state can silently overwrite newer external source.
