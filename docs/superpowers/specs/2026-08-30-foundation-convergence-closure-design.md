# Foundation Convergence Closure — Design

**Date:** 2026-08-30  
**Baseline:** `44b5ea12a5c2b014677258f4144981ac731ed4bd`  
**Scope:** close the repository-defined Foundation Convergence exit criteria without expanding the public alpha.19 protocol or weakening existing truth, recovery, learning, execution, or observatory boundaries.

## 1. Evidence-first closure rule

Closure is not a `12/12 = true` manifest. Every admitted criterion must be backed by executable behavior already present in the repository or by a new executable contract introduced in this closure. A test-file name, capability probe, provider binary, or documentation claim alone is not sufficient evidence.

The closure claim is deliberately narrow: Habitat satisfies the Foundation Convergence architectural exit criteria under the tested repository/CI conditions. It does not establish AGI, universal safety, universal semantic correctness, or superiority over another system.

## 2. Audit result

Waves 0–7 already provide executable coverage for public compatibility, workspace migration/recovery, provenance/authority, read neutrality, fault injection, controlled ablations, held-out learning promotion, exact rollback, release identity, constitutional learning boundaries, and headless Observatory operation.

The remaining material gap is exit criterion 3:

> Semantic precision is benchmarked across multiple languages/providers instead of described only by capability detection.

Existing semantic comparison tests exercise disagreement behavior, and older benchmarks exercise retrieval/context precision or backend equivalence. They do not measure semantic extraction against an oracle over a language × provider matrix. Therefore capability presence must not be promoted into closure evidence.

## 3. Semantic precision matrix

Add `benchmarks/semantic_precision_matrix.py` as a deterministic, self-contained benchmark.

### 3.1 Languages

The first admitted matrix contains two languages that have real compiler paths in Habitat and broad Tree-sitter support:

- Python
- TypeScript

The fixture sources are generated deterministically in a temporary directory. Each fixture has an explicit oracle of expected declaration identities represented as `(qualified_name, kind)` pairs. The oracle is independent of provider output.

### 3.2 Provider lanes

Each language is measured through two independent implementation lanes:

1. **Habitat compiler lane** — `habitat.compiler.compile_file()` with the provider it actually selects in the current environment. Provider identity is reported exactly (for example `python-ast`, `typescript-compiler-api`, or an explicit fallback identity).
2. **Tree-sitter lane** — `TreeSitterProvider` executed directly after a real runtime/grammar probe.

No fake provider is admissible. An unavailable Tree-sitter runtime/grammar is reported as unavailable with `precision = recall = null`; it is never converted to zero or success.

### 3.3 Matching and metrics

For each language/provider cell:

- `expected_count`
- `observed_count`
- `true_positive`
- `false_positive`
- `false_negative`
- `precision`
- `recall`
- exact sorted expected/observed identities
- provider identity/fingerprint
- availability/reason

Matching uses exact `(qualified_name, kind)` identities. Precision and recall are descriptive measurements only. Foundation closure does **not** require a target percentage; criterion 3 requires measured semantic precision across multiple languages/providers, not a superiority threshold.

### 3.4 Coverage admission

The report exposes `coverage_admissible`, derived rather than asserted. It is true only when:

- at least two languages were measured;
- each admitted language has at least two available provider lanes;
- the available lanes resolve to at least two distinct provider identities for that language;
- every admitted cell contains non-null precision and recall.

This boolean means only that the matrix has enough measured coverage to serve as criterion-3 evidence. It says nothing about whether the measured scores are high.

## 4. CI evidence

Habitat CI already installs the Tree-sitter extra on every Ubuntu/Windows × Python 3.10/3.14 job. Add a gating step that runs the semantic precision matrix and writes `.test-artifacts/semantic-precision-matrix.json`. The benchmark exits non-zero when coverage is not admissible. The existing artifact upload then preserves the exact report from each matrix job.

This makes criterion 3 reproducible and prevents a future dependency/provider regression from silently degrading the repository back to capability-only evidence.

## 5. Constitutional boundary audit

Exit criterion 11 is already represented at the model boundary by `ContextPolicy.from_mapping()`, which rejects every constitutional learning target and all unknown learning fields, and the service/repository paths accept validated immutable `ContextPolicy` records rather than arbitrary constitutional configuration. Closure will retain a focused behavioral test that attempts the public learning-policy registration path with a constitutional field and requires fail-closed rejection before persistence/activation.

No new constitutional configuration system is introduced.

## 6. Closure evidence record

Add a concise repository evidence document mapping all 12 canonical exit criteria to their executable surfaces after the RED→GREEN work is verified. The record references behavior and CI artifacts; it is not itself the verifier.

## 7. Compatibility boundary

This closure must not:

- rename alpha.19 protocol methods;
- alter the 12-tool MCP surface;
- introduce a second database/cache daemon;
- weaken source authority, mutation freshness, recovery, approval, containment, release, or authority-class rules;
- make Observatory mandatory;
- persist benchmark metrics as authoritative workspace state;
- introduce timing/performance thresholds or comparative superiority claims.
