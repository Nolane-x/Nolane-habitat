# Workspace-Scoped LSP Runtime Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real, explicitly activated, workspace-scoped LSP 3.18 stdio runtime that provides read-only semantic evidence under Habitat admission without granting source or mutation authority.

**Architecture:** A bounded JSON-RPC/LSP transport owns one subprocess and lifecycle. A read-only semantic provider normalizes negotiated LSP results, while a workspace runtime manager owns activation, document synchronization, freshness checks, admission/revocation, and reporting. The public workspace facade owns the manager; `_workspace_core.py` remains untouched.

**Tech Stack:** Python 3.10–3.14 stdlib (`subprocess`, `threading`, `queue`, `json`, `urllib.parse`, `hashlib`), Habitat SemanticProvider/AdmissionRegistry, `unittest`, GitHub Actions Ubuntu/Windows matrix.

**Spec:** `docs/superpowers/specs/2026-08-28-lsp-runtime-kernel-design.md`

## Global Constraints

- Target LSP protocol semantics: 3.18 over stdio JSON-RPC 2.0.
- No automatic LSP process start during workspace create/open/index.
- LSP operations are read-only in this wave: definition, references, hover, document symbols, diagnostics.
- No rename, code action, formatting, workspace edit, execute-command, or arbitrary method passthrough.
- `source_authority=False` and `mutation_authority=False` for every LSP provider.
- LSP `semantic` trust must not authorize source mutation.
- Maximum inbound body: 8 MiB; retained stderr: 64 KiB; pending requests: 128.
- Default request timeout: 5s; initialize timeout: 10s; shutdown timeout: 3s; terminate grace: 2s.
- No shell execution; server commands are argv with `shell=False`.
- `_workspace_core.py` is not modified.
- Existing Habitat agent protocol and MCP public method names remain unchanged.

---

### Task 1: Bounded LSP frame codec

**Files:**
- Create: `habitat/semantic/lsp_transport.py`
- Create: `tests/test_lsp_transport.py`

**Interfaces:**
- Produces: `LspProtocolError(ValueError)`.
- Produces: `encode_lsp_message(message: dict) -> bytes`.
- Produces: `LspFrameDecoder(max_body_bytes: int = 8 * 1024 * 1024)` with `feed(data: bytes) -> list[dict]`.

- [ ] **Step 1: Write RED tests for fragmented and batched framing**

```python
class LspTransportTests(unittest.TestCase):
    def test_decoder_handles_fragmented_header_and_body(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, encode_lsp_message
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        wire = encode_lsp_message(payload)
        decoder = LspFrameDecoder()
        out = []
        for chunk in (wire[:7], wire[7:19], wire[19:31], wire[31:]):
            out.extend(decoder.feed(chunk))
        self.assertEqual(out, [payload])

    def test_decoder_handles_multiple_frames_in_one_feed(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, encode_lsp_message
        first = {"jsonrpc": "2.0", "id": 1, "result": 1}
        second = {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 3}}
        self.assertEqual(LspFrameDecoder().feed(encode_lsp_message(first) + encode_lsp_message(second)), [first, second])
```

- [ ] **Step 2: Write RED tests for malformed/oversized input**

```python
    def test_decoder_rejects_missing_content_length(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError
        with self.assertRaises(LspProtocolError):
            LspFrameDecoder().feed(b"Content-Type: application/json\r\n\r\n{}")

    def test_decoder_rejects_oversized_body_before_body_arrives(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError
        with self.assertRaises(LspProtocolError):
            LspFrameDecoder(max_body_bytes=32).feed(b"Content-Length: 100\r\n\r\n")

    def test_decoder_rejects_non_object_json(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError
        with self.assertRaises(LspProtocolError):
            LspFrameDecoder().feed(b"Content-Length: 2\r\n\r\n[]")
```

- [ ] **Step 3: Run RED proof**

Run: `python -m unittest tests.test_lsp_transport -v`  
Expected: import errors because `habitat.semantic.lsp_transport` does not exist.

- [ ] **Step 4: Implement the codec**

```python
class LspProtocolError(ValueError):
    pass


def encode_lsp_message(message: dict) -> bytes:
    if not isinstance(message, dict):
        raise TypeError("LSP JSON-RPC message must be an object")
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


class LspFrameDecoder:
    def __init__(self, max_body_bytes: int = 8 * 1024 * 1024):
        self._buffer = bytearray()
        self.max_body_bytes = int(max_body_bytes)

    def feed(self, data: bytes) -> list[dict]:
        self._buffer.extend(data)
        messages = []
        while True:
            header_end = self._buffer.find(b"\r\n\r\n")
            if header_end < 0:
                return messages
            raw_headers = bytes(self._buffer[:header_end]).decode("ascii", errors="strict")
            lengths = []
            for line in raw_headers.split("\r\n"):
                name, sep, value = line.partition(":")
                if not sep:
                    raise LspProtocolError("invalid LSP header")
                if name.strip().lower() == "content-length":
                    lengths.append(value.strip())
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise LspProtocolError("exactly one valid Content-Length is required")
            length = int(lengths[0])
            if length > self.max_body_bytes:
                raise LspProtocolError("LSP body exceeds configured limit")
            body_start = header_end + 4
            if len(self._buffer) < body_start + length:
                return messages
            body = bytes(self._buffer[body_start:body_start + length])
            del self._buffer[:body_start + length]
            try:
                value = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LspProtocolError("invalid LSP JSON body") from exc
            if not isinstance(value, dict):
                raise LspProtocolError("LSP JSON-RPC message must be an object")
            messages.append(value)
```

- [ ] **Step 5: Run GREEN proof and full regression**

Run: `python -m unittest tests.test_lsp_transport -v` then `python -m unittest discover -q`.

- [ ] **Step 6: Commit**

`git commit -am "feat: add bounded LSP frame codec"`

---

### Task 2: Deterministic fake LSP server and process lifecycle

**Files:**
- Create: `tests/fake_lsp_server.py`
- Modify: `habitat/semantic/lsp_transport.py`
- Create: `tests/test_lsp_process_session.py`

**Interfaces:**
- Produces: `LspServerSpec(provider_id: str, languages: frozenset[str], argv: tuple[str, ...], required_capabilities: frozenset[str] = frozenset())`.
- Produces: `LspProcessSession(spec, root: Path, *, request_timeout_s=5.0, initialize_timeout_s=10.0, shutdown_timeout_s=3.0, terminate_grace_s=2.0)`.
- Produces: `start() -> dict`, `request(method: str, params: dict | None = None, timeout_s: float | None = None) -> object`, `notify(method: str, params: dict | None = None) -> None`, `close() -> None`, `status() -> dict`.

- [ ] **Step 1: Add a fake stdio server**

The server reads `Content-Length` frames using the same wire rules but must not import Habitat production transport. It responds to `initialize`, `shutdown`, `textDocument/definition`, `textDocument/references`, `textDocument/hover`, `textDocument/documentSymbol`, accepts notifications, and supports `--mode normal|initialize-error|crash-after-init|hang-request|malformed-frame`.

- [ ] **Step 2: Write RED lifecycle tests**

```python
def fake_spec(mode="normal"):
    return LspServerSpec(
        provider_id="lsp.fake",
        languages=frozenset({"python"}),
        argv=(sys.executable, str(Path(__file__).with_name("fake_lsp_server.py")), "--mode", mode),
        required_capabilities=frozenset({"definition"}),
    )


def test_start_performs_initialize_and_initialized(self):
    session = LspProcessSession(fake_spec(), self.root)
    caps = session.start()
    self.assertTrue(caps["definitionProvider"])
    self.assertEqual(session.status()["state"], "READY")
    session.close()
    self.assertEqual(session.status()["state"], "CLOSED")
```

Also cover initialize error, crash, no `shell=True`, and idempotent close.

- [ ] **Step 3: Run RED proof**

Run: `python -m unittest tests.test_lsp_process_session -v`  
Expected: missing lifecycle classes/methods.

- [ ] **Step 4: Implement `LspProcessSession`**

Use `subprocess.Popen(list(spec.argv), stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=False, bufsize=0)`. Start dedicated daemon reader threads for stdout and stderr. Stdout feeds `LspFrameDecoder`; responses are correlated into bounded pending request slots. Notifications are appended to a bounded deque. `start()` sends `initialize`, validates the result object/capabilities, then sends `initialized`.

- [ ] **Step 5: Implement deterministic close**

`close()` sends `shutdown`, waits up to `shutdown_timeout_s`, sends `exit`, closes pipes, waits, then `terminate()`/`kill()` only if deadlines expire. Transition state monotonically; any protocol/process failure sets `FAILED`.

- [ ] **Step 6: Run focused/full tests and commit**

Run both LSP test modules plus `python -m unittest discover -q`.  
Commit: `feat: add workspace-scoped LSP process lifecycle`.

---

### Task 3: Timeouts, cancellation, crash revocation primitives, and bounded diagnostics

**Files:**
- Modify: `habitat/semantic/lsp_transport.py`
- Modify: `tests/fake_lsp_server.py`
- Modify: `tests/test_lsp_process_session.py`

**Interfaces:**
- Produces: `LspRequestTimeout(TimeoutError)`.
- `status()` includes `consecutive_timeouts`, `stderr_tail`, `pending_requests`, `state`, `failure_reason`.

- [ ] **Step 1: Write RED tests**

Test one timed-out request sends `$/cancelRequest`, three consecutive request timeouts transition session to `FAILED`, a crash transitions to `FAILED`, and stderr retention never exceeds 64 KiB.

- [ ] **Step 2: Run RED proof**

Run focused module; expect timeout/cancellation/status assertions to fail.

- [ ] **Step 3: Implement timeout/cancel policy**

On timeout: remove pending slot, increment consecutive count, best-effort notify `$/cancelRequest` with original ID, raise `LspRequestTimeout`. Successful request resets consecutive count. At three consecutive timeouts call `_fail("three consecutive request timeouts")` and terminate process.

- [ ] **Step 4: Implement bounded stderr tail**

Append bytes/text into a tail buffer and truncate from the left to the final 64 KiB after every append.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: harden LSP timeout and failure handling`.

---

### Task 4: Read-only LSP SemanticProvider and normalization

**Files:**
- Create: `habitat/semantic/lsp_provider.py`
- Create: `tests/test_lsp_provider.py`

**Interfaces:**
- Produces: `LspSemanticProvider(SemanticProvider)`.
- Descriptor: `layer="language-semantic-service"`, `trust_ceiling="semantic"`, `lifecycle="workspace-scoped"`, `incremental=True`, both authority flags false.
- Produces read-only methods: `definition`, `references`, `hover`, `document_symbols`.

- [ ] **Step 1: Write RED descriptor/allowlist tests**

Assert mutation-producing capability names never appear and `source_authority`/`mutation_authority` remain false.

- [ ] **Step 2: Write RED normalization tests**

Use fake server responses and assert normalized records include provider ID, URI/range, method, semantic trust, revision, digest, document version, and provider fingerprint.

- [ ] **Step 3: Implement provider**

The provider wraps an already-started session. Its descriptor capabilities are the intersection of negotiated server capabilities and Habitat's fixed allowlist: `definition`, `references`, `hover`, `document-symbols`, `diagnostics`.

- [ ] **Step 4: Implement stable fingerprint**

Fingerprint canonical JSON of provider ID, resolved argv executable, executable version evidence when available, negotiated capability digest, and protocol target. Never include timestamps.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: add read-only LSP semantic provider`.

---

### Task 5: Workspace LSP runtime manager, explicit activation, document sync, freshness

**Files:**
- Create: `habitat/semantic/lsp_runtime.py`
- Modify: `habitat/semantic/admission.py`
- Create: `tests/test_lsp_runtime.py`

**Interfaces:**
- AdmissionRegistry adds `revoke(provider_id: str, reason: str = "") -> SemanticProviderAdmission` and read-only `is_admitted(provider_id: str) -> bool`.
- Produces: `LspRuntimeManager(root: Path, semantic_registry: SemanticAdmissionRegistry, revision_getter: Callable[[], str])`.
- Manager methods: `activate(spec) -> dict`, `query(provider_id, capability, path, *, position=None) -> object`, `close_provider(provider_id)`, `close()`, `status() -> dict`.

- [ ] **Step 1: Write RED explicit-activation/admission tests**

Construct a manager and assert no process/provider is active before `activate`. Activation with fake server performs handshake then makes `providers_for("definition", language="python")` include `lsp.fake`. Failed initialize leaves it unadmitted.

- [ ] **Step 2: Write RED document freshness tests**

First query emits didOpen version 1. Change bytes, query again, assert didChange version 2. Configure fake server to delay a response; mutate bytes/revision before response and assert the manager raises a stale-result error instead of returning/persisting it.

- [ ] **Step 3: Implement admission revoke/status support**

`revoke` removes admission but preserves registration/probe history. `is_admitted` checks the current admission map.

- [ ] **Step 4: Implement activation and sync**

`activate` starts session, validates required capabilities, creates provider, registers/probes/admit with handshake/fingerprint/capability/root evidence. Manager tracks open docs with digest/revision/version. Use full-text didChange in Wave 2.

- [ ] **Step 5: Implement crash/close revocation**

Before every selection/query, verify session state is READY. If failed/closed, revoke provider. `close_provider` sends didClose for live opened documents, closes session, revokes admission.

- [ ] **Step 6: Run focused/full tests and commit**

Commit: `feat: add explicit workspace LSP runtime manager`.

---

### Task 6: Workspace facade and Semantic Fabric integration

**Files:**
- Modify: `habitat/workspace.py`
- Modify: `habitat/semantic/fabric.py`
- Create: `tests/test_workspace_lsp_runtime.py`

**Interfaces:**
- Public workspace adds `lsp_activate(spec) -> dict`, `lsp_status() -> dict`, `lsp_query(provider_id, capability, path, *, position=None) -> object`.
- `close()` closes the LSP manager before closing the underlying workspace core.

- [ ] **Step 1: Write RED no-autostart test**

Create/open workspace and assert `lsp_status()["providers"] == []`; fake server marker file must not exist before explicit activation.

- [ ] **Step 2: Write RED report consistency test**

After explicit fake activation, `ws.semantic_fabric()` must show `lsp.fake` as `detected=True`, `admitted=True`, `lifecycle="workspace-scoped"`, and only negotiated read-only capabilities.

- [ ] **Step 3: Implement facade ownership**

Instantiate `LspRuntimeManager` lazily on first LSP operation so ordinary workspace construction cannot spawn anything. The manager receives the workspace's existing `semantic_registry` and revision getter.

- [ ] **Step 4: Bind Fabric report to runtime truth**

Keep host binary discovery, but merge admitted runtime identities from the same registry. Do not infer admission from `shutil.which`.

- [ ] **Step 5: Run focused/full tests and commit**

Commit: `feat: integrate explicit LSP runtime with workspace`.

---

### Task 7: Trust/authority separation regression gate

**Files:**
- Modify: `habitat/workspace.py` only if needed to centralize the mutation-authority check.
- Create: `tests/test_lsp_authority_boundary.py`

**Interfaces:**
- No new public mutation API.

- [ ] **Step 1: Write RED/characterization test**

Create or inject a `SymbolRecord` derived from an admitted LSP provider with `trust="semantic"`; assert `stage_symbol_change()` rejects it unless it is independently backed by an exact/source-authorized anchor. Also assert existing Python AST exact symbol mutation remains allowed.

- [ ] **Step 2: Run the test before production changes**

If it already passes, keep it as a characterization/protection test and make no authority code change. If it fails, fix the authority gate rather than lowering LSP trust.

- [ ] **Step 3: Run full regression and commit**

Commit: `test: lock LSP semantic trust out of mutation authority` (or `fix:` if production changes are required).

---

### Task 8: Final CI evidence, review, and merge

**Files:**
- Modify docs only if implementation behavior differs from the approved spec; otherwise no production changes after final candidate starts verification.

- [ ] **Step 1: Run full repository suite on exact candidate head**

`python -m unittest discover -q`.

- [ ] **Step 2: Require GitHub matrix**

Exact head must pass Ubuntu/Windows x Python 3.10/3.14 through release identity, full regression, foundation baseline, isolated matrix, compatibility, protocol, DB/source recovery, fault injection, independent reproducibility, distribution verification, Semgrep, truth-core, artifact upload.

- [ ] **Step 3: Require CodeQL**

Exact head CodeQL must conclude `success`.

- [ ] **Step 4: Review invariants**

Verify: no auto-start, no shell, no unbounded queues, no mutation methods, semantic trust is read-only, stale result rejection, admission revocation, deterministic close, no `_workspace_core.py` changes, no protocol/MCP drift.

- [ ] **Step 5: Mark PR ready and merge with exact SHA**

Use `expected_head_sha` so GitHub rejects a moved head.

- [ ] **Step 6: Verify post-merge main**

Confirm `main` points to merge commit and post-merge CI/CodeQL start on that SHA.
