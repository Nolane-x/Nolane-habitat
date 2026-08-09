# Alpha.1 Architecture

```text
                       ordinary source tree / ZIP import
                                  │
                         canonical source truth
                                  │
                   ┌──────────────┴──────────────┐
                   │                             │
             deep hash refresh             cheap reconcile
                   │                             │
                   ▼                             │
          changed-file compiler cache ◄─────────┘
          │        │        │
          │        │        └─ diagnostics
          │        └────────── symbols
          └─────────────────── relation facts
                   │
                   ▼
             SQLite Semantic Twin
     files / symbols / relations / diagnostics
     revisions / contexts / transactions / runs / sessions
                   │
       ┌───────────┼─────────────┬───────────────┐
       ▼           ▼             ▼               ▼
 Context V2   Mutation Engine  Execution      UI Runtime
 task lanes   symbol anchors   capabilities   DOM/ARIA/layout
 graph slice  diff/preflight   test evidence  semantic actions
 paging       commit/rollback  verify plan    state delta
       │           │             │               │
       └───────────┴─────────────┴───────────────┘
                           │
                    Agent Protocol
               habitat.agent.v1alpha1
                           │
                    AI agent session
```

## Authority model

1. **Canonical:** exact source bytes in the ordinary project tree.
2. **Exact/parser evidence:** source-bound compiler objects and diagnostics.
3. **Derived:** relations/test links/context rankings.
4. **Heuristic:** Java fallback, CSS selector candidates and other explicitly bounded approximations.
5. **Runtime observation:** browser/process results bound to a revision/session, never silently promoted to canonical source truth.

## Why terminal/browser/file tree are not primary primitives

- Execution is requested by capability ID and returns a typed receipt.
- Tests return normalized evidence plus raw output only as fallback.
- UI actions target semantic handles, not screen coordinates.
- Source is requested by semantic object or bounded source page, not by mandatory whole-file open.
- Context is compiled and paged separately from source bodies.

The human can still use the project normally outside Habitat because source authority is unchanged.
