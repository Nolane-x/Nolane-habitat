# Foundation Convergence Wave 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a machine-checked truth baseline for alpha.19 before changing Habitat's semantic or cognitive architecture.

**Architecture:** Wave 0 extends the existing release-identity/truth-core pipeline rather than creating a parallel validation stack. It fixes current-document drift, records a reproducible foundation benchmark snapshot, and keeps every change outside runtime source-authority/mutation semantics.

**Tech Stack:** Python 3.10+, `unittest`, existing Habitat CLI/workspace APIs, GitHub Actions, JSON evidence artifacts.

**Spec:** `docs/design/FOUNDATION-CONVERGENCE.md`

## Global Constraints

- Baseline is `0.1.0-alpha.19` at commit `5a676f7b542e6b71465047804dfa57e3056988e5`.
- Canonical source files remain executable truth.
- Existing public protocol method names and the 12-tool MCP surface remain unchanged.
- Existing alpha.19 workspaces must remain readable; Wave 0 performs no storage migration.
- Existing read-only operations remain logically state-neutral.
- Mutation journaling, recovery, path identity, approval, lease, and revision semantics are not changed in Wave 0.
- CI remains Windows + Ubuntu and Python 3.10 + 3.14 compatible.

---

## File Structure

Wave 0 intentionally changes few files:

- `tools/check_release_identity.py` — extend the existing identity checker to validate designated current documents and current local Markdown links.
- `tests/test_release_identity_consistency.py` — focused TDD coverage for current-document identity and broken-link detection.
- `docs/IMPLEMENTATION-STATUS.md` — correct the current release heading/status wording from alpha.17 to alpha.19 without rewriting historical capability claims.
- `docs/LIMITATIONS.md` — correct current release heading/scope wording from alpha.17 to alpha.19 while preserving the limitations themselves.
- `README.md` — replace the broken current architecture link with the Foundation Convergence design link while retaining historical architecture documents.
- `benchmarks/foundation_baseline.py` — deterministic local baseline collector for cold ingest, warm reconcile, context orientation, semantic provider report, and database size.
- `tests/test_foundation_baseline.py` — contract tests for the baseline collector and JSON schema.
- `.github/workflows/ci.yml` — run the foundation baseline in CI and upload its artifact; do not make benchmark thresholds release-blocking in the first Wave 0 commit.
- `docs/runbooks/REPOSITORY-GOVERNANCE.md` — document the required repository ruleset/status-check configuration separately from runtime code.

---

### Task 1: Strengthen current-release identity checking

**Files:**
- Modify: `tools/check_release_identity.py`
- Create: `tests/test_release_identity_consistency.py`

**Interfaces:**
- Consumes: `check_identity(root: Path, *, source_commit: str | None = None) -> dict`
- Produces: the same public function/signature and report keys, plus deterministic `current_documents` and `broken_links` fields.

- [ ] **Step 1: Write failing tests for current document version drift**

Create `tests/test_release_identity_consistency.py` with a temporary minimal checkout fixture. The fixture must include `VERSION`, `pyproject.toml`, `habitat/__init__.py`, `CHANGELOG.md`, plugin metadata, README, implementation status, and limitations.

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.check_release_identity import check_identity


class ReleaseIdentityConsistencyTests(unittest.TestCase):
    def _root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "habitat").mkdir()
        (root / "plugins/nolane-habitat/.codex-plugin").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "VERSION").write_text("0.1.0-alpha.19\n", encoding="utf-8")
        (root / "pyproject.toml").write_text('version = "0.1.0a19"\n', encoding="utf-8")
        (root / "habitat/__init__.py").write_text('__version__ = "0.1.0-alpha.19"\n', encoding="utf-8")
        (root / "CHANGELOG.md").write_text("## 0.1.0-alpha.19\n", encoding="utf-8")
        (root / "plugins/nolane-habitat/.codex-plugin/plugin.json").write_text(
            json.dumps({"version": "0.1.0-alpha.19"}), encoding="utf-8"
        )
        (root / "README.md").write_text(
            "Nolane Habitat 0.1.0-alpha.19\n[Design](docs/design/FOUNDATION-CONVERGENCE.md)\n",
            encoding="utf-8",
        )
        (root / "docs/IMPLEMENTATION-STATUS.md").write_text(
            "# Implementation Status — 0.1.0-alpha.19\n", encoding="utf-8"
        )
        (root / "docs/LIMITATIONS.md").write_text(
            "# Habitat 0.1.0-alpha.19 Limitations and Claim Boundary\n", encoding="utf-8"
        )
        (root / "docs/design").mkdir()
        (root / "docs/design/FOUNDATION-CONVERGENCE.md").write_text("# Design\n", encoding="utf-8")
        return td, root

    def test_current_documents_must_match_version(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        (root / "docs/LIMITATIONS.md").write_text(
            "# Habitat 0.1.0-alpha.17 Limitations and Claim Boundary\n", encoding="utf-8"
        )
        report = check_identity(root)
        self.assertFalse(report["ok"])
        self.assertTrue(any("docs/LIMITATIONS.md" in error for error in report["errors"]))

    def test_current_local_markdown_link_must_exist(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        (root / "README.md").write_text(
            "Nolane Habitat 0.1.0-alpha.19\n[Design](docs/design/MISSING.md)\n",
            encoding="utf-8",
        )
        report = check_identity(root)
        self.assertFalse(report["ok"])
        self.assertIn("docs/design/MISSING.md", report["broken_links"])
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
python -m unittest -v tests.test_release_identity_consistency
```

Expected: both tests fail because `check_identity` currently checks only README as a current document and does not expose/validate local Markdown links.

- [ ] **Step 3: Extend the identity checker without changing its CLI contract**

Replace `CURRENT_DOCUMENTS` with exact designated current-document patterns:

```python
CURRENT_DOCUMENTS = {
    "README.md": lambda version: f"Nolane Habitat {version}",
    "docs/IMPLEMENTATION-STATUS.md": lambda version: f"Implementation Status — {version}",
    "docs/LIMITATIONS.md": lambda version: f"Habitat {version} Limitations and Claim Boundary",
}
LOCAL_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
```

Add a pure helper:

```python
def _broken_local_markdown_links(root: Path, relative: str, content: str) -> list[str]:
    base = (root / relative).parent
    broken: list[str] = []
    for raw in LOCAL_MARKDOWN_LINK.findall(content):
        target = raw.split("#", 1)[0].strip()
        if not target:
            continue
        candidate = (base / target).resolve()
        if root != candidate and root not in candidate.parents:
            broken.append(raw)
            continue
        if not candidate.exists():
            broken.append(raw)
    return sorted(set(broken))
```

Update `check_identity` to collect deterministic `current_documents` and `broken_links` fields. Only scan the designated current documents for local-link correctness in Wave 0; historical docs are not required to have every old link remain live.

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
python -m unittest -v tests.test_release_identity_consistency
```

Expected: PASS.

- [ ] **Step 5: Run existing release-identity and contract coverage**

Run:

```bash
python tools/check_release_identity.py
python -m unittest -q
```

Expected before Task 2: `check_release_identity.py` should now fail only for real current-document drift/broken current link(s) in the repository, proving the new gate detects the existing inconsistency. The full suite may therefore fail through identity-specific tests until Task 2 fixes current docs; no unrelated regression is acceptable.

- [ ] **Step 6: Commit**

```bash
git add tools/check_release_identity.py tests/test_release_identity_consistency.py
git commit -m "test: enforce current release document truth"
```

---

### Task 2: Repair alpha.19 current-document truth

**Files:**
- Modify: `docs/IMPLEMENTATION-STATUS.md`
- Modify: `docs/LIMITATIONS.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the stricter `check_identity` contract from Task 1.
- Produces: current documents that identify alpha.19 consistently and contain no broken designated current links.

- [ ] **Step 1: Update only the current release identity headings**

Change:

```markdown
# Implementation Status — 0.1.0-alpha.17
```

to:

```markdown
# Implementation Status — 0.1.0-alpha.19
```

Change:

```markdown
# Habitat 0.1.0-alpha.17 Limitations and Claim Boundary
```

to:

```markdown
# Habitat 0.1.0-alpha.19 Limitations and Claim Boundary
```

Do not silently reinterpret historical sections; the body remains a truthful limitations/status description unless a sentence explicitly claims alpha.17 is the current release.

- [ ] **Step 2: Replace the broken README current architecture link**

Replace the current link to nonexistent `docs/architecture/ALPHA17-ARCHITECTURE.md` with:

```markdown
- [Foundation Convergence architecture](docs/design/FOUNDATION-CONVERGENCE.md)
```

Historical alpha architecture documents remain untouched.

- [ ] **Step 3: Verify the new truth gate passes**

Run:

```bash
python tools/check_release_identity.py
python -m unittest -v tests.test_release_identity_consistency
```

Expected: PASS, `broken_links` is empty.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/IMPLEMENTATION-STATUS.md docs/LIMITATIONS.md
git commit -m "docs: align current alpha19 truth surfaces"
```

---

### Task 3: Add deterministic foundation baseline evidence

**Files:**
- Create: `benchmarks/foundation_baseline.py`
- Create: `tests/test_foundation_baseline.py`

**Interfaces:**
- Produces CLI:

```text
python benchmarks/foundation_baseline.py --repo <project> --out <json> [--task <text>]
```

- Produces schema `foundation-baseline.v1` with top-level keys `schema`, `suite`, `source`, `cold_ingest`, `warm_reconcile`, `orientation`, `semantic_fabric`, `storage`, and `claim_boundary`.

- [ ] **Step 1: Write the failing baseline contract test**

Create a tiny Python project in a temporary directory and invoke a pure `collect_baseline(repo: Path, task: str) -> dict` function.

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.foundation_baseline import collect_baseline


class FoundationBaselineTests(unittest.TestCase):
    def test_collects_cold_warm_context_and_storage_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            report = collect_baseline(root, "understand add")
            self.assertEqual(report["schema"], "foundation-baseline.v1")
            self.assertEqual(report["suite"], "foundation-baseline")
            self.assertGreaterEqual(report["cold_ingest"]["wall_ms"], 0)
            self.assertGreaterEqual(report["warm_reconcile"]["wall_ms"], 0)
            self.assertIn("available_count", report["semantic_fabric"])
            self.assertGreater(report["storage"]["sqlite_bytes"], 0)
            self.assertEqual(report["orientation"]["task"], "understand add")
```

- [ ] **Step 2: Verify the test fails**

Run:

```bash
python -m unittest -v tests.test_foundation_baseline
```

Expected: FAIL because `benchmarks.foundation_baseline` does not exist.

- [ ] **Step 3: Implement the collector using public Workspace operations**

Implement `collect_baseline` so it:

1. creates a temporary Habitat workspace outside the source root;
2. measures `HabitatWorkspace.create(...)` wall time as cold ingest;
3. records revision/file/symbol counts from public/store read methods without mutating source;
4. calls `ws.reconcile()` once after cold ingest and measures warm reconcile;
5. calls `ws.orient(task, budget=18)` and records context object count, handle, and decision packet metadata that is already public;
6. calls `ws.semantic_fabric()` and records the provider report;
7. records SQLite file size;
8. closes the workspace before temporary-directory cleanup;
9. returns durations as measurements, not pass/fail claims.

Use `time.perf_counter_ns()` and convert to integer milliseconds. The report's `claim_boundary` must state that a single baseline run is descriptive evidence, not a performance superiority claim.

- [ ] **Step 4: Run focused test repeatedly**

Run:

```bash
python -m unittest -v tests.test_foundation_baseline
python -m unittest -v tests.test_foundation_baseline
python -m unittest -v tests.test_foundation_baseline
```

Expected: all three runs PASS, proving deterministic schema/lifecycle even though timing values vary.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/foundation_baseline.py tests/test_foundation_baseline.py
git commit -m "bench: add foundation baseline evidence"
```

---

### Task 4: Integrate baseline evidence into CI without premature performance gates

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `docs/runbooks/REPOSITORY-GOVERNANCE.md`

**Interfaces:**
- Consumes: `benchmarks/foundation_baseline.py` from Task 3.
- Produces: `.test-artifacts/foundation-baseline.json` in every CI lane.

- [ ] **Step 1: Add a CI baseline collection step after release identity**

Add:

```yaml
      - name: Collect foundation baseline evidence
        run: python benchmarks/foundation_baseline.py --repo . --task "map Habitat release identity and semantic foundation" --out .test-artifacts/foundation-baseline.json
```

Do not add timing thresholds in Wave 0. A slower Windows runner is not evidence of a Habitat regression by itself.

- [ ] **Step 2: Document required repository rules**

Create `docs/runbooks/REPOSITORY-GOVERNANCE.md` with the exact desired `main` policy:

```markdown
# Repository Governance

For `main`, repository settings should require pull requests and the successful Habitat CI + Habitat CodeQL checks before merge. Force pushes and branch deletion should be blocked. Stable releases require independent review; alpha prereleases may follow the documented owner-authorized path only when all technical evidence gates are commit-bound and successful.

The repository settings are an external authority surface: code and documentation may describe the intended policy, but Habitat must not claim a rule is active unless GitHub reports it active.
```

Also state that this runbook is descriptive until the GitHub ruleset API/settings confirm enforcement.

- [ ] **Step 3: Compile and run local matrix**

Run:

```bash
python -m compileall -q habitat tests tools benchmarks
python tools/check_release_identity.py
python -m unittest discover -q
python tools/run_test_matrix.py --workers 1 --timeout 180
```

Expected: all completed suites PASS. If the local environment lacks optional UI/MCP dependencies, use the repository's documented dev installation before treating missing optional dependencies as product failures.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml docs/runbooks/REPOSITORY-GOVERNANCE.md
git commit -m "ci: record foundation truth baseline"
```

---

## Wave 0 Completion Gate

Before Wave 1 begins, collect and retain evidence that:

- `check_release_identity.py` passes and reports no current broken links;
- current docs identify alpha.19 consistently;
- focused new tests pass;
- full regression and isolated matrix pass;
- CI produces a `foundation-baseline.json` artifact on Windows/Ubuntu and Python 3.10/3.14;
- no storage schema version changed;
- no protocol/MCP method changed;
- no source mutation, recovery, security, or authority semantic changed;
- repository governance documentation does not claim enforcement until the GitHub ruleset is actually observed as enabled.

The resulting baseline becomes the comparison point for Semantic Fabric V2 in Wave 1.
