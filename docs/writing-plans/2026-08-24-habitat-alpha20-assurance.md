# Alpha.20 Assurance and Trustworthy Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** make a Habitat workspace demonstrably safe to evolve by strengthening mutation admission, protocol conformance, artifact provenance, and observer isolation with machine-verifiable evidence.

**Architecture:** Alpha.20 treats four boundaries as separate proof targets: untrusted mutation payload → policy/transaction state, untrusted NDJSON → protocol dispatch, source checkout → reproducible distributable artifacts, and authoritative SQLite state → observer projection. Each boundary gets a minimal fail-closed implementation, a regression test that records the formerly unsafe transition, and a commit-bound evidence artefact. A release remains blocked until every artefact is independently reviewed.

**Tech Stack:** Python 3.10+, `unittest`/`pytest`, SQLite, strict JSON/NDJSON, Git, Python build/sdist tooling, existing Habitat CLI/MCP/Observatory.

**Spec:** `docs/control/CHARTER.md`, `docs/COMPATIBILITY.md`, `docs/LIMITATIONS.md`, and the frozen `tests/fixtures/contracts/agent-v1alpha2.json` contract.

## Global Constraints

- Canonical project files remain the only source truth; Habitat state is derived and may not silently change for a rejected request.
- `habitat.agent.v1alpha2` remains frozen unless protocol version, fixture, migration notes, and compatibility evidence change together.
- The Observatory stays loopback, read-only, and uses a separate query-only SQLite connection.
- Every code change follows red → green testing; a failing test must name the previously unsafe production transition.
- Every emitted machine report binds the exact 40-character commit SHA and hashes its canonical JSON form.
- No Git tag, GitHub release, or claim of hostile-code isolation is allowed without the existing admission gate and independent review.

---

## File map

| File | Responsibility |
| --- | --- |
| `habitat/mutation.py` | Normalize a requested source mutation before any reconcile, transaction, backup, or journal persistence. |
| `habitat/workspace.py` | Validate a mutation before consuming approvals or acquiring path leases, then stage only a normalized transaction. |
| `tests/test_mutation_recovery.py` | Assert rejected mutation payloads leave source bytes, revision, SQLite data, approval state, and journals unchanged. |
| `tests/fixtures/protocol/adversarial-v1alpha2.json` | Versioned hostile NDJSON corpus and expected typed protocol envelopes. |
| `tools/run_protocol_conformance_suite.py` | Execute the protocol fixture and write a commit-bound conformance report. |
| `tests/test_protocol_conformance.py` | Test parser/reply behaviour and strict read-only state neutrality. |
| `tools/verify_reproducible_build.py` | Build two independent copies, normalize sdist metadata, compare hashes, and write provenance for both inputs. |
| `tests/test_reproducible_build.py` | Prove a clean-copy verifier rejects a missing/dirty/mismatched checkout and accepts identical artifact digests. |
| `tools/build_release_manifest.py` | Bind checked artefacts, gate reports, commit identity, and provenance ledger into one immutable candidate manifest. |
| `habitat/observatory.py` | Project authoritative SQLite state without a control-plane connection or mutation capability. |
| `tests/test_observatory.py` | Assert observer requests cannot write, migrate, refresh, or alter the authoritative workspace database. |

## Task 1: Make mutation admission side-effect free before authorization

**Status:** Completed locally on the candidate; regression evidence covers stale-source reconciliation and approval-token consumption. The focused suite and matrix remain release evidence, not a substitute for independent review.

**Files:**

- Modify: `habitat/mutation.py:33-191`
- Modify: `habitat/workspace.py:2446-2495`
- Test: `tests/test_mutation_recovery.py`

**Interfaces:**

- Consumes: `MutationEngine._normalize_operations(operations: list[dict]) -> list[dict]`.
- Produces: `MutationEngine._begin_normalized(normalized: list[dict]) -> TransactionRecord`; `HabitatWorkspace.stage_change(...) -> dict` only consumes approval or leases after normalization succeeds.

- [ ] **Step 1: Write the failing regression tests.**

```python
with self.assertRaisesRegex(ValueError, "operations must be a non-empty list"):
    workspace.stage_change([])
self.assertEqual(database_before, "\n".join(workspace.store.conn.iterdump()))

with self.assertRaisesRegex(ValueError, "create_file requires UTF-8 string content"):
    workspace.stage_change([{"op": "create_file", "path": "new.py", "content": 7}], approval_id=approval_id)
self.assertIsNone(workspace.store.conn.execute(
    "SELECT consumed_at FROM approvals WHERE id=?", (approval_id,)
).fetchone()[0])
```

- [ ] **Step 2: Run the tests and observe the unsafe transition.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_mutation_recovery.py -q`

Expected before the repair: a stale external file changes `workspace.revision` after `stage_change([])`, or an invalid structural mutation has a non-null `approvals.consumed_at`.

- [ ] **Step 3: Implement the smallest admission split.**

```python
def _begin_normalized(self, normalized: list[dict]) -> TransactionRecord:
    self.workspace.reconcile()
    base = self.workspace.revision
    _, _, preview = self._prepare(normalized)
    # create and persist the TransactionRecord here

def begin(self, operations: list[dict]) -> TransactionRecord:
    return self._begin_normalized(self._normalize_operations(operations))
```

At the top of `stage_change`, create one `MutationEngine`, call `_normalize_operations`, and pass only that normalized list to `_begin_normalized` after the policy/lease checks. Do not make the private `_begin_normalized` public.

- [ ] **Step 4: Verify valid mutation, policy, and recovery behaviour.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_mutation_recovery.py tests\test_workspace.py tests\test_alpha10_deep_evolution.py -q`

Expected: all tests pass; a valid approved structural mutation consumes its token exactly once and still produces the existing journaled transaction.

- [ ] **Step 5: Commit the bounded change.**

```powershell
git add habitat/mutation.py habitat/workspace.py tests/test_mutation_recovery.py
git commit -m "security: preflight mutation payloads before side effects"
```

## Task 2: Turn protocol hostile-input tests into a replayable corpus gate

**Files:**

- Modify: `tests/fixtures/protocol/adversarial-v1alpha2.json`
- Modify: `tools/run_protocol_conformance_suite.py`
- Modify: `tests/test_protocol_conformance.py`
- Test: `tests/test_protocol_conformance_suite.py`

**Interfaces:**

- Consumes: one fixture case `{id, raw, expected_code, expected_kind}`.
- Produces: `protocol-conformance.json` with `source_commit`, per-case verdicts, `status`, `failures`, and `report_sha256`.

- [ ] **Step 1: Write a failing corpus case and runner assertion.**

```python
case = {"id": "duplicate-key-nested", "raw": '{"method":"protocol.capabilities","params":{"x":1,"x":2}}',
        "expected_code": "INVALID_JSON", "expected_kind": "error"}
result = run_case(case)
self.assertEqual(case["expected_code"], result["code"])
self.assertEqual(case["expected_kind"], result["kind"])
```

- [ ] **Step 2: Run the focused protocol test.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_protocol_conformance.py tests\test_protocol_conformance_suite.py -q`

Expected before the repair: the new corpus case is absent or the runner omits the typed-envelope assertion.

- [ ] **Step 3: Add strict corpus execution without weakening the parser.**

```python
for case in fixture["cases"]:
    reply = protocol.handle_raw(case["raw"])
    verdicts.append({"id": case["id"], "kind": reply["kind"], "code": reply.get("code")})
```

Reject duplicate keys at every JSON-object level; never downgrade malformed JSON to a generic exception or include exception text in the reply.

- [ ] **Step 4: Run the runner and verify the report is hash-bound.**

Run: `.\.venv\Scripts\python.exe tools\run_protocol_conformance_suite.py --source-commit (git rev-parse HEAD) --out .test-artifacts\protocol-conformance.json`

Expected: `status` is `passed`, every fixture case has a verdict, and `report_sha256` matches canonical JSON with its own hash field omitted.

- [ ] **Step 5: Commit the protocol evidence gate.**

```powershell
git add tests/fixtures/protocol/adversarial-v1alpha2.json tools/run_protocol_conformance_suite.py tests/test_protocol_conformance.py tests/test_protocol_conformance_suite.py
git commit -m "test(protocol): replay hostile NDJSON conformance corpus"
```

## Task 3: Prove reproducibility across clean source copies

**Status:** In progress. Unit-level clean/dirty/distinct-checkout checks are implemented; the candidate still requires the post-commit end-to-end clean-copy proof and CI evidence.

**Files:**

- Modify: `tools/verify_reproducible_build.py`
- Test: `tests/test_reproducible_build.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md`

**Interfaces:**

- Consumes: `--source-commit <sha>`, two clean worktree paths, and output directory.
- Produces: a report containing both resolved `HEAD`s, dirty-state verdicts, non-reversible checkout identities, normalized artifact SHA-256 values, build environment identity, and a canonical report hash.

- [ ] **Step 1: Write tests that distinguish a clean independent copy from one checkout built twice.**

```python
with self.assertRaisesRegex(ValueError, "clean checkout"):
    verify_clean_checkout(dirty_copy, expected_commit)
self.assertEqual(first["normalized_sha256"], second["normalized_sha256"])
self.assertNotEqual(first["worktree"], second["worktree"])
```

- [ ] **Step 2: Run the verifier unit tests.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_reproducible_build.py -q`

Expected before the repair: the script either has no clean-worktree identity or permits two builds from the same directory.

- [ ] **Step 3: Require two distinct clean copies and record the build provenance.**

```python
def verify_clean_checkout(path: Path, expected_commit: str) -> dict:
    head = git(path, "rev-parse", "HEAD").strip()
    dirty = git(path, "status", "--porcelain=v1").strip()
    if head != expected_commit or dirty:
        raise ValueError("clean checkout does not match source commit")
    return {"checkout_id": sha256(str(path.resolve()).encode()).hexdigest(), "head": head, "clean": True}
```

Build once per copy with the same fixed `SOURCE_DATE_EPOCH`; normalise only permitted sdist metadata before comparing hashes. Never claim dependency hermeticity unless the environment digest is also captured.

- [ ] **Step 4: Execute both CI and local proof paths.**

Run: `.\.venv\Scripts\python.exe tools\verify_reproducible_build.py --source-commit (git rev-parse HEAD) --first <clean-copy-a> --second <clean-copy-b> --out .test-artifacts\reproducible-build.json`

Expected: two distinct clean `HEAD`s match, normalized artifact hashes match, and the report records environment limitations explicitly.

- [ ] **Step 5: Commit the clean-copy gate and update truthful release guidance.**

```powershell
git add tools/verify_reproducible_build.py tests/test_reproducible_build.py .github/workflows/ci.yml docs/runbooks/RELEASE-ADMISSION.md
git commit -m "release: require clean-copy reproducibility evidence"
```

## Task 4: Bind all admission evidence into a provenance ledger

**Files:**

- Modify: `tools/build_release_manifest.py`
- Modify: `tools/promote_release.py`
- Test: `tests/test_release_manifest.py`
- Modify: `docs/runbooks/RELEASE-ADMISSION.md`

**Interfaces:**

- Consumes: commit SHA plus named, hash-verified reports: contracts, recovery, protocol, reproducibility, scanner, and review.
- Produces: one `release-manifest.json` whose entries include `{name, sha256, source_commit, status}` and whose manifest SHA is stable.

- [ ] **Step 1: Write a failing manifest rejection test.**

```python
with self.assertRaisesRegex(ValueError, "source_commit mismatch"):
    build_manifest(source_commit=commit_a, reports=[report_for(commit_b)])
with self.assertRaisesRegex(ValueError, "required evidence missing"):
    build_manifest(source_commit=commit_a, reports=[])
```

- [ ] **Step 2: Run the release-manifest tests.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_release_manifest.py -q`

Expected before the repair: a manifest can be formed from an unbound, failed, or cross-commit report.

- [ ] **Step 3: Enforce named required evidence and canonical hashing.**

```python
REQUIRED_REPORTS = frozenset({"contracts", "mutation-recovery", "protocol-conformance", "reproducible-build", "scanner", "review"})
if {item["name"] for item in reports} != REQUIRED_REPORTS:
    raise ValueError("required evidence missing or duplicated")
```

Reject a report when its own hash fails, its status is not `passed`, or its `source_commit` differs from the candidate. Keep `promote_release.py --dry-run` non-publishing.

- [ ] **Step 4: Verify a valid synthetic ledger and an invalid mixed ledger.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_release_manifest.py tests\test_release_admission.py -q`

Expected: valid same-commit fixtures produce a deterministic manifest; every missing, duplicate, failed, tampered, or mismatched input is blocked.

- [ ] **Step 5: Commit ledger admission hardening.**

```powershell
git add tools/build_release_manifest.py tools/promote_release.py tests/test_release_manifest.py docs/runbooks/RELEASE-ADMISSION.md
git commit -m "release: bind admission evidence to candidate provenance"
```

## Task 5: Make Observatory read-only guarantees independently observable

**Status:** In progress. HTTP-level state-neutrality coverage is implemented for health, snapshot, and activity reads; complete matrix evidence remains required.

**Files:**

- Modify: `habitat/observatory.py`
- Test: `tests/test_observatory.py`
- Modify: `docs/COMPATIBILITY.md`
- Modify: `docs/LIMITATIONS.md`

**Interfaces:**

- Consumes: an Observatory HTTP/SSE read request against an initialized workspace.
- Produces: a projection snapshot; it never calls `HabitatWorkspace.reconcile`, `refresh`, `activity_emit`, a transaction method, or a write-capable SQLite connection.

- [ ] **Step 1: Write a database-snapshot regression test.**

```python
before = "\n".join(workspace.store.conn.iterdump())
response = request_observatory_snapshot(base_url)
self.assertEqual(200, response.status)
self.assertEqual(before, "\n".join(workspace.store.conn.iterdump()))
```

- [ ] **Step 2: Run the read-only Observatory test.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_observatory.py -q`

Expected before the repair: the test fails if an observer endpoint shares the authoritative connection or emits activity while serving a snapshot.

- [ ] **Step 3: Isolate the read model.**

```python
uri = f"file:{quote(str(db_path.resolve()))}?mode=ro&immutable=1"
with sqlite3.connect(uri, uri=True) as connection:
    connection.execute("PRAGMA query_only=ON")
    return project_snapshot(connection)
```

Treat immutable mode as a projection optimisation only after checking WAL/Snapshot semantics; use a fresh read-only connection per request where immutable visibility would be false. Do not catch write failures and continue as if a projection were valid.

- [ ] **Step 4: Verify the endpoint and whole regression matrix.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_observatory.py tests\test_protocol_conformance.py -q`

Then run: `.\.venv\Scripts\python.exe tools\run_test_matrix.py --workers 1 --timeout 180`

Expected: all tests pass and the relevant matrix report records no cleanup or lifecycle failure.

- [ ] **Step 5: Commit the isolated observer proof.**

```powershell
git add habitat/observatory.py tests/test_observatory.py docs/COMPATIBILITY.md docs/LIMITATIONS.md
git commit -m "security: prove observatory reads are state neutral"
```

## Final admission checkpoint

- [ ] Run `python -m compileall habitat tools`.
- [ ] Run the full balanced matrix once on the candidate commit.
- [ ] Run Semgrep/CodeQL according to the existing CI workflow and preserve the commit-bound reports.
- [ ] Build the candidate manifest in dry-run mode and confirm that every required report is same-commit, passed, and hash-valid.
- [ ] Request an independent reviewer to inspect the manifest and candidate diff. Do not create a tag or GitHub Release while this review is missing.

## Coverage review

| Requirement | Implemented by |
| --- | --- |
| Rejected mutation has no hidden durable side effect | Task 1 |
| Hostile requests receive stable protocol envelopes | Task 2 |
| Reproducible build claim is bounded to independent clean copies | Task 3 |
| Promotion consumes only candidate-bound evidence | Task 4 |
| Human observation cannot become a control path | Task 5 |
| No premature release claim | Final admission checkpoint |

The plan intentionally does **not** claim distributed consensus, universal remote-provider correctness, universal semantic precision, or production hostile-code isolation. Those require different authority, implementation, and external evaluation work.
