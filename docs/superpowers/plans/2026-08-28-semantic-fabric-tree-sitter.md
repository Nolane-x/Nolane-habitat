# Semantic Fabric Tree-sitter Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Tree-sitter from a detected host capability into a real, admitted, provenance-bound broad syntax provider used by the compiler as a parser-trust fallback.

**Architecture:** Keep Tree-sitter optional to the core package. A `TreeSitterProvider` uses the standard `tree_sitter.Parser` objects supplied by `tree-sitter-language-pack`, advertises only grammars actually available on the host, and enters the existing `SemanticAdmissionRegistry` through the same register/probe/admit path as TypeScript. Precise/exact providers retain precedence; Tree-sitter is a broad parser-level fallback and never gains source or mutation authority.

**Tech Stack:** Python 3.10+, `tree-sitter`, `tree-sitter-language-pack`, unittest, existing Semantic Fabric V2 admission/runtime/compiler contracts, GitHub Actions Ubuntu/Windows matrix.

**Spec:** `docs/design/FOUNDATION-CONVERGENCE.md`

## Global Constraints

- Preserve `fabric_version = 1`; provider-admission semantics remain `contract_version = 2`.
- Tree-sitter trust ceiling is `parser`; it never has source or mutation authority.
- Core install remains lightweight: Tree-sitter is an optional extra, not a mandatory dependency.
- CI installs the optional Tree-sitter extra so the real parser path is exercised on Ubuntu/Windows and Python 3.10/3.14.
- TypeScript compiler API retains precedence for JavaScript/TypeScript when admitted.
- Python AST remains the exact primary parser for valid Python; Tree-sitter may recover syntax structure only when exact parsing fails.
- Provider detection is not admission. Only the existing registry may make a provider selectable.
- Cache identity must change when the admitted Tree-sitter runtime/fingerprint changes.
- Do not introduce a graph database, LSP process manager, SCIP importer, or new mutation authority in this wave.

---

### Task 1: Optional runtime dependency and provider contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Create: `habitat/semantic/tree_sitter_provider.py`
- Create: `tests/test_tree_sitter_provider.py`

**Interfaces:**
- Produces: `TreeSitterProvider(SemanticProvider)`
- Produces: `TreeSitterProvider.available() -> tuple[bool, str]`
- Produces: `TreeSitterProvider.parse(root, path, text, file_id) -> SemanticParseResult`

- [x] **Step 1: Write RED tests** requiring the provider module, parser-level descriptor, fail-honest missing-runtime behavior, and CI installation of the optional extra.
- [x] **Step 2: Run RED on PR CI** and verify failures are caused by the missing provider/extra rather than import or fixture errors.
- [ ] **Step 3: Add optional dependency group** `tree-sitter` with `tree-sitter>=0.26,<0.27` and `tree-sitter-language-pack>=1.12.3,<2`; include it in CI installation without adding it to core dependencies.
- [ ] **Step 4: Implement minimal provider probing** using `tree_sitter_language_pack.has_language/get_parser`; advertise only grammars that can actually be obtained.
- [ ] **Step 5: Run GREEN targeted/full tests** and keep provider unavailable when runtime/grammars cannot be proved.

### Task 2: Real syntax extraction and provenance

**Files:**
- Modify: `habitat/semantic/tree_sitter_provider.py`
- Modify: `tests/test_tree_sitter_provider.py`

**Interfaces:**
- `parse(...)` returns `SemanticParseResult(provider="tree-sitter", available=True, ...)` when an admitted grammar parses successfully.
- Emitted `SymbolRecord.trust` is `parser`.
- Tree-sitter syntax errors become parser-trust diagnostics rather than exact/compiler diagnostics.

- [ ] **Step 1: Write RED fixtures** for Python, TypeScript/JavaScript, and Java declarations plus malformed source recovery.
- [ ] **Step 2: Verify RED** because the provider does not yet extract those declarations/diagnostics.
- [ ] **Step 3: Implement explicit declaration maps** for supported language node kinds and obtain names through Tree-sitter `name` fields; do not use broad suffix heuristics that inflate false positives.
- [ ] **Step 4: Emit stable symbol IDs** using existing `stable_id` and source line ranges from nodes.
- [ ] **Step 5: Emit a parser-trust diagnostic** when the root tree reports syntax errors while preserving any recoverable symbols.
- [ ] **Step 6: Verify GREEN** on real runtime tests.

### Task 3: Runtime admission and precedence

**Files:**
- Modify: `habitat/semantic/runtime.py`
- Modify: `habitat/semantic/admission.py`
- Modify: `habitat/semantic/base.py`
- Modify: `habitat/semantic/typescript.py`
- Modify: `tests/test_semantic_runtime_registry.py`
- Modify: `tests/test_semantic_admission_registry.py`

**Interfaces:**
- Default runtime registers TypeScript first, Tree-sitter second.
- `SemanticProvider.provider_fingerprint() -> str | None` contributes to admission cache identity.
- Registry `cache_identity()` includes provider fingerprint.

- [ ] **Step 1: Write RED tests** proving TypeScript precedence over Tree-sitter and provider-fingerprint-driven cache identity changes.
- [ ] **Step 2: Verify RED** against current runtime/registry.
- [ ] **Step 3: Add default `provider_fingerprint()`** to `SemanticProvider`; TypeScript returns compiler version, Tree-sitter returns runtime/language-pack identity plus admitted grammar set.
- [ ] **Step 4: Include fingerprint in registry cache identity** without weakening existing admission evidence checks.
- [ ] **Step 5: Register Tree-sitter after TypeScript** in `build_default_semantic_registry()` so capability selection remains precise-first.
- [ ] **Step 6: Verify GREEN** and existing admission/runtime tests.

### Task 4: Compiler fallback integration

**Files:**
- Modify: `habitat/compiler.py`
- Create: `tests/test_tree_sitter_compile_integration.py`

**Interfaces:**
- JavaScript/TypeScript: admitted TypeScript compiler → admitted Tree-sitter → regex fallback.
- Python: exact AST success remains unchanged; on AST syntax failure, admitted Tree-sitter may recover parser-trust structure.
- Java: admitted Tree-sitter → existing regex fallback.
- Other currently recognized text languages may use admitted Tree-sitter only when the provider explicitly advertises that language.

- [ ] **Step 1: Write RED integration tests** for precise-provider precedence and Tree-sitter fallback selection.
- [ ] **Step 2: Verify RED** because current compiler has no Tree-sitter fallback path.
- [ ] **Step 3: Add a small provider-selection helper** that asks the workspace registry for admitted `parse` providers by language and can exclude an already-attempted provider.
- [ ] **Step 4: Integrate fallback paths** while preserving legacy behavior when no semantic registry is supplied.
- [ ] **Step 5: Verify provider/trust metadata** and full regression.

### Task 5: Diagnostic truth and final verification

**Files:**
- Modify only if required by failing contract: `habitat/semantic/fabric.py`
- Modify: `tests/test_semantic_workspace_admission.py` if a workspace-level assertion is needed.

**Interfaces:**
- `workspace.semantic_fabric()` reports admitted Tree-sitter from the same registry used by compilation.
- Detected but unadmitted host Tree-sitter remains diagnostic-only.

- [ ] **Step 1: Add/extend RED workspace assertion** that compilation and `semantic_fabric()` agree about Tree-sitter admission.
- [ ] **Step 2: Implement only the minimum report adaptation if existing generic runtime-report merging is insufficient.
- [ ] **Step 3: Run the exact final candidate through the full Habitat CI matrix and CodeQL.**
- [ ] **Step 4: Confirm Ubuntu/Windows × Python 3.10/3.14 pass release identity, full regression, baseline, isolated matrix, compatibility, protocol, DB/source recovery, fault injection, reproducible builds, distribution verification, Semgrep, truth-core, and artifact upload.
- [ ] **Step 5: Review PR diff for authority regressions, host-dependent false claims, provider precedence, and cache invalidation before merge.**
