# Nolane Habitat Security Scale and Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Habitat enforceable capability boundaries, privacy lifecycle controls, failure-recovery evidence, accessible Observatory behavior, scale budgets, and reproducible supply-chain-aware releases.

**Architecture:** Add capability and budget enforcement at authority/execution boundaries, a single redaction/privacy service before persistence or display, deterministic fault injection and SLO reporting around core operations, then platform-scale and release gates. Keep the trusted-local execution profile truthful; this plan does not relabel it as hostile-code isolation.

**Tech Stack:** Python 3.10+, SQLite/WAL, Windows/POSIX filesystem APIs, vanilla JavaScript Observatory, `unittest`, GitHub Actions, CodeQL, Semgrep, CycloneDX SBOM, setuptools.

**Spec:** `docs/superpowers/specs/2026-08-23-habitat-production-grade-evolution-design.md`

## Global Constraints

- Begin state-mutating tasks only after Truth Core Tasks 1–3 in `2026-08-23-habitat-comprehensive-hardening.md` pass.
- Default Observatory binding remains `127.0.0.1`; no Observatory HTTP route mutates workspace or agent state.
- The trusted-local execution provider reports `sandboxed=false`, `network_restricted=false`, and `filesystem_restricted=false` until a separately verified containment provider exists.
- Canonical path containment must cover traversal, symlink, Windows junction/reparse point, case folding, alternate separators, UNC paths, and race-safe final target checks.
- Secrets and agent-private state must be redacted before durable logging, Observatory serialization, export, and release artifacts.
- Every budget enforcement decision must be deterministic from recorded inputs and must emit used, remaining, and rejected-cost evidence.
- Release admission always emits a machine-readable report, including when blocked.
- Production security scans exclude intentionally vulnerable benchmark fixtures but retain an explicit separate example-fixture scan.
- WCAG 2.2 AA is the target for audited Observatory screens, including keyboard navigation and reduced motion.

---

## File and interface map

| Unit | Responsibility | Stable interface introduced here |
|---|---|---|
| `habitat/security/capabilities.py` | truthful authority/execution capability model | `CapabilityReport`, `require_capability` |
| `habitat/security/boundaries.py` | path and resource boundary enforcement | `PathBoundary`, `OperationBudget`, `BudgetLedger` |
| `habitat/security/redaction.py` | secret/private-state detection and redaction | `RedactionEngine`, `RedactionReceipt` |
| `habitat/privacy.py` | export, retention, forget, and verification | `PrivacyService`, `ForgetReport` |
| `habitat/operations/faults.py` | deterministic test-only failure points | `FaultInjector`, `FaultSpec` |
| `habitat/operations/slo.py` | SLO samples, profiles, and admission | `SloProfile`, `SloReport`, `evaluate_slos` |
| `habitat/scale.py` | generated scale fixtures and bounded metrics | `ScaleProfile`, `ScaleResult` |
| `habitat/release.py` | release manifest and promotion verdict | `ReleaseManifest`, `PromotionVerdict` |

## Task 1: Enforce truthful capability reports and a threat model

**Files:**

- Create: `habitat/security/__init__.py`
- Create: `habitat/security/capabilities.py`
- Create: `docs/security/THREAT-MODEL.md`
- Create: `docs/security/CAPABILITY-MATRIX.md`
- Modify: `habitat/backends/base.py`
- Modify: `habitat/execution.py`
- Modify: `habitat/workspace.py`
- Create: `tests/test_capabilities.py`

**Interfaces:**

- Consumes: backend/source/execution provider metadata and session bootstrap from the Intelligence plan.
- Produces: `CapabilityReport`, `ExecutionCapability`, `require_capability`, and a serialized report in manifest/orient responses. The Intelligence plan's session bootstrap consumes the same workspace report without duplicating capability logic.

- [ ] **Step 1: Write failing false-capability tests.**

```python
def test_local_execution_never_claims_unverified_sandboxing(self) -> None:
    report = self.ws.capability_report()
    execution = report["execution"]
    self.assertFalse(execution["sandboxed"])
    self.assertFalse(execution["network_restricted"])
    self.assertFalse(execution["filesystem_restricted"])
    self.assertEqual("trusted-local-process", execution["profile"])
```

- [ ] **Step 2: Run and record every current capability source.**

Run: `python -m unittest -v tests.test_capabilities`

Expected: FAIL until one typed report replaces scattered manifest dictionaries and optimistic labels.

- [ ] **Step 3: Implement the capability model.**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCapability:
    profile: str
    sandboxed: bool
    network_restricted: bool
    filesystem_restricted: bool
    process_isolated: bool
    verified_by: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityReport:
    source_authority: dict
    execution: ExecutionCapability
    mutation: dict
    observatory: dict
    generated_at_revision: str


def require_capability(report: CapabilityReport, name: str) -> None:
    values = {
        "sandboxed": report.execution.sandboxed,
        "network_restricted": report.execution.network_restricted,
        "filesystem_restricted": report.execution.filesystem_restricted,
    }
    if not values.get(name, False):
        raise PermissionError(f"required capability is not verified: {name}")
```

- [ ] **Step 4: Derive the threat model.**

Document assets, trust boundaries, entry points, unacceptable losses, attacker/error models, preventive/detective/recovery controls, control owners, residual risks, and control-failure tests. Include malicious repository content, path escape, secret exposure, local network access, unbounded provider processes, database corruption, benchmark gaming, and false sandbox claims.

- [ ] **Step 5: Add downgrade tests.**

When a provider probe fails or expires, capability state downgrades and dependent operations fail closed. Cached success cannot survive provider identity/version change.

- [ ] **Step 6: Verify and commit.**

Run: `python -m unittest -v tests.test_capabilities`

Run: `python -m habitat.cli capabilities <temporary-workspace> --json`

Commit: `git commit -m "feat(security): enforce truthful capabilities"`

## Task 2: Harden path boundaries and operation budgets

**Files:**

- Create: `habitat/security/boundaries.py`
- Modify: `habitat/source_bridge.py`
- Modify: `habitat/mutation.py`
- Modify: `habitat/backends/local.py`
- Modify: `habitat/ui/browser_provider.py`
- Modify: `habitat/runtime_twin.py`
- Create: `tests/test_path_boundaries.py`
- Create: `tests/test_operation_budgets.py`

**Interfaces:**

- Consumes: capability reports from Task 1 and atomic transactions/journals from Truth Core.
- Produces: `PathBoundary.resolve_for_read`, `resolve_for_write`, `OperationBudget`, `BudgetLedger.spend`, and `BudgetReceipt`.

- [ ] **Step 1: Write traversal, link, and race regression tests.**

```python
def test_write_rejects_symlink_that_resolves_outside_authority(self) -> None:
    outside = self.base / "outside.txt"
    outside.write_text("protected", encoding="utf-8")
    link = self.source / "escape.txt"
    self.make_link(link, outside)
    boundary = PathBoundary(self.source)
    with self.assertRaisesRegex(PermissionError, "outside authority root"):
        boundary.resolve_for_write("escape.txt")
    self.assertEqual("protected", outside.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run on Windows and Ubuntu and capture platform-specific failures.**

- [ ] **Step 3: Implement canonical boundary resolution.**

```python
class PathBoundary:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)

    def resolve_for_read(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve(strict=True)
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError("path resolves outside authority root")
        return candidate

    def resolve_for_write(self, relative: str) -> Path:
        parent = (self.root / relative).parent.resolve(strict=True)
        if parent != self.root and self.root not in parent.parents:
            raise PermissionError("write parent resolves outside authority root")
        return parent / Path(relative).name
```

Before final replace, revalidate the parent and target identity using platform file metadata to detect link/reparse substitution between preparation and commit.

- [ ] **Step 4: Implement atomic budget spending.**

```python
@dataclass(frozen=True)
class OperationBudget:
    max_bytes: int
    max_items: int
    max_duration_ms: int


@dataclass(frozen=True)
class BudgetReceipt:
    category: str
    spent_bytes: int
    spent_items: int
    spent_duration_ms: int
    remaining_bytes: int
    remaining_items: int
    remaining_duration_ms: int


class BudgetLedger:
    def __init__(self, budget: OperationBudget) -> None:
        self.remaining_bytes = budget.max_bytes
        self.remaining_items = budget.max_items
        self.remaining_duration_ms = budget.max_duration_ms

    def spend(
        self,
        category: str,
        *,
        bytes_: int = 0,
        items: int = 0,
        duration_ms: int = 0,
    ) -> BudgetReceipt:
        if bytes_ < 0 or items < 0 or duration_ms < 0:
            raise ValueError("budget spend cannot be negative")
        if (
            bytes_ > self.remaining_bytes
            or items > self.remaining_items
            or duration_ms > self.remaining_duration_ms
        ):
            raise RuntimeError(f"operation budget exceeded: {category}")
        self.remaining_bytes -= bytes_
        self.remaining_items -= items
        self.remaining_duration_ms -= duration_ms
        return BudgetReceipt(
            category,
            bytes_,
            items,
            duration_ms,
            self.remaining_bytes,
            self.remaining_items,
            self.remaining_duration_ms,
        )
```

- [ ] **Step 5: Apply budgets.**

Enforce bytes/items/duration at source enumeration, hashing, compiler input, context paging, runtime ingestion, browser frames, screenshots, event rings, retries, and evolution trials. Rejected work emits a bounded receipt without persisting rejected payload bytes.

- [ ] **Step 6: Add boundary and exhaustion coverage.**

Cover `..`, mixed separators, absolute paths, case variants, UNC/device paths, junctions, symlinks, deleted/recreated parents, hard links where supported, zero budget, exact budget, concurrent spend, retry exhaustion, and close cleanup.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_path_boundaries tests.test_operation_budgets`

Commit: `git commit -m "fix(security): enforce path and resource boundaries"`

## Task 3: Add secret redaction and a verifiable privacy lifecycle

**Files:**

- Create: `habitat/security/redaction.py`
- Create: `habitat/privacy.py`
- Modify: `habitat/storage.py`
- Modify: `habitat/observatory.py`
- Modify: `habitat/protocol.py`
- Modify: `habitat/context/compiler.py`
- Modify: `habitat/retention.py`
- Create: `tests/test_redaction.py`
- Create: `tests/test_privacy_lifecycle.py`
- Create: `docs/security/PRIVACY.md`

**Interfaces:**

- Consumes: provenance, memory lifecycle, path boundaries, and operation budgets.
- Produces: `RedactionEngine.redact`, `RedactionReceipt`, `PrivacyService.export`, `forget`, `verify_forgotten`, and `ForgetReport`.

- [ ] **Step 1: Write failing persistence/display leak tests.**

```python
def test_secret_is_redacted_before_storage_and_observatory(self) -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    event = self.ws.runtime_ingest({"kind": "log", "message": f"token={secret}"})
    self.assertNotIn(secret, json.dumps(event))
    snapshot = self.ws.observatory_snapshot()
    self.assertNotIn(secret, json.dumps(snapshot))
    raw = self.ws.store.conn.execute(
        "SELECT attributes_json FROM runtime_events ORDER BY started_at DESC LIMIT 1"
    ).fetchone()[0]
    self.assertNotIn(secret, raw)
```

- [ ] **Step 2: Run and identify each persistence/display boundary.**

- [ ] **Step 3: Implement deterministic redaction.**

```python
import hashlib
import json
import re


@dataclass(frozen=True)
class RedactionReceipt:
    rule_ids: tuple[str, ...]
    replacements: int
    input_digest: str
    output_digest: str


class RedactionEngine:
    RULES = (
        ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
        ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
        ("credential-field", re.compile(r"(?i)(password|secret|token)\s*[:=]\s*[^\s,;]+")),
    )

    def redact(self, value: object) -> tuple[object, RedactionReceipt]:
        input_bytes = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        rule_ids: set[str] = set()
        replacements = 0

        def visit(item: object) -> object:
            nonlocal replacements
            if isinstance(item, dict):
                return {str(key): visit(child) for key, child in item.items()}
            if isinstance(item, list):
                return [visit(child) for child in item]
            if isinstance(item, tuple):
                return tuple(visit(child) for child in item)
            if not isinstance(item, str):
                return item
            result = item
            for rule_id, pattern in self.RULES:
                result, count = pattern.subn(f"[REDACTED:{rule_id}]", result)
                if count:
                    rule_ids.add(rule_id)
                    replacements += count
            return result

        output = visit(value)
        output_bytes = json.dumps(output, sort_keys=True, default=str).encode("utf-8")
        return output, RedactionReceipt(
            rule_ids=tuple(sorted(rule_ids)),
            replacements=replacements,
            input_digest=hashlib.sha256(input_bytes).hexdigest(),
            output_digest=hashlib.sha256(output_bytes).hexdigest(),
        )
```

Rules cover common token/key/password/private-key patterns, declared project secret paths, agent-private fields, and high-entropy values with conservative evidence. Redaction stores rule IDs and digests, never the original secret.

- [ ] **Step 4: Route all outward/durable surfaces through redaction.**

Apply before runtime/event/log persistence, context serialization, project memory, Observatory snapshots/SSE, protocol errors, exports, diagnostics, benchmark artifacts, and release reports. Source-authority exact reads remain exact and authorized; they are not copied into logs or Observatory.

- [ ] **Step 5: Implement export and forget.**

`PrivacyService.export(scope, agent_id)` emits a manifest of included tables/objects and redaction receipts. `forget` covers primary rows, dependent rows, FTS/search documents, compile/project caches, journals, temporary overlays, retained Observatory frames, migration backups selected by explicit policy, and exported artifacts registered in the workspace ledger.

- [ ] **Step 6: Verify deletion.**

`verify_forgotten` scans declared storage surfaces for object IDs and secret digests, runs SQLite foreign-key/integrity checks, and reports externally copied artifacts that Habitat cannot delete automatically.

- [ ] **Step 7: Add adversarial tests.**

Cover split secrets, nested JSON, encoded values, false-positive-like ordinary identifiers, agent-private memory, export/reimport, forget/reopen, backup retention, FTS remnants, crash mid-forget, and idempotent rerun.

- [ ] **Step 8: Verify and commit.**

Run: `python -m unittest -v tests.test_redaction tests.test_privacy_lifecycle`

Commit: `git commit -m "feat(privacy): add redaction export and forget proof"`

## Task 4: Create deterministic fault injection and SLO admission

**Files:**

- Create: `habitat/operations/__init__.py`
- Create: `habitat/operations/faults.py`
- Create: `habitat/operations/slo.py`
- Modify: `habitat/workspace.py`
- Modify: `habitat/storage.py`
- Modify: `habitat/source_bridge.py`
- Modify: `habitat/mutation.py`
- Create: `tests/test_fault_injection.py`
- Create: `tests/test_slo_admission.py`
- Create: `tools/run_reliability_suite.py`

**Interfaces:**

- Consumes: Truth Core transaction/recovery boundaries and budget receipts from Task 2.
- Produces: `FaultSpec`, `FaultInjector.hit`, `SloSample`, `SloProfile`, `SloReport`, and `evaluate_slos`.

- [ ] **Step 1: Write failing atomicity and report-always tests.**

```python
def test_fault_after_revision_insert_recovers_to_one_complete_state(self) -> None:
    injector = FaultInjector({"refresh.after_revision_insert": 1})
    before = self.snapshot_truth(self.ws)
    with self.assertRaisesRegex(RuntimeError, "injected fault"):
        self.ws.refresh("fault-suite", fault_injector=injector)
    reopened = HabitatWorkspace(self.habitat)
    self.addCleanup(reopened.close)
    after = self.snapshot_truth(reopened)
    self.assertEqual(before, after)
```

- [ ] **Step 2: Run and confirm no typed fault interface/report exists.**

- [ ] **Step 3: Implement test-only injection.**

```python
@dataclass(frozen=True)
class FaultSpec:
    point: str
    occurrence: int
    exception_type: str = "RuntimeError"


class FaultInjector:
    def __init__(self, schedule: dict[str, int] | None = None) -> None:
        self.schedule = dict(schedule or {})
        self.counts: dict[str, int] = {}

    def hit(self, point: str) -> None:
        self.counts[point] = self.counts.get(point, 0) + 1
        if self.schedule.get(point) == self.counts[point]:
            raise RuntimeError(f"injected fault: {point}")
```

Production constructors receive a no-op injector by default. Environment variables cannot activate faults in packaged runtime code.

- [ ] **Step 4: Instrument critical points.**

Cover migration backup/DDL/version update, refresh upsert/relations/revision/events/fingerprint/commit, source journal prepare/replace/cleanup, mutation apply/rollback/recovery, privacy forget, MCP initialize/close, provider start/stop, and Observatory snapshot/SSE.

- [ ] **Step 5: Implement SLO evaluation.**

```python
import statistics


@dataclass(frozen=True)
class SloSample:
    scenario_id: str
    completed: bool
    latency_ms: float
    peak_memory_bytes: int
    baseline_latency_ms: float
    baseline_peak_memory_bytes: int
    error: str | None = None


@dataclass(frozen=True)
class SloProfile:
    profile_id: str
    required_success_ratio: float
    max_median_regression: float
    max_peak_memory_regression: float
    required_cycles: int


@dataclass(frozen=True)
class SloReport:
    profile_id: str
    admitted: bool
    total: int
    completed: int
    median_latency_regression: float
    peak_memory_regression: float
    failures: tuple[str, ...]

    @classmethod
    def from_samples(
        cls,
        profile: SloProfile,
        samples: tuple[SloSample, ...],
        *,
        admitted: bool,
    ) -> "SloReport":
        return cls(
            profile_id=profile.profile_id,
            admitted=admitted and len(samples) >= profile.required_cycles,
            total=len(samples),
            completed=sum(sample.completed for sample in samples),
            median_latency_regression=_ratio_regression(
                statistics.median(sample.latency_ms for sample in samples),
                statistics.median(sample.baseline_latency_ms for sample in samples),
            ),
            peak_memory_regression=_ratio_regression(
                max(sample.peak_memory_bytes for sample in samples),
                max(sample.baseline_peak_memory_bytes for sample in samples),
            ),
            failures=tuple(
                f"{sample.scenario_id}: {sample.error}"
                for sample in samples
                if not sample.completed
            ),
        )


def _ratio_regression(current: float, baseline: float) -> float:
    return (current / baseline) - 1.0 if baseline else float(current > 0)


def evaluate_slos(profile: SloProfile, samples: tuple[SloSample, ...]) -> SloReport:
    completed = [sample for sample in samples if sample.completed]
    ratio = len(completed) / len(samples) if samples else 0.0
    if not samples:
        return SloReport(
            profile.profile_id, False, 0, 0, 1.0, 1.0, ("no SLO samples",)
        )
    latency_regression = _ratio_regression(
        statistics.median(sample.latency_ms for sample in samples),
        statistics.median(sample.baseline_latency_ms for sample in samples),
    )
    memory_regression = _ratio_regression(
        max(sample.peak_memory_bytes for sample in samples),
        max(sample.baseline_peak_memory_bytes for sample in samples),
    )
    admitted = (
        ratio >= profile.required_success_ratio
        and latency_regression <= profile.max_median_regression
        and memory_regression <= profile.max_peak_memory_regression
    )
    return SloReport.from_samples(profile, samples, admitted=admitted)
```

- [ ] **Step 6: Make reports unconditional.**

`run_reliability_suite.py` writes a partial report atomically after each scenario and a final verdict on success, test failure, timeout, infrastructure error, or keyboard interruption.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_fault_injection tests.test_slo_admission`

Run: `python tools/run_reliability_suite.py --profile local-1k --out .test-artifacts/reliability.json`

Commit: `git commit -m "test(reliability): add fault and SLO admission"`

## Task 5: Make Observatory accessible, bounded, and reconnect-safe

**Files:**

- Modify: `habitat/observatory.py`
- Modify: `habitat/observatory_read_model.py`
- Modify: `habitat/observatory_assets/app.js`
- Modify: `habitat/observatory_assets/style.css`
- Create: `tests/test_observatory_accessibility.py`
- Create: `tests/test_observatory_sse.py`
- Create: `tests/fixtures/observatory/`
- Create: `docs/OBSERVATORY.md`

**Interfaces:**

- Consumes: consistent read model from Comprehensive Hardening Task 7, redaction from Task 3, and SLO samples from Task 4.
- Produces: versioned `habitat.observatory.snapshot.v2` projections, resumable sequence receipts, accessibility fixture reports, and bounded level-of-detail state.

- [ ] **Step 1: Write failing keyboard, reduced-motion, and resume tests.**

```python
def test_sse_resume_returns_every_retained_event_after_last_id(self) -> None:
    server = self.start_observatory(ring_size=8)
    emitted = [server.emit("activity", {"n": n}) for n in range(5)]
    resumed = server.resume(last_event_id=emitted[1]["id"])
    self.assertEqual(
        [item["id"] for item in emitted[2:]],
        [item["id"] for item in resumed],
    )
```

- [ ] **Step 2: Capture current DOM/accessibility fixtures and failure behavior.**

- [ ] **Step 3: Enforce resumable transport.**

The ring stores monotonically increasing IDs and revision bindings. Resume within the ring returns the exact suffix. Resume outside the ring emits one typed `snapshot-required` event. Duplicate IDs and cross-workspace IDs are rejected.

- [ ] **Step 4: Add adaptive level of detail.**

Bound DOM nodes, edges, frames, activity rows, and animation work per view. Aggregate distant/low-relevance objects and page exact details on selection. No snapshot may copy raw source bodies or private memory into the browser.

- [ ] **Step 5: Meet accessibility contracts.**

Add landmarks, meaningful headings, accessible names/roles, keyboard focus order, visible focus, non-color status cues, live-region updates for connection state, contrast tokens, zoom-safe layout, and `prefers-reduced-motion` behavior that removes cinematic motion while retaining state changes.

- [ ] **Step 6: Test browser-visible behavior.**

Use the frontend testing/debugging workflow during implementation. Test 320px, 768px, 1440px, 200% zoom, keyboard-only navigation, reduced motion, reconnect, snapshot-required, malformed event, provider-degraded, empty workspace, and 10,000-object bounded views.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_observatory_accessibility tests.test_observatory_sse`

Run: `node --check habitat/observatory_assets/app.js`

Commit: `git commit -m "feat(observatory): add accessible bounded resilience"`

## Task 6: Define scale profiles and incremental performance budgets

**Files:**

- Create: `habitat/scale.py`
- Create: `benchmarks/generate_scale_project.py`
- Create: `benchmarks/run_scale_profile.py`
- Create: `benchmarks/profiles/local-1k.json`
- Create: `benchmarks/profiles/local-10k.json`
- Create: `tests/test_scale_profiles.py`
- Modify: `tools/check_performance_budget.py`

**Interfaces:**

- Consumes: SLO report types and operation budgets from Tasks 2 and 4.
- Produces: `ScaleProfile`, `ScaleResult`, deterministic project generators, and platform baseline artifacts.

- [ ] **Step 1: Write failing deterministic-generation tests.**

```python
def test_same_profile_seed_produces_same_project_manifest(self) -> None:
    profile = ScaleProfile("local-1k", files=1000, mean_bytes=1024, seed=20260823)
    first = generate_project(self.temp / "first", profile)
    second = generate_project(self.temp / "second", profile)
    self.assertEqual(first.manifest_hash, second.manifest_hash)
```

- [ ] **Step 2: Run and verify scale interfaces are absent.**

- [ ] **Step 3: Implement profiles.**

```python
import hashlib
import json
import random
from pathlib import Path


@dataclass(frozen=True)
class ScaleProfile:
    profile_id: str
    files: int
    mean_bytes: int
    seed: int
    languages: tuple[str, ...] = ("python", "javascript", "css", "markdown")


@dataclass(frozen=True)
class ScaleResult:
    profile_id: str
    manifest_hash: str
    cold_ingest_ms: float
    warm_refresh_ms: float
    targeted_refresh_ms: float
    peak_memory_bytes: int
    compiled_files: int
    authority_bytes_read: int


@dataclass(frozen=True)
class GeneratedProject:
    root: Path
    manifest_hash: str


def build_scale_manifest(profile: ScaleProfile) -> dict:
    rng = random.Random(profile.seed)
    files = []
    for index in range(profile.files):
        language = profile.languages[index % len(profile.languages)]
        suffix = {
            "python": ".py",
            "javascript": ".js",
            "css": ".css",
            "markdown": ".md",
        }[language]
        token = rng.randrange(1_000_000_000)
        files.append({
            "path": f"src/{language}/file_{index:05d}{suffix}",
            "language": language,
            "token": token,
            "target_bytes": profile.mean_bytes,
        })
    return {"profile_id": profile.profile_id, "seed": profile.seed, "files": files}


def materialize_scale_manifest(root: Path, manifest: dict) -> None:
    for item in manifest["files"]:
        path = root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        line = f"fixture {item['language']} {item['token']}\n"
        repeats = max(1, item["target_bytes"] // len(line.encode("utf-8")))
        path.write_text(line * repeats, encoding="utf-8")


def generate_project(root: Path, profile: ScaleProfile) -> GeneratedProject:
    manifest = build_scale_manifest(profile)
    materialize_scale_manifest(root, manifest)
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return GeneratedProject(root=root, manifest_hash=digest)
```

- [ ] **Step 4: Generate realistic topology.**

Projects contain bounded import graphs, tests, configs, CSS selectors, Markdown links, long files, minified files, ignored/generated paths, rename/delete variants, and controlled dependency fan-out. Generation uses the seed and writes a manifest hash.

- [ ] **Step 5: Enforce incremental invariants.**

Warm unchanged refresh compiles zero files and writes no revision. One-file targeted refresh considers the changed file plus declared semantic dependents. Context stays within budget. Observatory projection remains bounded. Resource counts return to baseline after close.

- [ ] **Step 6: Establish platform baselines.**

Run local-1k on every pull request and local-10k nightly on Windows, Ubuntu, and macOS. Store median/p95 latency, peak memory, authority bytes, compiled files, database size, and handle/process deltas. Reject more than 20% median or peak-memory regression without an accepted performance record.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_scale_profiles`

Run: `python benchmarks/run_scale_profile.py --profile benchmarks/profiles/local-1k.json --out .test-artifacts/scale-local-1k.json`

Commit: `git commit -m "perf: add deterministic Habitat scale profiles"`

## Task 7: Produce reproducible packages, SBOMs, and provenance

**Files:**

- Create: `constraints/release.txt`
- Create: `tools/build_release.py`
- Create: `tools/verify_release_artifacts.py`
- Create: `tests/test_release_artifacts.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/codeql.yml`
- Create: `.github/workflows/release-candidate.yml`
- Create: `docs/RELEASE.md`

**Interfaces:**

- Consumes: quality, benchmark, privacy, fault, SLO, scale, and evolution reports.
- Produces: wheel/sdist, CycloneDX SBOM, checksums, provenance JSON, plugin archive, and verification verdict.

- [ ] **Step 1: Write failing artifact completeness tests.**

```python
def test_release_manifest_hashes_every_distributed_artifact(self) -> None:
    manifest = json.loads((self.dist / "release-manifest.json").read_text())
    distributed = {
        path.name for path in self.dist.iterdir()
        if path.is_file() and path.name != "release-manifest.json"
    }
    self.assertEqual(distributed, set(manifest["sha256"]))
    for name, digest in manifest["sha256"].items():
        self.assertEqual(digest, sha256_file(self.dist / name))
```

- [ ] **Step 2: Run and verify the current packaging flow lacks the full manifest.**

- [ ] **Step 3: Implement deterministic build orchestration.**

Set `SOURCE_DATE_EPOCH` from the audited commit timestamp, build wheel and sdist from a clean checkout, normalize generated manifest ordering, package plugin files from the same commit, and refuse dirty tracked changes.

- [ ] **Step 4: Generate supply-chain evidence.**

Create CycloneDX SBOMs for runtime and each optional extra, record exact Python/build tool versions, dependency constraints, source commit, tag, platform, workflow identity, artifact hashes, test/scan/benchmark report hashes, and known residual risks.

- [ ] **Step 5: Rebuild and compare.**

Build twice in fresh equivalent environments. Require identical wheel/plugin hashes; if sdist metadata prevents identical bytes, require identical normalized archive member names, modes, content hashes, and provenance with the variance explicitly recorded.

- [ ] **Step 6: Add installation smoke tests.**

Install the wheel into fresh Python 3.10 and 3.14 environments on Windows and Ubuntu. Run CLI help, create/orient/close, MCP initialize/list, plugin validation, database doctor, and package metadata identity.

- [ ] **Step 7: Verify and commit.**

Run: `python -m unittest -v tests.test_release_artifacts`

Run: `python tools/build_release.py --out dist`

Run: `python tools/verify_release_artifacts.py dist/release-manifest.json`

Commit: `git commit -m "release: add reproducible artifacts and SBOM"`

## Task 8: Add canary promotion, rollback, and incident evidence

**Files:**

- Create: `habitat/release.py`
- Create: `tools/promote_release.py`
- Create: `tests/test_release_promotion.py`
- Create: `docs/runbooks/DATABASE-RECOVERY.md`
- Create: `docs/runbooks/MCP-LIFECYCLE.md`
- Create: `docs/runbooks/OBSERVATORY-DEGRADED.md`
- Create: `docs/runbooks/PRIVACY-INCIDENT.md`
- Modify: `tools/release_check.py`
- Modify: `CHANGELOG.md`

**Interfaces:**

- Consumes: release artifacts from Task 7 and every admission report produced by the three plan files.
- Produces: `ReleaseManifest`, `PromotionVerdict`, `evaluate_promotion`, canary receipts, rollback bundle, and incident runbooks.

- [ ] **Step 1: Write failing missing-evidence and rollback tests.**

```python
def test_promotion_blocks_when_truth_core_evidence_is_missing(self) -> None:
    manifest = self.make_manifest(reports={"semantic": "hash-a"})
    verdict = evaluate_promotion(manifest, target="beta-candidate")
    self.assertFalse(verdict.admitted)
    self.assertIn("truth-core", verdict.missing_reports)
```

- [ ] **Step 2: Run and verify no promotion model exists.**

- [ ] **Step 3: Implement promotion gates.**

```python
@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit: str
    reports: dict[str, str]
    artifact_hashes: dict[str, str]
    residual_risks: tuple[str, ...]


@dataclass(frozen=True)
class PromotionVerdict:
    target: str
    admitted: bool
    missing_reports: tuple[str, ...]
    failed_gates: tuple[str, ...]
    residual_risks: tuple[str, ...]


REQUIRED_REPORTS = {
    "alpha-candidate": frozenset({"truth-core", "matrix", "faults", "artifacts"}),
    "beta-readiness": frozenset({"semantic", "context", "memory", "privacy"}),
    "beta-candidate": frozenset({"coordination", "mcp-soak", "observatory", "scale"}),
    "production-candidate": frozenset({"security", "slo", "sbom", "reproducibility"}),
}


def evaluate_promotion(manifest: ReleaseManifest, target: str) -> PromotionVerdict:
    required = REQUIRED_REPORTS[target]
    missing = tuple(sorted(required - manifest.reports.keys()))
    failed = tuple(sorted(
        name for name, digest in manifest.reports.items()
        if name in required and not digest
    ))
    return PromotionVerdict(
        target=target,
        admitted=not missing and not failed,
        missing_reports=missing,
        failed_gates=failed,
        residual_risks=manifest.residual_risks,
    )
```

- [ ] **Step 4: Add canary workspace migration.**

Copy a declared set of anonymized/synthetic legacy workspaces, run read-only doctor, migration backup, upgrade, integrity checks, orient/context/search, governed no-op mutation, close/reopen, and downgrade/restore validation. Hash every input and report.

- [ ] **Step 5: Build rollback bundles.**

Bundle previous verified package/plugin hashes, migration backups, compatibility notes, restore commands, and verification steps. Rollback never pretends a newer database is readable by an older binary unless the compatibility test proved it.

- [ ] **Step 6: Create incident runbooks.**

Each runbook contains detection signals, immediate containment, evidence preservation, safe diagnostics, recovery, validation, user-visible communication fields, residual risk, and conditions requiring release withdrawal.

- [ ] **Step 7: Make blocked releases visible.**

`promote_release.py` always writes `promotion-verdict.json`. It never tags, publishes, or uploads when `admitted=false`. External publication remains a separate explicitly authorized action.

- [ ] **Step 8: Verify and commit.**

Run: `python -m unittest -v tests.test_release_promotion`

Run: `python tools/promote_release.py --manifest dist/release-manifest.json --target alpha-candidate --dry-run --out .test-artifacts/promotion-verdict.json`

Commit: `git commit -m "release: add canary promotion and rollback evidence"`

---

## Final verification

- [ ] Run capability, boundary, budget, redaction, and privacy tests on Windows and Ubuntu.
- [ ] Run every deterministic fault point and confirm complete-old or complete-new recovery.
- [ ] Run 100 workspace and MCP lifecycle cycles with no increasing resource trend.
- [ ] Run Observatory accessibility, SSE, malformed-event, reconnect, reduced-motion, and bounded-LOD tests.
- [ ] Run local-1k on pull requests and local-10k on the three supported desktop platforms.
- [ ] Run CodeQL for Python/JavaScript and Semgrep with production/example findings separated.
- [ ] Build twice, verify artifact/SBOM/provenance hashes, and install smoke-test fresh wheels.
- [ ] Run canary migration/restore fixtures and emit promotion verdict.
- [ ] Confirm no command publishes externally during dry-run or when admission is blocked.

## Completion definition

This plan is complete when Habitat enforces truthful capabilities and path/resource boundaries, proves privacy deletion and failure recovery, keeps Observatory accessible and bounded, meets declared scale/SLO profiles, produces verifiable artifacts and SBOMs, and blocks promotion whenever evidence or rollback safety is missing.
