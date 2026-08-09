# Nolane Habitat 0.1.0-alpha.2 — Self-Audit

Date: 2026-08-07
Audit mode: adversarial implementation review + executable regression/admission gates
Verdict: **ADMIT AS ALPHA RESEARCH CHECKPOINT**, subject to the explicit boundaries below.

## 1. Claim under audit

Alpha.2 claims a stronger **project-to-agent semantic loop** than alpha.1 for the supported fixtures:

- source stays canonical;
- unchanged files can reuse provenance-bound semantic artifacts;
- Python/TypeScript supported static cross-file relationships can be resolved more precisely than same-name grep/regex;
- references/events/impact become first-class structured evidence;
- supported Python verification can be targeted without exposing a terminal primitive;
- browser UI can expose semantic runtime state and bounded JS listener source evidence;
- all precision/capability gaps remain visible.

This audit does **not** admit claims of universal repository understanding, universal token reduction, AGI capability, production hostile-code isolation, or framework-complete UI ownership.

## 2. High-risk invariants attacked

| Invariant | Attack/probe | Result |
|---|---|---|
| Ingestion must not execute project code | Python file with side-effect payload; TypeScript file containing `child_process.execSync` | PASS: marker not created |
| ZIP cannot escape workspace | `../` traversal, symlink and oversize archive fixtures | PASS |
| Runtime project resource routing cannot escape source root | traversal request from browser resource router | PASS |
| Consequential edits cannot silently overwrite stale external changes | stage → external edit → commit | PASS: conflict rejected |
| Heuristic symbols cannot masquerade as safe semantic edit anchors | Java heuristic symbol mutation attempt | PASS: refused |
| Semantic duplicate names must not fabricate precise call targets | duplicate Python/TypeScript function exports | PASS for bounded qualified/compiler-resolved cases |
| No-op workspace refresh must not reparse unchanged files | demo + 251-file AGI stress corpus | PASS: 0 file compiles on warm refresh |
| One changed file should not force file-level recompilation of all others | AGI stress one-file edit | PASS: 1 compiled / 250 reused |
| Stale compiler artifacts must not survive upgrade/provider drift | simulated alpha.1 cache + forged provider fingerprint | PASS after corrective patch |
| Browser runtime ownership must survive multiple workspaces | two browser workspaces + close one | PASS after corrective patch |
| Agent protocol must not expose generic shell | unknown `shell.exec` request | PASS: typed rejection |
| Targeted test selection must not include unrelated controlled fixture | two independent Python subsystems/tests | PASS: only reaching test selected |

## 3. Failed rounds preserved

### F1 — Python module symbol index duplicated identical top-level name/qname
Impact: qualified call resolution could look ambiguous even when static import evidence was unique.
Correction: deduplicate module symbol buckets.
Regression: `test_python_qualified_call_disambiguates_duplicate_names`.

### F2 — TypeScript semantic edge coexisted with wrong heuristic alternative
Impact: compiler-resolved call was present but an unrelated same-name target could remain in the graph.
Correction: compiler-semantic evidence suppresses weaker same-callsite heuristic alternatives.
Regression: `test_typescript_program_disambiguates_duplicate_exports`.

### F3 — Context graph self-reinforcement A→B→A
Impact: graph traversal could inflate a candidate because its own path returned to it.
Correction: evidence may compound only across distinct semantic roots; self-cycle reinforcement is blocked.
Regression: duplicate-name Context V3 fixture.

### F4 — Test source lexical text became an implementation root
Impact: a test mentioning a duplicate symbol could reinforce an unrelated production implementation.
Correction: implementation-task semantic expansion begins from production roots; tests are discovered downstream.
Regression: Context V3 duplicate-name fixture.

### F5 — Playwright sync runtime collision appeared only in the full suite
Impact: isolated browser tests passed, but later workspace initialization could fail when another sync driver existed.
Correction: process-shared Playwright/browser engine, workspace-scoped contexts/sessions.
Regression: `test_multiple_workspace_browser_runtimes_share_engine_without_cross_invalidating`.

### F6 — Cache identity used source state more strongly than toolchain state
Impact: an unchanged file could reuse semantic facts created by an older compiler/parser contract.
Correction: per-file compiler-cache version/fingerprint + project semantic provider fingerprint; legacy cache recompiles once.
Regressions: migration and provider-fingerprint-drift tests.

### F7 — Benchmark harness failed when executed directly from source checkout
Impact: release evidence depended on ambient Python import path rather than the delivery itself.
Correction: benchmark scripts explicitly bootstrap the delivery root; final release verification executes them from extracted ZIP.
Verifier: direct alpha.2 demo/stress invocation and release-extraction gate.

### F8 — README quick-start drifted from the executable CLI
Impact: a human/operator following documentation would invoke a nonexistent `ingest --workspace` form.
Correction: quick-start now uses `create SOURCE WORKSPACE` and positional workspace arguments matching `python -m habitat --help`.
Verifier: CLI smoke included in `TEST-EVIDENCE-alpha2.txt`.

## 4. Evidence currently observed

### Full test suite

Current development-tree result before packaging: **57/57 PASS**.

### Alpha.2 vertical demo

- semantic credential target outranks unrelated duplicate;
- impacted test candidate: `tests/test_auth.py` only;
- targeted verification exit code: `0`;
- runtime UI action result: `Hello Nolane`;
- warm refresh: `0` compiled, `7` reused, semantic-project cache reused.

See `reports/DEMO-EVIDENCE-alpha2.json`.

### Supplied AGI ZIP stress corpus

Observed in the final development-tree stress run:

- 251 files;
- 865 symbols;
- 3429 occurrences;
- source bytes: 88,271,461;
- indexed text bytes: 1,723,080;
- warm refresh: 0 compiled / 251 reused / semantic cache hit;
- one-file external edit: 1 compiled / 250 reused / semantic cache recomputed.

Timing is host-specific and must not be generalized. See `reports/AGI-ZIP-STRESS-alpha2.json`.

## 5. Unresolved adversarial findings

### Medium — read-only metadata reconciliation can be temporarily stale
`reconcile()` optimizes for size+mtime. A metadata-preserving content mutation can remain unseen until deep refresh or consequential preflight.
Disposition: documented; does not block alpha because mutation paths deep-hash before write. Future watcher/Merkle work required.

### Medium — whole-project semantic layer is conservative rather than dependency-partition incremental
One source change reparses one file but currently recomputes cross-file relation semantics.
Disposition: admitted as explicit alpha boundary; no false incremental whole-program claim.

### High for production, non-blocking for research alpha — execution is not a hardened sandbox
Typed capabilities still launch host processes when explicitly invoked.
Disposition: blocks production/untrusted-execution claim, not the current research checkpoint.

### Medium — static impact can miss runtime registration/reflection
Targeted tests may be incomplete when the dependency is absent from the semantic graph.
Disposition: full-suite fallback remains necessary when evidence is weak; future runtime/test-coverage lane required.

### Medium — browser semantic observation is not visual equivalence
DOM/ARIA/layout/listener evidence cannot prove visual quality or framework component ownership.
Disposition: screenshots remain secondary evidence; no visual-completeness claim admitted.

## 6. Admission decision

**ADMIT `0.1.0-alpha.2` as an experimental checkpoint** if and only if the packaged artifact passes:

1. archive integrity;
2. delivery-manifest hash verification;
3. clean extracted full test suite;
4. clean extracted direct alpha.2 vertical demo;
5. compile/import sanity from the extracted source tree.

Any failure in source-boundary safety, stale-mutation protection, ingestion non-execution, semantic trust labeling, or archive integrity revokes admission.
