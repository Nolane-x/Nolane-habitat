# Nolane Habitat 0.1.0-alpha.3 — Self-Audit

## Audit posture

This audit uses the supplied Nolane AGI cognitive-method pack as an engineering discipline: separate source truth from interpretation, preserve competing hypotheses, run discriminating probes, keep negative results, bind consequential actions to read-back evidence, and admit only the claim supported by executable evidence.

Alpha.3 is **not** audited as “AGI software.” It is audited as an agent-native project workspace checkpoint.

## Protected invariants rechecked

1. **Canonical source authority** — SQLite/semantic caches remain rebuildable derivative state.
2. **No project execution during indexing** — Python/TypeScript project source is parsed/indexed without import/build-script execution.
3. **No generic agent shell** — unknown `shell.exec` remains rejected; typed capabilities are the normal execution surface.
4. **Mutation integrity is stronger than observation acceleration** — stage/commit/rollback deep-hash source instead of trusting watcher metadata.
5. **Evidence trust remains explicit** — exact/semantic/parser/derived/heuristic lanes are not flattened.
6. **Stale context does not silently drift** — materialization on a stale handle fails closed; refresh creates a new immutable handle.
7. **UI ownership remains bounded** — parser correlation is not promoted into runtime proof.

## Alpha.3 challenge ledger

### F1 — Per-file cache masked non-incremental graph persistence
**Finding:** alpha.2 could reuse file compiler artifacts but still globally replace relation/occurrence rows.

**Risk:** “incremental workspace” would describe parser behavior while storage work remained global.

**Correction:** set-diff `sync_relations` / `sync_occurrences`; graph delta exposed in refresh receipts.

**Verifier:** no-op graph-sync regression; supplied AGI ZIP warm refresh reports 2,918 relations and 3,429 occurrences unchanged with zero insert/update/delete.

### F2 — Semantic cache invalidation boundary was too broad
**Finding:** root-digest semantic cache invalidated heavy providers on unrelated source classes.

**Correction:** provider-domain digests/fingerprints. Documentation and Python changes do not invalidate the TypeScript domain when JS/TS inputs/toolchain are unchanged.

**Verifier:** domain-cache regressions + AGI ZIP documentation/code probes.

### F3 — Watcher could have become a false integrity oracle
**Finding:** polling size/mtime can miss a content edit that preserves metadata.

**Correction:** watcher only proposes candidates. Foreground admission hashes those candidates. Consequential mutations still deep-hash the complete project.

**Verifier:** metadata-preserving adversarial edit is detected by mutation-grade reconciliation.

### F4 — Duplicate JSX semantic identity
**Finding:** one JSX element with the same literal value in both `id` and `data-testid` initially generated duplicate stable symbol IDs and violated SQLite uniqueness.

**Correction:** deduplicate `(anchor,line)` before symbol emission.

**Verifier:** unique-anchor runtime test and duplicate-anchor downgrade regression.

### F5 — Context orientation still preserved repeated-inspection choreography
**Finding:** an agent could still need many `inspect` calls after orientation, which merely renames a human-style open/read loop.

**Correction:** bounded Context Materializer packages selected semantic objects and exact **symbol bodies**, never automatic whole-file bodies, under source/object budgets. Omissions are explicit.

**Verifier:** materializer boundedness, stale-handle and schema tests; end-to-end demo materializes 6 objects and 361 exact-source bytes in the observed run.

**Boundary:** this is interface/plumbing evidence, not proof of lower total model tokens.

### F6 — Navigation benchmark harness API mismatch
**Finding:** benchmark used `.get()` on `sqlite3.Row`.

**Correction:** harness now obeys storage row contract and must fail rather than emit partial numbers when broken.

**Verifier:** regenerated `NAVIGATION-PLUMBING-AB-alpha3.json` with all three targets found by both arms.

### F7 — Admission command omitted required stress corpus
**Finding:** first final-admission invocation called `alpha3_agi_stress.py` without `source_zip`.

**Correction:** fail-fast preserved; evidence chain was rerun using `/mnt/data/Nolane-AGI-Cognitive-System-4.0.0(1).zip` rather than accepting an older report.

**Verifier:** current `AGI-ZIP-STRESS-alpha3.json` release field is alpha.3 and reports 251 files / 865 symbols / 3,429 occurrences.

### F8 — Report summarizer invented the wrong field path
**Finding:** release summary helper expected `verification.execution`; demo contract exposes `verification.receipt`.

**Correction:** treat report JSON as typed evidence and read the actual schema/contract. The demo itself was valid; only the human summary helper failed.

**Verifier:** targeted receipt has exit code 0 in current demo evidence.

## Evidence observations before packaging

### Unit/adversarial suite
`71/71 PASS` in the alpha.3 source tree.

### End-to-end demo
Observed in the current alpha.3 evidence run:

- Context Materializer: 361 exact-source bytes, 6 objects, 0 omissions under that fixture/budget.
- Targeted verification: exit code 0.
- Watcher: README candidate admitted with exactly 1 file hashed in targeted refresh.
- Runtime UI: semantic output becomes `Hello Nolane` when browser capability is available.
- Final warm deep refresh: 0 files compiled, 9 reused on the demo project.

### Supplied AGI ZIP stress corpus
Observed:

- 251 files;
- 865 symbols;
- 3,429 occurrences;
- warm deep refresh: 0 compiled / 251 reused;
- graph persistence on warm refresh: 2,918 relation rows unchanged and 3,429 occurrence rows unchanged;
- documentation-only targeted mutation: 1 file hashed/compiled and both base + TypeScript semantic provider domains reused;
- Python targeted mutation: 1 file hashed/compiled, base domain invalidated, TypeScript domain reused.

These are synchronization/indexing measurements on this corpus, not intelligence measurements.

### Deterministic navigation-plumbing fixture
Both the disclosed filesystem baseline and Habitat found all three hidden target symbols. The filesystem baseline scans 12,219 source bytes / 124 files per task. Habitat requested 100–132 exact source bytes plus 1,026–2,522 bytes of bounded context packet in two agent-facing calls in these synthetic cases.

This baseline is intentionally simple and deterministic. It does **not** justify a claim that an LLM will use fewer tokens, finish faster or solve more tasks. The separate same-model benchmark contract remains unexecuted by design.

## Remaining high-risk frontier

- process-local polling is not an OS-native/persistent watcher;
- read-side metadata optimization can temporarily miss metadata-preserving edits;
- TypeScript semantic state is provider-domain cached but not node-level incrementally updated after JS/TS changes;
- Java remains heuristic; Tree-sitter/LSP/SCIP precise providers remain gaps on the release host;
- no multiprocess workspace lease/transaction broker;
- typed executions are not hostile-code sandboxing;
- UI→framework ownership is correlation, not runtime provenance proof;
- no controlled same-model repeated-trial productivity/token benchmark has been run.

## Admission decision before artifact verification

**Provisionally ADMIT 0.1.0-alpha.3 as an experimental checkpoint** only for the bounded mechanisms above, conditional on the packaged ZIP independently passing:

1. archive integrity;
2. manifest completeness and independent SHA-256 verification;
3. clean-extracted full test suite;
4. clean-extracted alpha.3 demo;
5. clean-extracted supplied-AGI-ZIP stress probe;
6. package version/import smoke;
7. executable README quick-start smoke.

If any gate fails, the artifact is rejected until corrected and rebuilt.

## Release-gate environment finding

### F9 — pip build isolation required unavailable package-index access
**Finding:** clean-extracted `pip install --target ... .` invoked PEP 517 build isolation and attempted to fetch `setuptools>=68`; the release environment's package index returned no candidate.

**Diagnosis:** environment/dependency-fetch failure, not a Habitat import/build defect. The host already provides setuptools 82.0.1, which satisfies the declared build requirement.

**Correction:** rerun the package smoke with `--no-build-isolation --no-deps`, explicitly using the installed build toolchain rather than weakening `pyproject.toml` or pretending the failed gate passed.

**Verifier:** isolated target install succeeded and imported `habitat.__version__ == 0.1.0-alpha.3`.
