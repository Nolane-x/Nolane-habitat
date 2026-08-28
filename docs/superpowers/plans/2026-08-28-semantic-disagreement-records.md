# Semantic Disagreement Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, bounded, revision-bound semantic disagreement records over admitted parse providers without changing primary compiler precedence or mutation authority.

**Architecture:** A pure disagreement engine owns canonical claims, deterministic IDs, conflict classification, and bounded comparison. A parse-lane collector executes admitted providers independently and converts `SemanticParseResult` objects into claims. `HabitatWorkspace` exposes a read-only on-demand facade; no storage schema, `_workspace_core.py`, MCP, or agent protocol changes occur.

**Tech Stack:** Python 3.10–3.14 stdlib (`dataclasses`, `hashlib`, `json`, `pathlib`), Habitat `SemanticAdmissionRegistry` / `SemanticParseResult`, `unittest`, GitHub Actions Ubuntu/Windows matrix.

**Spec:** `docs/superpowers/specs/2026-08-28-semantic-disagreement-records-design.md`

## Global Constraints

- Source bytes remain executable truth.
- Admission is required before provider comparison.
- Primary `compile_file()` behavior is unchanged.
- No majority vote or winner selection; every disagreement is unresolved.
- Provider failure/unavailable state cannot create negative-space conflicts.
- Maximum compared providers: 4.
- Maximum total claims: 5,000.
- Maximum disagreements: 2,000.
- Source input is bounded to the existing 5 MiB compiler parse limit.
- No `_workspace_core.py`, storage schema, MCP, agent protocol, workflow, or mutation-surface changes.

---

### Task 1: Canonical semantic claims and deterministic disagreement engine

**Files:**
- Create: `habitat/semantic/disagreement.py`
- Create: `tests/test_semantic_disagreement.py`

**Interfaces:**
- Produces: `SemanticClaim` dataclass.
- Produces: `SemanticDisagreementRecord` dataclass.
- Produces: `make_claim(...) -> SemanticClaim`.
- Produces: `compare_claims(claims_by_provider, *, comparison_complete, max_disagreements=2000) -> dict`.

- [ ] **Step 1: Write RED tests** for identical claims, attribute conflict, location-only conflict, presence conflict, incomplete comparison suppression, and deterministic IDs independent of provider input order.

- [ ] **Step 2: Run RED proof** with `python -m unittest tests.test_semantic_disagreement -v`; expected import failure because `habitat.semantic.disagreement` does not exist.

- [ ] **Step 3: Implement minimal canonical model and engine.** Canonicalize JSON with sorted compact encoding; derive claim/record IDs with SHA-256; classify unequal symbol values as location conflict when only range fields differ, otherwise attribute conflict. Emit presence conflicts only when `comparison_complete=True`.

- [ ] **Step 4: Run focused tests**, then `python -m unittest discover -s tests -v`.

- [ ] **Step 5: Commit** `feat: add semantic disagreement engine`.

---

### Task 2: Bounded parse-lane claim collector

**Files:**
- Create: `habitat/semantic/comparison.py`
- Create: `tests/test_semantic_comparison.py`

**Interfaces:**
- Consumes: `SemanticAdmissionRegistry.providers_for("parse", language=...)`.
- Consumes: `SemanticParseResult`.
- Produces: `compare_parse_providers(root, path, registry, revision, *, max_providers=4, max_claims=5000, max_disagreements=2000) -> dict`.

- [ ] **Step 1: Write RED fake-provider tests** covering two agreeing providers, conflicting providers, unavailable provider, throwing provider, provider limit, claim truncation, and admitted-only selection.

- [ ] **Step 2: Run RED proof**; expected import failure for `habitat.semantic.comparison`.

- [ ] **Step 3: Implement collector.** Validate path containment; reject binary/oversized source as bounded incomplete reports; capture path/digest/revision once; execute each admitted provider independently; normalize symbols, unresolved relations, and diagnostics to claims; mark provider failure/unavailable as incomplete; compare claims; verify revision getter/digest after collection and raise `SemanticComparisonStaleError` on drift.

- [ ] **Step 4: Run focused and full regression tests.**

- [ ] **Step 5: Commit** `feat: compare admitted semantic providers`.

---

### Task 3: Workspace read facade and non-auto-run Fabric projection

**Files:**
- Modify: `habitat/workspace.py`
- Create: `tests/test_workspace_semantic_disagreements.py`

**Interfaces:**
- Produces: `HabitatWorkspace.semantic_disagreements(path: Path) -> dict`.
- Adds diagnostic-only optional Fabric fields after an explicit comparison: `semantic_disagreement_state` with last path/count/complete/truncated/revision.

- [ ] **Step 1: Write RED tests** proving the facade returns revision/digest-bound records, path escape is rejected, `semantic_fabric()` does not run comparison automatically, and an explicitly requested comparison can be summarized without changing provider admission.

- [ ] **Step 2: Run RED proof**; expected `AttributeError` for missing workspace method.

- [ ] **Step 3: Implement facade** using current `self.semantic_registry` and `self.revision`. Cache only the bounded summary in memory; never persist claims or start providers merely for Fabric reporting.

- [ ] **Step 4: Run focused and full regression tests.**

- [ ] **Step 5: Commit** `feat: expose semantic disagreement projection`.

---

### Task 4: Authority and compatibility characterization gates

**Files:**
- Create: `tests/test_semantic_disagreement_authority.py`
- Create: `tests/test_semantic_disagreement_compatibility.py`

**Interfaces:**
- No new production interface unless a test reveals a real contract defect.

- [ ] **Step 1: Add characterization tests** proving semantic disagreement evidence cannot authorize `replace_symbol_source`, `compile_file()` primary output remains unchanged when comparison is never requested, ordinary workspace create/open/refresh does not execute disagreement comparison, and no provider admission changes after comparison.

- [ ] **Step 2: Run focused tests.** If any fail, debug root cause before modifying production.

- [ ] **Step 3: Run full regression suite.**

- [ ] **Step 4: Audit changed filenames** and fail if `_workspace_core.py`, `habitat/storage.py`, MCP/protocol files, or workflows changed.

- [ ] **Step 5: Commit** `test: lock semantic disagreement authority boundaries`.

---

### Task 5: Exact-head release gate and merge

**Files:** no planned production changes.

- [ ] **Step 1:** Open/maintain Draft PR against `main`.
- [ ] **Step 2:** Verify exact head SHA.
- [ ] **Step 3:** Require Habitat CI success for Ubuntu/Windows × Python 3.10/3.14 on that SHA, including full regression, protocol/recovery, reproducibility, and Semgrep gates.
- [ ] **Step 4:** Require CodeQL Python and JavaScript/TypeScript success on the same SHA.
- [ ] **Step 5:** Confirm no unresolved review threads and final changed-file boundary.
- [ ] **Step 6:** Mark Ready and merge using `expected_head_sha` only after every exact-head gate is green.
- [ ] **Step 7:** Verify `main` points to the merge commit before starting Truth/Evidence Convergence.
