# Self-Audit — Nolane Habitat 0.1.0-alpha.1

## Release question

Does alpha.1 materially advance the thesis that an AI agent can work inside a project-native semantic environment rather than repeatedly reconstructing project state through file-tree/terminal/browser presentation?

**Bounded answer: yes for the implemented vertical slice; not yet for full production coding-agent workloads.**

## Executable evidence

### Test suite

- **41/41 tests passed** in the final pre-package run.
- Includes archive safety, source authority, no source execution during indexing, semantic compiler trust, incremental reuse, context ranking/paging, semantic mutation safety, structured test evidence, verification planning, checkpoint invalidation, protocol negotiation, schema contract validation, runtime Chromium UI actions, external project resource loading and source-root escape blocking.
- Full log: `reports/TEST-EVIDENCE-alpha1.txt`.

### End-to-end vertical demo

`reports/DEMO-EVIDENCE-alpha1.json` executes one synthetic project through:

1. source ingest;
2. task orientation;
3. exact symbol inspection;
4. staged symbol-source mutation + diff preview;
5. commit to canonical source;
6. verification planning;
7. structured unittest execution (`passed`);
8. runtime browser open;
9. semantic `fill` + `click` actions;
10. observed UI state delta to `Hello Nolane`;
11. task checkpoint/resume;
12. warm refresh with `compiled_files=0`, `reused_files=5`.

### Supplied AGI ZIP stress corpus

`reports/AGI-ZIP-STRESS-alpha1.json` uses the supplied AGI skill archive as a large corpus, not as Habitat's target project specification.

Observed in this environment:

- source files: **251**;
- source bytes after managed extraction: **88,271,461**;
- indexed text bytes: **1,723,080**;
- semantic symbols: **865**;
- cold ingest: approximately **0.65 s** in that run;
- warm deep refresh: approximately **0.14 s**;
- warm deep refresh: **0 files recompiled, 251 compile-cache entries reused**.

These are engineering measurements. They do **not** establish model-token reduction, lower cost, or improved task success.

## Design corrections made during alpha.1

### 1. Alpha.0 was not actually incremental enough

`refresh()` reparsed every project file. Alpha.1 now deep-hashes source for consequential freshness but reuses compiler facts for unchanged digests and only reparses/reindexes changed files.

### 2. Context V2 initially regressed ranking

A superficial lexical `login` match overtook the more decision-relevant `validate_credentials` symbol. The scoring model was corrected to reward multi-concept structural coverage and reduce correlated lexical amplification. The original failure is now covered by regression tests.

### 3. Browser navigation assumption failed

Ordinary localhost/file navigation returned `ERR_BLOCKED_BY_ADMINISTRATOR` in the execution environment. Rather than bypassing the test or downgrading the capability claim, runtime project loading was redesigned:

- canonical HTML is loaded with Playwright `set_content`;
- a synthetic project base URL is inserted;
- relative JS/CSS/image requests are intercepted and fulfilled directly from the source root;
- traversal outside the source root is rejected.

External project JS execution and escape blocking are now tested.

## Claims supported by evidence

Alpha.1 can reasonably claim that it provides:

- project ingest from folder/ZIP/file;
- rebuildable semantic twin with source authority preserved;
- per-file incremental compiler reuse;
- exact Python syntax objects and parser-grade TypeScript syntax objects when the provider is available;
- first-class parser diagnostics;
- bounded task context compilation with explicit provenance/trust and paging;
- exact source paging;
- guarded semantic symbol replacement for non-heuristic anchors;
- structured execution/test receipts;
- a structural verification-plan primitive;
- runtime semantic browser observation/action for project HTML when browser capability is available;
- initial UI→source hints;
- persistent task checkpoint/resume invalidation;
- an agent protocol that does not expose generic shell as a primitive.

## Claims explicitly **not** supported yet

Do not claim:

- Habitat is a secure sandbox;
- Habitat understands arbitrary repositories completely;
- TypeScript/Java cross-file references are fully precise;
- runtime UI semantics prove visual correctness;
- framework component/source mapping is complete;
- checkpoints resume the entire runtime world;
- Habitat reduces model tokens by a particular percentage;
- Habitat improves task success relative to Claude Code/Codex/other agents;
- Habitat is production-ready.

## Highest-priority remaining risks

1. no LSP/SCIP whole-program reference/type lane;
2. no Tree-sitter incremental syntax-tree layer;
3. no background watcher/event journal or multiprocess lease;
4. local execution is not sandboxed;
5. affected-test selection is structural but not yet test-identity/minimal-execution aware;
6. framework UI requires managed dev-server lifecycle + source maps/component mapping;
7. same-model controlled benchmark is absent.

## Release decision

**Promote to `0.1.0-alpha.1` as a complete checkpoint delivery.**

Reason: all alpha.1 postconditions claimed in the release documents have executable evidence, discovered regressions were corrected rather than hidden, source-authority/safety invariants remain intact, and unresolved capabilities are explicitly bounded.
