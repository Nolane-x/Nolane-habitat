# Truth / Evidence Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive constitutional truth/evidence layer that separates authority from confidence, normalizes existing evidence into deterministic claims, exposes contradiction/staleness projection, and replaces the single ad-hoc `replace_symbol_source` trust check with an inspectable authority declaration without changing storage schemas, compiler selection, semantic admission, recovery, MCP, or protocol behavior.

**Architecture:** New pure modules under `habitat/truth/` own authority taxonomy, immutable claims, record adapters, and contradiction/staleness projection. `HabitatWorkspace` remains a thin compatibility facade: it explicitly projects already-resident evidence and delegates the existing symbol-mutation boundary to the authority helper. Existing tables remain the source of stored evidence; no normalized-claim database is introduced.

**Tech Stack:** Python 3.10–3.14 stdlib (`dataclasses`, `enum`, `hashlib`, `json`, `types`, `typing`), existing Habitat Store/semantic records, `unittest`, GitHub Actions Ubuntu/Windows matrix.

**Spec:** `docs/superpowers/specs/2026-08-28-truth-evidence-convergence-design.md`

## Global Constraints

- Authority is categorical, never a numeric confidence/rank.
- Unknown trust/authority fails closed for action authorization.
- Existing `TrustGrade` fields and uncertainty weighting remain compatible; neither can elevate action authority.
- Source bytes and indexed digest/revision bindings remain canonical truth.
- No schema migration and no edits to `habitat/storage.py` or `habitat/storage_migrations.py`.
- No `_workspace_core.py`, compiler-selection, semantic-admission, MCP, protocol, workflow, or transaction-recovery changes.
- Truth projection is explicit and read-only; it never starts LSP/SCIP, compares providers, refreshes, or reconciles implicitly.
- Contradictions remain unresolved; there is no majority vote or winner selection.
- Output is deterministic and bounded.
- Python 3.10 compatibility is mandatory; use `class AuthorityClass(str, Enum)`, not `StrEnum`.

---

### Task 1: Authority taxonomy and explicit operation declarations

**Files:**
- Create: `tests/test_truth_authority.py`
- Create: `habitat/truth/__init__.py`
- Create: `habitat/truth/authority.py`

**Interfaces:**
- `AuthorityClass` string enum with exactly seven architecture classes.
- `legacy_authority(trust) -> AuthorityClass | None`.
- `OperationAuthorityDeclaration` immutable record.
- `operation_authority(operation) -> OperationAuthorityDeclaration`.
- `operation_allows_evidence(operation, authority) -> bool`.

- [ ] **Step 1: Write RED tests** proving exact seven enum values, conservative legacy trust mapping, unknown trust maps to no authority, no numeric rank/comparison API exists, declarations are inspectable, `replace_symbol_source` accepts only `SOURCE_EXACT`, direct-source operations do not accept derived evidence anchors, and confidence is not an authorization input.
- [ ] **Step 2: Verify RED** on the Draft PR exact head; expected failure is missing `habitat.truth` / authority interface, not an unrelated error.
- [ ] **Step 3: Implement minimal authority kernel** with explicit accepted-class sets only; do not introduce strength/rank helpers.
- [ ] **Step 4: Verify focused tests and full regression** on the implementation head.
- [ ] **Step 5: Commit** `feat: add truth authority kernel`.

---

### Task 2: Deterministic immutable truth claims

**Files:**
- Create: `tests/test_truth_claims.py`
- Create: `habitat/truth/claims.py`
- Modify: `habitat/truth/__init__.py`

**Interfaces:**
- `TruthClaim` frozen dataclass.
- `make_truth_claim(...) -> TruthClaim`.
- deterministic canonical JSON/value digest/claim ID helpers kept internal.

- [ ] **Step 1: Write RED tests** for mapping-order-independent IDs, finite JSON validation, authority/provenance-sensitive identity, immutable canonical value/provenance, confidence stored independently from authority, unknown authority rejection, and origin-authority preservation without promotion.
- [ ] **Step 2: Verify RED**; expected failure is missing claim API.
- [ ] **Step 3: Implement minimal claim model.** Canonicalize JSON using sorted compact encoding with `allow_nan=False`; deep-freeze mappings/lists for immutable public values; calculate SHA-256 value/claim identities from thawed canonical data.
- [ ] **Step 4: Verify focused and full regression tests.**
- [ ] **Step 5: Commit** `feat: add deterministic truth claims`.

---

### Task 3: Side-effect-free adapters over existing evidence structures

**Files:**
- Create: `tests/test_truth_adapters.py`
- Create: `habitat/truth/adapters.py`
- Modify: `habitat/truth/__init__.py`

**Interfaces:**
- `claim_from_file_record`
- `claim_from_symbol_record`
- `claim_from_relation_record`
- `claim_from_diagnostic_record`
- `claim_from_occurrence_record`
- `claim_from_evidence_row`
- `claim_from_semantic_claim`
- `claim_from_epistemic_item`
- `claim_from_memory`

- [ ] **Step 1: Write RED tests** using dataclasses/dicts/SQLite-row-shaped mappings. Prove file snapshots become `SOURCE_EXACT`; legacy semantic/parser/heuristic/derived mapping is conservative; generic evidence cannot self-upgrade; semantic claims preserve provider fingerprint/evidence; epistemic items are always `MODEL_INFERRED`; memories are always `MEMORY_RECALLED`; valid original authority is provenance only; invalid explicit original authority is rejected.
- [ ] **Step 2: Verify RED**; expected missing adapter API.
- [ ] **Step 3: Implement deterministic adapters** with no database access or provider execution. Missing provenance remains absent; JSON payload strings are parsed strictly when contract says they are JSON.
- [ ] **Step 4: Verify focused and full regression tests.**
- [ ] **Step 5: Commit** `feat: adapt existing evidence into truth claims`.

---

### Task 4: Deterministic contradiction and staleness projection

**Files:**
- Create: `tests/test_truth_projection.py`
- Create: `habitat/truth/projection.py`
- Modify: `habitat/truth/__init__.py`

**Interfaces:**
- `StaleClaimRecord` frozen dataclass.
- `TruthContradictionRecord` frozen dataclass.
- `claim_staleness(...)`.
- `project_truth(claims, *, current_revision, current_digests, max_claims=500) -> dict`.

- [ ] **Step 1: Write RED tests** proving revision mismatch is stale, digest mismatch/unavailable path binding fails closed, stale historical claims do not create contradictions, current unequal values for same subject/predicate/revision do create one unresolved deterministic contradiction, input ordering does not change IDs/output ordering, weaker-claim plurality never upgrades authority, and bounds/truncation are deterministic.
- [ ] **Step 2: Verify RED**; expected missing projection API.
- [ ] **Step 3: Implement pure projection.** Compare only non-stale claims in the same explicit scope; retain stale claims as records; never select winners or synthesize stronger authority.
- [ ] **Step 4: Verify focused and full regression tests.**
- [ ] **Step 5: Commit** `feat: project truth contradictions and staleness`.

---

### Task 5: Workspace truth facade and mutation authority integration

**Files:**
- Create: `tests/test_workspace_truth_projection.py`
- Create: `tests/test_truth_mutation_authority.py`
- Modify: `habitat/workspace.py`

**Interfaces:**
- `HabitatWorkspace.truth_projection(*, max_claims=500, semantic_claims=()) -> dict`.
- Existing `stage_change()` behavior preserved, but `replace_symbol_source` authority is evaluated by the truth authority kernel.

- [ ] **Step 1: Write RED workspace tests** proving `truth_projection()` is absent before implementation, is bounded/deterministic when added, includes existing file/symbol/relation/diagnostic/occurrence/evidence rows, accepts explicitly supplied semantic claims, detects external source drift as stale without calling refresh/reconcile, and does not call `compare_parse_providers`, `_lsp_manager`, `_scip_manager`, or alter semantic admission.
- [ ] **Step 2: Write RED mutation tests** proving the authority helper is the enforcement seam while preserving legacy behavior: exact symbol anchors pass into existing transaction handling; semantic/parser/heuristic/derived/unknown anchors fail with the existing `TransactionConflict` boundary/message; confidence or recalled origin authority cannot make a non-exact anchor authoritative.
- [ ] **Step 3: Verify RED** on exact test-only head; failures must be missing facade/kernel integration, not fixture mistakes.
- [ ] **Step 4: Implement minimal workspace facade.** Read only already-resident Store rows; derive current canonical digests without refresh; adapt through `habitat.truth.adapters`; project through `project_truth`. Do not persist normalized claims.
- [ ] **Step 5: Replace only the ad-hoc `symbol['trust'] != 'exact'` authorization decision with `legacy_authority(...)` + `operation_allows_evidence(...)`; preserve the external failure text and allow MutationEngine to keep canonical digest/source checks.
- [ ] **Step 6: Verify focused tests, semantic disagreement compatibility tests, mutation recovery tests, and full regression.**
- [ ] **Step 7: Commit** `feat: expose workspace truth projection`.

---

### Task 6: Compatibility boundary and exact-head completion gate

**Files:**
- Create or extend only tests if a missing characterization is found.
- No planned production changes.

- [ ] **Step 1: Run characterization gates** proving TrustGrade remains unchanged; `habitat/uncertainty.py` weighting is not used by authority authorization; compile provider precedence/admission behavior remains unchanged; semantic disagreement remains explicit; ordinary create/open/refresh never executes truth/semantic comparison automatically.
- [ ] **Step 2: Audit changed filenames** and fail completion if `_workspace_core.py`, `habitat/storage.py`, `habitat/storage_migrations.py`, compiler-selection code, MCP/protocol files, workflows, or transaction-recovery code changed without a separately proven defect.
- [ ] **Step 3: Open/maintain Draft PR against `main`; freeze one final candidate SHA.**
- [ ] **Step 4: Require Habitat CI success on that exact SHA for Ubuntu/Windows × Python 3.10/3.14, including full regression, isolated matrix, compatibility, protocol, DB/mutation recovery, fault injection, reproducibility, distribution verification, Semgrep, and quality gate.
- [ ] **Step 5: Require CodeQL success on the same SHA.**
- [ ] **Step 6: Confirm head has not drifted and all review threads are resolved.**
- [ ] **Step 7: Mark Ready and merge with `expected_head_sha` only after every exact-head gate is green.**
- [ ] **Step 8: Verify `main` points to the resulting merge commit and post-merge status before beginning Foundation Convergence Wave 3.

## Completion Boundary

Wave 2 is complete only when the exact merged candidate satisfies every design exit criterion. Passing focused tests without the cross-platform exact-head gates is not completion.
