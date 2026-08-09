# Self Audit — Habitat 0.1.0-alpha.9

Alpha.9 follows an evidence-first release gate. Failures and rejected hypotheses are retained rather than removed from the narrative.

## Findings and corrections

### A9-F1 — Partial containment could be mislabeled as sandbox
**Observation:** Linux `unshare -Urn` is available, but filesystem confinement is not.
**Correction:** the profile is named `network-contained`; receipts state `filesystem_restricted=false`, `sandboxed=false`; `untrusted` policy refuses it.
**Verifier:** policy/containment adversarial test and vertical demo security report.

### A9-F2 — Multi-agent state could be shared without ownership semantics
**Observation:** sharing SQLite/revision state alone is not multi-agent coordination.
**Correction:** agent sessions, agent-scoped utility, per-path leases, transaction owner binding and owner-only commit/rollback.
**Verifier:** Agent A lease prevents Agent B overlapping stage; owner commit passes.

### A9-F3 — Repeated evidence from one provider could become fake consensus
**Observation:** multiple pytest receipts are correlated evidence.
**Correction:** uncertainty fusion groups by source/provider and uses diminishing returns; `calibrated_probability=false`.
**Verifier:** alpha.9 uncertainty regression.

### A9-F4 — Persistent semantic state was overgeneralized
**Observation:** prior work showed not every provider benefits from unbounded persistence.
**Correction:** TypeScript keeps a real service session; Jedi remains bounded LRU plus persistent semantic partitions.
**Verifier:** historical alpha.7 lifecycle tests remain admitted.

### A9-F5 — Long test process can outlive useful result / runner wall clock
**Observation:** combined discovery/shard commands can be cut by the external runner despite earlier test cases passing.
**Correction:** explicit `shutdown_runtime_services()` is a host lifecycle API; release admission distinguishes module/shard PASS from runner timeout.
**Boundary:** this remains test-runner latency variance and should be further optimized; timeout is never relabeled PASS.

### A9-F6 — Benchmark demo direct execution had import-path drift
**Observation:** direct `python benchmarks/alpha9_demo.py` initially could not import Habitat without caller PYTHONPATH.
**Correction:** benchmark resolves delivery root itself.
**Verifier:** vertical demo executes directly.

### A9-F7 — Package identity drift
**Observation:** VERSION/runtime were alpha.9 while `pyproject.toml` still declared `0.1.0a8`.
**Correction:** package version changed to `0.1.0a9`; regression binds all three identities.
**Verifier:** `tests.test_alpha9_schema_contracts.Alpha9SchemaContracts.test_release_identity_consistent`.

### A9-F8 — A/B harness can be mistaken for superiority evidence
**Observation:** an executable harness can look like a benchmark result even when contract-double agents are used.
**Correction:** harness contains no model/evaluator, marks `same_model_required=true`, and carries an explicit claim boundary.
**Verifier:** paired harness contract test + smoke report.

## Open production blockers
- filesystem-confined hostile-code sandbox / external isolation provider;
- distributed leases, consensus, semantic rebase/merge;
- enterprise retention/encryption/secret-state governance;
- transitive dependency/API/runtime world model;
- broader language precision;
- calibrated uncertainty and provider-disagreement calculus;
- actual same-model Habitat-vs-filesystem experiment with independent evaluator;
- service decomposition of the growing HabitatWorkspace coordination surface.

### A9-F9 — Release summary reader drifted from stress-report schema
**Observation:** RC demo/stress/package gates completed, but the release summary script attempted to read legacy `no_gold.context.*` fields; alpha.9 stress emits flat `no_gold.{confidence,abstained,region_count,source_bytes_read}`.
**Correction:** release verification consumes the actual alpha.9 report contract; core behavior/report generation was not changed.
**Verifier:** RC stress report shows `confidence=low`, `abstained=true`, `source_bytes_read=0`.
