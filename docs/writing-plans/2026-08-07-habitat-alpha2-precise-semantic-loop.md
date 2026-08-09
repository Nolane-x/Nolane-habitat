# Nolane Habitat alpha.2 — Precise Semantic Loop Implementation Plan

Date: 2026-08-07
Release target: `0.1.0-alpha.2`
Status: implementation checkpoint

## 0. Charter

Habitat exists to reduce the amount of human-oriented navigation an AI agent must perform while preserving ordinary project files as the source of truth. Alpha.2 must improve **decision-relevant precision**, not merely add more APIs.

Hard constraints:

1. Source files remain authoritative. Derived indexes may be deleted and rebuilt.
2. Ingestion must not execute project code, package hooks, annotation processors, or arbitrary build scripts.
3. Semantic claims carry provenance/trust. Missing precise providers are capability gaps, not permission to relabel heuristics as precise.
4. Agent actions remain typed. Generic shell is not introduced as an agent primitive.
5. Mutations are staged, digest-bound, reviewable, reversible, and followed by read-back/reindex.
6. Runtime UI semantics are primary; pixels remain optional secondary evidence.
7. Every promotion claim is bounded to executable evidence produced in this release.

## 1. Belief state before implementation

### B1 — File-level parsing is insufficient
Alpha.1 can find symbols, but cross-file calls can still be resolved by name. Prediction: a repository containing duplicate function names can create incorrect graph expansion or affected-test candidates.

### B2 — Cache reuse is not equivalent to incremental cognition
Alpha.1 avoids reparsing unchanged files, but project relations are rebuilt globally. Prediction: warm refresh is cheap on parsing but still performs unnecessary relation work and lacks explicit invalidation evidence.

### B3 — Test discovery must become graph-based evidence
Import-only linkage is too coarse for changed symbols. Prediction: symbol-level call/reference edges will reduce the candidate test set while retaining the true affected test in controlled fixtures.

### B4 — UI source hints need runtime evidence
DOM id and CSS-selector hints do not identify external JavaScript handlers. Prediction: instrumented event-listener registration can create runtime JS source hints without screenshots or browser devtools UI.

### B5 — A workspace that “lives” needs an event journal
A revision alone tells an agent that state changed, but not what the environment observed. Prediction: append-only file/semantic events will make resume/reorientation cheaper and auditable.

## 2. Capability diagnosis

Available on checkpoint host:

- Python AST: available.
- Node + TypeScript Compiler API: available.
- Playwright + system Chromium: available.
- Tree-sitter Python bindings: unavailable.
- SCIP indexers: unavailable.
- LSP servers such as Pyright / typescript-language-server: unavailable.
- `java` / `javac`: available, but running compilation during ingestion is deliberately prohibited because untrusted projects may trigger processors/build behavior.

Decision: exploit compiler-grade TypeScript semantics and Python AST linkage now; implement explicit probe contracts for Tree-sitter/LSP/SCIP without claiming them as active providers.

## 3. Milestones and falsifiable postconditions

### M1 — Semantic trust model v2
Tasks:
- Add `semantic` trust grade between exact source and parser heuristics.
- Add first-class occurrences/references with source anchors and provider provenance.
- Persist occurrences in SQLite.

Postconditions:
- `workspace.inspect(symbol)` can expose definition/reference occurrences.
- No semantic relation is emitted without a provider/trust/evidence path.

Failure probes:
- Duplicate same-name functions across modules must not cause compiler-resolved TypeScript calls to point to both.
- Missing target definitions remain unresolved rather than fabricated.

### M2 — Python project linker
Tasks:
- Record import aliases and from-import symbol bindings during AST extraction.
- Record qualified call candidates (`module::symbol`, `Class.method`, etc.).
- Resolve cross-file imports/calls against project module identities.
- Retain name-only fallback as heuristic and label ambiguity.

Postconditions:
- `import auth; auth.validate()` resolves to `auth.py::validate`.
- `from auth import validate as v; v()` resolves to the same symbol.
- Duplicate `validate()` in unrelated modules does not receive a parser/semantic edge from qualified calls.

### M3 — TypeScript whole-project semantic linker
Tasks:
- Use TypeScript `Program` + `TypeChecker` over project JS/TS files.
- Resolve call targets to compiler declarations.
- Resolve module imports to actual project files.
- Emit semantic call/import relations and reference occurrences.
- Cache project semantic output and reuse it when no source digest changed.

Postconditions:
- Two modules exporting same function name are disambiguated by compiler-resolved calls.
- Warm refresh with no changes reuses semantic-project cache.

Safety:
- Use compiler API only; never execute project scripts.

### M4 — Incremental/event journal
Tasks:
- Add append-only events table with monotonically increasing sequence.
- Record create/modify/delete observations, refresh boundary, revision transition, semantic provider reuse/recompute.
- Add `workspace.events.poll` and `workspace.diff.since`.

Postconditions:
- External edit produces a file-modified event and revision transition.
- No-op refresh does not fabricate a new revision.
- Event polling is bounded and cursorable.

### M5 — Affected-test intelligence v2
Tasks:
- Traverse incoming `calls`, `imports`, and explicit `tests` edges from changed symbols/files.
- Rank candidate test files with evidence paths and trust.
- Add targeted verification execution with framework-safe argv construction.
- Fall back to whole suite when selection is unsupported or evidence is weak.

Postconditions:
- Controlled project with two unrelated test files selects only the test that reaches the changed symbol.
- Targeted test execution returns a structured receipt and records whether selection was targeted or full-suite fallback.

### M6 — Runtime UI→source v2
Tasks:
- Expand static HTML semantic IDs to `id`, `data-testid`, and stable `name` anchors.
- Instrument `addEventListener` registrations inside browser runtime.
- Expose listener source URLs/line/column as runtime evidence.
- Map `habitat.local/<path>` listener frames back to project source files.

Postconditions:
- Clicking a button wired by external `app.js` yields a source hint for `app.js` in the element observation.
- Resource traversal outside the source root remains blocked.

### M7 — Context Compiler v3
Tasks:
- Add semantic-reference lane and affected-test lane.
- Prefer compiler-semantic relation paths over heuristic same-name edges.
- Expose omissions/trust distribution and explicit capability gaps.
- Add a compact `decision_packet` view for agent orientation.

Postconditions:
- Duplicate-name adversarial fixture ranks the compiler-resolved target above unrelated duplicate.
- Context packet does not contain raw full-file source by default.

### M8 — Protocol + schemas + docs
Tasks:
- Bump protocol to `v1alpha2`.
- Add methods for references, impact, targeted verify, event poll, revision diff, provider report.
- Add JSON schemas for occurrences, events, impact plans, verification receipts.
- Update architecture/status/limitations/install docs.

### M9 — Verification/admission
Required evidence:
- Full unit/adversarial suite.
- End-to-end alpha.2 demo.
- AGI ZIP stress: cold ingest + no-op warm refresh + one-file mutation + event evidence.
- Package extraction test from final ZIP.
- Delivery manifest with SHA-256.
- Self-audit preserving failed findings and bounded claims.

Admission rule:
- Any unresolved high finding involving source escape, stale mutation, fabricated semantic precision, project-code execution during ingestion, or archive corruption blocks release.

## 4. Unknown-unknown probes

1. Symlinks introduced after ingestion.
2. Case-sensitive/case-insensitive path collisions.
3. Generated/minified files overwhelming semantic indexes.
4. Monorepos with multiple modules using same import stem.
5. TypeScript path aliases without tsconfig resolution.
6. Python namespace packages and relative imports.
7. DOM listeners installed by frameworks after initial render.
8. Test frameworks whose CLI selectors differ from file paths.
9. Metadata-preserving external edits.
10. Semantic provider version changes invalidating cached relations.

Not all are expected to be solved in alpha.2. Each unresolved item must remain visible in limitations rather than silently disappearing.

## 5. Release claim boundary

Alpha.2 may claim only that executable fixtures demonstrate:
- stronger cross-file semantic resolution for supported Python/TypeScript patterns;
- first-class reference/event/impact evidence;
- targeted verification on supported test providers;
- runtime event-listener source hints for supported browser cases;
- cache reuse/invalidation behavior measured by included probes.

Alpha.2 must **not** claim universal code understanding, universal token savings, complete build-system understanding, or equivalent semantics for unsupported languages.


## 6. Outcome ledger — checkpoint close

| Milestone | Outcome | Admission evidence |
|---|---|---|
| M1 semantic trust/occurrences | PASS | persisted occurrences + schema/reference tests |
| M2 Python project linker | PASS, bounded | qualified/alias/relative-import duplicate-name tests |
| M3 TypeScript project semantics | PASS when provider available | Program+TypeChecker duplicate-export test; provider gap stays explicit |
| M4 event journal | PASS | external-edit journal + revision diff tests |
| M5 affected tests | PASS, bounded | unrelated-test exclusion + targeted Python verification |
| M6 UI→source v2 | PASS, bounded | runtime external-JS listener source hint + resource escape regression |
| M7 Context V3 | PASS on controlled fixture | semantic path reranks duplicate target; self-cycle correction preserved |
| M8 protocol/schemas/docs | PASS | v1alpha2 protocol and JSON schema suite |
| M9 verification/admission | PASS pending final packaged-artifact gate | 57/57 development tests, vertical demo, AGI-ZIP stress, self-audit |

### Belief changes discovered during implementation

- Source digest alone is **not** sufficient cache identity. Provider/compiler fingerprint is now part of reuse admission.
- Isolated runtime tests are **not** sufficient to validate browser lifecycle; full-suite multi-workspace behavior is now regression-tested.
- A correct semantic edge is **not** sufficient if retrieval ranking can still favor lexical noise; semantic evidence now participates in reranking.
- Development-tree benchmark success is **not** release reproducibility; benchmark scripts must execute directly from the extracted delivery.

### Deferred by explicit boundary rather than omission

Tree-sitter, LSP, SCIP, Java precise parsing, background watchers, production sandboxing, framework-complete UI source maps and controlled same-model token/task-success evaluation remain outside alpha.2 admission. They stay visible in `docs/LIMITATIONS.md` and `docs/control/UNKNOWN-UNKNOWNS.md`.
