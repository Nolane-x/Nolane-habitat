# SCIP Index Runtime — Design Specification

**Status:** Foundation Convergence Wave 1 completion slice  
**Baseline:** `main` at `f6d8b995fd7ecc53bb0fd6e6229248e3b13d3afe`  
**Protocol source:** SCIP `scip.proto` (`Index` / `Metadata` / `Document` / `Occurrence`)  
**Primary objective:** admit existing or explicitly generated `.scip` indexes as read-only compiler-precise semantic evidence while preserving source authority, freshness, bounded-resource, and mutation-safety guarantees.

## 1. Scope

This slice completes the SCIP portion of Foundation Convergence Wave 1. It does not introduce the Wave 2 Authority Kernel and does not grant SCIP data mutation authority.

Habitat will support:

- explicit activation of an existing `.scip` file;
- bounded parsing of the Protobuf wire format needed by current SCIP indexes;
- preservation of indexer name/version/arguments, original project root, index digest, and current Habitat revision/source fingerprint;
- read-only document occurrences, definition lookup, reference lookup, symbol metadata, and occurrence diagnostics;
- explicit command-backed index generation with `shell=False`, timeout, bounded stderr/stdout, and activation only after a valid index is produced;
- runtime status and Semantic Fabric reporting from admitted runtime truth.

## 2. Non-negotiable invariants

1. Canonical project files remain executable/source truth.
2. SCIP providers always expose `source_authority=False` and `mutation_authority=False`.
3. No `.scip` file is auto-discovered or auto-admitted during workspace create/open/index/refresh.
4. Activation is explicit and requires successful parse, path validation, source binding, provider fingerprinting, registration/probe/admission.
5. Index generation never uses a shell; commands are argv and run with `shell=False`.
6. No rename, code action, formatting, workspace edit, execute-command, or other mutation-producing SCIP surface exists.
7. Document paths must be canonical POSIX-style relative paths and must not escape the Habitat source root when materialized.
8. Every accepted query result carries provider ID, tool identity, index digest, activation revision, source digest evidence, and observed timestamp.
9. Source freshness is fail-closed: a workspace revision change invalidates the activated snapshot; returned definition/reference locations are also digest-checked against current bytes.
10. Parsing and command execution are bounded. Default maximum index size is 256 MiB, maximum documents 250,000, maximum occurrences 5,000,000, indexer timeout 120 seconds, retained stdout/stderr 64 KiB each.
11. Unknown Protobuf fields and supported wire types are skipped safely; malformed varints, truncated length-delimited fields, impossible ranges, or unsupported group wire types fail activation.
12. Existing public agent protocol and MCP method/tool names remain unchanged.
13. `_workspace_core.py` remains untouched.

## 3. Architecture

### 3.1 `habitat/semantic/scip_wire.py`

A dependency-free bounded Protobuf wire reader specialized for consuming SCIP. It is not a general Protobuf implementation. It supports wire types 0, 1, 2, and 5; groups (3/4) are rejected. It exposes helpers for varints, length-delimited fields, packed int32 ranges, and deterministic field iteration.

### 3.2 `habitat/semantic/scip_index.py`

Parses the SCIP messages Habitat needs:

- `Index.metadata` and repeated `Index.documents`;
- `Metadata.version`, `tool_info`, `project_root`, `text_document_encoding`;
- `ToolInfo.name`, `version`, `arguments`;
- `Document.relative_path`, `language`, `position_encoding`, `occurrences`, `symbols`;
- `Occurrence.range`, typed ranges, `symbol`, `symbol_roles`, diagnostics;
- `SymbolInformation.symbol`, documentation, kind, display name, enclosing symbol;
- `Diagnostic.severity`, code, message, source.

The parser builds a compact immutable `ScipIndexSnapshot` and secondary indexes by symbol and path. Definition status comes from `SymbolRole.Definition` bit `0x1`; all other symbol occurrences are references unless symbol text is empty.

### 3.3 `habitat/semantic/scip_provider.py`

A read-only semantic provider over one validated snapshot. Descriptor:

- `layer="compiler-index"`;
- `trust_ceiling="semantic"`;
- `lifecycle="workspace-scoped"`;
- capabilities: `definitions`, `references`, `document-symbols`, `diagnostics`;
- both authority flags false.

The provider normalizes SCIP records into Habitat-owned envelopes rather than exposing parser internals as authority.

### 3.4 `habitat/semantic/scip_runtime.py`

Workspace owner for explicit activation and generation. It binds a snapshot to:

- current Habitat revision;
- SHA-256 of the index bytes;
- original SCIP tool identity/root;
- SHA-256 digests of materialized indexed documents.

Queries fail with `ScipStaleIndexError` after revision drift or source-digest drift. Closing/replacing an activation revokes admission.

### 3.5 Workspace facade

`HabitatWorkspace` adds:

- `scip_activate(index_path: Path, provider_id: str | None = None) -> dict`;
- `scip_generate(spec: ScipIndexerSpec) -> dict`;
- `scip_status() -> dict`;
- `scip_definitions(provider_id: str, symbol: str) -> list[dict]`;
- `scip_references(provider_id: str, symbol: str) -> list[dict]`;
- `scip_document(provider_id: str, path: Path) -> dict`.

These are Python facade methods only in this wave; agent protocol and MCP remain unchanged.

## 4. Source binding and staleness

Activation records the current Habitat revision and current SHA-256 for every SCIP document that materializes under the source root. Missing documents remain visible as unavailable evidence but cannot be returned as current source locations.

Before a query:

- the current Habitat revision must equal the activation revision;
- each location about to be returned must still resolve under the source root;
- its current SHA-256 must equal the activation digest.

A mismatch raises `ScipStaleIndexError`. The caller must explicitly regenerate/reactivate; there is no auto-respawn or auto-reindex loop.

## 5. Index generation

`ScipIndexerSpec` is immutable and contains provider ID, argv, output path, timeout, and optional environment additions. The output path must remain under Habitat metadata or the workspace root and cannot overwrite canonical source files unless it already names a `.scip` artifact. Generation captures bounded output, requires exit code zero, requires the output file to exist, then activates it through the same validation path as an existing index.

## 6. Semantic disagreement boundary

This slice does not yet persist cross-provider disagreements. It deliberately makes SCIP results provider-identifiable and revision-bound so the next Wave 1 slice can compare SCIP, LSP, Jedi, and TypeScript precise evidence without inventing provenance retroactively.

## 7. Tests and exit criteria

The slice is complete only when:

1. a deterministic hand-built Protobuf fixture parses without external SCIP tooling;
2. malformed/truncated/oversized payloads fail closed;
3. canonical path checks reject absolute, `.`/`..`, empty-component, and escaping paths;
4. metadata/tool identity and index digest are preserved;
5. definitions/references/diagnostics return normalized read-only evidence;
6. source/revision drift rejects stale queries;
7. no automatic activation occurs;
8. generated index commands use `shell=False` and bounded execution;
9. SCIP semantic evidence cannot authorize source replacement;
10. `semantic_fabric()` reports admitted SCIP runtime identity only after explicit activation;
11. full Ubuntu/Windows × Python 3.10/3.14 CI and CodeQL pass on the exact PR head.
