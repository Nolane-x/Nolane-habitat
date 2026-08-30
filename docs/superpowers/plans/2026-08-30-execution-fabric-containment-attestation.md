# Execution Fabric Containment Attestation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Habitat's execution containment claims typed, probe-bound, attached to actual execution receipts, and fail-closed instead of inferred from capability labels.

**Architecture:** Keep the existing local-process, Linux `unshare`, and Bubblewrap providers. Add one immutable containment-evidence kernel, adapt each provider to emit a truthful attestation, bind that attestation into execution receipts, and make the public capability report consume only that typed evidence. Correct the existing Bubblewrap resource-limit overclaim by applying and verifying the same strict POSIX limiter on the actual Bubblewrap launch.

**Tech Stack:** Python stdlib, frozen dataclasses, subprocess/POSIX `resource` where available, existing execution providers, unittest.

**Spec:** `docs/superpowers/specs/2026-08-30-execution-fabric-containment-attestation-design.md`

## Global Constraints

- Preserve alpha.19 public protocol/MCP/source/mutation/recovery/Learning Plane behavior.
- Keep trusted-local execution available and explicitly non-sandboxed.
- No second database, daemon, container runtime, VM, microVM, privilege broker, or custom seccomp filter.
- Capability labels or executable presence alone never prove containment.
- A `True` containment control requires successful same-provider evidence.
- Existing capability-report compatibility fields remain present.
- Bubblewrap claim boundary must continue to state that kernel/runtime vulnerabilities remain outside the proof boundary.
- RED must be observed before production implementation for each behavior-changing task.
- Final merge requires exact-head CI/CodeQL/review/thread/boundary/main-drift verification.

---

### Task 1: Immutable Containment Evidence Kernel

**Files:**
- Create: `habitat/security/containment.py`
- Modify: `habitat/security/__init__.py` only if exports are required by the existing package pattern.
- Create: `tests/test_containment_attestation.py`

**Interfaces:**
- Produces:
  - `CONTAINMENT_CONTROLS: tuple[str, ...]`
  - `ProbeReceipt`
  - `ContainmentAttestation`
  - `unverified_attestation(provider_id: str, provider_version: str, claim_boundary: str) -> ContainmentAttestation`
- Consumes: no execution-provider state.

- [ ] **Step 1: Write RED frozen-domain tests**

Require exact controls:

```python
(
    "process_isolation",
    "filesystem_isolation",
    "network_isolation",
    "user_isolation",
    "capability_drop",
    "resource_limits",
    "secret_boundary",
)
```

Require:

```python
receipt = ProbeReceipt(
    receipt_id="probe:net:1",
    provider_id="executor:fixture",
    control="network_isolation",
    mechanism="linux-unshare-user-network",
    attempted=True,
    success=True,
    detail="user+network namespace launch passed",
)
```

and frozen-instance behavior.

- [ ] **Step 2: Write RED fail-closed attestation tests**

Construct:

```python
ContainmentAttestation(
    provider_id="executor:fixture",
    provider_version="fixture-v1",
    process_isolation=False,
    filesystem_isolation=False,
    network_isolation=True,
    user_isolation=True,
    capability_drop=False,
    resource_limits=False,
    secret_boundary=False,
    probe_receipts=(network_receipt, user_receipt),
    claim_boundary="fixture only",
)
```

Tests require rejection of:
- unknown controls;
- duplicate receipt IDs;
- `success=True` with `attempted=False`;
- receipt provider mismatch;
- any `True` control without a successful same-control receipt;
- empty provider/version/receipt/mechanism/detail/claim-boundary strings.

- [ ] **Step 3: Write RED deterministic serialization/fingerprint tests**

`as_dict()` must emit tuples as JSON-compatible lists in deterministic control/receipt order. `fingerprint` must be 64 lowercase hex chars and change when any control, provider identity, receipt field, or claim boundary changes.

- [ ] **Step 4: Observe RED on exact test commit**

Run full regression. Expected failure: `habitat.security.containment` missing; no unrelated legacy failures.

- [ ] **Step 5: Implement minimal frozen kernel**

Canonical fingerprint encoding:

```python
json.dumps(
    self.as_dict(),
    sort_keys=True,
    ensure_ascii=True,
    separators=(",", ":"),
).encode("utf-8")
```

Every true field is validated against successful receipts by exact control name.

- [ ] **Step 6: Verify focused tests + full regression and commit**

---

### Task 2: Provider Attestation Adapters and Probe Truth

**Files:**
- Modify: `habitat/backends/base.py`
- Modify: `habitat/backends/local.py`
- Modify: `habitat/execution.py`
- Modify: `habitat/sandbox.py`
- Create: `tests/test_execution_provider_attestation.py`
- Extend: `tests/test_capabilities.py` only for provider construction fixtures if required.

**Interfaces:**
- Consumes Task 1 `ContainmentAttestation`, `ProbeReceipt`, `unverified_attestation`.
- Produces:

```python
ExecutionProvider.containment_attestation() -> ContainmentAttestation
resource_limit_probe() -> dict
containment_probe() -> dict  # existing API retained, richer evidence allowed
bubblewrap_probe() -> dict   # existing API retained, richer evidence allowed
```

- [ ] **Step 1: RED base-provider fail-closed contract**

A minimal custom `ExecutionProvider` subclass that does not override `containment_attestation()` must return an all-false attestation bound to its own `provider_id`, not raise and not infer from `info.capabilities`.

- [ ] **Step 2: RED trusted-local and network-contained contracts**

For trusted local require all controls false.

For a mocked successful `containment_probe()` + `resource_limit_probe()` require network-contained:

```python
process_isolation=False
filesystem_isolation=False
network_isolation=True
user_isolation=True
capability_drop=False
resource_limits=True
secret_boundary=True
```

Require corresponding successful receipts for each true control. A denied namespace probe must fail provider attestation closed for network/user controls rather than converting `network-containment` capability text into proof.

- [ ] **Step 3: RED Bubblewrap attestation contract**

Mock a successful `bubblewrap_probe()` and successful `resource_limit_probe()`. Require:

```python
process_isolation=True
filesystem_isolation=True
network_isolation=True
user_isolation=True
capability_drop=True
resource_limits=True
secret_boundary=True
```

Mock Bubblewrap unavailable/non-zero and retain constructor fail-closed behavior. No `custom_seccomp_filter=True` claim is introduced.

- [ ] **Step 4: RED POSIX resource-limit probe**

On POSIX with `resource`, `resource_limit_probe()` must launch a child through the same limiter and verify finite bounds for NOFILE, NPROC where supported, FSIZE, and CORE. On Windows/no-`resource`, it returns unavailable rather than claiming success.

- [ ] **Step 5: Observe RED**

Expected failures: missing typed provider method and missing strict resource probe. Existing trusted-local tests must remain otherwise green.

- [ ] **Step 6: GREEN provider adapters**

Add a non-abstract base method:

```python
def containment_attestation(self) -> ContainmentAttestation:
    return unverified_attestation(
        self.info.provider_id,
        self.info.kind,
        "provider has not supplied containment evidence",
    )
```

Local and Bubblewrap providers override it using exact probe results. Cache only process-local immutable probe results where current code already caches/probes; do not persist them as source truth.

- [ ] **Step 7: GREEN strict resource limiter/probe**

Replace the best-effort limiter with a helper that clamps requested soft limits to the host hard limit and raises when an enforced limit cannot be installed. `resource_limit_probe()` uses a child process and parses observed limits. Never claim a limit on unsupported Windows hosts.

- [ ] **Step 8: Verify focused provider/probe tests + full regression and commit**

---

### Task 3: Bind Actual Execution Receipts and Fix Bubblewrap Resource-Limit Overclaim

**Files:**
- Modify: `habitat/execution.py`
- Modify: `habitat/sandbox.py`
- Modify: `habitat/backends/local.py`
- Extend: `tests/test_execution.py`
- Create: `tests/test_execution_containment_receipts.py`

**Interfaces:**
- Consumes provider attestations from Task 2.
- Produces exact receipt fields:

```python
receipt.environment_fingerprint["containment_attestation"]
receipt.environment_fingerprint["containment_attestation_fingerprint"]
```

- [ ] **Step 1: RED trusted-local receipt compatibility**

Run a harmless local command. Require legacy fields remain present and truthful:

```python
sandboxed is False
network_restricted is False
filesystem_restricted is False
resource_limited is False
secret_environment_scrubbed is False
```

and require an all-false typed attestation/fingerprint matching the provider attestation.

- [ ] **Step 2: RED network-contained receipt binding**

With namespace/resource probes mocked successful and subprocess launch mocked/fixture-safe, require the actual receipt attestation to prove only network + user + resource + secret controls. It must not claim filesystem, PID, or capability-drop isolation.

- [ ] **Step 3: RED secret-boundary execution test**

Inject a synthetic environment name such as `HABITAT_API_KEY=wave6-fixture-secret`; execute a contained child that prints its environment keys. Require the synthetic secret name/value is absent from child output while a safe marker such as `HABITAT_CONTAINED_EXECUTION=1` is present for the network-contained profile.

- [ ] **Step 4: RED Bubblewrap resource truth test**

Patch the strict limiter hook and Bubblewrap command construction. Require `run_bwrap_action()` to install the limiter on the actual host launch before it may serialize `resource_limits=True`. If limiter setup is unavailable, the attestation and legacy `resource_limited` projection must be false or execution must fail closed; it may never remain an unbacked `True`.

- [ ] **Step 5: GREEN internal execution controls**

Keep existing positional signature compatibility and add keyword-only internal controls, conceptually:

```python
def run_action(
    root,
    capability,
    argv,
    timeout_s=60,
    capability_kind=None,
    containment_profile="trusted-local",
    *,
    apply_resource_limits=False,
    containment_attestation=None,
):
    ...
```

Network-contained automatically enables the limiter. Bubblewrap explicitly enables it. Legacy booleans are derived from the typed attestation rather than separately authored.

- [ ] **Step 6: GREEN provider run binding**

`LocalExecutionProvider.run()` and `BubblewrapExecutionProvider.run()` obtain their exact attestation once for the invocation and pass/bind it so the receipt fingerprint equals the serialized attestation used for that execution.

- [ ] **Step 7: Verify focused execution tests + full regression and commit**

---

### Task 4: Capability Report Consumes Attestation, Never Capability Strings

**Files:**
- Modify: `habitat/security/capabilities.py`
- Modify: `habitat/_workspace_core.py`
- Extend: `tests/test_capabilities.py`
- Extend protocol/public compatibility tests only if serialized additive fields require fixtures.

**Interfaces:**
- Consumes `ContainmentAttestation`.
- Produces:

```python
build_capability_report(
    *,
    source_authority: dict,
    execution_provider: dict,
    generated_at_revision: str,
    execution_attestation: ContainmentAttestation | None = None,
) -> CapabilityReport
```

`ExecutionCapability` keeps all existing fields and adds:

```python
containment_attestation: dict
attestation_fingerprint: str
```

- [ ] **Step 1: RED arbitrary-label rejection**

Update the old test that supplied:

```python
capabilities=[
    "full-sandbox",
    "filesystem-confinement",
    "network-confinement",
    "pid-namespace",
]
```

Without `execution_attestation`, require `sandboxed=False` and `require_capability(report, "sandboxed")` to fail closed.

- [ ] **Step 2: RED typed-attestation admission**

Pass a valid Bubblewrap-like attestation. Require legacy projections:

```python
sandboxed=True
network_restricted=True
filesystem_restricted=True
process_isolated=True
verified_by=(attestation.provider_id,)
```

and exact serialized attestation + fingerprint.

- [ ] **Step 3: RED workspace capability report wiring**

Patch the workspace execution provider's `containment_attestation()` with a typed fixture and prove `workspace.capability_report()` and `workspace.enter()["capability_report"]` expose that exact evidence. Trusted-local default remains non-sandboxed.

- [ ] **Step 4: GREEN capability projection**

Define sandboxed compatibility projection only when the typed attestation proves at least:

```python
filesystem_isolation
and network_isolation
and process_isolation
and user_isolation
and capability_drop
```

Resource limits and secret boundary remain separately visible in the nested attestation and do not get silently collapsed into the legacy sandbox boolean.

- [ ] **Step 5: Verify focused capability/CLI/protocol tests + full regression and commit**

---

### Task 5: Wave 6 Fault Closure and Exact-Head Certification

**Files:**
- Create: `tests/test_execution_fabric_faults.py`
- Update plan/PR metadata only after code head is otherwise final.

**Interfaces:**
- Consumes Tasks 1-4.
- Produces machine evidence for Wave 6 exit criteria and claim boundary.

- [ ] **Step 1: RED fault matrix**

Machine-test:
- forged successful receipt with provider mismatch rejects;
- true control with only failed receipt rejects;
- denied `unshare` produces no network/user claim;
- Bubblewrap missing/non-zero produces no provider construction;
- capability strings cannot bypass missing attestation;
- attestation fingerprint mismatch in a receipt fails a validation helper or provider binding check;
- trusted-local remains executable without acquiring sandbox claims.

- [ ] **Step 2: RED claim-boundary audit**

Assert Bubblewrap attestation/report text explicitly excludes custom Habitat seccomp and kernel/runtime vulnerability proof. Assert no Wave 6 public field contains `microvm`, `hostile_code_safe`, or equivalent universal-safety claim.

- [ ] **Step 3: GREEN certification-only gaps**

Implement only defects exposed by the fault/claim tests. Do not weaken evidence validation and do not turn missing probes into success.

- [ ] **Step 4: Exact-final-head certification**

Require:
- Ubuntu/Windows × Python 3.10/3.14 Habitat CI success;
- CodeQL success;
- full regression and legacy public protocol/MCP compatibility;
- database/source-mutation recovery and fault-injection success;
- reproducible artifacts/distribution success;
- Semgrep success;
- no unresolved review threads/comments blocking correctness;
- changed-file boundary audit;
- immediate `main` drift check;
- merge with exact expected head SHA;
- verify `main` equals returned merge SHA.

**Claim boundary:** Wave 6 proves fail-honest containment reporting and execution-receipt binding for the controls Habitat mechanically probes and actually applies. It does not prove universal hostile-code safety, kernel isolation, or microVM equivalence.
