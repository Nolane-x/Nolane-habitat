# Workspace-Scoped LSP Runtime Kernel — Design Specification

**Status:** approved Foundation Convergence Wave 2 design  
**Baseline:** `main` at `6476bda8466fbad202a1eda8e2ba07fbdcfdc21e`  
**Protocol target:** Language Server Protocol 3.18 over JSON-RPC 2.0  
**Primary objective:** make LSP a real, admitted, workspace-scoped semantic sensor without allowing external language servers to acquire source or mutation authority.

---

## 1. Problem statement

Habitat now has an enforceable semantic admission runtime and a real Tree-sitter provider. The remaining semantic precision gap is cross-file language semantics: definitions, references, diagnostics, hover/type information, and language-server-native document symbols. `semantic_fabric_report()` can detect LSP binaries, but detection is not activation and must not be presented as active semantic truth.

A language server is materially different from a stateless parser:

- it is a long-lived subprocess with protocol state;
- it may inspect project configuration and execute plugin/configuration logic;
- it maintains document/workspace caches;
- it can return stale results after source revisions change;
- it can crash, hang, emit malformed protocol frames, or advertise unsupported capabilities;
- some servers support mutation-producing operations such as rename/code actions.

Wave 2 therefore introduces a small process/lifecycle kernel first. Provider adapters sit above that kernel. Mutation-producing LSP features remain out of scope until a later authority-promotion design.

---

## 2. Non-negotiable invariants

1. **Detection is not activation.** Finding `pyright-langserver`, `rust-analyzer`, `gopls`, `clangd`, `jdtls`, or another binary never admits a provider.
2. **Activation is explicit.** Creating/opening a Habitat workspace must not automatically spawn a language server merely because one is installed.
3. **Admission requires a successful protocol handshake.** A provider can become selectable only after process start, `initialize` response, capability validation, `initialized`, and concrete admission evidence.
4. **Workspace scope.** Each active LSP session belongs to exactly one Habitat workspace/source root. No global cross-project process pool.
5. **Read-only first.** Wave 2 supports definition, references, diagnostics, hover, and document symbols only. Rename, code actions, formatting, workspace edits, execute-command, and mutation-producing requests are not exposed.
6. **Trust is not authority.** LSP-derived records may carry `semantic` trust, but neither trust grade nor provider capability grants source/mutation authority.
7. **Revision binding.** Every accepted semantic result is bound to the Habitat revision/source digest/document version that produced it. Results for stale document versions are rejected or explicitly marked stale and never persisted as current truth.
8. **Fail closed.** Timeout, malformed frame, process exit, capability mismatch, invalid result shape, or document-version mismatch invalidates the request; repeated process failure revokes admission for the session.
9. **Deterministic cleanup.** `HabitatWorkspace.close()` closes all LSP sessions. The lifecycle is `initialize -> initialized -> shutdown -> exit`; a bounded forced termination is allowed only after graceful shutdown exceeds its deadline.
10. **Bounded resources.** stderr capture, pending requests, message size, request timeouts, and shutdown timeouts are bounded. No unbounded reader queues.
11. **No shell execution.** LSP commands are launched as argv with `shell=False`.
12. **No wire/protocol drift elsewhere.** Existing Habitat agent protocol and MCP method/tool names remain unchanged in this wave.

---

## 3. Recommended architecture

### 3.1 `LspProcessSession`

A low-level workspace-scoped JSON-RPC/LSP transport owner.

Responsibilities:

- spawn one configured language-server argv;
- encode outbound `Content-Length` framed JSON-RPC messages;
- parse inbound frames incrementally, including partial reads;
- correlate responses to request IDs;
- route server notifications without blocking request completion;
- bound message size and stderr capture;
- maintain explicit session state;
- implement request timeout and cancellation;
- perform graceful shutdown and bounded forced termination;
- expose a diagnostic snapshot without exposing raw private model reasoning.

State machine:

`NEW -> STARTING -> INITIALIZING -> READY -> SHUTTING_DOWN -> CLOSED`

Any protocol/process fault from `STARTING` onward can transition to `FAILED`; `FAILED` is terminal for that session object.

### 3.2 `LspServerSpec`

Immutable configuration describing a concrete server adapter:

- provider ID;
- language set;
- argv;
- initialization options/settings when required;
- expected minimum capabilities;
- optional executable fingerprint probe;
- document selector/file-extension mapping.

The spec does not imply admission.

### 3.3 `LspSemanticProvider`

A read-only `SemanticProvider` adapter built on an active `LspProcessSession`.

Descriptor:

- `layer = "language-semantic-service"`;
- `trust_ceiling = "semantic"`;
- `lifecycle = "workspace-scoped"`;
- `incremental = True`;
- `source_authority = False`;
- `mutation_authority = False`;
- capabilities limited to the successfully negotiated read-only set.

The provider is not registered/admitted in the default semantic registry until explicit activation succeeds.

### 3.4 `LspRuntimeManager`

Workspace-level owner of active LSP sessions/providers.

Responsibilities:

- keep zero or more active language-server sessions for one workspace;
- activate a configured server explicitly;
- register/probe/admit its `LspSemanticProvider` into the workspace `SemanticAdmissionRegistry` only after handshake proof;
- revoke the provider on close/crash/restart;
- synchronize source documents with monotonically increasing LSP document versions;
- invalidate cached semantic identity whenever session fingerprint/capabilities change;
- expose status/diagnostic snapshots for `semantic_fabric()`.

This manager is owned by the public `HabitatWorkspace` facade rather than the preserved alpha.19 `_workspace_core` implementation.

---

## 4. Protocol framing and limits

Wave 2 supports stdio LSP transport only.

Hard defaults:

- maximum inbound JSON-RPC body: **8 MiB**;
- maximum retained stderr: **64 KiB** per session;
- maximum pending requests: **128**;
- default semantic request timeout: **5 seconds**;
- initialize timeout: **10 seconds**;
- shutdown timeout: **3 seconds**;
- forced terminate grace after shutdown timeout: **2 seconds**.

Inbound framing parser requirements:

- accept `\r\n\r\n` header termination;
- require exactly one valid non-negative `Content-Length` header;
- reject body sizes over the configured limit before allocation/read completion;
- reject invalid UTF-8 or non-object JSON-RPC payloads;
- preserve extra bytes for the next frame;
- support headers/body arriving over multiple reads;
- never use line-oriented JSON parsing for LSP messages.

---

## 5. Initialization and capability proof

Activation sequence:

1. Resolve executable path without shell expansion.
2. Spawn process with stdin/stdout/stderr pipes.
3. Send `initialize` with workspace root URI and conservative client capabilities.
4. Validate a JSON-RPC result object.
5. Extract server `capabilities`.
6. Intersect server capabilities with Habitat's read-only capability allowlist.
7. Require every adapter-declared minimum capability.
8. Send `initialized` notification.
9. Create the semantic provider descriptor from the negotiated capability intersection.
10. Register -> probe -> admit using evidence containing:
   - executable path/version fingerprint;
   - initialize success;
   - negotiated capabilities digest;
   - workspace root digest/identity;
   - protocol target `3.18`.

An executable that starts but fails initialization remains detected but unadmitted.

---

## 6. Document synchronization and freshness

Wave 2 implements text-document synchronization for files actually queried through LSP.

For each open document, Habitat tracks:

- canonical relative path;
- URI;
- language ID;
- current source digest;
- current Habitat revision;
- monotonically increasing integer LSP document version.

Rules:

- first query sends `textDocument/didOpen` with current bytes;
- source digest change sends `textDocument/didChange` using full-document synchronization unless the server proves a supported incremental sync mode and a later wave adopts incremental edits;
- workspace close/session close sends `didClose` for opened documents when the session is still alive;
- every query captures `(revision, digest, document_version)` before sending;
- a response arriving after any of those values changes is rejected as stale;
- stale responses are diagnostic evidence only and are not persisted as current semantic truth.

---

## 7. Read-only semantic operations

Initial adapter surface:

- definition;
- references;
- hover;
- document symbols;
- diagnostics received through `textDocument/publishDiagnostics`.

Normalization target is Habitat-owned semantic objects rather than exposing raw LSP shapes to agents.

Results include provenance fields sufficient to reconstruct:

- provider ID/fingerprint;
- server capability digest;
- request method;
- Habitat revision;
- file digest/document version;
- source URI/range;
- observed timestamp.

Wave 2 explicitly does **not** implement rename, codeAction, formatting, workspace/applyEdit, workspace/executeCommand, or arbitrary LSP method passthrough.

---

## 8. Authority boundary

The existing trust vocabulary (`heuristic`, `parser`, `derived`, `semantic`, `exact`) is evidence-quality metadata, not an authorization lattice by itself.

Wave 2 must therefore prevent the following inference:

`LSP result has trust=semantic -> result may authorize source replacement`

No LSP-derived symbol/reference may authorize `replace_symbol_source`, rename, or any mutation-producing operation in this wave.

A later Authority Kernel wave will introduce an explicit action-authority class independent from trust grade. Until that exists, LSP-derived semantic anchors are read-only inputs to cognition, navigation, diagnostics, impact analysis, and verification.

---

## 9. Failure and revocation semantics

A session/provider is revoked from selection when any of these occur:

- process exits unexpectedly;
- JSON-RPC framing becomes invalid;
- initialization or required-capability negotiation fails;
- explicit session close;
- provider re-probe/restart invalidates prior admission;
- runtime fingerprint changes.

A single ordinary request timeout fails that request and sends `$/cancelRequest` when possible; it does not immediately kill the server. Repeated timeout/process-health policy remains conservative and deterministic: three consecutive request timeouts mark the session failed and revoke admission.

No automatic respawn loop is allowed in Wave 2.

---

## 10. Testing strategy

CI must not require Pyright, clangd, rust-analyzer, gopls, or Java tooling. A deterministic fake LSP server implemented in Python is the protocol oracle for lifecycle tests.

Required tests:

- fragmented header/body framing;
- multiple frames in one read;
- invalid/missing/oversized `Content-Length`;
- invalid UTF-8/JSON;
- initialize success and capability intersection;
- initialize timeout/error/process exit;
- unsupported required capability prevents admission;
- explicit activation required;
- document open/change/version monotonicity;
- stale response rejection after source change;
- request timeout + cancellation;
- crash revokes admission;
- graceful shutdown and forced termination fallback;
- stderr retention bound;
- no mutation-producing method exposure;
- LSP `semantic` trust cannot authorize source mutation;
- Ubuntu/Windows x Python 3.10/3.14 full regression.

The fake server must support fault modes through argv flags/environment local to the test process and must not open network ports.

---

## 11. Integration boundaries

Files expected in this wave:

- `habitat/semantic/lsp_transport.py` — framing/process session only;
- `habitat/semantic/lsp_provider.py` — read-only semantic provider/normalization;
- `habitat/semantic/lsp_runtime.py` — workspace manager/activation/document sync;
- `habitat/workspace.py` — facade ownership, activation/status/close seams;
- `habitat/semantic/admission.py` — explicit revoke/status support where needed;
- `habitat/semantic/fabric.py` — report active negotiated LSP runtime truth;
- `tests/fake_lsp_server.py` — deterministic stdio server;
- focused `tests/test_lsp_*.py` files.

Do not add LSP logic to `_workspace_core.py`.

---

## 12. Exit criteria

Wave 2 is complete only when:

1. no LSP process starts during ordinary workspace create/open/index;
2. explicit activation of the fake server performs a real initialize handshake and admits a provider;
3. negotiated read-only operations work through Habitat-owned normalization;
4. document freshness rejects stale responses;
5. crash/close/re-probe revokes admission;
6. no mutation-producing LSP method is exposed;
7. LSP semantic trust cannot authorize source mutation;
8. `semantic_fabric()` reports detected and admitted LSP state from the same runtime truth;
9. all existing regression, compatibility, protocol, recovery, reproducibility, distribution, Semgrep, truth-core, and CodeQL gates pass on Ubuntu/Windows x Python 3.10/3.14;
10. the exact PR head is merged only after those gates pass.

---

## 13. Deferred work

Explicitly deferred to later Foundation Convergence waves:

- production adapters for every detected server beyond a minimal generic command-backed spec;
- mutation-producing rename/code-action/formatting support;
- automatic language-server installation;
- TCP/WebSocket LSP transport;
- server auto-respawn/retry orchestration;
- persistent LSP response cache across Habitat process restarts;
- SCIP ingestion;
- explicit Trust/Action Authority Kernel classes;
- Benchmark Lab and Learning Plane policy optimization.
