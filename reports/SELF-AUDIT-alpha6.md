# Nolane Habitat 0.1.0-alpha.6 — Self-Audit

Date: 2026-08-07

## Admission posture

This audit distinguishes executable mechanism evidence from product/capability claims. Alpha.6 is admitted only for the bounded backend/cognition mechanisms verified in this delivery.

## Failure / correction ledger

### F1 — alpha.5 manifest schema rejected backend metadata

**Observation:** adding schema-3 `backend` metadata broke the existing manifest schema contract.

**Cause:** the schema treated the alpha.5 shape as the only valid shape.

**Correction:** schema 3 explicitly models backend identity while schema 2 remains accepted for existing workspaces; runtime migrates legacy manifests in memory to local authority.

**Verifier:** schema regression suite and reopening alpha<=5-style local workspaces.

### F2 — expected late source-digest fault, observed earlier context invalidation

**Observation:** a mirror authority was externally edited after a context handle was compiled. The failure probe expected `source-digest-drift-during-fault`, but `context-revision-stale` occurred first.

**Cause:** backend reconciliation correctly hydrated authority drift and advanced workspace revision before exact page fault.

**Correction:** retain the earlier invalidation and update the test to the stronger invariant: stale context must never reach exact-source admission.

**Verifier:** `test_mirror_page_fault_detects_authority_drift_before_reconcile`.

### F3 — Residency leaked the backend abstraction

**Observation:** source-byte estimation for resident symbols read `resolve_source_path(...).read_text()` directly from the semantic materialization.

**Risk:** a remote/mirror backend could present stale/non-authoritative compiler bytes as exact source evidence.

**Correction:** Residency exact-source estimation now calls `workspace.read_source_bytes`, which routes through backend authority.

**Verifier:** alpha.6 backend cognition suite and direct source-access audit.

### F4 — backend-equivalence harness used a nonexistent storage convenience API

**Observation:** harness called `Store.all_relations()`.

**Cause:** benchmark author assumed a convenience method instead of the real Store contract.

**Correction:** use explicit relation table query for the deterministic signature.

**Verifier:** fresh `BACKEND-EQUIVALENCE-alpha6.json`.

### F5 — backend-equivalence harness assumed wrong occurrence columns

**Observation:** after F4 correction the harness used `line/column/symbol_id`, but actual schema is `start_line/start_column/target_id`.

**Correction:** bind the harness to the real occurrence schema.

**Verifier:** equivalence benchmark passes before/after semantic signatures.

### F6 — first targeted-refresh refactor polluted deep refresh

**Observation:** a scripted edit attached `paths_considered=len(normalized)` to deep `refresh()`, causing `NameError: normalized` during workspace creation.

**Cause:** overly broad replacement while instrumenting targeted listing mode.

**Correction:** deep refresh reports `full-enumeration`/hashed-file count; only `refresh_paths` reports targeted/no-enumeration metrics.

**Verifier:** targeted refresh regression plus full 120-test suite.

### F7 — backend targeted hydration still left a workspace O(project) listing tax

**Observation:** backend `reconcile(paths)` became targeted, but `HabitatWorkspace.refresh_paths` still built a complete `iter_project_files()` map.

**Correction:** validate/resolve only supplied candidate paths after backend hydration. No whole materialized-root enumeration in the targeted path.

**Verifier:** `test_mirror_targeted_refresh_does_not_require_full_backend_enumeration` checks backend listing mode, one path considered and one file hashed.

### F8 — combined source admission command timed out after tests

**Observation:** the chained admission process produced `120/120 OK` and compile evidence, then timed out before producing demo/equivalence/stress artifacts.

**Interpretation:** this did not prove the later gates. No prior reports were reused.

**Correction:** run every expensive verifier independently with its own timeout/output and parse each fresh artifact.

**Verifier:** fresh alpha.6 demo, backend equivalence, context precision, AGI-ZIP stress and quick-start artifacts exist and parse.

## Fresh source-tree evidence

### Regression suite

`120 / 120 PASS`.

### End-to-end mirror backend demo

- retrieval confidence: high;
- page-plan exact source: 205 bytes on fixture;
- context feedback recorded as non-authoritative utility prior;
- work episode links context → transaction → commit → verification → close;
- semantic mutation updates canonical authority and compiler mirror identically;
- targeted verification: passed;
- receipt execution backend: `authority-local-process`;
- no-gold: low confidence, abstain, zero source bytes.

### Backend equivalence

Local and directory-mirror fixture agree on:

- pre-mutation semantic signature;
- post-mutation semantic signature;
- task context paths/confidence;
- canonical source after mutation;
- passing verification.

Execution provenance is intentionally different by backend.

### 202-file retrieval/planner fixture

- credential: high confidence, 127 exact-source bytes, zero noise files;
- billing: high confidence, 92 exact-source bytes, zero noise files;
- no-gold: low confidence, abstain, 0 source bytes.

### Supplied AGI ZIP stress

- files: 251;
- symbols: 865;
- occurrences: 4,372;
- warm refresh: 0 compiled / 251 reused;
- no-gold planner: abstain, zero source bytes;
- context feedback remains bounded and follow-up confidence stays high for the supported query.

## Claim boundary

### Admitted on tested fixtures/environment

- backend authority/materialization separation;
- local and mirror semantic equivalence for the fixture;
- authority-safe exact source;
- targeted known-path no-enumeration hydration;
- backend/execution provenance in receipts;
- bounded context utility prior;
- selective page planning/no-gold abstention;
- workflow episode provenance;
- backend/episode-bound checkpoint continuity;
- retained alpha.5 semantic/context/evidence capabilities under regression.

### Not admitted

- Cloudflare Computer integration;
- production remote transport/change feed;
- universal remote scaling;
- model token savings;
- same-model coding superiority;
- complete program causality;
- online learned retrieval optimum;
- hostile-code production sandbox;
- AGI capability.

## Source-tree admission decision

**ADMIT alpha.6 source tree provisionally**, conditional on final packaged artifact independently passing manifest integrity, clean-extracted tests, demo, equivalence, AGI stress, context precision, quick-start and isolated package import.
