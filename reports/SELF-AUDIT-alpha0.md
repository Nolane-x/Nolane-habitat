# Self-Audit — 0.1.0-alpha.0

## Verdict

**Bounded pass as a working research prototype. Not V1, not a sandbox, not a complete semantic compiler, and not evidence of token-efficiency yet.**

## Attacks / failures found during construction

### A1 — Test harness silently discovered zero tests

**Finding:** Initial `unittest discover` invocation did not collect the test directory in the first run.

**Patch:** Make test package/import path explicit and run `discover -s tests`.

**Regression:** full suite now collected explicitly.

### A2 — Context Compiler ranked UI noise above implementation

**Finding:** For “where is login credential validation implemented?”, lexical ranking placed `login-form` above `validate_credentials`.

**Why it mattered:** This would recreate the agent’s navigation burden despite having an index.

**Patch:** Add deterministic identifier decomposition/fuzzy lane, intent-aware code-object bias and ranking regression.

**Regression:** test asserts `validate_credentials` is first.

### A3 — Semantic store duplicated source text

**Finding:** Early schema stored source text in `files` while FTS stored it again.

**Why it mattered:** Violated the product’s anti-bloat thesis.

**Patch:** Remove source body from `files`; use contentless FTS5 plus separate metadata row mapping. Exact source stays in canonical files.

**Regression:** schema test asserts no `indexed_text` column and search remains functional.

### A4 — Large-file coverage was silent

**Finding:** Index/parse byte caps existed implicitly, so “not found” could be misread as corpus-wide absence.

**Patch:** Persist `indexed_bytes`, `index_truncated`, `parse_complete`; expose `index_health`; Context Slice emits uncertainty for selected truncated/incomplete files.

**Regression:** large-file coverage test.

### A5 — Immediate edit API was weaker than claimed transaction model

**Finding:** A one-shot edit did not allow a meaningful stale interval between stage and commit.

**Patch:** Add persistent stage/commit/rollback operations; automatic source reconcile before commit and rollback.

**Regression:** external human edit after stage blocks commit; committed edit can rollback only if no newer source change.

### A6 — Capability discovery could imply unavailable tools

**Finding:** Merely seeing a manifest is not proof that npm/Maven/Gradle/pytest is executable.

**Patch:** Every capability now includes availability and reason; run rejects unavailable capabilities.

## Remaining high-risk gaps

1. **Execution isolation:** local subprocess provider is not sandboxed. This blocks any security claim for untrusted automated runs.
2. **Semantic precision:** JS/TS/Java extraction is heuristic. Consequential refactors require Tree-sitter/LSP/SCIP precision lanes.
3. **Runtime UI:** static HTML observation is insufficient for JS applications and visual correctness.
4. **Filesystem freshness:** fast reconcile trusts size+mtime as the cheap trigger; pathological same-size/same-mtime edits need periodic digest reconciliation.
5. **Concurrent Habitat processes:** no source-root lease yet.
6. **Benchmark evidence:** byte proxy/stress tests do not prove token or task-success gains.

## Protected dimensions status

- Source authority: PASS.
- Transaction reversibility: PASS for implemented mutation primitive.
- Stale external edit blocking: PASS for staged transaction path.
- No generic agent shell primitive: PASS.
- Archive traversal/symlink/size controls: PASS within tested cases.
- Trust-grade honesty: PASS for current extractors.
- Large-file uncertainty visibility: PASS.
- Runtime execution safety: NOT ESTABLISHED.
- Runtime web UI understanding: NOT ESTABLISHED.
- Token-efficiency improvement: NOT ESTABLISHED.
