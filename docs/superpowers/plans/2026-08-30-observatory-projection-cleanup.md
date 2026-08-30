# Observatory Projection Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate Habitat's read-only observability projection from its cinematic HTTP frontend, prove the Observatory is durably state-neutral and independently disable-able, and add descriptive headless/frontend cost evidence.

**Architecture:** Extract the existing `ObservatoryReadModel` into a frontend-independent `habitat/observability.py` core, move HTTP/SSE/static/cinematic delivery into `habitat/observatory_frontend.py`, and keep `habitat/observatory.py` as a compatibility/CLI facade. Preserve existing wire/import/asset compatibility while removing the startup activity write and measuring projection/server costs only through an explicit benchmark surface.

**Tech Stack:** Python stdlib, SQLite read-only URI connections, `http.server`, frozen/read-only projection patterns, unittest, existing GitHub CI/CodeQL gates.

**Spec:** `docs/superpowers/specs/2026-08-30-observatory-projection-cleanup-design.md`

## Global Constraints

- Preserve alpha.19 public protocol method names and the 12-tool MCP surface.
- Preserve existing Observatory URL paths, snapshot shapes, CLI name, and packaged assets.
- Existing workspace/schema/source-authority/recovery/Learning Plane/Execution Fabric behavior remains compatible.
- Observatory remains observer-only and receives no mutation authority.
- No second database, cache database, daemon, or durable Observatory truth store.
- Core projection SQLite connections remain `mode=ro` + `PRAGMA query_only=ON`.
- `habitat-agent-server --no-observatory` remains supported and becomes an explicit headless compatibility gate.
- Cost measurements are descriptive; no machine-specific timing threshold or superiority claim.
- Unavailable/unmeasured cost values are `None`/JSON `null`, never fabricated zero.
- RED must be observed before production implementation for each behavior-changing task.
- Final merge requires exact-head CI/CodeQL/review/thread/boundary/main-drift verification.

---

### Task 1: State-Neutral Observability Core

**Files:**
- Create: `habitat/observability.py`
- Modify: `habitat/observatory.py`
- Create: `tests/test_observability_core.py`

**Interfaces:**
- Produces `ObservatoryReadModel` from `habitat.observability`.
- `habitat.observatory.ObservatoryReadModel` remains a compatibility re-export.
- `ObservatoryServer` continues to consume the same read-model API: `revision()`, `latest_activity_seq()`, `activity_since()`, `snapshot()`.

- [ ] **Step 1: Write RED startup-state-neutrality test**

Create a workspace, record the complete SQLite dump **before constructing/starting** the Observatory, then construct/start/status/GET health/stop and require byte-for-byte dump equality afterwards:

```python
database_before = "\n".join(ws.store.conn.iterdump())
server = ObservatoryServer(ws).start(open_browser=False)
try:
    self.assertTrue(server.status()["read_only"])
finally:
    server.close()
self.assertEqual(database_before, "\n".join(ws.store.conn.iterdump()))
```

Expected RED: current `ObservatoryServer.start()` emits durable `observatory.started` activity.

- [ ] **Step 2: Write RED frontend-independent core import/projection test**

Use a clean subprocess so prior test imports cannot hide coupling:

```python
code = """
import json, sys
from habitat.observability import ObservatoryReadModel
print(json.dumps({
  'frontend_loaded': 'habitat.observatory_frontend' in sys.modules,
  'legacy_observatory_loaded': 'habitat.observatory' in sys.modules,
}))
"""
```

Require both flags false. Also instantiate `ObservatoryReadModel(ws)` and require a normal snapshot with `read_only=True` and current revision.

Expected RED: `habitat.observability` does not exist.

- [ ] **Step 3: Observe RED on exact test commit**

Run full regression. Accept only the two new contract failures; existing Observatory/runtime/protocol tests must otherwise remain green.

- [ ] **Step 4: Extract the read model without semantic changes**

Move the existing `ObservatoryReadModel` implementation and its read-only projection helpers into `habitat/observability.py`. Its database connection remains:

```python
uri = self.db_path.as_uri() + "?mode=ro"
conn = sqlite3.connect(uri, uri=True, timeout=2.0)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA query_only=ON")
```

Do not create a Store, writable connection, new database path, or persistent cache.

- [ ] **Step 5: Remove the startup mutation**

Delete the `workspace.activity_emit("observatory.started", ...)` call from `ObservatoryServer.start()`. Keep process-local `status()` as the sole server lifecycle projection.

- [ ] **Step 6: Re-export the read model from `habitat.observatory`**

Replace the in-module class definition with:

```python
from .observability import ObservatoryReadModel
```

so old imports remain valid.

- [ ] **Step 7: Verify focused tests + full regression and commit**

Require startup state neutrality, core import independence, alpha11 Observatory tests, protocol compatibility, and full regression success before Task 2.

---

### Task 2: Cinematic Frontend / Transport Split

**Files:**
- Create: `habitat/observatory_frontend.py`
- Modify: `habitat/observatory.py`
- Modify: `tests/test_alpha11_observatory_runtime.py` only where import fixtures need compatibility coverage
- Modify: `tests/test_alpha12_observatory_cinematic.py`
- Create: `tests/test_observatory_frontend_split.py`

**Interfaces:**
- `habitat.observatory_frontend.ObservatoryServer`
- `habitat.observatory.ObservatoryServer` compatibility re-export
- `habitat.observatory.start_observatory(workspace, *, host="127.0.0.1", port=0, open_browser=True)` unchanged
- all existing `/`, `/app.js`, `/style.css`, `/api/health`, `/api/snapshot`, `/api/activity`, `/api/ui-frame`, `/api/ui-stream`, `/events` paths unchanged.

- [ ] **Step 1: Write RED module-boundary tests**

Require a clean subprocess importing only `habitat.observability` not to load:

```python
"habitat.observatory_frontend"
"http.server"
"webbrowser"
```

Only assert the Habitat frontend module strictly; for stdlib modules, record/import-delta rather than assuming the interpreter never loaded them for unrelated reasons.

Require `habitat.observatory` still exports `ObservatoryReadModel`, `ObservatoryServer`, and `start_observatory`.

- [ ] **Step 2: Write RED HTTP compatibility test**

Start through the legacy facade and require existing JSON/asset endpoints and 405 mutation rejection to remain unchanged. Assert `server.read_model` is an instance of `habitat.observability.ObservatoryReadModel`.

- [ ] **Step 3: Observe RED**

Expected failure: `habitat.observatory_frontend` missing / HTTP classes still owned by `habitat.observatory`.

- [ ] **Step 4: Move frontend/server responsibilities**

Move `_Handler`, `_ThreadingHTTPServerV6`, `_ASSET_DIR`, `ObservatoryServer`, and static/UI-frame transport helpers into `habitat/observatory_frontend.py`.

The frontend imports:

```python
from .observability import ObservatoryReadModel
```

and may use workspace only for existing artifact-path access and server status. It must not call workspace mutation methods.

- [ ] **Step 5: Make `habitat.observatory` a compatibility/CLI facade**

Keep CLI parsing and `main()` there. Re-export:

```python
from .observability import ObservatoryReadModel
from .observatory_frontend import ObservatoryServer
```

`start_observatory()` remains API-compatible.

- [ ] **Step 6: Verify alpha11/alpha12 cinematic + full regression and commit**

Existing frontend markup/assets/cinematic frame behavior must remain green. No visual redesign is part of this task.

---

### Task 3: Independent Disable and Headless Protocol Proof

**Files:**
- Modify: `habitat/server.py` only if a correctness gap is exposed
- Create: `tests/test_observatory_headless.py`
- Extend: `tests/test_alpha11_observatory_runtime.py` only for manifest compatibility if necessary

**Interfaces:**
- Existing CLI flag: `habitat-agent-server --no-observatory`
- Existing `serve_stdio(workspace, inp=None, out=None) -> int`
- No new protocol method or configuration store.

- [ ] **Step 1: Write RED/characterization test that `--no-observatory` never starts frontend**

Patch `HabitatWorkspace.observatory_start` to raise if called and patch `serve_stdio` to return `0`:

```python
with patch.object(HabitatWorkspace, "observatory_start", side_effect=AssertionError("frontend started")):
    with patch("habitat.server.serve_stdio", return_value=0):
        self.assertEqual(0, server.main([str(workspace_dir), "--no-observatory"]))
```

This may begin GREEN; if so, retain it as compatibility evidence and do not modify production for the sake of creating a RED.

- [ ] **Step 2: Write clean-interpreter headless import test**

Open/create a workspace, call a core read operation (`enter()`/protocol capabilities), and verify `habitat.observatory_frontend` is absent from `sys.modules` unless an Observatory API is explicitly requested.

- [ ] **Step 3: Write protocol behavior test with frontend disabled**

Run `serve_stdio()` over an in-memory request/response stream with no Observatory start and require a normal read-only protocol request to succeed. Existing public method names and MCP count remain unchanged.

- [ ] **Step 4: Implement only exposed independence defects**

If production already satisfies a test, keep the characterization test and make no gratuitous change. Any needed import must remain lazy at the explicit Observatory boundary.

- [ ] **Step 5: Verify headless + protocol/MCP/full regression and commit**

This task is complete only with machine evidence that frontend absence does not break core operation.

---

### Task 4: Descriptive Headless / Frontend Cost Evidence

**Files:**
- Create: `benchmarks/observatory_projection_costs.py`
- Create: `tests/test_observatory_costs.py`

**Interfaces:**
- `measure_observatory_costs(workspace, *, include_frontend: bool = False) -> dict`
- optional CLI accepts an existing workspace path and `--include-frontend`
- JSON fields:
  - `workspace_revision`
  - `headless_projection_wall_ms`
  - `headless_projection_bytes`
  - `frontend_start_wall_ms`
  - `frontend_health_wall_ms`
  - `frontend_included`
  - `claim_boundary`

- [ ] **Step 1: Write RED schema/missing-value tests**

With `include_frontend=False`, require:

```python
self.assertGreaterEqual(report["headless_projection_wall_ms"], 0)
self.assertGreater(report["headless_projection_bytes"], 0)
self.assertIsNone(report["frontend_start_wall_ms"])
self.assertIsNone(report["frontend_health_wall_ms"])
self.assertFalse(report["frontend_included"])
```

Require claim text to say measurements are descriptive and not evidence of reasoning/task-success superiority.

- [ ] **Step 2: Write state-neutrality test**

Take SQLite dump before and after both headless measurement and an explicitly included frontend measurement. Require exact equality.

- [ ] **Step 3: Observe RED**

Expected failure: benchmark/measurement module missing.

- [ ] **Step 4: Implement explicit measurement only**

Use `time.perf_counter_ns()` and canonical compact JSON:

```python
start = time.perf_counter_ns()
snapshot = ObservatoryReadModel(workspace).snapshot()
projection_ms = (time.perf_counter_ns() - start) / 1_000_000
projection_bytes = len(json.dumps(snapshot, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8"))
```

Only import/start `ObservatoryServer` when `include_frontend=True`; measure one `/api/health` GET, then close it. Do not persist measurements.

- [ ] **Step 5: Verify focused cost tests + full regression and commit**

Never add timing ceilings to CI; only structural/non-negative/state-neutral assertions are gating.

---

### Task 5: Observer Authority Fault Closure and Exact-Head Certification

**Files:**
- Create: `tests/test_observatory_projection_faults.py`
- Update plan/PR metadata only after production head is otherwise final.

**Interfaces:**
- Consumes Tasks 1-4 only.
- Produces machine evidence for Wave 7/master-plan exit criteria.

- [ ] **Step 1: Write fault/authority matrix**

Machine-test all of:

- server construction/start/status/GET/HEAD/stop leaves SQLite dump unchanged;
- POST/PUT/PATCH/DELETE return observer-read-only/405 and cannot mutate Store;
- direct Observability Core projection creates no new `.sqlite*`/database file;
- core import/use does not import `habitat.observatory_frontend`;
- headless agent server performs a core protocol read without frontend startup;
- legacy `habitat.observatory` imports and endpoint schemas still work;
- `observatory_assets` remain packaged source;
- descriptive cost report uses `None` for unmeasured frontend data;
- claim boundary contains no statement that cinematic rendering improves reasoning/task success.

- [ ] **Step 2: Observe RED for any remaining gap**

If all fault tests are already GREEN after Tasks 1-4, record them as closure characterization. Do not manufacture a production change.

- [ ] **Step 3: Implement only defects exposed by closure tests**

Do not weaken read-only SQLite, HTTP method rejection, privacy boundaries, source authority, or protocol compatibility to make closure green.

- [ ] **Step 4: Self-review changed-file boundary**

Every changed file must belong to Observatory projection cleanup, tests, explicit benchmark evidence, or the Wave 7 design/plan. No unrelated refactor.

- [ ] **Step 5: Exact-final-head certification**

Require on one immutable final SHA:

- Ubuntu/Windows × Python 3.10/3.14 Habitat CI SUCCESS;
- full regression SUCCESS;
- legacy compatibility/protocol/MCP SUCCESS;
- database/source-mutation recovery and fault injection SUCCESS;
- reproducible artifacts/distribution SUCCESS;
- Semgrep SUCCESS;
- CodeQL SUCCESS;
- no unresolved review threads/comments blocking correctness;
- changed-file boundary audit clean;
- branch behind `main` by zero commits immediately before merge.

- [ ] **Step 6: Exact-head merge and main verification**

Merge with `expected_head_sha=<final Wave 7 SHA>`. Fetch `main` immediately afterwards and require it equals the returned merge SHA.

**Claim boundary:** Wave 7 proves projection separation, observer-only state neutrality, frontend independence, and descriptive cost measurement. It does not prove that cinematic rendering improves reasoning quality, model capability, or task success.
