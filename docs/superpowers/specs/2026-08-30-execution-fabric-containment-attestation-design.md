# Execution Fabric Containment Attestation Design

**Status:** implementation design for Foundation Convergence Wave 6

**Source requirements:** `docs/design/FOUNDATION-CONVERGENCE.md` §9 and Foundation exit criterion requiring containment attestation that proves actual execution controls.

## Goal

Turn Habitat's existing local-process, Linux `unshare`, and Bubblewrap containment mechanisms into one fail-honest Execution Fabric whose security claims are typed, probe-bound, attached to actual execution receipts, and consumed by the public capability report. Wave 6 does **not** invent a new sandbox or claim universal hostile-code/microVM safety.

## Existing execution truth

Habitat already has real containment mechanisms, but their truth is fragmented:

- `habitat/execution.py` probes Linux `unshare -Urn`, can launch a network-contained profile, scrubs secret-bearing environment names, and applies POSIX resource limits.
- `habitat/sandbox.py` probes and launches Bubblewrap with user/pid/ipc/uts/network namespaces, a confined mount view, `--cap-drop ALL`, and `--clearenv`.
- `habitat/backends/local.py` exposes `LocalExecutionProvider` and `BubblewrapExecutionProvider`.
- `habitat/security/capabilities.py` currently reconstructs sandbox truth from aggregate capability strings. That is too weak: labels such as `full-sandbox` are declarations, not evidence.
- `ExecutionReceipt.environment_fingerprint` currently carries ad-hoc booleans, including a Bubblewrap `resource_limited=True` claim even though the Bubblewrap path invokes `run_action(..., containment_profile="trusted-local")` and therefore does not currently install the RLIMIT pre-exec hook. Wave 6 must correct that mismatch rather than preserve it.

## 1. Typed evidence kernel

Create `habitat/security/containment.py` with two frozen values.

```python
@dataclass(frozen=True)
class ProbeReceipt:
    receipt_id: str
    provider_id: str
    control: str
    mechanism: str
    attempted: bool
    success: bool
    detail: str

@dataclass(frozen=True)
class ContainmentAttestation:
    provider_id: str
    provider_version: str
    process_isolation: bool
    filesystem_isolation: bool
    network_isolation: bool
    user_isolation: bool
    capability_drop: bool
    resource_limits: bool
    secret_boundary: bool
    probe_receipts: tuple[ProbeReceipt, ...]
    claim_boundary: str
```

Supported controls are exactly:

- `process_isolation`
- `filesystem_isolation`
- `network_isolation`
- `user_isolation`
- `capability_drop`
- `resource_limits`
- `secret_boundary`

Every `True` attestation field must have at least one successful receipt for the same `provider_id` and exact control. Duplicate receipt IDs, unknown controls, `success=True` with `attempted=False`, provider mismatch, empty identities, or a `True` control without evidence fail closed.

Both values expose canonical JSON-compatible `as_dict()` data. `ContainmentAttestation.fingerprint` is SHA-256 over canonical JSON excluding no security field. This gives execution receipts and capability reports one stable causal identity.

## 2. Provider attestation contract

Extend `ExecutionProvider` with:

```python
def containment_attestation(self) -> ContainmentAttestation:
    ...
```

The base implementation is non-abstract and returns an all-false unverified attestation. This preserves compatibility for future/custom providers: a provider that has not implemented Wave 6 evidence loses claims, not functionality.

### Trusted local provider

`LocalExecutionProvider(containment_profile="trusted-local")` attests all seven controls as `False`. Running on the host is allowed under trusted policy but is not described as a sandbox.

### Network-contained local provider

The existing `unshare -Urn` probe supports only the controls it actually requests:

- `network_isolation=True` when the launch probe succeeds;
- `user_isolation=True` when the same launch probe succeeds;
- `process_isolation=False` because no PID namespace is requested;
- `filesystem_isolation=False`;
- `capability_drop=False`;
- `resource_limits=True` only when the POSIX RLIMIT enforcement probe succeeds and that enforcement is installed on the actual run;
- `secret_boundary=True` only because the actual run uses the restricted environment constructor.

The attestation must not infer any stronger control from the provider's capability strings.

### Bubblewrap provider

`BubblewrapExecutionProvider` remains fail-closed at construction when the existing minimal Bubblewrap launch cannot execute. Its attestation is built from that real probe and the execution controls used by `build_bwrap_command()`:

- user namespace;
- PID namespace;
- network namespace;
- confined mount/filesystem view;
- dropped capabilities;
- cleared environment;
- POSIX resource limits only after the Bubblewrap execution path actually installs and verifies the RLIMIT mechanism.

The claim boundary remains explicit: no Habitat custom seccomp profile is introduced, and kernel/Bubblewrap vulnerabilities are outside the proof boundary.

## 3. Resource-limit truthfulness

Refactor the private execution path so resource limits are an explicit internal execution control rather than an accidental side effect of the `network-contained` profile.

Use a strict POSIX pre-exec limiter that never increases a host hard limit and fails the child launch when a requested limit cannot be installed. Add a `resource_limit_probe()` that launches a tiny Python child under the same limiter and verifies the child observes bounded values. On platforms without `resource`, the probe is unavailable and `resource_limits=False`.

`run_action()` keeps its existing public positional compatibility and gains internal keyword-only control arguments. The network-contained profile enables resource limits automatically. `run_bwrap_action()` explicitly enables the same limiter, fixing the current false `resource_limited=True` claim.

## 4. Actual-run attestation receipt

Every execution provider binds the attestation used for that run into `ExecutionReceipt.environment_fingerprint`:

```python
{
    ... existing compatibility fields ...,
    "containment_attestation": attestation.as_dict(),
    "containment_attestation_fingerprint": attestation.fingerprint,
}
```

The legacy booleans (`sandboxed`, `network_restricted`, `filesystem_restricted`, `resource_limited`, `secret_environment_scrubbed`) remain for compatibility but are projections of the typed attestation, never independently authored truth.

For Bubblewrap, `sandboxed=True` means the attestation proves at least filesystem + network + process + user isolation and capability drop. It does not mean microVM-grade isolation.

## 5. Public capability report

Refactor `build_capability_report()` to accept a typed `ContainmentAttestation` in addition to provider metadata. `HabitatWorkspace.capability_report()` supplies `self.backend.execution_provider.containment_attestation()`.

`ExecutionCapability` preserves current public fields:

- `profile`
- `sandboxed`
- `network_restricted`
- `filesystem_restricted`
- `process_isolated`
- `verified_by`

and adds serialized `containment_attestation` plus `attestation_fingerprint`.

Arbitrary strings in `execution_provider["capabilities"]` can no longer produce a verified sandbox. Without a valid typed attestation, all containment claims are false. This is intentionally fail-closed.

## 6. Probe and fault behavior

Tests must cover:

- missing `unshare` / denied namespace probe;
- missing Bubblewrap / Bubblewrap non-zero probe;
- malformed or forged attestation evidence;
- provider ID mismatch;
- capability strings claiming sandbox without attestation;
- Bubblewrap resource-limit claim only after the limiter is actually installed;
- network-contained profile never claiming filesystem/PID isolation;
- contained execution not receiving synthetic secret environment variables;
- execution receipt fingerprint matching the exact attestation serialized into the receipt.

No probe may modify canonical project source.

## 7. Compatibility and claim boundary

- Existing source authority, mutation, approval, revision, recovery, protocol, MCP, and Learning Plane behavior remain unchanged.
- Trusted-local execution remains available and explicitly non-sandboxed.
- Existing provider discovery APIs remain available.
- Existing serialized capability-report fields remain available; only false-positive sandbox inference is removed.
- No new database or persistent truth store is introduced.
- No custom seccomp filter, VM, microVM, container daemon, or privilege broker is added.
- Presence of `bwrap`, `unshare`, a flag, or a capability label is never sufficient proof by itself; the corresponding probe must succeed.

## Verification

Each behavior-changing task follows observed RED -> minimal GREEN -> full regression. Final Wave 6 merge requires exact-head Ubuntu/Windows × Python 3.10/3.14 CI, CodeQL, public compatibility/protocol conformance, database/source recovery, fault injection, reproducible artifacts, Semgrep, review/thread audit, changed-file boundary audit, immediate `main` drift check, expected-head merge, and post-merge verification.

**Claim boundary:** Wave 6 proves that Habitat reports and receipts only the containment controls its configured execution provider has mechanically evidenced and actually applies. It does not prove immunity to kernel/runtime vulnerabilities or safe execution of arbitrary hostile code on every host.
