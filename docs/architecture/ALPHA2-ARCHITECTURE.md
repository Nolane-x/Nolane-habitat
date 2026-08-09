# Alpha.2 Architecture — Precise Semantic Loop

## Architectural thesis

Habitat must not ask an agent to reconstruct project state from human-oriented files on every turn. It maintains a rebuildable semantic twin whose objects remain bound to canonical source digests and whose action surface is typed.

```text
canonical project files
        │
        ├────────────── human IDE / ordinary build tools
        │
        ▼
source bridge + digest/revision journal
        │
        ▼
file compiler cache
 ├─ Python AST
 ├─ TypeScript file parser
 ├─ HTML semantic parser
 └─ honest language fallbacks
        │
        ▼
project semantic linker
 ├─ qualified Python imports/calls
 ├─ TypeScript Program + TypeChecker
 ├─ relation graph
 └─ occurrence/reference index
        │
        ├──────────────► Context Compiler V3
        │                   ├─ lexical lane
        │                   ├─ symbol lane
        │                   ├─ diagnostic lane
        │                   ├─ semantic graph lane
        │                   └─ trust / omission packet
        │
        ├──────────────► Impact Engine
        │                   └─ changed object → callers/importers → affected tests
        │
        ├──────────────► Transaction Engine → canonical files → reindex/read-back
        │
        └──────────────► Runtime UI
                            ├─ DOM/accessibility/layout
                            ├─ semantic actions
                            ├─ state deltas
                            └─ runtime listener source evidence
```

## Trust lattice

`exact` — source-bounded fact with exact anchor.

`semantic` — compiler/runtime semantic resolution to a concrete project object.

`parser` — syntax parser fact without full semantic resolution.

`derived` — deterministic inference from weaker/structural evidence.

`heuristic` — candidate evidence that must not anchor consequential mutation without exact read-back.

The lattice describes evidence quality, not certainty of overall program behavior.

## Project semantic cache

Per-file compile facts and project-semantic facts are distinct:

- file cache is bound to file digest **and compiler/provider fingerprint**; legacy or toolchain-stale artifacts are recompiled rather than trusted;
- project cache is bound to root digest, semantic-provider algorithm version and provider/toolchain fingerprint;
- no-op refresh can reuse both;
- one-file changes recompile one file but may recompute project links because dependency consequences can cross files.

This is intentionally conservative. Future incremental dependency partitions can recompute only affected semantic components.

## Occurrences

Definitions, calls and imports are stored as source-anchored occurrences. A symbol can therefore be inspected without grep:

```text
workspace.references(symbol)
  → definition/reference/call/import records
  → path + line + provider + trust + evidence
```

## Affected tests

Impact analysis traverses incoming `calls`, `imports_symbol`, `imports`, and `tests` relations. It returns ranked test files with evidence chains. For Python unittest/pytest, Habitat can execute only selected files/modules. Other test providers currently fall back to their declared suite command.

## Event journal

Every deep refresh records a semantic-refresh receipt. Source changes additionally create file-created/modified/deleted events with previous/current revision and digests. The journal is append-only and cursorable.

It is not yet a background watcher: ordinary reconcile uses metadata, while deep refresh hashes source bytes.

## UI source evidence

Project HTML runs through an isolated browser context. Habitat injects non-project instrumentation before page scripts to observe `addEventListener` registration stacks. Stack frames pointing to `habitat.local/<project-path>` are mapped back to indexed source files.

Instrumentation is evidence-producing runtime machinery, not canonical project code, and never writes instrumentation into source files.

## Explicit non-capabilities

- Tree-sitter structural incremental parsing is not active on the release host.
- LSP and SCIP are provider gaps, not simulated features.
- Java remains heuristic at ingestion because executing javac/annotation processors against untrusted projects is outside the ingestion trust boundary.
- Browser semantics do not prove visual quality.
- Runtime JS listener capture does not guarantee component ownership for framework-generated abstractions.
