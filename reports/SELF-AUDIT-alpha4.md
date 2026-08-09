# Nolane Habitat 0.1.0-alpha.4 — Self-Audit

## Audit posture

Alpha.4 is audited as an **agent-native project workspace checkpoint**, not as AGI software. The supplied Nolane AGI cognitive-method pack is used as an engineering discipline: separate authority from hypotheses, keep rivals alive, run discriminating probes, preserve negative results, use loss-aware context, bind continuation to environment state, and admit only claims supported by executable evidence.

## Protected invariants rechecked

1. Canonical source remains authority; SQLite/semantic/residency state is derivative.
2. Residency stores semantic references/provenance, not copied exact source bodies.
3. Indexing does not execute project Python/TypeScript code.
4. Generic `shell.exec` remains absent from the normal agent protocol.
5. Consequential mutation still performs integrity-grade canonical-source reconciliation.
6. Weak UI/language evidence retains trust grade instead of becoming proof by repetition.
7. Telemetry is non-authoritative and cannot change the measured operation response.
8. Checkpoints bind environment/provider/resident evidence instead of relying on narrative summary alone.

## Alpha.4 challenge ledger

### F1 — “Incremental graph persistence” did not guarantee incremental relation reasoning
Alpha.3 synchronized graph rows by set-diff, but base relation resolution lacked explicit per-source dirty partitions.

**Correction:** resolver index + per-source partition fingerprints based on unresolved facts and relevant candidate-resolution surface.

**Verifier:** warm AGI stress has 78/78 partitions reused and 0 recomputed; resolution-surface expansion regression invalidates the dependent caller partition.

### F2 — Relation partition fingerprint was initially too coarse
The first alpha.4 fingerprint included source digest, which dirtied a relation partition after a body-only change even when semantic outbound facts were identical.

**Correction:** remove source digest from relation partition identity. Compiler/provider/cache version remains a separate invalidation boundary.

**Verifier:** body-only edits with stable outbound facts recompile the changed file but recompute 0 relation partitions.

### F3 — Residency can become stale authority
Persistent context is useful only if it does not silently preserve an obsolete implementation.

**Correction:** every resident carries source digest/provenance. Stale residents remain visible but are excluded from current exact-source materialization.

**Verifier:** alpha.4 demo changes the pinned auth source and reports resident states `fresh=3, stale=1, missing=0`.

### F4 — Pinned memory can violate a capacity target
An early design assumption that eviction could always restore capacity is false if pinned entries alone exceed the bound.

**Correction:** never silently evict pins. Report explicit `overcommitted=true` and reason.

**Verifier:** dedicated pinned-overcommit regression.

### F5 — Residency could amplify confirmation bias
A remembered auth object should not appear in an unrelated billing task only because it was previously viewed.

**Correction:** resident prior requires canonical-source freshness and current-task relevance. It remains a bounded ranking lane, not authority.

**Verifier:** related follow-up shows `resident` lane; unrelated billing task does not pull auth residency.

### F6 — Checkpoint summary was not a sufficient continuation contract
Task notes cannot certify that source/provider state remains valid.

**Correction:** checkpoint binds source revision/root, compiler/provider fingerprint, event cursor and resident object digests. Resume returns `direct`, `selective-revalidate` or `reorient`.

**Verifier:** unchanged → direct; unrelated edit → selective-revalidate; resident-source edit → reorient.

### F7 — Framework ownership stopped one hop too early
Element→component mapping still left the agent searching for the interaction implementation.

**Correction:** static TSX handler attributes emit `handles_event` relations and runtime unique anchors may expose handler source hints.

**Verifier:** alpha.4 demo/runtime regression exposes `framework-event-handler:click` to `App.tsx` handler at parser trust.

### F8 — Benchmark instrumentation itself can become a failure source
A telemetry recorder exception must not perturb the operation being measured.

**Correction:** trace recording is outside the authoritative operation path and its own failure is swallowed after the real response is formed.

**Verifier:** forced recorder exception leaves `workspace.query` successful.

### F9 — Structural bonus polluted task context with unrelated helper functions
The first alpha.4 trace benchmark selected `billing.py` and several `noise_*.py` entries for a credential task. The cause was `_symbol_score`: being a function/class added implementation score even without any task concept match.

**Correction:** at least one strong content/path concept match is now required before structural/task-class/trust bonuses can promote a symbol.

**Verifier:** regenerated trace benchmark selects only `auth.py` for credential tasks and only `billing.py` for billing; dedicated 20-noise-file regression is green.

## Source-tree evidence before packaging

### Unit/adversarial suite
`88/88 PASS` after the retrieval correction.

### End-to-end alpha.4 demo
Observed on the current fixture:

- resident materialization: 4 objects / 266 exact-source bytes;
- traced follow-up workload: 2 protocol calls, 318 exact-source bytes in the observed demo trace;
- after source mutation: one pinned auth resident becomes stale while three residents remain fresh;
- targeted verification chooses `tests/test_auth.py` and exits 0;
- runtime UI evidence includes one `framework-event-handler:click` hint;
- final warm deep refresh: 0 compiled / 5 reused; 0 base relation partitions recomputed.

### Supplied AGI ZIP stress corpus
Observed:

- 251 files;
- 865 symbols;
- 3,429 occurrences;
- warm deep refresh: 0 compiled / 251 reused;
- base relation partitions: 78 total / 78 reused / 0 recomputed;
- documentation targeted edit: 1 file compiled, 0 relation partitions recomputed;
- Python body-only targeted edit used by this probe: 1 file compiled, 0 relation partitions recomputed.

These are workspace plumbing measurements, not intelligence measurements.

### Protocol trace plumbing fixture
After correction:

- credential cold task: only `auth.py`, 2 protocol calls, 127 exact-source bytes;
- related resident task: only `auth.py`, 2 calls, 127 exact-source bytes;
- unrelated billing task: only `billing.py`, 2 calls, 92 exact-source bytes.

The filesystem comparison is a disclosed deterministic full-text scan. It is **not** a model baseline, so no token/success claim is admitted.

## Remaining high-risk frontier

- TypeScript Program/TypeChecker state remains coarse after JS/TS source edits;
- Tree-sitter/LSP/SCIP precise provider lanes remain unavailable on this release host;
- resident ranking policy has not been evaluated on long-horizon real-model trajectories;
- no multiprocess workspace lease/transaction coordinator;
- typed execution is not hostile-code containment;
- framework handler/ownership evidence is not universal runtime provenance;
- no controlled repeated same-model productivity/token benchmark has been run.

## Provisional admission decision

**Provisionally ADMIT 0.1.0-alpha.4 as an experimental checkpoint** only for the bounded mechanisms above, conditional on final packaged artifact independently passing:

1. archive integrity;
2. manifest completeness/hash/root-hash verification;
3. clean-extracted full test suite;
4. clean-extracted alpha.4 demo;
5. clean-extracted supplied-AGI-ZIP stress;
6. clean-extracted protocol trace benchmark;
7. README CLI quick-start smoke;
8. isolated package import/version smoke.

Any failure rejects the artifact until corrected and rebuilt.

## RC release-gate environment finding

### F10 — standard-library venv could not see the host setuptools backend
**Finding:** RC package smoke inside a newly-created `venv` failed with `BackendUnavailable: Cannot import 'setuptools.build_meta'`. Inspection showed that this venv's `sys.path` included `/usr/...` system locations but not the host `/opt/pyvenv/lib/python3.13/site-packages`, where verified `setuptools 82.0.1` and `setuptools.build_meta` are installed.

**Diagnosis:** environment/toolchain visibility failure, not evidence that Habitat's package metadata is invalid. The host Python can import `setuptools.build_meta` and satisfies `setuptools>=68`.

**Correction:** keep the declared build requirement unchanged. Run the package smoke with the verified host backend using `pip --no-build-isolation --no-deps --target <isolated-target>`, then import with Python isolated mode plus only that target inserted into `sys.path`.

**Verifier:** target install succeeded; imported module path is `/tmp/alpha4-package-target/habitat/__init__.py`; `habitat.__version__ == 0.1.0-alpha.4`.
