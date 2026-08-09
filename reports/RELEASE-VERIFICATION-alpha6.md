# Nolane Habitat 0.1.0-alpha.6 — Release Verification

Date: 2026-08-07

## Source-tree admission

Fresh alpha.6 source-tree gates:

- unittest discovery: **120 / 120 PASS**;
- `compileall`: PASS;
- JSON schema/report parse: PASS;
- README/CLI quick-start (`create → enter → orient → backend-info`): PASS;
- alpha.6 mirror-backend vertical demo: PASS;
- local-vs-directory-mirror semantic equivalence: PASS;
- 202-file context precision/planner harness: PASS;
- supplied Nolane AGI ZIP stress: PASS.

## RC independent artifact gate

Artifact: `Nolane-Habitat-0.1.0-alpha.6-RC.zip`

Independent clean extraction verifier (separate from `tools/package.py`):

- manifest version: `0.1.0-alpha.6`;
- listed entries excluding manifest: **189**;
- missing: 0;
- extra: 0;
- file size/hash mismatch: 0;
- independently recomputed manifest root hash: PASS;
- ZIP integrity: PASS.

Clean-extracted RC execution:

- **120 / 120 tests PASS**;
- compileall PASS (run independently after the combined gate process was interrupted);
- alpha.6 vertical demo PASS;
- backend equivalence PASS;
- context precision/planner PASS;
- supplied AGI ZIP stress PASS;
- CLI quick-start PASS;
- isolated `pip --no-build-isolation --no-deps --target` install/import PASS;
- imported `habitat.__version__ == 0.1.0-alpha.6` from the isolated target;
- optional MCP missing-SDK negative path PASS on this host.

## Key bounded evidence

### Backend equivalence fixture

Local and directory-mirror backends agree on pre/post semantic signatures, context paths/confidence, canonical mutation output and successful verification. Execution provenance differs by backend as intended.

### Targeted remote-like hydration

Known-path mirror refresh reports `targeted-no-enumeration`, one path considered and one workspace hash for the single-file fixture. Full mirror reconciliation remains an O(project) operation and is not claimed as production remote scaling.

### Context planner fixture

With 200 distractors:

- credential task: high confidence, 127 exact-source bytes, zero distractor paths;
- billing task: high confidence, 92 exact-source bytes, zero distractor paths;
- no-gold task: low confidence, abstain, zero source bytes.

These are deterministic source-byte measurements, not token measurements.

### Supplied AGI corpus

- 251 files;
- 865 symbols;
- 4,372 occurrences;
- warm refresh: 0 compiled / 251 reused;
- no-gold page planner: abstain, zero source bytes.

## Release-tooling failure retained

A single chained source admission command timed out after printing `120/120 OK`, before later evidence artifacts were produced. No prior artifacts were reused. Every expensive gate was rerun independently and fresh outputs were parsed.

The first RC combined `tests → compileall` shell also exceeded its outer command budget after tests, despite tests passing. Compileall was rerun independently with a bounded timeout and passed. This is treated as release-harness behavior, not silently converted into core evidence.

## Claim boundary

This release verifies Habitat mechanisms on the tested host/fixtures. It does **not** establish:

- Cloudflare Computer compatibility or network integration;
- production remote storage/execution correctness;
- universal LLM token reduction;
- coding-task success uplift;
- complete program causality;
- production hostile-code isolation;
- AGI capability.

Final `COMPLETE-DELIVERY` must still pass ZIP integrity, independent manifest/hash verification and clean-extracted regression/evidence gates after this report is included.
