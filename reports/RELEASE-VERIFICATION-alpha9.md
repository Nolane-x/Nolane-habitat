# Release Verification — Habitat 0.1.0-alpha.9

## RC archive / manifest
- RC ZIP integrity: PASS.
- Independent manifest entries: 263.
- missing: 0; extra: 0; size/hash problems: 0.
- independent root hash recomputation: PASS.

## Clean-extracted changed-surface gate
- alpha.9 benchmark/policy/schema + execution/protocol/storage/workspace: 22/22 PASS.
- compileall `habitat` + `benchmarks`: PASS.

## Vertical alpha.9 demo from RC
- commit: committed.
- targeted verification: passed.
- overlapping second-agent stage: TransactionConflict (fail before durable overlapping transaction).
- Git working tree dirty after canonical mutation: true; history_count=1.
- direct dependencies discovered: 1.
- execution `full_sandbox`: false (claim remains partial containment only).

## Supplied AGI ZIP stress from RC
- corpus files: 251; symbols: 865; occurrences: 4351.
- ordinary warm reconcile hashed files: 0.
- Python/Jedi warm precision partitions reused: 78; recomputed: 0.
- no-gold: confidence=low, abstained=true, exact source bytes=0.

## Isolated package install
- `pip --no-deps --no-build-isolation --target /tmp/a9-pkg-target .`: PASS.
- imported module path: `/tmp/a9-pkg-target/habitat/__init__.py`.
- runtime version: `0.1.0-alpha.9`.
- package metadata: `0.1.0a9`.

## Historical regression evidence
- source-tree exhaustive shards before final docs/package metadata: 162 tests PASS.
- release identity correction added one new test; alpha.9 schema contract after correction: 2/2 PASS.
- final discovered test count: 163.
- a long monolithic/full-module runner can exceed the external tool wall clock; no monolithic 163/163 PASS is claimed. This remains recorded tooling/performance debt.

## Claim boundary
Alpha.9 admission establishes bounded governance, local multi-agent ownership, temporal/dependency cognition, partial network containment and an executable A/B contract. It does **not** establish hostile-code sandbox safety, distributed multi-agent correctness, calibrated probability or same-model coding superiority.
