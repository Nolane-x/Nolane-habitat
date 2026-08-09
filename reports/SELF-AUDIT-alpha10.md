# Self Audit — Habitat 0.1.0-alpha.10

Alpha.10 uses an evidence-first admission gate. Failures, rejected hypotheses and tooling limitations remain visible.

## Findings and corrections

### A10-F1 — Invariant protocol regression used the wrong response contract
**Observation:** a new test treated `HabitatProtocol.handle()` as though it returned a raw workspace object.
**Correction:** keep the protocol response envelope and test `ok/result` rather than changing transport semantics.
**Verifier:** alpha.10 invariant protocol regression.

### A10-F2 — Git `for-each-ref` delimiter assumption was wrong
**Observation:** `%x1f` produced no parsed branch rows in the real-repository regression.
**Correction:** use the tab-format contract supported by `for-each-ref`.
**Verifier:** alpha.10 Git branches test.

### A10-F3 — Legacy alpha.9 release test froze the release number instead of the invariant
**Observation:** the historical test required alpha.9 literally, making a valid alpha.10 release fail.
**Correction:** historical test now enforces VERSION/runtime/PEP440 consistency; alpha.10 owns the exact alpha.10 assertion.
**Verifier:** historical + alpha.10 release-identity tests.

### A10-F4 — Optimistic rebase alone could cross stale cognition
**Observation:** target digests can remain valid even if an agent observed another file changed by a peer.
**Correction:** pending read-set invalidation blocks owner commit until selective revalidation; then disjoint optimistic rebase may proceed.
**Verifier:** coordination regression + vertical demo.

### A10-F5 — Persistent/provider lifecycle does not justify one universal caching policy
**Observation:** earlier releases already showed unbounded Jedi persistence is pathological while TypeScript benefits from a real service session.
**Correction:** alpha.10 preserves provider-specific lifecycle rather than forcing a uniform "persistent brain" abstraction.
**Verifier:** historical lifecycle/partition regressions remain green.

### A10-F6 — Full sandbox capability is unavailable on this host
**Observation:** Bubblewrap is not installed; only user/network namespace capability is detectable.
**Correction:** full sandbox provider is optional and executable-probed; untrusted execution fails closed instead of silently downgrading.
**Boundary:** the Bubblewrap path is covered by command/policy regressions but cannot be end-to-end admitted on this host.

### A10-F7 — A/B orchestration can be mistaken for quality evidence
**Observation:** a runnable harness looks benchmark-like even with mock agents.
**Correction:** schema 3 exposes observed model/scaffold IDs, independent evaluator requirement and `strong_evidence_ready`; contract smoke is marked `product_quality_evidence=false`.
**Verifier:** `AB-HARNESS-CONTRACT-alpha10.json`.

### A10-F8 — Guidance discovery could become automatic context pollution
**Observation:** repository guidance is useful input but is not verified world truth and can add context cost.
**Correction:** discover metadata/scopes but never auto-inject; body enters context only through explicit bounded read.
**Verifier:** alpha.10 guidance regression.

### A10-F9 — Per-module test isolation had poor economics
**Observation:** spawning language/browser providers for every module exceeded the external runner budget.
**Correction:** default test matrix uses four empirically balanced process shards; per-module mode remains forensic.
**Verifier:** `TEST-MATRIX-alpha10.json` covers 186 tests.

### A10-F10 — Four-shard parallelism was host-sensitive
**Observation:** the same four shards that pass sequentially hit the external runner limit when launched concurrently.
**Correction:** admission uses completed sequential isolated shard results; parallel mode is optional, not an invariant.
**Boundary:** throughput tuning remains host-specific.

### A10-F11 — Monolithic long-lived test process remains a diagnostic debt
**Observation:** historical attempts can encounter pathological provider/browser state or external wall-clock termination despite exhaustive isolated-shard success.
**Correction:** host-level `shutdown_runtime_services()` remains available and release evidence separates functional regression coverage from monolithic lifecycle probing.
**Boundary:** do not relabel a monolithic timeout as PASS.

### A10-F12 — Stress-summary key drift occurred in an ad-hoc reader
**Observation:** one summary helper looked for legacy deep-refresh field names while the report itself was correct.
**Correction:** release verification consumes the actual report schema; core stress output was not changed to satisfy the helper.

## Explicit open boundaries
- No full sandbox admission on the current host; no claim against kernel/Bubblewrap vulnerabilities.
- No distributed multi-process consensus, causal ordering or semantic merge/rebase protocol.
- No encryption at rest for cognitive state.
- No formal invariant proof engine.
- No calibrated probability calculus.
- No complete production/runtime world model.
- No universal language semantic parity.
- No real same-model Habitat-vs-filesystem superiority result.
