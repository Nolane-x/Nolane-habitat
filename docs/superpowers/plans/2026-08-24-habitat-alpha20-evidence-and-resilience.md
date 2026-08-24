# Nolane Habitat Alpha.20+ Evidence, Resilience, and Trust Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the next Habitat candidate easier to trust by removing dynamic SQL ambiguity, continuously proving CI supply-chain integrity, supervising semantic-provider lifecycles, proving database recovery under contention, enforcing protocol compatibility and privacy boundaries, and producing independently reviewable release evidence.

**Architecture:** Keep the public MCP and CLI envelopes unchanged. Place SQL identifier validation in one small module, make each CI scanner emit a hashable report, and make provider cleanup testable through the existing runtime lifecycle boundary. Add a small set of deterministic, isolated test harnesses for SQLite recovery, wire contracts, redaction, resource limits, and distribution contents. Promotion remains an evidence decision: CI success is necessary, but not sufficient for a public tag or release.

**Tech Stack:** Python 3.10+, SQLite, `unittest`, GitHub Actions, CodeQL, Semgrep, JSON evidence manifests, vanilla JavaScript Observatory.

**Spec:** `docs/superpowers/specs/2026-08-23-habitat-production-grade-evolution-design.md`

## Global Constraints

- Preserve `habitat.agent.v1alpha2`, existing MCP tool names, JSON field names, CLI entry points, and Observatory read-only behavior.
- Support Ubuntu and Windows on Python 3.10 and 3.14; every new behavior has a platform-neutral regression test and runs in the four-way CI matrix.
- SQL values always use SQLite placeholders. A dynamic SQLite identifier is accepted only after membership in a module-local immutable allow-list.
- Do not infer release admission from a green check. A candidate needs hash-bound evidence, an independent review record, and a dry-run verdict before any tag or GitHub release action.
- Keep scanner artifacts under `.test-artifacts/` and do not commit generated reports, manifests, or downloaded CI artifacts.
- Pin every `uses:` entry in a workflow to a 40-character commit SHA and retain a human-readable major-version comment.
- A provider timeout or close must not leave an owned process alive; an unavailable provider must be reported as unavailable rather than represented as a successful semantic result.
- User-facing README copy names only shipped, verified behavior. Engineering boundaries and residual risks stay in versioned docs and release evidence.

---

## File and interface map

| Unit | Responsibility | Interface introduced or strengthened |
|---|---|---|
| `habitat/sql_safety.py` | safe composition of SQLite identifiers and placeholder groups | `quote_identifier`, `placeholder_group` |
| `habitat/storage.py` | Store query construction through allow-listed identifiers | `Store.save_json`, `Store.load_json`, evidence and feedback selectors |
| `habitat/storage_migrations.py` | migration DDL through immutable schema metadata | `schema_identifier` |
| `habitat/retention.py` | retention cleanup using static table metadata | `apply` |
| `tools/run_semgrep.py` | deterministic scanner invocation and report normalization | `main(argv) -> int` |
| `tools/quality_gate.py` | require a current scanner report when configured | `collect_quality_evidence` |
| `habitat/runtime_lifecycle.py` | report and close every registered semantic runtime | `shutdown_runtime_services`, `runtime_service_status` |
| `habitat/release.py` | require reviewer and scanner bindings for promotion | `ReleaseManifest`, `evaluate_promotion` |
| `tools/build_release_manifest.py` | build a manifest from local, hashable evidence files | `main(argv) -> int` |
| `tools/run_db_recovery_suite.py` | prove lock, rollback, reopen, and integrity behavior | `main(argv) -> int` |
| `tests/test_mcp_contracts.py` | protect public tool envelope compatibility | versioned request/response fixtures |
| `habitat/redaction.py` | remove source and secret-bearing values from exported evidence | `redact_for_export(value) -> value` |
| `tools/verify_distribution.py` | attest package contents and generated provenance | `main(argv) -> int` |
| `habitat/authorization.py` | make every active capability explicit, bounded, and auditable | `authorize_operation(request, policy) -> Decision` |
| `tools/run_upgrade_recovery_suite.py` | prove upgrade, restore, and downgrade safety from fixtures | `main(argv) -> int` |
| `tools/run_scale_suite.py` | measure bounded behavior on a deterministic project corpus | `main(argv) -> int` |
| `tools/verify_provenance.py` | verify that a release receipt binds source, CI, evidence, and artifacts | `main(argv) -> int` |
| `habitat/activity_integrity.py` | canonical, redacted hash-chain records for durable activity and checkpoints | `append_activity_record`, `verify_activity_chain` |
| `tools/run_mutation_recovery_suite.py` | exercise source-mutation journal recovery at each crash boundary | `main(argv) -> int` |
| `tools/run_protocol_conformance_suite.py` | replay valid and hostile MCP/CLI fixtures without external services | `main(argv) -> int` |
| `tools/run_semantic_conformance_suite.py` | compare provider-labelled semantic answers to a synthetic truth corpus | `main(argv) -> int` |
| `tools/run_observatory_budget_suite.py` | prove bounded, redacted, monotonic Observatory read projections | `main(argv) -> int` |
| `tools/verify_reproducible_build.py` | compare two clean local builds from one immutable candidate | `main(argv) -> int` |

## Task 1: Introduce a tested SQLite identifier boundary — delivered in Alpha.19 candidate

**Files:**

- Create: `habitat/sql_safety.py`
- Modify: `habitat/storage.py`
- Modify: `habitat/storage_migrations.py`
- Modify: `habitat/retention.py`
- Create: `tests/test_sql_safety.py`

**Interfaces:**

- Consumes: immutable table and column names owned by `Store`, migration metadata, and retention specs.
- Produces: `quote_identifier(value: str, allowed: frozenset[str]) -> str` and `placeholder_group(count: int) -> str`.

- [ ] **Step 1: Write the failing identifier and placeholder tests.**

```python
from habitat.sql_safety import placeholder_group, quote_identifier


def test_quote_identifier_accepts_only_allow_list_members(self):
    allowed = frozenset({"sessions", "runs"})
    self.assertEqual('"sessions"', quote_identifier("sessions", allowed))
    with self.assertRaisesRegex(ValueError, "unsupported SQLite identifier"):
        quote_identifier("sessions; DROP TABLE files;--", allowed)


def test_placeholder_group_has_one_placeholder_per_value(self):
    self.assertEqual("?", placeholder_group(1))
    self.assertEqual("?,?,?", placeholder_group(3))
    with self.assertRaisesRegex(ValueError, "positive"):
        placeholder_group(0)
```

- [ ] **Step 2: Run the test to verify the boundary is absent.**

Run: `python -m unittest -v tests.test_sql_safety`

Expected: FAIL with `ModuleNotFoundError: No module named 'habitat.sql_safety'`.

- [ ] **Step 3: Implement the minimal boundary.**

```python
from __future__ import annotations

import re


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(value: str, allowed: frozenset[str]) -> str:
    if value not in allowed or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"unsupported SQLite identifier: {value!r}")
    return f'"{value}"'


def placeholder_group(count: int) -> str:
    if count < 1:
        raise ValueError("placeholder count must be positive")
    return ",".join("?" for _ in range(count))
```

- [ ] **Step 4: Move every formatted identifier in the listed storage modules behind the boundary.**

Use immutable `frozenset` declarations beside the data they protect. For example, `Store.save_json` and `Store.load_json` pass `_JSON_TABLES` to `quote_identifier`; `active_evidence_ids`, `resolve_evidence`, `context_utility_for`, and `agent_context_utility_for` use `placeholder_group(len(values))` only after returning early for empty lists. `repair_additive_columns` validates table and column names against `_ADDITIVE_COLUMNS` before composing its `ALTER TABLE` statement. Retention keeps its table map immutable and validates before composing `DELETE`.

- [ ] **Step 5: Add an integration test against a temporary database.**

```python
def test_store_rejects_untrusted_json_table_without_executing_sql(self):
    with tempfile.TemporaryDirectory() as td:
        store = Store(Path(td) / "habitat.sqlite3")
        self.addCleanup(store.close)
        with self.assertRaisesRegex(ValueError, "unsupported JSON table"):
            store.save_json("sessions; DROP TABLE files;--", "x", {"ok": True})
        self.assertIsNotNone(store.conn.execute("SELECT name FROM sqlite_master WHERE name='files'").fetchone())
```

- [ ] **Step 6: Verify and commit the isolated change.**

Run: `python -m unittest -v tests.test_sql_safety tests.test_storage tests.test_storage_migrations`

Run: `semgrep scan --config p/default --exclude .venv --exclude .git habitat`

Commit:

```powershell
git add habitat/sql_safety.py habitat/storage.py habitat/storage_migrations.py habitat/retention.py tests/test_sql_safety.py
git commit -m "fix(storage): constrain dynamic SQLite identifiers"
```

## Task 2: Make Semgrep a hashable CI evidence producer — delivered in Alpha.19 candidate

**Files:**

- Create: `tools/run_semgrep.py`
- Modify: `tools/quality_gate.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md`
- Create: `tests/test_semgrep_evidence.py`
- Modify: `tests/test_quality_gate.py`

**Interfaces:**

- Consumes: a semgrep executable, an immutable ruleset selector, a target directory, and the Git commit supplied by CI.
- Produces: a JSON report with `scanner`, `ruleset`, `source_commit`, `target`, `findings`, `status`, and `report_sha256` fields; `collect_quality_evidence` accepts an optional scanner report path.

- [ ] **Step 1: Write the failing report-normalization test.**

```python
def test_normalize_semgrep_report_binds_the_scanned_commit(self):
    raw = {"results": [{"check_id": "rule", "path": "x.yml"}]}
    report = normalize_semgrep_report(raw, ruleset="p/github-actions", source_commit="a" * 40, target=".github")
    self.assertEqual("semgrep", report["scanner"])
    self.assertEqual(1, report["findings"])
    self.assertEqual("a" * 40, report["source_commit"])
    self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")
```

- [ ] **Step 2: Run the test to verify the report producer is absent.**

Run: `python -m unittest -v tests.test_semgrep_evidence`

Expected: FAIL with `ImportError` for `normalize_semgrep_report`.

- [ ] **Step 3: Implement deterministic report normalization and CLI exit behavior.**

```python
def normalize_semgrep_report(raw: dict, *, ruleset: str, source_commit: str, target: str) -> dict:
    findings = len(raw.get("results", []))
    report = {
        "scanner": "semgrep",
        "ruleset": ruleset,
        "source_commit": source_commit,
        "target": target,
        "findings": findings,
        "status": "passed" if findings == 0 else "failed",
    }
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**report, "report_sha256": hashlib.sha256(encoded).hexdigest()}
```

`main` runs `semgrep scan --config p/github-actions --json .github`, writes the normalized result atomically, and returns `0` only when `findings == 0`.

- [ ] **Step 4: Require the scanner report in CI without replacing CodeQL.**

Add a `Run GitHub Actions Semgrep policy` step after release identity and before tests:

```yaml
- name: Run GitHub Actions Semgrep policy
  run: python tools/run_semgrep.py --source-commit ${{ github.sha }} --out .test-artifacts/semgrep-workflows.json
```

Pass `--scanner .test-artifacts/semgrep-workflows.json` to `tools/quality_gate.py`. Update the quality gate so malformed, wrong-commit, nonzero-finding, or missing scanner reports are failures with explicit reasons.

- [ ] **Step 5: Add quality-gate failure coverage.**

```python
def test_quality_gate_blocks_a_scanner_report_for_another_commit(self):
    scanner = self.write_json({"scanner": "semgrep", "source_commit": "b" * 40, "findings": 0, "status": "passed"})
    result = main(["--identity", str(self.identity), "--matrix", str(self.matrix), "--scanner", str(scanner), "--expected-commit", "a" * 40, "--out", str(self.out)])
    self.assertEqual(1, result)
    self.assertIn("scanner source commit mismatch", self.read_out()["reasons"])
```

- [ ] **Step 6: Verify and commit.**

Run: `python -m unittest -v tests.test_semgrep_evidence tests.test_quality_gate tests.test_ci_security`

Run: `python tools/run_semgrep.py --source-commit $(git rev-parse HEAD) --out .test-artifacts/semgrep-workflows.json`

Commit:

```powershell
git add tools/run_semgrep.py tools/quality_gate.py .github/workflows/ci.yml docs/runbooks/RELEASE-ADMISSION.md tests/test_semgrep_evidence.py tests/test_quality_gate.py
git commit -m "ci: bind Semgrep policy evidence to candidate commits"
```

## Task 3: Supervise semantic provider ownership and cleanup

**Files:**

- Modify: `habitat/runtime_lifecycle.py`
- Modify: `habitat/semantic/ts_language_service.py`
- Modify: `habitat/semantic/python_jedi.py`
- Create: `tests/test_semantic_lifecycle.py`
- Modify: `tests/test_ts_language_service.py`
- Modify: `tests/test_python_jedi.py`

**Interfaces:**

- Consumes: provider-specific `close` routines and current `runtime_service_status` data.
- Produces: `register_runtime_service(name: str, close: Callable[[], None], status: Callable[[], dict]) -> None`, `shutdown_runtime_services() -> dict[str, dict]`, and a status record containing `state`, `owned_processes`, and `last_error`.

- [ ] **Step 1: Write the failing supervisor test using an owned child process.**

```python
def test_shutdown_closes_each_registered_runtime_once(self):
    closed: list[str] = []
    register_runtime_service("fixture", lambda: closed.append("fixture"), lambda: {"state": "ready", "owned_processes": 0})
    report = shutdown_runtime_services()
    self.assertEqual(["fixture"], closed)
    self.assertEqual("closed", report["fixture"]["state"])
```

- [ ] **Step 2: Run the test to verify registration is absent.**

Run: `python -m unittest -v tests.test_semantic_lifecycle.SemanticLifecycleTests.test_shutdown_closes_each_registered_runtime_once`

Expected: FAIL with `ImportError` for `register_runtime_service`.

- [ ] **Step 3: Implement a small idempotent registry in `runtime_lifecycle.py`.**

```python
_SERVICES: dict[str, tuple[Callable[[], None], Callable[[], dict]]] = {}


def register_runtime_service(name: str, close: Callable[[], None], status: Callable[[], dict]) -> None:
    _SERVICES[name] = (close, status)


def shutdown_runtime_services() -> dict[str, dict]:
    report: dict[str, dict] = {}
    for name, (close, status) in tuple(_SERVICES.items()):
        try:
            close()
            report[name] = {**status(), "state": "closed"}
        except Exception as exc:
            report[name] = {"state": "close-failed", "last_error": str(exc)[:300]}
    _SERVICES.clear()
    return report
```

- [ ] **Step 4: Register the TypeScript and Jedi providers at creation, and prove process cleanup.**

Extend existing provider tests so an unresponsive TypeScript process and a Jedi compiler subprocess are both observed alive before close and not alive after `shutdown_runtime_services`. The test uses `poll() is None` before shutdown and `poll() is not None` after shutdown, with a bounded retry of 2 seconds.

- [ ] **Step 5: Verify repeated lifecycle behavior.**

```python
def test_repeated_register_shutdown_cycles_leave_no_services(self):
    for _ in range(100):
        register_runtime_service("fixture", lambda: None, lambda: {"owned_processes": 0})
        self.assertEqual("closed", shutdown_runtime_services()["fixture"]["state"])
    self.assertEqual({}, runtime_service_status())
```

- [ ] **Step 6: Verify and commit.**

Run: `python -m unittest -v tests.test_semantic_lifecycle tests.test_ts_language_service tests.test_python_jedi`

Commit:

```powershell
git add habitat/runtime_lifecycle.py habitat/semantic/ts_language_service.py habitat/semantic/python_jedi.py tests/test_semantic_lifecycle.py tests/test_ts_language_service.py tests/test_python_jedi.py
git commit -m "fix(semantic): supervise provider lifecycle cleanup"
```

## Task 4: Produce promotion-ready release evidence without publishing — delivered in Alpha.19 candidate

**Files:**

- Modify: `habitat/release.py`
- Modify: `tools/build_release_manifest.py`
- Modify: `tools/promote_release.py`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md`
- Modify: `tests/test_release_manifest.py`
- Modify: `tests/test_release_promotion.py`

**Interfaces:**

- Consumes: hashable truth-core, matrix, fault, artifact, and scanner reports plus a reviewer record.
- Produces: `ReleaseManifest(..., reviewer_hashes: tuple[str, ...])` and a dry-run verdict that lists missing evidence, invalid hashes, and reviewer binding failures.

- [ ] **Step 1: Write the failing independent-review test.**

```python
def test_alpha_candidate_requires_an_independent_reviewer_binding(self):
    manifest = ReleaseManifest(
        version="0.1.0-alpha.20",
        commit="a" * 40,
        reports={
            "truth-core": "1" * 64,
            "matrix": "2" * 64,
            "faults": "3" * 64,
            "artifacts": "4" * 64,
            "scanner": "5" * 64,
        },
        artifact_hashes={"wheel": "b" * 64},
        residual_risks=(),
        reviewer_hashes=(),
    )
    verdict = evaluate_promotion(manifest, target="alpha-candidate")
    self.assertFalse(verdict.admitted)
    self.assertIn("reviewer_hashes:missing", verdict.failed_gates)
```

- [ ] **Step 2: Run the test to verify the reviewer binding is not yet enforced.**

Run: `python -m unittest -v tests.test_release_promotion.ReleasePromotionTests.test_alpha_candidate_requires_an_independent_reviewer_binding`

Expected: FAIL because `ReleaseManifest` does not accept `reviewer_hashes` or promotion admits without it.

- [ ] **Step 3: Extend the manifest and verifier.**

```python
@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    commit: str
    reports: dict[str, str]
    artifact_hashes: dict[str, str]
    residual_risks: tuple[str, ...]
    reviewer_hashes: tuple[str, ...] = ()
```

For `alpha-candidate`, add `scanner` to `REQUIRED_REPORTS` and require at least one 64-hex reviewer hash distinct from every report and artifact hash. `build_release_manifest.py` accepts repeatable `--review NAME=PATH` arguments, hashes each file, and serializes both the name and digest. `promote_release.py` remains dry-run-only and still never creates a tag, uploads an artifact, or creates a GitHub release.

- [ ] **Step 4: Add exact negative-path tests.**

```python
def test_alpha_candidate_rejects_reviewer_hash_that_equals_an_artifact_hash(self):
    digest = "b" * 64
    manifest = ReleaseManifest(
        version="0.1.0-alpha.20",
        commit="a" * 40,
        reports={
            "truth-core": "1" * 64,
            "matrix": "2" * 64,
            "faults": "3" * 64,
            "artifacts": "4" * 64,
            "scanner": "5" * 64,
        },
        artifact_hashes={"wheel": digest},
        residual_risks=(),
        reviewer_hashes=(digest,),
    )
    verdict = evaluate_promotion(manifest, target="alpha-candidate")
    self.assertIn("reviewer_hashes:not-independent", verdict.failed_gates)
```

- [ ] **Step 5: Update the runbook with an executable, non-publishing sequence.**

```powershell
python tools\build_release_manifest.py --version 0.1.0-alpha.20 --commit (git rev-parse HEAD) `
  --report truth-core=.test-artifacts\truth-core.json --report matrix=.test-artifacts\matrix.json `
  --report faults=.test-artifacts\faults.json --report artifacts=.test-artifacts\artifacts.json `
  --report scanner=.test-artifacts\semgrep-workflows.json --artifact wheel=dist\nolane_habitat-0.1.0a20-py3-none-any.whl `
  --review independent-review=reports\independent-review.json --out dist\release-manifest.json
python tools\promote_release.py --manifest dist\release-manifest.json --target alpha-candidate --dry-run --out .test-artifacts\promotion-verdict.json
```

- [ ] **Step 6: Verify and commit.**

Run: `python -m unittest -v tests.test_release_manifest tests.test_release_promotion`

Run: `python tools/promote_release.py --help`

Commit:

```powershell
git add habitat/release.py tools/build_release_manifest.py tools/promote_release.py docs/runbooks/RELEASE-ADMISSION.md tests/test_release_manifest.py tests/test_release_promotion.py
git commit -m "release: require independent review evidence"
```

## Task 5: Add deterministic storage and provider fault evidence — delivered in Alpha.19 candidate

**Files:**

- Create: `habitat/operations/faults.py`
- Create: `habitat/operations/__init__.py`
- Modify: `habitat/storage.py`
- Modify: `habitat/runtime_lifecycle.py`
- Create: `tests/test_fault_injection.py`
- Create: `tools/run_reliability_suite.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**

- Consumes: named fault points, an occurrence schedule, temporary workspace fixtures, and release evidence output paths.
- Produces: `FaultInjector(schedule: dict[str, int])`, `FaultInjector.hit(point: str) -> None`, and a JSON reliability report with the candidate commit, executed fault points, and zero/positive failures.

- [ ] **Step 1: Write the failing atomic rollback test.**

```python
def test_fault_after_begin_immediate_rolls_back_the_store_transaction(self):
    injector = FaultInjector({"storage.atomic.after_begin": 1})
    with self.assertRaisesRegex(RuntimeError, "injected fault: storage.atomic.after_begin"):
        with self.store.atomic(fault_injector=injector):
            self.store.set_meta("probe", "changed")
    self.assertIsNone(self.store.get_meta("probe"))
```

- [ ] **Step 2: Run the test to verify the injector is absent.**

Run: `python -m unittest -v tests.test_fault_injection.FaultInjectionTests.test_fault_after_begin_immediate_rolls_back_the_store_transaction`

Expected: FAIL with `ModuleNotFoundError: No module named 'habitat.operations'`.

- [ ] **Step 3: Implement the test-only injector and explicit Store hook.**

```python
@dataclass
class FaultInjector:
    schedule: dict[str, int]
    counts: dict[str, int] = field(default_factory=dict)

    def hit(self, point: str) -> None:
        self.counts[point] = self.counts.get(point, 0) + 1
        if self.schedule.get(point) == self.counts[point]:
            raise RuntimeError(f"injected fault: {point}")
```

`Store.atomic` receives `fault_injector: FaultInjector | None = None`; the no-injector path is unchanged. Call `hit("storage.atomic.after_begin")` after `BEGIN IMMEDIATE`, `hit("storage.atomic.before_commit")` before commit, and `hit("semantic.shutdown.before_close")` before each registered provider close.

- [ ] **Step 4: Add recovery and close tests.**

```python
def test_fault_before_provider_close_reports_failure_and_continues_other_services(self):
    closed: list[str] = []
    register_runtime_service("first", lambda: closed.append("first"), lambda: {})
    register_runtime_service("second", lambda: closed.append("second"), lambda: {})
    report = shutdown_runtime_services(fault_injector=FaultInjector({"semantic.shutdown.before_close": 1}))
    self.assertEqual(["second"], closed)
    self.assertEqual("close-failed", report["first"]["state"])
    self.assertEqual("closed", report["second"]["state"])
```

- [ ] **Step 5: Produce an evidence report from only temporary fixtures.**

`tools/run_reliability_suite.py` creates a temporary workspace, runs the transaction and provider-fault tests through `unittest`, writes `source_commit`, `executed_fault_points`, `failures`, and `report_sha256`, then exits nonzero if any reliability test fails. CI runs it after the isolated matrix and uploads `.test-artifacts/reliability.json`.

- [ ] **Step 6: Verify and commit.**

Run: `python -m unittest -v tests.test_fault_injection tests.test_semantic_lifecycle`

Run: `python tools/run_reliability_suite.py --source-commit $(git rev-parse HEAD) --out .test-artifacts/reliability.json`

Commit:

```powershell
git add habitat/operations habitat/storage.py habitat/runtime_lifecycle.py tests/test_fault_injection.py tools/run_reliability_suite.py .github/workflows/ci.yml
git commit -m "test(reliability): bind fault evidence to candidate commits"
```

---

## Task 6: Prove SQLite concurrency, crash recovery, and integrity boundaries — delivered in Alpha.19 candidate

**Why this matters:** Habitat stores the project truth core in SQLite. A schema that is valid in a single process is not sufficient evidence that a busy writer, failed transaction, interrupted migration, or reopen preserves the same truth.

**Files:**

- Create: `tests/test_storage_recovery.py`
- Create: `tools/run_db_recovery_suite.py`
- Modify: `habitat/storage.py` only if a test exposes an unbounded or ambiguous recovery path
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md`

**Required scenarios:**

- [ ] Hold `BEGIN IMMEDIATE` in a second SQLite connection, perform a Habitat write, and prove that the public outcome is `StoreBusyError`, not a partial row or raw SQLite error.
- [ ] Force exceptions at the start, middle, and end of a nested `Store.atomic` scope; reopen the database and prove the committed state equals the last known-good state.
- [ ] Start from a pre-migration backup fixture, interrupt the repair path, reopen, and prove both the original backup and the live schema’s version-marker invariant are preserved.
- [ ] Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check` after every fault scenario; a non-`ok` result is a suite failure with the exact fixture name retained in the JSON report.
- [ ] Run each scenario in a fresh temporary directory. The harness must never use a real project workspace or delete a user database.

**Evidence contract:** `db-recovery.json` records `source_commit`, scenario names, SQLite version, checks executed, failures, and a canonical `report_sha256`. CI uploads it and promotion requires its hash in the release manifest.

**Acceptance:** contention, rollback, migration recovery, reopen, and integrity checks are deterministic on Windows and Ubuntu; the report is bound to the exact candidate commit.

## Task 7: Freeze the public MCP and CLI contract with compatibility fixtures

**Why this matters:** An agent can be correct internally yet unusable when a stable tool name, input key, error shape, or read-only promise silently changes.

**Files:**

- Create: `tests/test_mcp_contracts.py`
- Create: `tests/fixtures/contracts/agent-v1alpha2.json`
- Create: `tools/verify_contracts.py`
- Modify: `habitat/mcp_adapter.py`, `habitat/protocol.py`, and CLI entry modules only when a fixture finds a real divergence
- Modify: `docs/COMPATIBILITY.md`

**Required scenarios:**

- [ ] Snapshot the sorted MCP tool catalogue, required input fields, response top-level fields, and error class for `habitat.agent.v1alpha2`.
- [ ] Replay supported legacy fixture requests against a disposable workspace and compare semantic fields, not volatile timestamps, paths, or hash values.
- [ ] Assert that unknown fields are either deliberately ignored or rejected with a documented typed error—never accepted with an accidental side effect.
- [ ] Assert that read-only tools leave a before/after workspace digest unchanged, including the database and Observatory state files.
- [ ] Require an explicit compatibility-policy entry, migration guide, and major/minor version decision for every fixture update.

**Evidence contract:** `contract.json` contains the protocol version, fixture digest, candidate commit, compatible/breaking verdict, and a machine-readable list of intentional changes.

**Acceptance:** no public surface regression can be introduced by refactoring alone; any compatibility break is visible, versioned, and blocks an alpha promotion until explicitly reviewed.

## Task 8: Make exported evidence private by default and provenance-complete

**Why this matters:** Debug and release evidence must help reviewers without silently exporting source bodies, local absolute paths, tokens, or environment-specific identities.

**Files:**

- Create: `habitat/redaction.py`
- Create: `tests/test_export_redaction.py`
- Modify: evidence/export/Observatory serializers that emit project-derived records
- Modify: `tools/build_release_manifest.py`
- Modify: `docs/SECURITY.md` and `docs/runbooks/RELEASE-ADMISSION.md`

**Required scenarios:**

- [ ] Treat source text, absolute filesystem paths outside the declared project root, authorization values, URLs with credentials, and configurable secret-pattern matches as sensitive export inputs.
- [ ] Preserve the minimum reviewable facts: stable relative path where authorised, record type, digest, size, timestamp class, reason, and redaction count.
- [ ] Test nested dictionaries, arrays, exception messages, Unicode, malformed values, and duplicate secret occurrences. Redaction must be idempotent.
- [ ] Add negative fixtures containing representative credential-like strings; assert they never appear in JSON evidence, release manifests, CI artifacts, or Observatory export views.
- [ ] Bind a redaction-policy digest and count summary into every candidate manifest, so a reviewer knows which policy produced the evidence.

**Acceptance:** exported evidence is useful for audit but cannot be mistaken for permission to disclose project content; a failing negative fixture blocks packaging.

## Task 9: Enforce runtime budgets, cancellation, and degradation semantics

**Why this matters:** Semantic services and Observatory are valuable only while their failure modes stay bounded. A slow provider, oversized workspace, or disconnected client must degrade visibly rather than consume unbounded time, memory, or subprocesses.

**Files:**

- Create: `habitat/runtime_limits.py`
- Create: `tests/test_runtime_limits.py`
- Modify: semantic provider adapters, `runtime_lifecycle.py`, and Observatory transport only at verified boundary points
- Create: `tools/run_resource_suite.py`
- Modify: `docs/OPERATIONS.md`

**Required scenarios:**

- [ ] Define explicit budgets for provider response wait, stdout/stderr capture, request payload bytes, result item count, and owned-process shutdown grace period. Defaults must be conservative and documented.
- [ ] Feed an unresponsive provider and an oversized synthetic response; prove a typed `unavailable` or `truncated` status is returned, the budget reason is observable, and all owned processes are reaped.
- [ ] Cancel an in-flight request; prove cancellation is idempotent, does not commit a partial semantic result, and does not block a later healthy request.
- [ ] Exercise 100 repeated timeout/cancel/restart cycles and measure that the runtime registry, temporary files, and child-process count return to baseline.
- [ ] Ensure Observatory presents bounded status metadata and never infers a successful result from a timeout, cancellation, or truncation.

**Evidence contract:** `resource-limits.json` records configured budgets, measured maxima, shutdown outcomes, known skips, and report hash. A result above its declared ceiling is a failure, not a warning.

**Acceptance:** every intentionally bounded operation has an observable reason, deterministic test coverage, and a cleanup assertion.

## Task 10: Attest distribution contents and dependency provenance before promotion

**Partial foundation delivered in the Alpha.19 candidate:** CI builds a wheel and sdist without implicit network resolution, verifies both filenames and hashes against the repository version, smoke-installs the wheel offline into a temporary target before isolated import, and emits a deterministic member manifest that rejects unsafe paths, secret-bearing filenames, local databases, Habitat state, and bytecode caches. The verifier also compares the wheel `METADATA` and sdist `PKG-INFO` name, version, and canonical `Requires-Dist` inventories, then binds the inventory digest into artifact evidence. An explicit member allow-list, SBOM/lock provenance, and artifact-vs-source identity proof stay required before this task is complete.

**Why this matters:** A green source checkout does not prove that the wheel/sdist is complete, installable, free of generated secrets, or produced from the reviewed commit.

**Files:**

- Create: `tools/verify_distribution.py`
- Create: `tests/test_distribution_verification.py`
- Modify: package build workflow and `.gitignore` only as needed
- Modify: `tools/build_release_manifest.py`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md`

**Required scenarios:**

- [ ] Build wheel and sdist in a clean temporary directory, install the wheel in an isolated environment, and run a small import/CLI smoke test without using the source tree.
- [ ] Enumerate package members deterministically; reject `.env` files, `.test-artifacts`, local databases, private keys, absolute build paths, and files outside an allow-listed distribution policy.
- [ ] Record SHA-256 values for wheel, sdist, package-member manifest, build interpreter, and declared runtime dependencies. The candidate commit must match release identity metadata.
- [ ] Generate an SBOM or a deterministic dependency inventory from package metadata; its digest becomes a manifest report and its generation command is recorded.
- [ ] Re-run content verification from the generated artifacts, not a mutable checkout. A mismatch between source identity and artifact identity blocks promotion.

**Evidence contract:** `distribution.json` binds artifact hashes, member-manifest hash, dependency-inventory hash, source commit, and smoke-test result into the candidate manifest.

**Acceptance:** the released package is independently inspectable and installable, its contents are deliberate, and reviewers can distinguish source evidence from artifact evidence.

---

## Task 11: Enforce an explicit capability boundary for every state-changing operation

**Why this matters:** Habitat is useful because it can orient agents and govern changes. That same capability becomes unsafe if a tool, path, command, or outbound request is trusted merely because it arrived through an MCP or CLI envelope. The system needs a single place to answer: *who may act, on what, with which limits, and how is the decision recorded?*

**Files:**

- Create: `habitat/authorization.py`
- Create: `tests/test_authorization_boundary.py`
- Modify: MCP mutation handlers, CLI mutation entry points, and workspace lifecycle boundaries only where they currently make an authorization decision
- Modify: `docs/SECURITY.md`, `docs/OPERATIONS.md`, and `docs/COMPATIBILITY.md`

**Required scenarios:**

- [ ] Define a declarative capability policy for read, workspace-write, configuration-write, process-spawn, network, export, and release actions. The default is deny; every grant has a concrete workspace scope, operation budget, expiry or lifecycle boundary, and reason.
- [ ] Canonicalize and validate every filesystem target before a mutation. Reject path traversal, symlink escape, drive/UNC aliases, and writes outside the selected workspace; test on Windows and POSIX path forms.
- [ ] Treat shell invocation, package installation, network retrieval, and external publication as distinct capabilities. A read-only MCP request must never gain any of them as a side effect.
- [ ] Emit a compact decision receipt containing the policy digest, operation class, workspace-relative target, allow/deny decision, and redacted reason. Do not include tokens, source text, or absolute paths.
- [ ] Add adversarial fixtures for malformed JSON, duplicate keys, unexpected nested fields, encoded traversal, cancellation immediately before a write, and a stale authorization receipt.

**Evidence contract:** `authorization.json` binds the policy digest, negative-fixture catalogue digest, allowed/denied counts, candidate commit, and report hash. A new mutation surface cannot be promoted until it is classified by the policy and covered by a deny-path test.

**Acceptance:** no active operation relies on implied authority. A reviewer can prove that a request was either denied safely or performed exactly within an explicit, bounded capability.

## Task 12: Make upgrade, backup, restore, and rollback a first-class recovery contract

**Why this matters:** Database integrity after one process failure is necessary, but Habitat also needs to survive version change. A user must be able to make a backup, upgrade through supported versions, verify the result, and recover without relying on undocumented local state.

**Files:**

- Create: `tests/fixtures/upgrades/` with minimal versioned workspaces and databases
- Create: `tests/test_upgrade_recovery.py`
- Create: `tools/run_upgrade_recovery_suite.py`
- Modify: migration, backup, restore, and version-reporting code only if the fixtures reveal a real ambiguity
- Modify: `docs/runbooks/RECOVERY.md` and `docs/COMPATIBILITY.md`

**Required scenarios:**

- [ ] Build immutable fixtures for the oldest supported schema plus each supported intermediate schema. Upgrade each fixture to the candidate, reopen it twice, and compare a semantic state digest with the expected result.
- [ ] Before every migration, create a verified backup with a manifest containing format version, source schema version, relative members, and hashes. Simulate interruption before swap, during swap, and after swap; prove a known-good backup remains recoverable.
- [ ] Make restore an explicit command with a dry-run mode. It must refuse mismatched project identity, corrupt manifests, path escapes, schema versions outside policy, and a destination that is not empty or explicitly approved.
- [ ] Define the rollback promise precisely: data migrations that are not reversible must be reported as such before mutation; a code rollback must never silently reinterpret newer state as older state.
- [ ] Test locale-sensitive paths, long paths, interrupted writes, read-only destinations, disk-full-like write failures through a controlled writer, and SQLite journal modes supported by Habitat.

**Evidence contract:** `upgrade-recovery.json` includes fixture hashes, from/to schema versions, backup and restore outcomes, semantic state digests, recovery timing class, candidate commit, and report hash.

**Acceptance:** a supported upgrade has a deterministic recovery path with a tested negative path, and the user can distinguish an unsupported rollback from a successful restore before data changes.

## Task 13: Establish scale, latency, and resource-regression budgets from deterministic corpora

**Why this matters:** Timeout handling prevents one bad request from running forever, but it does not show whether a healthy large workspace stays usable. Habitat needs performance evidence that is repeatable enough to catch regressions without turning CI into a flaky benchmark.

**Files:**

- Create: `tests/fixtures/scale/` or a deterministic corpus generator with only synthetic files
- Create: `tests/test_scale_contracts.py`
- Create: `tools/run_scale_suite.py`
- Modify: indexing, storage, semantic providers, or Observatory only after a profiled regression is reproduced
- Modify: `docs/OPERATIONS.md`

**Required scenarios:**

- [ ] Define three synthetic workspace tiers by file count, aggregate bytes, symbol count, and database record count. The generator must be seed-based, offline, and never include customer or repository source.
- [ ] Measure cold and warm orientation, a representative semantic request, an evidence query, cancellation latency, and shutdown latency. Record count/size inputs and measured maxima rather than a single opaque score.
- [ ] Set broad, platform-specific ceilings for CI and stricter trending baselines for scheduled runs. A ceiling breach is a failure; a baseline regression opens a review item rather than silently changing the threshold.
- [ ] Repeat the small tier enough times to reveal descriptor, process, temporary-file, cache, and transaction growth. Assert that cleanup returns each observable counter to baseline within a bounded grace period.
- [ ] Store only aggregate timings and resource counters in reports. Do not export corpus paths, file bodies, or process environment data.

**Evidence contract:** `scale.json` records corpus generator digest and seed, platform/runtime, declared ceilings, measured maxima, cleanup counters, candidate commit, and report hash.

**Acceptance:** performance changes are intentional and reviewable; an increase in work or resource use cannot hide behind a green functional test suite.

## Task 14: Bind every promotion to verifiable provenance and an operational response path

**Partial foundation delivered in the Alpha.19 candidate:** the release manifest builder accepts only report payloads whose embedded canonical digest verifies, and the alpha gate rejects required reports that are absent, non-passing, or bound to a different commit. A signed receipt and response drill are still required before this task is complete.

**Why this matters:** Package hashing proves bytes but not the entire chain that produced them. A trustworthy release also needs a clear response when a dependency vulnerability, compromised workflow, or serious regression is discovered after publication.

**Files:**

- Create: `tools/verify_provenance.py`
- Create: `tests/test_provenance_verification.py`
- Modify: release workflow, `tools/build_release_manifest.py`, and `tools/promote_release.py`
- Create: `docs/runbooks/INCIDENT-RESPONSE.md`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md` and `docs/SECURITY.md`

**Required scenarios:**

- [ ] Create a canonical release receipt that binds the commit SHA, protected CI run identifiers, report hashes, wheel/sdist hashes, dependency-inventory hash, reviewer record hashes, and release manifest hash. Reject a receipt with a substituted report, artifact, commit, or workflow identity.
- [ ] Generate a signed provenance attestation using the repository's supported CI identity. Verification must use public metadata and must not depend on a developer's local secret or mutable branch name.
- [ ] Maintain a dependency policy: approved sources, lock or resolution digest, update cadence, vulnerability triage severity and response target, and an explicit exception record with expiry. New unresolved critical/high findings block promotion unless a documented, reviewed exception exists.
- [ ] Exercise the operational response path: revoke a candidate before publication; publish a correction advisory after a simulated defect; preserve evidence; identify affected artifact hashes; and verify that a rollback notice never deletes a user workspace or rewrites history.
- [ ] Test that release tooling defaults to dry-run and cannot tag, upload, or publish when the receipt is absent, invalid, expired, or for a different commit.

**Evidence contract:** `provenance.json` contains receipt digest, attestation verification result, dependency-policy digest, known-exception summary, response-drill result, candidate commit, and report hash.

**Acceptance:** a public release can be traced from artifact back to reviewed source and CI evidence, and there is a rehearsed, non-destructive response when that trust chain is challenged.

## Task 15: Make the workspace activity trail tamper-evident without retaining private reasoning

**Why this matters:** Habitat already records task, mutation, evidence, checkpoint, and Observatory activity. Those records become misleading if a truncated, reordered, or manually altered history can still look authoritative. The integrity layer must prove record continuity while preserving the existing rule that private reasoning and secret-bearing payloads are never exported.

**Files:**

- Create: `habitat/activity_integrity.py`
- Create: `tests/test_activity_integrity.py`
- Create: `tools/verify_workspace_ledger.py`
- Modify: activity emission and checkpoint persistence only at their existing durable write boundary
- Modify: `docs/OPERATIONS.md` and `docs/runbooks/RECOVERY.md`

**Interfaces:**

- Consumes: a prior digest, a strictly increasing activity sequence, a record class, a redacted payload, and a workspace identity digest.
- Produces: `append_activity_record(previous_digest: str, sequence: int, record: Mapping[str, object]) -> dict[str, object]` and `verify_activity_chain(records: Sequence[Mapping[str, object]], workspace_digest: str) -> ChainVerdict`.

**Required scenarios:**

- [ ] Canonicalize one public record with its sequence, record class, redacted payload digest, prior digest, and workspace identity digest; calculate the record digest over exactly those fields. Exclude source bodies, prompts, environment values, tokens, absolute paths, and private reasoning before hashing.
- [ ] Verify a valid chain after workspace close/reopen and bind every checkpoint to the exact last ledger digest. A checkpoint must be rejected when it names an earlier sequence, a different workspace digest, or a mismatched chain head.
- [ ] Create negative fixtures for a deleted middle record, record reordering, a substituted payload digest, a substituted predecessor digest, an incremented sequence without a valid predecessor, and a foreign-workspace checkpoint. Each must name the first failing sequence and never repair or rewrite the ledger automatically.
- [ ] Ensure repeated verification is read-only: it opens the workspace, emits no activity event, changes no modification time in the chain store, and returns the same verdict digest.
- [ ] Provide an export projection containing only record class, sequence, timestamps, bounded redacted summary, and cryptographic bindings. The export must preserve verification while omitting all prohibited values.

**Evidence contract:** `workspace-ledger.json` records fixture digests, verified sequence range, foreign/tamper rejection counts, redaction scan result, candidate commit, and report hash.

**Acceptance:** a reviewer can distinguish a complete, authentic public activity history from an incomplete or altered one without being given private model content or workspace secrets.

## Task 16: Prove crash recovery for source mutation at every journal transition

**Why this matters:** SQLite recovery alone does not prove that the journaled source mutation engine cannot leave a project half-edited. The mutation engine already persists a prepared/applying/committed journal, so its promises need deterministic interruption tests that operate on synthetic projects only.

**Partial foundation delivered in the Alpha.19 candidate:** a commit-bound `mutation-recovery` report now runs text replacement and structural create/move/delete interruption fixtures in CI. Each fixture closes and reopens the workspace, proves rollback to the original source state, and checks a second reopen performs no extra recovery. Exact fault hooks for every journal transition, controlled filesystem failures, and the full concurrency/path matrix remain required before this task is complete.

**Files:**

- Create: `tests/test_mutation_recovery.py`
- Create: `tools/run_mutation_recovery_suite.py`
- Modify: `habitat/mutation.py` only if a failure fixture reveals an incomplete recovery transition
- Modify: `docs/runbooks/RECOVERY.md`

**Interfaces:**

- Consumes: `MutationEngine.apply`, its persisted journal, a synthetic source tree digest, an injected transition name, and a fresh `HabitatWorkspace` reopen.
- Produces: `run_recovery_case(case: str, crash_at: str) -> dict[str, object]` where `crash_at` is one of `journal-prepared`, `journal-applying`, `after-write`, `after-structural-change`, or `before-commit-marker`.

**Required scenarios:**

- [ ] Start from a fixture containing a replacement, file creation, move, and deletion. Interrupt exactly after each named journal transition, close all workspace handles, reopen in a new process, and assert one of only two terminal states: the original tree digest or the complete intended tree digest. A mixed digest is a failure.
- [ ] Verify journal recovery is idempotent: reopen and recover twice; the second pass reports no additional work, preserves the terminal digest, and does not create a new transaction.
- [ ] Stage two disjoint mutations from the same revision and prove their rebased result matches the ordered application of both changes. Stage two overlapping mutations and prove one receives a typed conflict without changing the other mutation's files.
- [ ] Force controlled failures from source write, rename/move, permission update, journal write, and refresh/reindex boundaries. The report must preserve the original exception class but never store source body text.
- [ ] Run path fixtures for Windows drive-style, backslash, Unicode, spaces, and POSIX separators through the same relative-path normalizer; traversal, UNC/drive escape, and a symlink escape must fail before any journal is written.

**Evidence contract:** `mutation-recovery.json` records case names, pre/post tree digests, journal states, recovery actions, conflict outcomes, cleanup assertions, candidate commit, and report hash.

**Acceptance:** every supported source mutation has an all-or-nothing recovery outcome after a simulated process interruption, and unsafe paths cannot reach the journal or filesystem writer.

## Task 17: Replay hostile protocol inputs and prove read-only calls stay read-only

**Why this matters:** MCP and CLI requests are boundary inputs, not trusted in-process calls. Static happy-path fixtures protect compatibility, but they do not show that malformed, oversized, duplicated, or stale inputs preserve the tool's capability boundary and disclose only safe diagnostics.

**Files:**

- Create: `tests/fixtures/protocol/adversarial-v1alpha2.json`
- Create: `tests/test_protocol_conformance.py`
- Create: `tools/run_protocol_conformance_suite.py`
- Modify: `habitat/mcp_adapter.py`, CLI request parsing, or request validators only when a fixture exposes a boundary failure
- Modify: `docs/COMPATIBILITY.md` and `docs/SECURITY.md`

**Interfaces:**

- Consumes: versioned request fixtures, a temporary workspace digest, an agent handle, and the public MCP/CLI request adapters.
- Produces: `replay_protocol_case(case: Mapping[str, object]) -> ProtocolResult` with `outcome`, `error_class`, `response_shape`, `workspace_digest_before`, and `workspace_digest_after`.

**Partial foundation delivered in the Alpha.19 candidate:** the NDJSON adapter now rejects duplicate JSON keys, non-standard JSON numbers, unpaired Unicode surrogates, non-object requests, and payloads over 256 KiB before dispatch. A versioned adversarial fixture proves each rejection uses a typed, non-disclosing envelope and leaves the workspace revision unchanged. CI produces a hash-bound `protocol-conformance` report from that corpus, and alpha admission requires it. The read-only protocol subset now has a cold-workspace regression that compares source bytes, revision, active trace state, and SQLite logical dump before/after `protocol.capabilities` and `workspace.source.read`. The broader corpus, mutation-preparation checks, MCP SDK surface replay, and all read-only methods' logical-state digest remain required before this task is complete.

**Required scenarios:**

- [ ] Maintain a deterministic corpus covering missing required fields, wrong scalar/container types, unknown fields, duplicate JSON keys, invalid UTF-8 surrogate forms, stale/foreign agent and checkpoint handles, oversized strings/lists, empty change payloads, encoded path traversal, and invalid semantic identifiers.
- [ ] For every declared read-only tool, compare the workspace tree digest, SQLite logical-state digest, transaction count, agent-session count, and activity sequence before/after replay. A request may add an explicitly documented activity event only if the contract says it can; it must never create source or configuration writes.
- [ ] For mutation tools, prove validation failures occur before transaction preparation, backup creation, journal writing, source writes, process spawn, or network access. A failure response must have a stable typed envelope and omit paths outside the workspace, source text, secrets, and stack traces.
- [ ] Apply deterministic bounded mutation-style transformations to every fixture field (delete, duplicate, type swap, boundary length, Unicode normalization, and key reorder). Persist only the seed, corpus digest, case count, aggregate outcomes, and first counterexample digest.
- [ ] Replay the exact corpus against the current contract fixture and the prior supported fixture. A response-shape difference requires an explicit version change or a compatibility exception record; silent drift blocks promotion.

**Evidence contract:** `protocol-conformance.json` records fixture and generator digests, executed case count, state-change violations, disclosure scan result, version-pair comparison, candidate commit, and report hash.

**Acceptance:** public boundary behavior is both backwards-auditable and hostile-input-safe; an invalid request cannot acquire mutation authority or leak sensitive context.

## Task 18: Calibrate semantic answers against a provider-labelled truth corpus

**Why this matters:** A semantic system can appear useful while returning unsupported, stale, or fallback-derived claims as though they came from an authoritative provider. Habitat must measure provider availability, source anchors, and answer correctness separately, then expose a truthful degraded state.

**Files:**

- Create: `tests/fixtures/semantic-conformance/` with synthetic Python and TypeScript projects
- Create: `tests/test_semantic_conformance.py`
- Create: `tools/run_semantic_conformance_suite.py`
- Modify: semantic provider result envelopes and provider-status handling only if the corpus exposes an ambiguity
- Modify: `docs/COMPATIBILITY.md` and `docs/OPERATIONS.md`

**Interfaces:**

- Consumes: a fixture manifest containing expected symbols, definitions, references, ambiguous names, unsupported constructs, provider availability, and expected trust labels.
- Produces: `evaluate_semantic_case(case: SemanticCase, provider: Provider) -> SemanticVerdict` with `matches`, `missing`, `unexpected`, `provider`, `availability`, `trust`, and `anchor_digest`.

**Required scenarios:**

- [ ] Create compact synthetic fixtures for nested scopes, same-name symbols, aliases/imports, renames, generated-looking paths, unsupported language constructs, malformed source, and a provider that is intentionally unavailable. Fixtures must contain no third-party or user source.
- [ ] Require every returned definition/reference/mutation anchor to resolve to an exact fixture location and expected provider/trust label. A heuristic or fallback answer may be returned only when marked as such; it must never be labelled authoritative or semantic-provider verified.
- [ ] Compare cold and warm provider runs, then edit one fixture file and prove stale anchors are rejected or revalidated. Do not treat a cached answer as fresh merely because its symbol name still exists.
- [ ] Kill or timeout the TypeScript/Jedi child provider in a controlled test; report `unavailable` or `degraded`, prove cleanup succeeds, and assert that no partial result is reported as a passed semantic answer.
- [ ] Keep pass-rate thresholds meaningful: every required corpus assertion is exact, while optional-provider skips are counted and separately bounded. A new skip or a provider-label mismatch fails the evidence gate rather than improving a percentage.

**Evidence contract:** `semantic-conformance.json` records corpus digest, per-provider availability and exact-match counts, stale-anchor results, degradation/cleanup results, skip reasons, candidate commit, and report hash.

**Acceptance:** users and agents can tell whether a semantic fact is exact, heuristic, unavailable, stale, or unsupported, and the system has regression evidence for every distinction.

## Task 19: Make the Observatory a bounded, private, truthful operational projection

**Why this matters:** The Observatory is a human-facing read model. Its current read-only intention is valuable, but it must retain that property under large state, malformed stored metadata, concurrent activity, and provider failure. A visual dashboard that blocks work or quietly hides an error is not trustworthy observability.

**Files:**

- Create: `tests/test_observatory_budget.py`
- Create: `tools/run_observatory_budget_suite.py`
- Modify: `habitat/workspace.py`, `habitat/storage.py`, and `habitat/observatory.py` only to introduce bounded read queries, explicit snapshot metadata, or safe serialization
- Modify: `docs/OBSERVATORY.md` and `docs/OPERATIONS.md`

**Interfaces:**

- Consumes: a workspace with synthetic files, symbols, agents, episodes, evidence, activity, malformed metadata, and concurrent append activity.
- Produces: `observatory_snapshot() -> dict` extended only with `snapshot_bounds`, `snapshot_status`, `activity_seq`, and a redacted error summary when a bounded subprojection cannot be read.

**Required scenarios:**

- [ ] Replace fetch-all-then-slice behavior at each projection boundary with storage queries that apply a stable order and limit before materializing rows. Record declared limits in `snapshot_bounds`; no field is permitted to grow with total project size without an explicit reviewed budget.
- [ ] Verify the snapshot remains read-only: compare tree, logical database, transaction, agent-session, and activity state before/after repeated HTTP snapshot fetches. The local server may serve a snapshot but cannot mint agents, mutate source, or execute verification.
- [ ] Feed malformed JSON metadata, redaction candidates, oversized labels, and a failed semantic provider into the projection. The response must remain valid JSON, redact sensitive values, cap labels/summaries, and expose a typed bounded failure/degraded status rather than a false success.
- [ ] Interleave activity appends with repeated snapshots. `activity_seq` must be monotonic; each response declares its observed range; a client can detect a gap without interpreting a gap as a completed action.
- [ ] Measure snapshot latency and materialized row/byte counts for the small and medium synthetic corpora. Enforce broad platform-specific ceilings and assert that the server and workspace close with no live listener, provider, or SQLite handle.

**Evidence contract:** `observatory-budget.json` records limits, corpora digests, maximum materialized rows/bytes, latency maxima, privacy scan result, degradation cases, cleanup result, candidate commit, and report hash.

**Acceptance:** the Observatory remains a useful read-only view as a workspace grows, makes degradation visible, and never becomes a hidden control plane or a source of private data disclosure.

## Task 20: Require reproducible, hermetic package builds in addition to artifact inspection

**Why this matters:** Package member inspection proves that a single artifact looks intentional. It does not prove that the reviewed source produced it consistently. A candidate needs two independent clean builds with pinned build inputs and a clear verdict when byte-for-byte reproducibility is not yet possible.

**Files:**

- Create: `tools/verify_reproducible_build.py`
- Create: `tools/normalize_sdist.py`
- Create: `tests/test_reproducible_build.py`
- Create: `tests/test_normalize_sdist.py`
- Modify: `pyproject.toml`, CI build steps, and release manifest builder only when needed to declare/replay immutable build inputs
- Modify: `docs/runbooks/RELEASE-ADMISSION.md` and `docs/OPERATIONS.md`

**Interfaces:**

- Consumes: an exact commit, declared Python/build-backend versions, a fixed `SOURCE_DATE_EPOCH`, clean temporary source copies, and wheel/sdist artifact bytes.
- Produces: `build_twice_and_compare(source_commit: str, build_spec: BuildSpec) -> ReproducibilityVerdict` with artifact hashes, build-input digest, reproducibility status, and normalized-difference reason.

**Partial foundation delivered in the Alpha.19 candidate:** CI now builds twice per OS/Python lane with `SOURCE_DATE_EPOCH=0`, normalises sdist archive metadata through a tested `normalize_sdist.py`, verifies wheel and sdist SHA-256 equality, and blocks alpha promotion without the commit-bound `reproducible-build` report. The normaliser preserves regular-file/directory bytes, paths, and modes while rejecting links and unsupported member types. This is deliberately scoped to two build invocations in one checkout and lane; separate clean source copies, immutable build-environment provenance, and cross-lane policy remain required before this task is complete.

**Required scenarios:**

- [ ] Build the wheel and sdist twice from separate clean copies of the same checkout using no source-tree import, no implicit dependency resolution, the declared build backend, and a fixed timestamp source. Compare artifact SHA-256 values byte-for-byte on the same OS/Python lane.
- [ ] If a format cannot yet be byte-reproducible, require a deterministic member-and-metadata comparison that enumerates the exact differing fields. The verdict is `not-reproducible`, not `passed`, until an explicit temporary exception with expiry is independently reviewed.
- [ ] Reject a changed `VERSION`, build backend, dependency declaration, build environment marker, generated file, or source commit between the two builds. Test each substitution by making one input differ and asserting the first failing binding is reported.
- [ ] Persist the build interpreter version, backend distribution/version/hash, project metadata digest, environment allow-list digest, fixed epoch, command digest, and both artifact hashes. Never persist home paths, environment secrets, tokens, or arbitrary environment variables.
- [ ] Run the produced artifacts through the existing offline install/member checks after comparison. A reproducible but uninstallable package and an installable but non-reproducible package both block promotion.

**Evidence contract:** `reproducible-build.json` records both build-input digests, artifact hashes, comparison result, allowed difference rationale if any, downstream install/member verdicts, candidate commit, and report hash.

**Acceptance:** release evidence can show whether the package was rebuilt from the reviewed source under declared inputs, rather than merely asserting that one CI-generated archive exists.

## Delivery sequence and non-negotiable gates

| Milestone | Work | Promotion rule |
|---|---|---|
| Alpha.19 safety baseline | Tasks 1–2 | Delivered only with four-way CI and CodeQL on the exact commit. This is an engineering baseline, not release admission. |
| Alpha.20 recovery core | Tasks 3, 5, 6, 12, 16 | No candidate while semantic cleanup, database/source-transaction recovery, or upgrade/restore reports are missing or nonzero. |
| Contract, truth, and privacy boundary | Tasks 7, 8, 9, 11, 15, 17, 18, 19 | No candidate while a public-surface, ledger, semantic truth, redaction, resource-limit, Observatory, or authorization deny-path test fails. |
| Distribution and provenance | Tasks 4, 10, 13, 14, 20 | No tag or GitHub release without independent review, artifact inspection, reproducible-build, scale, and verified provenance evidence. |

The implementation order is intentionally safety-first: fix a failing boundary with its smallest deterministic test; attach a commit-bound report; then widen coverage to recovery, compatibility, privacy, and scale. A green test run never substitutes for the next gate's evidence.

---

## Final verification

- [ ] Run `python -m compileall -q habitat tests tools`.
- [ ] Run `python -m unittest discover -q` on the implementation host.
- [ ] Run `semgrep scan --config p/github-actions .github` and retain the generated report only under `.test-artifacts/`.
- [ ] Confirm every workflow `uses:` reference matches `@[0-9a-f]{40}` with `python -m unittest -v tests.test_ci_security`.
- [ ] Confirm the matrix passes on Ubuntu and Windows for Python 3.10 and 3.14, with artifact upload succeeding on every job.
- [ ] Confirm CodeQL passes for Python and JavaScript/TypeScript on the exact candidate commit.
- [ ] Run database recovery, contract, export-redaction, resource-limit, and distribution suites; retain their commit-bound reports.
- [ ] Run authorization, upgrade-recovery, scale, and provenance suites; retain their commit-bound reports.
- [ ] Run workspace-ledger, source-mutation recovery, protocol conformance, semantic conformance, Observatory budget, and reproducible-build suites; retain their commit-bound reports.
- [ ] Build a release manifest and run `promote_release.py --dry-run`; retain a blocked verdict when independent reviewer evidence is absent.
- [ ] Update README only if a verified, user-visible behavior changed; do not describe planned fault injection, scanner policy, or release promotion as shipped until its task is complete.

## Completion definition

The plan is complete when all dynamic SQLite identifiers are allow-listed; database and source-mutation recovery, upgrade/restore, compatibility, hostile-input conformance, semantic truth calibration, privacy, tamper-evident activity history, explicit authorization, Observatory budgets, resource limits, scanner, reliability, scale, distribution, reproducible-build, and provenance reports are commit-bound evidence; semantic providers cannot outlive their lifecycle boundary; and release promotion rejects every candidate missing independent reviewer evidence. A public tag or GitHub release remains a separate action after an independent reviewer approves the exact manifest.
