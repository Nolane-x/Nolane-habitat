# Nolane Habitat 0.1.0-alpha.1 — Semantic Runtime Implementation Plan

> This plan is an executable control artifact. A checked item means the delivery contains source plus executable or inspectable evidence. It does **not** promote the whole product capability to complete.

## 0. Release thesis

Alpha.0 proved that a normal folder/ZIP/file can be represented as a semantic workspace without making the semantic database authoritative. Alpha.1 must prove a stronger claim:

> An agent can remain inside Habitat for more of the coding loop — orientation, exact inspection, semantic mutation, verification planning, test evidence, UI observation/action, and task resume — while source files remain normal and synchronized.

The release is rejected if it merely adds wrappers around file reads or shell output.

## 1. Protected invariants

- [x] Canonical project source remains ordinary files.
- [x] Semantic state is rebuildable and may be discarded.
- [x] Indexing never imports/executes project Python/JS modules.
- [x] Consequential mutations perform deep source reconciliation.
- [x] Heuristic symbol anchors cannot be used for semantic symbol replacement.
- [x] Generic shell execution is not an agent protocol primitive.
- [x] Browser UI semantics are primary; screenshot is optional secondary evidence.
- [x] Runtime/provider absence is reported as capability absence.
- [x] Token/task-success improvements are not claimed from plumbing measurements.

## 2. Workstream A — Incremental semantic twin

### A1. Compile cache

**Mechanism**
- Persist provider identity and unresolved relation facts by file ID.
- During deep refresh, SHA-256 every source file.
- If digest is unchanged and compile cache exists, reuse symbols/diagnostics/relation facts.
- Recompile/reindex only changed files.
- Reconstruct the relation graph from changed compiler output + cached relation facts.

**Evidence**
- [x] Unit test changes one file in a multi-file project and asserts `compiled_files == 1`.
- [x] Warm AGI-ZIP refresh reports `compiled_files == 0`, `reused_files == 251`.

**Known cost**
- Whole-project SHA-256 remains O(source bytes) for deep refresh.
- Global relation resolution is rebuilt from cached facts.
- Background watcher/Merkle hierarchy remain future work.

### A2. First-class diagnostics

- [x] Diagnostic table with path, line, column, severity, source and trust.
- [x] Diagnostics enter lexical search.
- [x] `workspace.inspect` accepts diagnostic IDs.
- [x] TypeScript parse errors materialize as diagnostic objects when provider exists.

## 3. Workstream B — Precision provider lane

### B1. Provider contract

- [x] `SemanticProvider` interface.
- [x] `SemanticParseResult` separates provider availability, symbols, relations, diagnostics and reason.
- [x] Provider trust remains bounded (`parser`, not `exact`, for current TypeScript parser lane).

### B2. TypeScript compiler API

- [x] Probe Node + resolvable TypeScript compiler module.
- [x] Parse `.ts/.tsx/.js/.jsx` without executing project source.
- [x] Extract functions, classes, methods, interfaces, type aliases, enums and function-valued declarations.
- [x] Capture source line ranges.
- [x] Capture import/call-name syntax facts.
- [x] Capture parser diagnostics.
- [x] Fall back to prior conservative regex extraction if provider unavailable.

### B3. Deferred precision

- [ ] Type-checker-backed cross-file definition/reference resolution.
- [ ] LSP client/provider contract.
- [ ] SCIP import.
- [ ] Tree-sitter provider and incremental tree-edit cache.
- [ ] Java parser/LSP precision lane.

**Reason for deferral:** runtime UI and context/mutation primitives give a larger falsifiable vertical slice than pretending a partial LSP layer is already precise.

## 4. Workstream C — Context Compiler V2

### C1. Task classification

- [x] implementation, UI, test, build, documentation and generic classes.
- [x] edit imperatives (`fix`, `implement`, `refactor`, `bug`) win over secondary “verify tests” wording unless strong UI evidence dominates.
- [x] Regression: credential-validation task ranks `validate_credentials` above superficial `login`/UI matches.

### C2. Independent evidence lanes

- [x] lexical FTS lane.
- [x] symbol-structure/fuzzy identifier lane.
- [x] test-file lane.
- [x] active diagnostic lane.
- [x] bounded dependency graph lane.
- [ ] runtime failure-history lane.
- [ ] Git/history lane.
- [ ] optional embedding lane + ablation.

### C3. Context boundedness

- [x] object budget.
- [x] per-path diversity cap.
- [x] file-object cap.
- [x] task-specific test evidence anti-crowding rule.
- [x] context handle persisted separately from returned slice.
- [x] paged continuation API returns semantic metadata without raw source.
- [x] stale context handle reports revision mismatch instead of silently serving old context.

## 5. Workstream D — Source access and semantic mutation

### D1. Bounded exact source access

- [x] symbol-body exact source inspection.
- [x] whole-file source remains available as fallback.
- [x] paged `workspace.source.read(path,start_line,max_lines)`.
- [x] digest and revision included in source page receipt.

### D2. Semantic symbol mutation

- [x] `replace_symbol_source` operation.
- [x] Stage captures path/range/digest/exact old symbol source.
- [x] Refuse heuristic semantic anchors.
- [x] Unified-diff preview before commit.
- [x] Multi-file preflight computes all outputs before first canonical write.
- [x] Atomic writes and backups.
- [x] Rollback on partial failure.
- [x] Post-commit semantic added/removed symbol-ID diff.
- [ ] AST-aware partial-body rewrite preserving formatting/comments.
- [ ] formatter capability binding.
- [ ] merge/rebase strategy for concurrent edits.

## 6. Workstream E — Structured execution and test evidence

### E1. Capability discovery

- [x] Python unittest/pytest.
- [x] npm scripts classified as test/build/service/script.
- [x] Maven/Gradle.
- [x] availability reason.
- [x] toolchain version fingerprint when executable supports `--version`.

### E2. Process execution

- [x] `shell=False` program+argv execution.
- [x] source-root working directory.
- [x] timeout.
- [x] bounded raw stdout/stderr fallback.
- [x] source-change readback.
- [x] POSIX process-group kill on timeout.
- [ ] hardened filesystem/network sandbox.
- [ ] cross-platform process-tree containment parity.
- [ ] CPU/memory quotas.

### E3. Test normalization

- [x] unittest summary normalization.
- [x] pytest summary normalization.
- [x] Jest/Vitest summary normalization.
- [x] normalized status/pass/fail/error/skip counts.
- [x] failed-test identifiers where parsable.
- [x] structured test evidence attached to execution receipt.

### E4. Verification planning

- [x] derive `tests` relation when a test-like file imports target file.
- [x] `workspace.verification.plan` accepts changed paths/object IDs.
- [x] return structurally linked test files + available test capabilities.
- [x] explicitly state that current capability may run broader suite.
- [ ] affected-test execution at individual test identity granularity.
- [ ] coverage/runtime-history weighted minimal verification set.

## 7. Workstream F — Runtime AI-native UI

### F1. Browser capability

- [x] Probe Playwright import.
- [x] Probe system Chromium/Chrome executable.
- [x] Launch headless browser with explicit system executable fallback.
- [x] Do not declare availability if either layer is missing.

### F2. Project-resource runtime

Initial implementation attempted ordinary localhost navigation. The execution environment returned `ERR_BLOCKED_BY_ADMINISTRATOR`. Rather than weakening the test or claiming success, the design changed:

- [x] Load canonical project HTML through `page.set_content`.
- [x] Inject project-relative base URL.
- [x] Intercept `http://habitat.local/**` resources and fulfill them directly from source root.
- [x] Enforce source-root path containment on routed resources.
- [x] Preserve JS/CSS/image relative-resource behavior without requiring a human-visible web server/terminal.

### F3. Semantic observation

- [x] semantic handles.
- [x] role inference.
- [x] accessible-ish names from ARIA/labels/placeholder/alt/title/text.
- [x] value/checked/enabled/visibility.
- [x] bounding rectangles.
- [x] selected computed-style state.
- [x] Playwright ARIA snapshot.
- [x] console events.
- [x] network/resource events.
- [x] horizontal-overflow detector.
- [x] viewport-clipping detector.
- [x] optional screenshot receipt.

### F4. Semantic actions

- [x] click.
- [x] fill.
- [x] select.
- [x] check/uncheck.
- [x] press.
- [x] post-action semantic observation.
- [x] added/removed/changed element delta.

### F5. Source bridge

- [x] runtime DOM ID → indexed HTML ID source hint.
- [x] class/ID → CSS selector candidate hints.
- [ ] framework component ownership.
- [ ] source maps.
- [ ] CSS cascade proof.
- [ ] visual regression model.

## 8. Workstream G — Persistent living task state

- [x] checkpoint ID.
- [x] task and revision.
- [x] resident semantic object list.
- [x] per-object source digest.
- [x] resume classifies fresh/stale/missing objects.
- [x] stale/missing state recommends reorientation.
- [ ] warm/cold residency tiers.
- [ ] active transaction/run/browser/service references.
- [ ] resumable external service/browser world.

## 9. Workstream H — Agent protocol

- [x] protocol version `habitat.agent.v1alpha1`.
- [x] `protocol.capabilities` negotiation.
- [x] no `shell.exec`.
- [x] context paging.
- [x] source paging.
- [x] semantic symbol staging.
- [x] verification planning.
- [x] checkpoint/resume.
- [x] runtime UI open/observe/act/close.
- [x] persistent NDJSON server remains the intended browser-session transport.
- [ ] HTTP transport.
- [ ] Python SDK.
- [ ] TypeScript SDK.
- [ ] MCP adapter.

## 10. Test matrix

Alpha.1 release gate:

- archive traversal/symlink/size safety;
- no project execution during indexing;
- source-prompt prose has no authority;
- exact Python AST;
- best-available TypeScript provider trust;
- incremental cache reuse;
- context ranking regression;
- context page boundedness;
- semantic symbol mutation preview/commit/rollback;
- stale external-edit rejection;
- structured execution receipt;
- structured unittest evidence;
- verification-plan linkage;
- checkpoint/resume invalidation;
- runtime browser semantic action loop;
- UI source hint;
- protocol negotiation and no generic shell;
- schema JSON validity.

## 11. Stress corpus gate

Use the supplied `Nolane-AGI-Cognitive-System-4.0.0(1).zip` only as a **corpus/skill-system stress input**, not as Habitat's project specification.

Collect:
- cold ingest seconds;
- file/symbol/diagnostic counts;
- indexed vs source bytes;
- warm deep-refresh seconds;
- compiled vs reused file counts;
- several Context Compiler slices.

Do not infer token savings from these metrics.

## 12. Alpha.1 promotion criteria

Promote alpha.1 only if:

1. all unit/adversarial tests pass;
2. runtime UI action loop passes when browser capability is available;
3. warm refresh demonstrably reuses unchanged compile results;
4. source mutations remain digest/revision guarded;
5. protocol contains no generic shell primitive;
6. docs state unresolved LSP/sandbox/token-benchmark gaps;
7. delivery archive integrity passes.

## 13. Next checkpoint hypotheses

Alpha.2 should prioritize **semantic precision and verification intelligence**, not UI decoration:

1. LSP/SCIP cross-file definition/reference/type provider;
2. Tree-sitter incremental parser cache for supported languages;
3. structured diagnostic provider ingestion from type checkers/builds;
4. test identity graph + affected-test execution;
5. browser application-service lifecycle for framework dev servers;
6. UI component/source-map mapping;
7. background source watcher + event journal;
8. benchmark harness comparing plain file tools vs Habitat using the same model.

If alpha.2 cannot improve first-correct-location or reduce redundant source reconstruction under controlled tasks, redesign the semantic object/context model before adding more integrations.
