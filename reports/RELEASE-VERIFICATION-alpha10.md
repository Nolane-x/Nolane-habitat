# Release Verification — Nolane Habitat 0.1.0-alpha.10

## Admission model

This report distinguishes:
1. **source-tree regression evidence**;
2. **clean RC artifact evidence**;
3. **post-package final artifact evidence** (filled by final verification outside the archive and summarized in the final handoff).

A timeout is never relabeled as PASS. Mock A/B contract runs are never treated as product-quality evidence.

## Source-tree gates

- Version identity: `VERSION=0.1.0-alpha.10`, runtime `habitat.__version__=0.1.0-alpha.10`, PEP 440 package metadata `0.1.0a10`.
- JSON schemas/reports parse: PASS.
- `compileall`: PASS.
- README quick-start `create -> enter -> orient`: PASS, retrieval confidence `high` on the smoke fixture.
- Balanced isolated regression matrix: **186 tests**, four groups, **4 PASS / 0 failed / 0 timeout / 0 infra-error**.
- Per-module matrix default was rejected for poor provider-startup economics; module mode remains forensic.
- Four-shard concurrent admission attempt was host-sensitive and hit the external runner limit; completed sequential isolated shard results are the admitted evidence.
- Monolithic long-lived-host discovery remains a distinct lifecycle/performance diagnostic and is not represented as PASS.

## RC independent manifest gate

RC: `Nolane-Habitat-0.1.0-alpha.10-RC.zip`

- Manifest entries excluding manifest: **290**
- Missing: **0**
- Extra: **0**
- SHA-256/size mismatch: **0**
- Manifest root hash: **PASS**
- ZIP integrity: **PASS**
- Clean-extracted `compileall`: **PASS**

The manifest verifier independently recomputed hashes/root identity and did not call the packager as its verifier.

## RC clean-extracted regression matrix

- alpha0-4: **66 / 66 PASS**
- alpha5-7: **38 / 38 PASS**
- alpha8-10: **56 / 56 PASS**
- core: **26 / 26 PASS**
- Total: **186 / 186 PASS**

## RC vertical demo

Observed from `benchmarks/alpha10_demo.py`:

- release: `0.1.0-alpha.10`
- stale read-set blocks commit before revalidation: `TransactionConflict`
- selective revalidation acknowledged: `true`
- disjoint optimistic rebase commit: `committed`
- targeted verification: `passed`
- path policy approval required: `true`
- scoped guidance discovered: `1`
- current host `full_sandbox`: `false`

The sandbox result is intentionally negative: Bubblewrap is not installed on this host, so alpha.10 does not silently downgrade a requested full sandbox.

## RC supplied AGI ZIP stress

Corpus: user-supplied `Nolane-AGI-Cognitive-System-4.0.0(1).zip`.

- files: **251**
- symbols: **865**
- occurrences: **4,351**
- ordinary warm reconcile hashed files: **0**
- ordinary warm reconcile: approximately **23.43 ms** in this run
- explicit deep refresh compiled: **0**
- explicit deep refresh reused: **251**
- explicit deep refresh hashed: **251**
- explicit deep integrity hash I/O: **88,271,461 bytes**
- explorer confidence on the stress task: `medium`
- explorer exact source shown to agent: **6,608 bytes**
- backend authority bytes read for that source exposure: **23,119 bytes**
- no-gold confidence: `low`
- no-gold abstained: `true`
- no-gold exact source bytes: **0**
- current host full sandbox: `false`

Agent-visible source bytes and authority I/O remain separate metrics.

## A/B harness contract

`AB-HARNESS-CONTRACT-alpha10.json` uses mock external agent/evaluator commands only to exercise the admission contract:

- runs: **4**
- paired comparisons: **2**
- one observed mock model ID across all runs: yes
- one observed mock scaffold ID across all runs: yes
- independent evaluator configured: yes
- `strong_evidence_ready`: `true`
- `product_quality_evidence`: **false**

No Habitat-vs-filesystem superiority claim is admitted without real same-model/scaffold arms and a real independent evaluator.

## RC package smoke

Installed clean RC source into an isolated target with host build tooling:

- imported version: `0.1.0-alpha.10`
- imported module path: `/tmp/a10-pkg-target/habitat/__init__.py`
- import did not resolve to the source checkout.

## Explicit open boundaries

- Full filesystem/network hostile-code sandbox is **not admitted on this host**. Bubblewrap policy remains provider/caller defined even on hosts where it exists.
- No distributed multi-process consensus/semantic merge protocol.
- No encryption at rest for cognitive state.
- No calibrated Bayesian uncertainty.
- No formal proof engine for project invariants.
- No complete production/runtime world beyond connected evidence.
- No universal semantic parity across all programming languages.
- No real same-model Habitat-vs-filesystem result yet.
- Monolithic very-long-lived provider lifecycle/performance remains an engineering diagnostic surface.
