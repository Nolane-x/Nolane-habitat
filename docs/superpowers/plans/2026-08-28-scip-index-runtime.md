# SCIP Index Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicitly activated, bounded, read-only SCIP index semantics to Habitat and preserve source/index/tool provenance without granting mutation authority.

**Architecture:** A small dependency-free Protobuf wire reader feeds a SCIP-specific parser. A workspace-scoped provider/runtime binds parsed indexes to current source digests and Habitat revision, exposes read-only queries, and integrates admitted runtime identity into Semantic Fabric. Command-backed generation uses the same activation path.

**Tech Stack:** Python 3.10–3.14 stdlib (`dataclasses`, `hashlib`, `pathlib`, `subprocess`, `urllib.parse`), Habitat SemanticAdmissionRegistry, `unittest`, GitHub Actions Ubuntu/Windows matrix.

**Spec:** `docs/superpowers/specs/2026-08-28-scip-index-runtime-design.md`

## Global Constraints

- No automatic SCIP discovery/admission.
- No external Protobuf/SCIP runtime dependency is required for import.
- Maximum index size: 256 MiB; documents: 250,000; occurrences: 5,000,000.
- Generated indexer timeout: 120s; stdout/stderr retention: 64 KiB each.
- `source_authority=False`; `mutation_authority=False`.
- No agent protocol or MCP method changes.
- `_workspace_core.py` is not modified.
- All new behavior is TDD-first.

---

### Task 1: Bounded Protobuf wire reader

**Files:**
- Create: `habitat/semantic/scip_wire.py`
- Create: `tests/test_scip_wire.py`

**Interfaces:**
- Produces `ScipWireError(ValueError)`.
- Produces `encode_test_varint(value: int) -> bytes` for deterministic fixture construction in tests only through a public wire primitive acceptable for production use.
- Produces `iter_fields(payload: bytes | memoryview) -> iterator[tuple[int, int, object]]` where object is `int`, `bytes`, or fixed-width integer.
- Produces `decode_packed_int32(payload: bytes) -> tuple[int, ...]`.

- [ ] **Step 1: Write RED tests**

```python
from habitat.semantic.scip_wire import ScipWireError, decode_packed_int32, iter_fields


def test_iter_fields_reads_varint_and_length_delimited():
    payload = b"\x08\x96\x01\x12\x03abc"
    assert list(iter_fields(payload)) == [(1, 0, 150), (2, 2, b"abc")]


def test_iter_fields_rejects_truncated_varint():
    with pytest.raises(ScipWireError):
        list(iter_fields(b"\x08\x80"))


def test_iter_fields_rejects_groups():
    with pytest.raises(ScipWireError):
        list(iter_fields(b"\x0b"))


def test_decode_packed_int32():
    assert decode_packed_int32(b"\x01\x02\xac\x02") == (1, 2, 300)
```

- [ ] **Step 2: Run RED proof**

Run: `python -m unittest tests.test_scip_wire -v`  
Expected: import failure because `habitat.semantic.scip_wire` does not exist.

- [ ] **Step 3: Implement minimal bounded wire reader**

Implementation must reject field number 0, malformed varints over 10 bytes, truncated fixed/length-delimited fields, negative/overflow lengths, and wire types 3/4/6/7. It must not recurse by itself.

- [ ] **Step 4: Run GREEN proof and full regression**

Run: `python -m unittest tests.test_scip_wire -v` then `python -m unittest discover -q`.

- [ ] **Step 5: Commit**

Commit: `feat: add bounded SCIP protobuf wire reader`.

---

### Task 2: SCIP message parser and immutable snapshot

**Files:**
- Create: `habitat/semantic/scip_index.py`
- Create: `tests/scip_fixture.py`
- Create: `tests/test_scip_index.py`

**Interfaces:**
- `ScipParseError(ValueError)`.
- `ScipToolInfo(name: str, version: str, arguments: tuple[str, ...])`.
- `ScipLocation(path, start_line, start_column, end_line, end_column, symbol, roles)`.
- `ScipDiagnostic(severity, code, message, source, location)`.
- `ScipDocument(path, language, position_encoding, occurrences, symbols, diagnostics)`.
- `ScipIndexSnapshot(index_digest, project_root, protocol_version, text_document_encoding, tool, documents, definitions_by_symbol, references_by_symbol)`.
- `parse_scip_index(path: Path, *, max_index_bytes=256*1024*1024, max_documents=250_000, max_occurrences=5_000_000) -> ScipIndexSnapshot`.

- [ ] **Step 1: Build deterministic fixture encoder**

`tests/scip_fixture.py` implements only the field encoders needed to create valid `Index`/`Metadata`/`ToolInfo`/`Document`/`Occurrence`/`Diagnostic` messages. It must not import production parser code.

- [ ] **Step 2: Write RED parse tests**

Fixture contains `src/a.py` with definition `scip-python python demo 1.0 foo().` and `src/b.py` with one reference to the same symbol plus a warning diagnostic. Assert tool identity, document paths, 1-based normalized lines, definition/reference indexing, diagnostic source/severity, and SHA-256 index digest.

- [ ] **Step 3: Write RED validation tests**

Reject paths beginning `/`, containing `.` or `..` components, backslashes, `//`, NUL, oversized input, more than configured document/occurrence limits, malformed typed/deprecated ranges, and duplicate metadata fields.

- [ ] **Step 4: Implement parser**

Prefer typed range fields 8/9 over deprecated packed field 1. Convert SCIP zero-based lines/columns to Habitat one-based line and one-based column. Empty symbol occurrences may contribute diagnostics but not definition/reference indexes. Preserve unknown fields by ignoring them only after the wire reader validates their boundaries.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: parse bounded SCIP index snapshots`.

---

### Task 3: Read-only SCIP semantic provider

**Files:**
- Create: `habitat/semantic/scip_provider.py`
- Create: `tests/test_scip_provider.py`

**Interfaces:**
- `ScipSemanticProvider(SemanticProvider)`.
- Descriptor: `layer="compiler-index"`, `trust_ceiling="semantic"`, `lifecycle="workspace-scoped"`, `incremental=False`, authority flags false.
- Capabilities: `definitions`, `references`, `document-symbols`, `diagnostics`.
- Query methods return Habitat-owned dict envelopes with provider/tool/index/revision/source provenance.

- [ ] **Step 1: Write RED descriptor tests**

Assert no mutation capability appears and both authority flags are false.

- [ ] **Step 2: Write RED query tests**

Assert definitions/references/document results are normalized and contain `provider_id`, `provider_fingerprint`, `index_digest`, `tool`, `activation_revision`, `trust="semantic"`, and locations.

- [ ] **Step 3: Implement provider and stable fingerprint**

Fingerprint canonical JSON of provider ID, SCIP index digest, tool identity, protocol version, and sorted document paths. Timestamps must not affect it.

- [ ] **Step 4: Run focused/full tests and commit**

Commit: `feat: add read-only SCIP semantic provider`.

---

### Task 4: Workspace SCIP runtime, source binding, freshness

**Files:**
- Create: `habitat/semantic/scip_runtime.py`
- Modify: `habitat/workspace.py`
- Create: `tests/test_scip_runtime.py`
- Create: `tests/test_workspace_scip_runtime.py`

**Interfaces:**
- `ScipStaleIndexError(RuntimeError)`.
- `ScipRuntimeManager(root, semantic_registry, revision_getter)`.
- `activate(index_path, provider_id=None)`, `definitions`, `references`, `document`, `status`, `close_provider`, `close`.
- Workspace facade methods from the spec.

- [ ] **Step 1: Write RED explicit-activation/no-autostart tests**

Creating/opening/indexing a workspace must not read or admit `index.scip`. `scip_status()` initially reports an empty provider list.

- [ ] **Step 2: Write RED path/source binding tests**

Activation binds each materialized SCIP document to SHA-256 of current bytes. Missing files are reported but cannot be returned as current source evidence.

- [ ] **Step 3: Write RED stale tests**

After activation, source byte change or Habitat revision change causes all read queries to raise `ScipStaleIndexError` until explicit reactivation.

- [ ] **Step 4: Implement registration/admission lifecycle**

Register/rebind -> probe -> admit only after parsing and source binding succeed. Evidence includes `scip.index.sha256`, tool name/version, original root, activation revision, document fingerprint, and provider fingerprint. Close/replacement revokes admission.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: add workspace-scoped SCIP runtime`.

---

### Task 5: Explicit command-backed SCIP generation

**Files:**
- Modify: `habitat/semantic/scip_runtime.py`
- Modify: `habitat/workspace.py`
- Create: `tests/fake_scip_indexer.py`
- Create: `tests/test_scip_generation.py`

**Interfaces:**
- `ScipIndexerSpec(provider_id: str, argv: tuple[str, ...], output_path: Path, timeout_s: float = 120.0, env: tuple[tuple[str, str], ...] = ())`.
- `generate(spec) -> dict` runs argv with `shell=False`, bounded capture, validates output, then activates the index.

- [ ] **Step 1: Write RED execution tests**

Cover successful fake generation, nonzero exit, timeout, absent output, output path escape, and proof that no shell is used.

- [ ] **Step 2: Implement bounded generation**

Use `subprocess.Popen(list(argv), cwd=root, shell=False, stdout=PIPE, stderr=PIPE)`. Drain with `communicate(timeout=...)`; on timeout terminate then kill after a short bound. Retain only final 64 KiB per stream in returned status.

- [ ] **Step 3: Run focused/full tests and commit**

Commit: `feat: add explicit SCIP index generation`.

---

### Task 6: Semantic Fabric reporting and authority regression

**Files:**
- Modify: `habitat/semantic/fabric.py` only if the current admission projection needs a capability-list extension.
- Create: `tests/test_scip_semantic_fabric.py`
- Create: `tests/test_scip_authority_boundary.py`

**Interfaces:**
- No new mutation API.

- [ ] **Step 1: Write RED/characterization report test**

Before activation, no admitted SCIP identity exists. After activation, `semantic_fabric()` reports the provider as admitted, `layer="compiler-index"`, semantic trust, exact tool/index fingerprint evidence, and only read-only capabilities.

- [ ] **Step 2: Lock mutation boundary**

Inject or select SCIP-derived semantic evidence and prove `replace_symbol_source` remains rejected unless independently backed by an exact source-authorized Habitat symbol anchor.

- [ ] **Step 3: Run full regression and commit**

Commit: `test: lock SCIP evidence behind read-only authority boundary`.

---

### Task 7: Exact-head verification and merge gate

**Files:**
- Documentation changes only if behavior differs from the approved design.

- [ ] **Step 1: Run complete local-style suite in GitHub matrix**

Exact candidate must pass Ubuntu/Windows × Python 3.10/3.14 Habitat CI, including full regression, compatibility, protocol, recovery, reproducibility, distribution verification, Semgrep, truth-core, and artifact upload.

- [ ] **Step 2: Require CodeQL**

Exact candidate CodeQL must conclude `success`.

- [ ] **Step 3: Review invariants**

Verify no auto-activation, no shell, no mutation capability, bounded parser/execution, source freshness, admission revocation, `_workspace_core.py` untouched, protocol/MCP unchanged.

- [ ] **Step 4: Merge only with exact head SHA**

Use `expected_head_sha`; verify post-merge `main` and post-merge workflows before starting semantic-disagreement work.
