# Alpha.3 Architecture — Live Semantic Workspace

Alpha.3 adds a distinction that did not exist cleanly in alpha.2: **observation acceleration is not integrity authority**.

```text
                         CANONICAL SOURCE ROOT
                                 │
               ┌─────────────────┴─────────────────┐
               │                                   │
       metadata observation                 deep integrity scan
       (reconcile / watcher)                (mutation boundary)
               │                                   │
       candidate source paths                       │
               │                                   │
       targeted content hash  ◄────────────────────┘
               │
       per-file compiler/cache
               │
    ┌──────────┴───────────┐
    │                      │
base semantic domain   TypeScript domain
    │                      │
    └──────────┬───────────┘
               │
      merged semantic graph
               │
      relation/occurrence diff
               │
         persistent twin
               │
 ┌─────────────┼─────────────────────┐
 │             │                     │
context     impact/tests         runtime UI
 │                                   │
context.refresh                 DOM/ARIA/layout
context.materialize             listener evidence
 │                              JSX anchor ownership
 └──────────────┬────────────────────┘
                ▼
              AGENT
```

## Semantic cache domains

Alpha.2 used a project-wide root digest for whole semantic cache admission. Alpha.3 separates provider work:

- `semantic-base-v4`: semantic-bearing source files + provider identities;
- `semantic-typescript-v4`: JS/TS source domain + TypeScript version/availability;
- `semantic-project-v2`: retained as a compatibility/provider-drift sentinel, not the heavy cache payload.

A documentation-only edit can therefore change the canonical revision without forcing the TypeScript Program/TypeChecker to rerun.

## Graph persistence

Relations and occurrences are synchronized by identity and content. A semantic refresh now emits a graph delta receipt. A no-op refresh must report zero inserted, updated and deleted rows.

## Live watcher

`PollingSourceWatcher` is intentionally narrow. It owns no SQLite connection and runs no parser. It emits metadata candidate observations into an in-memory queue. `HabitatWorkspace.watch_poll/watch_wait` admit those candidates through `refresh_paths()` on the caller thread.

This avoids turning a performance optimization into an unsafe concurrent source of truth.

## Context lifecycle

Context slices are immutable revision-bound artifacts.

```text
ctx@revision-A
      │ source changes
      ▼
workspace.context.refresh(ctx)
      │
      ├─ retained objects
      ├─ added objects
      ├─ removed objects
      ├─ missing objects
      └─ changed paths
      ▼
ctx@revision-B
```

`context.materialize` turns a fresh handle into a bounded decision packet. It materializes exact source only for symbol bodies that fit the explicit byte budget. File objects remain metadata-only unless a separate exact-source API is requested.

## Framework ownership

TSX/JSX parser anchors with literal `id` or `data-testid` become `ui-element` symbols. A containing function/class obtains a `renders` relation. Runtime elements with matching explicit attributes receive source candidates:

- unique JSX anchor → parser trust;
- duplicate anchor → heuristic trust;
- runtime JS listener stack → independent semantic runtime evidence when available.

No candidate is promoted to proof of runtime component ownership.
