# Foundation Convergence Closure — Implementation Plan

Baseline: `44b5ea12a5c2b014677258f4144981ac731ed4bd`

## 1. RED semantic precision contract

Add `tests/test_semantic_precision_matrix.py` first. Require a deterministic Python + TypeScript oracle, Habitat compiler and Tree-sitter lanes, exact TP/FP/FN with precision/recall, explicit unavailable metrics, and fail-closed coverage requiring two languages and two distinct available providers per language. Verify failure because the benchmark module is absent.

## 2. GREEN benchmark

Add `benchmarks/semantic_precision_matrix.py`. Reuse `compile_file()` and `TreeSitterProvider`; do not change Semantic Fabric. Report actual selected provider identity and fingerprint. Missing provider measurements remain null. Scores are descriptive; no quality threshold or superiority claim is introduced.

## 3. CI evidence

Add a gating CI command that writes `.test-artifacts/semantic-precision-matrix.json`. Existing artifact upload preserves the report on every Ubuntu/Windows and Python matrix job.

## 4. Constitutional learning boundary

Confirm the existing learning-policy path rejects constitutional fields before persistence. Add only a focused test if current executable coverage does not prove this behavior. Production code changes are allowed only after a clean RED failure exposes a real gap.

## 5. Closure evidence map

After GREEN behavior, add `docs/evidence/FOUNDATION-CONVERGENCE-CLOSURE.md` mapping all 12 canonical exit criteria to concrete executable tests/tools/artifacts. The document is an evidence index, not a manual pass manifest.

## 6. Certification

Certify the exact final SHA with full Habitat CI, isolated matrix, public compatibility, protocol conformance, recovery, reliability, reproducibility, distribution, Semgrep, and CodeQL. Recheck changed files, review surface, and main drift before merge. Then require fresh post-merge CI/CodeQL before a closure claim.

Claim boundary: architectural Foundation Convergence closure under tested conditions only; no AGI, universal safety, universal semantic correctness, or comparative superiority claim.
