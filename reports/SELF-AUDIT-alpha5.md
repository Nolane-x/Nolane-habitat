# Nolane Habitat 0.1.0-alpha.5 — Self-Audit

## Audit posture

Alpha.5 is admitted only as an **experimental agent-native project workspace checkpoint**. The supplied Nolane AGI cognitive-method pack is used as an engineering discipline: explicit charter, rival hypotheses, discriminating probes, negative-result retention, trust separation, bounded context, environment-bound continuation and fail-closed admission. This is not an AGI-capability claim.

## Protected invariants rechecked

1. Canonical project files remain authoritative; semantic/Merkle/evidence/context state is derivative and rebuildable.
2. Indexing and Python precision analysis do not import or execute project Python modules.
3. Exact source is not silently duplicated into residency; virtual pages fault source only when requested and digest-check the exact bytes read.
4. Weak/heuristic evidence never becomes exact merely through repetition or graph propagation.
5. Consequential mutation remains digest-bound and conflict-checked.
6. Resolved runtime/test evidence remains audit history but cannot contaminate current live retrieval.
7. No-gold/low-evidence retrieval can abstain instead of filling a context budget with noise.
8. Telemetry/Merkle/retrieval metadata are not source authority.
9. MCP is an optional adapter, not a core dependency or an admission shortcut.

## Alpha.5 challenge ledger

### F1 — Resolved evidence leaked back through lexical FTS
The evidence table correctly marked a test failure inactive after repair, but the lexical index remained append-only and could still return that historical row.

**Correction:** live retrieval now checks the authoritative active bit before admitting an evidence FTS hit.

**Verifier:** resolved-evidence regression plus end-to-end evidence lifecycle: active failure count `1 → 0`, followed by task orientation with no resolved evidence object.

### F2 — Precise Jedi evidence originally superseded too broadly
An early overlay removed weak parser call relations for the whole caller function when only one call-site had been proven by Jedi. This could erase unresolved facts.

**Correction:** semantic supersession is scoped to the exact proven source call-site/line; unresolved call-sites keep weaker evidence.

**Verifier:** mixed resolved/unresolved-calls regression.

### F3 — Equal-trust occurrence dedup could retain the generic linker
Provider outputs with the same occurrence identity/trust could leave `project-linker` instead of the more discriminating Jedi/TypeScript provider.

**Correction:** deterministic provider ranking prefers `python-jedi` / `typescript-program` at equal trust.

**Verifier:** provider occurrence regression.

### F4 — Provider invalidation was initially too sensitive to body text
The first Python/TypeScript precision fingerprint effectively treated body-only edits as public semantic-surface changes and could broaden recomputation unnecessarily.

**Correction:** conservative API/import surface fingerprints use definition identity/import facts rather than implementation body content; source digest remains partition-local.

**Verifier:** warm/body-only/public-surface partition tests. Python/Jedi warm stress: 78 reused / 0 recomputed; body-only corpus probe: 77 reused / 1 recomputed. TypeScript fixture: body-only edit scans 1/3 partitions; API-surface expansion scans 3/3.

### F5 — Top-score confidence was vulnerable to one common term
The AGI-corpus no-gold query `quantum banana teleportation matrix` initially became high confidence because `matrix` was common enough to create a strong candidate.

**Correction:** retrieval confidence now requires concept coverage across independent indexed evidence, not merely a strong top candidate.

**Verifier:** supplied AGI corpus now returns `low` confidence + abstention; 200-distractor no-gold returns zero selected paths and zero source bytes.

### F6 — Exact lexical concept coverage was too brittle
After F5, the valid task `fix credential validation login` was temporarily classified low despite correct targets because exact lexical evidence did not treat `credential ↔ credentials` and `validation ↔ validate` as supported concepts.

**Correction:** concept support may use indexed symbol/path morphology with a bounded fuzzy threshold; it still reads no source bytes.

**Verifier:** new morphology regression returns high confidence; end-to-end demo returns high confidence with 187 exact-source bytes. The AGI no-gold regression remains low/abstain.

### F7 — Virtual page fault originally repeated workspace reconciliation
The first virtual-memory implementation called the public source-read path for every page, causing redundant global reconciliation work.

**Correction:** the workspace reconciles once before a batch fault; each page then reads its backing bytes directly, hashes exactly those bytes, fail-closes on digest drift, slices the bounded range and applies the byte budget.

**Verifier:** virtual-page tests, stale/digest-drift tests and end-to-end prefetch.

### F8 — Benchmark/report tooling drifted from evolving report schemas
During admission, helper summaries referenced outdated keys (`no_gold`, old Merkle field names, etc.) and one combined verifier command stopped after pytest before later reports existed.

**Correction:** admission gates are run separately, outputs are written before summary consumption, and current report contracts are parsed directly. Stale alpha.4 reports are not reused as alpha.5 evidence.

**Verifier:** fresh alpha.5 demo, AGI stress and context-precision report files plus JSON parse gate.

### F9 — Real MCP runtime is not available on this build host
The `mcp` Python package is absent. Installing it merely to make a release claim would mix network/environment acquisition with core admission.

**Correction:** Habitat core has no MCP dependency. The adapter is verified with an SDK contract double for the compact 12-tool/resource registration surface and fails clearly when the optional SDK is absent.

**Verifier:** alpha.5 MCP adapter tests in the 111-test suite. **Real SDK stdio runtime remains unadmitted on this host.**

## Fresh source-tree evidence

### Unit/adversarial suite
`111/111 PASS` after all alpha.5 corrections.

### End-to-end alpha.5 demo
- calibrated task context: `high` confidence;
- virtual context prefetch: 187 exact-source bytes;
- semantic Python rename spans 3 project paths and targeted verification passes;
- induced test failure creates active evidence, repair resolves it (`1 → 0`);
- Merkle diff reads 0 additional source bytes;
- runtime semantic UI assertion passes for `Hello Nolane` with screenshot oracle disabled;
- final warm refresh compiles 0 files and reuses all fixture files/providers.

### Supplied AGI ZIP stress corpus
- 251 files / 865 symbols / 4,372 occurrences;
- source bytes: 88,271,461; indexed text bytes: 1,723,080;
- warm refresh: 0 compiled / 251 reused;
- Python/Jedi precision partitions: 78 reused / 0 recomputed warm;
- one body-only Python probe: 1 file compiled, Jedi 77 reused / 1 recomputed;
- Merkle query: 0 source bytes reread;
- no-gold query: low confidence + abstention.

These are workspace plumbing/semantic-provider measurements, not intelligence or universal performance measurements.

### 202-file context-precision fixture
- deterministic full scan reads 202 files / 8,111 source bytes per task;
- Habitat credential task: `auth.py`, high confidence, 127 exact-source bytes, 2 protocol calls, 0 noise paths;
- Habitat billing task: `billing.py`, high confidence, 92 exact-source bytes, 2 protocol calls, 0 noise paths;
- Habitat no-gold: low confidence, abstain, 0 exact-source bytes, 0 noise paths.

This is **not** a same-model agent A/B and does not establish token/coding-success superiority.

## Remaining high-risk frontier

- TypeScript dirty runs still construct a whole-project Program/TypeChecker; traversal/output is partitioned, language-service state is not persistent.
- Java remains heuristic; LSP/SCIP/Tree-sitter precision lanes are explicit gaps on this host.
- Jedi unresolved-call count on a large dynamic Python corpus remains substantial and must not be mistaken for absence evidence.
- semantic rename is Python/Jedi-only and intentionally fail-closed.
- runtime UI assertions do not prove universal framework provenance or pixel correctness.
- typed execution is not hostile-code containment.
- MCP real runtime is not admitted on this host because the optional SDK is absent.
- no controlled repeated same-model coding benchmark has been run; no universal token/cost/success claim is admitted.

## Provisional admission decision

**Provisionally ADMIT alpha.5 source tree** for the bounded mechanisms above, conditional on final packaged artifact independently passing:

1. ZIP integrity;
2. independent manifest completeness/hash/root-hash verification;
3. clean-extracted 111-test suite;
4. clean-extracted compileall;
5. fresh alpha.5 demo;
6. fresh supplied-AGI-ZIP stress;
7. fresh 200-distractor context-precision harness;
8. README quick-start;
9. isolated package import/version smoke;
10. MCP missing-SDK fail-clear behavior plus contract-double registration tests.

Any failure rejects the artifact until corrected and rebuilt.

## RC release-gate tooling finding

### F10 — MCP negative-path smoke called a non-public/nonexistent helper name
The first RC smoke attempted to import `run_mcp_server`, while the actual supported module surface is `build_server()` plus CLI entrypoint `main` (`habitat-mcp-server`). The SDK absence itself was correctly observed, but the harness failed before testing Habitat's intended missing-SDK error.

**Correction:** inspect `pyproject.toml` + `habitat.mcp_adapter`, invoke the actual `build_server()` entrypoint, and separately run the MCP adapter contract tests.

**Verifier:** with no `mcp` package on the host, `build_server()` raises the documented clear `RuntimeError` recommending `nolane-habitat[mcp]`; MCP adapter contract subset passes `4/4`.
