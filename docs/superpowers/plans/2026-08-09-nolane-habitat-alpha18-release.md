# Nolane Habitat alpha.18 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish Nolane Habitat 0.1.0-alpha.18 with reliable Windows mutation behavior, a product-led onboarding experience, and a reusable Codex plugin with operator and maintainer skills.

**Architecture:** Keep Habitat's existing one-workspace MCP adapter and make it discoverable through a repository plugin, local marketplace installation, root agent guidance, and concise setup documentation. Repair platform-specific behavior at the storage boundary: transaction IDs stay public API values while their on-disk journals use deterministic safe directory names, and atomic replacement retries only transient Windows sharing errors.

**Tech Stack:** Python 3.10+, SQLite, unittest, Jedi, Model Context Protocol SDK v2, Codex plugins/skills, GitHub Releases.

## Global Constraints

- Preserve the public transaction identifier format such as `tx:<hash>`.
- Store all new transaction journal and backup paths below `<workspace>/transactions/` using a deterministic filesystem-safe component.
- Preserve read access to journal directories created by alpha.17 on platforms that allowed the legacy transaction ID component.
- Retry only Windows sharing/access violations with `winerror` 5, 32, or 33; re-raise every other replacement error.
- Keep test cleanup explicit; do not weaken production SQLite lifetime semantics to accommodate a test fixture.
- Keep README and GitHub release copy factual, product-led, English, and free of speculative/unfinished claims.
- Use package version `0.1.0a18`, display version `0.1.0-alpha.18`, plugin version `0.1.0-alpha.18`, and Git tag `v0.1.0-alpha.18`.
- Stage named files and directories only; never use `git add .` or `git add -A`.

---

## File structure and responsibilities

| Path | Responsibility |
| --- | --- |
| `.gitignore` | Keep virtual environments, Habitat workspaces, SQLite files, and local Codex state out of commits. |
| `pyproject.toml` | Package metadata and development dependency contract. |
| `habitat/mutation.py` | Transaction journal/backup path mapping and recovery. |
| `habitat/source_bridge.py` | Atomic file replacement with transient Windows retry. |
| `tests/test_workspace.py` | End-to-end transaction storage regression. |
| `tests/test_alpha17_stability_completion.py` | Deterministic retry and concurrent atomic-write regressions. |
| `tests/test_alpha4_agent_residency.py`, `tests/test_alpha4_schema_contracts.py`, `tests/test_workspace.py` | Explicit close before a temporary directory exits. |
| `tests/test_alpha10_deep_evolution.py`, `tests/test_alpha11_observatory_runtime.py`, `tests/test_alpha12_observatory_cinematic.py`, `tests/test_alpha13_microdepth_resilience.py`, `tests/test_alpha15_ai_operator.py`, `tests/test_alpha16_forensic_nearlive.py` | Cleanup ordering in shared test workspace helpers. |
| `plugins/nolane-habitat/` | Portable Codex plugin and its two skills. |
| `.agents/plugins/marketplace.json` | Repository marketplace entry for the portable plugin. |
| `AGENTS.md` | Concise source-root orientation for agents maintaining Habitat. |
| `docs/CODEX-INTEGRATION.md` | Copy-and-run installation, MCP lifecycle, and tool workflow. |
| `README.md` | Product-led GitHub landing page and quickest-start route. |
| `VERSION`, `CHANGELOG.md` | Version and release record. |

## Task 1: Import a clean baseline and align the development dependency contract

**Files:**

- Create: `.gitignore`
- Modify: `pyproject.toml:16-27`
- Modify: `tests/test_python_jedi.py`

**Interfaces:**

- Consumes: existing optional dependency groups in `pyproject.toml`.
- Produces: a tracked alpha.17 baseline and a `.[dev]` installation that includes `jedi>=0.19,<1`.

- [ ] **Step 1: Write the packaging regression assertion**

Add a small test that reads `pyproject.toml` with the project-supported parser path and asserts the `dev` optional dependency list contains the same `jedi>=0.19,<1` constraint as `python-semantic`. Keep the assertion local to package metadata:

```python
def test_dev_extra_includes_python_semantic_provider():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    self.assertIn('dev = ["jsonschema>=4", "jedi>=0.19,<1"]', text)
```

- [ ] **Step 2: Run the packaging regression before the manifest change**

Run:

```powershell
python -m unittest -q tests.test_python_jedi.PythonJediSemanticTests.test_dev_extra_includes_python_semantic_provider
```

Expected: FAIL because the `dev` group currently contains only `jsonschema>=4`.

- [ ] **Step 3: Add the dependency and repository ignores**

Change the dependency declaration to:

```toml
dev = ["jsonschema>=4", "jedi>=0.19,<1"]
```

Create `.gitignore` with the exact local-state patterns:

```gitignore
.venv/
.habitat/
*.sqlite3
*.sqlite3-*
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/
```

- [ ] **Step 4: Verify the development installation and Jedi semantic behavior**

Run:

```powershell
python -m pip install -e ".[dev,mcp,python-semantic]"
python -c "import jedi; print(jedi.__version__)"
python -m unittest -q tests.test_python_jedi
```

Expected: the metadata assertion and the Jedi semantic tests pass.

- [ ] **Step 5: Create the tracked baseline commit**

Review first:

```powershell
git diff --check
git status --short
```

Stage the explicit source set, excluding runtime files covered by `.gitignore`:

```powershell
git add -- .gitignore CHANGELOG.md README.md VERSION WRITING-PLANS.md artifacts benchmarks docs examples habitat pyproject.toml reports schemas tests tools
git diff --cached --check
git commit -m "chore: import Nolane Habitat alpha.17 baseline"
```

## Task 2: Make transaction persistence filesystem-safe without changing transaction IDs

**Files:**

- Modify: `habitat/mutation.py:153-236`
- Modify: `tests/test_workspace.py:42-48`

**Interfaces:**

- Consumes: `MutationEngine._journal_path(txid: str) -> Path`, journal payload field `transaction_id`, and the public `TransactionRecord.id`.
- Produces: `MutationEngine._transaction_dir(txid: str) -> Path` and backward-compatible journal discovery.

- [ ] **Step 1: Write a failing end-to-end path regression**

Add a test beside `test_transaction_syncs_to_external_source` that commits one replacement and asserts the public ID is retained in the journal while no path component contains a colon:

```python
def test_transaction_journal_uses_filesystem_safe_directory(self):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = self.make_project(root)
        with HabitatWorkspace.create(src, root / "hab") as ws:
            result = ws.change([{
                "op": "replace_text", "path": "auth.py",
                "old": 'password == "secret"',
                "new": 'password == "safer-secret"',
            }])
            journals = list((root / "hab" / "transactions").glob("*/journal.json"))
            self.assertEqual(len(journals), 1)
            self.assertNotIn(":", journals[0].parent.name)
            self.assertEqual(
                json.loads(journals[0].read_text(encoding="utf-8"))["transaction_id"],
                result["id"],
            )
```

Add `import json` beside the existing standard-library imports in the test
module.

- [ ] **Step 2: Run the regression before implementation**

Run:

```powershell
python -m unittest -q tests.test_workspace.WorkspaceTests.test_transaction_journal_uses_filesystem_safe_directory
```

Expected: ERROR on Windows when the old `tx:<hash>` directory is created.

- [ ] **Step 3: Centralize directory mapping in the mutation engine**

Add a deterministic helper using a SHA-256 digest. Keep the original tx ID only in the journal payload and store:

```python
def _transaction_dir(self, txid: str) -> Path:
    digest = hashlib.sha256(txid.encode("utf-8")).hexdigest()
    return self.workspace.habitat_dir / "transactions" / f"tx-{digest}"
```

Add a private legacy lookup that returns
`<workspace>/transactions/<txid>` only when that directory already exists.
Make `_journal_path`, `_backup`, and `_restore_from_journal` use the
same selected directory helper. In `recover_pending`, obtain the transaction
ID from `journal["transaction_id"]`, skip an unreadable/malformed journal,
and never infer the public ID from its safe directory name.

- [ ] **Step 4: Run focused mutation and recovery tests**

Run:

```powershell
python -m unittest -q tests.test_workspace tests.test_alpha8_integrity_cognition
```

Expected: transaction, rollback, and write-ahead recovery tests pass on Windows.

- [ ] **Step 5: Commit the transaction-storage repair**

```powershell
git add -- habitat/mutation.py tests/test_workspace.py
git diff --cached --check
git commit -m "fix: make transaction journals Windows-safe"
```

## Task 3: Retry only transient Windows atomic replacements

**Files:**

- Modify: `habitat/source_bridge.py:102-171`
- Modify: `tests/test_alpha17_stability_completion.py:97-118`

**Interfaces:**

- Consumes: `atomic_write(path: Path, data: bytes) -> None`.
- Produces: `_replace_with_retry(tmp: Path, path: Path) -> None`, called by `atomic_write`.

- [ ] **Step 1: Write a deterministic retry test**

Capture the original `os.replace`, then patch the module-local replacement
function to raise one sharing violation followed by the original replacement:

```python
def test_atomic_write_retries_a_transient_windows_sharing_violation(self):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.txt"
        path.write_bytes(b"seed")
        original_replace = source_bridge.os.replace
        error = PermissionError(13, "Access is denied")
        error.winerror = 32
        with mock.patch(
            "habitat.source_bridge.os.replace",
            side_effect=[error, original_replace],
        ) as replace, mock.patch("habitat.source_bridge.time.sleep") as sleep:
            atomic_write(path, b"updated")
        self.assertEqual(path.read_bytes(), b"updated")
        self.assertEqual(replace.call_count, 2)
        sleep.assert_called_once()
```

Add these exact imports beside the existing imports in the test file:

```python
from unittest import mock
from habitat import source_bridge
```

- [ ] **Step 2: Run the deterministic test before implementation**

Run:

```powershell
python -m unittest -q tests.test_alpha17_stability_completion.Alpha17StabilityCompletionTests.test_atomic_write_retries_a_transient_windows_sharing_violation
```

Expected: FAIL because the first `PermissionError` escapes `atomic_write`.

- [ ] **Step 3: Add a narrow retry helper**

Import `time` and define:

```python
_WINDOWS_REPLACE_RETRY_DELAYS = (0.005, 0.01, 0.02, 0.04, 0.08)

def _replace_with_retry(tmp: Path, path: Path) -> None:
    for delay in (*_WINDOWS_REPLACE_RETRY_DELAYS, None):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or delay is None:
                raise
            time.sleep(delay)
```

Replace only the `os.replace(tmp, path)` call in `atomic_write` with this
helper. Leave unique temporary naming, metadata copying, fsync behavior, and
the final cleanup unchanged.

- [ ] **Step 4: Verify retry and contention behavior**

Run:

```powershell
python -m unittest -q tests.test_alpha17_stability_completion.Alpha17StabilityCompletionTests.test_atomic_write_retries_a_transient_windows_sharing_violation
python -m unittest -q tests.test_alpha17_stability_completion.Alpha17StabilityCompletionTests.test_atomic_write_uses_unique_same_directory_temps_under_concurrency
```

Expected: both tests pass repeatedly on Windows without left-over temporary files.

- [ ] **Step 5: Commit the atomic-write repair**

```powershell
git add -- habitat/source_bridge.py tests/test_alpha17_stability_completion.py
git diff --cached --check
git commit -m "fix: retry transient Windows atomic replacements"
```

## Task 4: Correct Windows test workspace cleanup order

**Files:**

- Modify: `tests/test_alpha4_agent_residency.py:182-189`
- Modify: `tests/test_alpha4_schema_contracts.py:20-30`
- Modify: `tests/test_workspace.py:42-48`
- Modify: `tests/test_alpha10_deep_evolution.py:16-23`
- Modify: `tests/test_alpha11_observatory_runtime.py:18-21`
- Modify: `tests/test_alpha12_observatory_cinematic.py:15-21`
- Modify: `tests/test_alpha13_microdepth_resilience.py:17-22`
- Modify: `tests/test_alpha15_ai_operator.py:23-29`
- Modify: `tests/test_alpha16_forensic_nearlive.py:25-30`

**Interfaces:**

- Consumes: `HabitatWorkspace.close() -> None` and `unittest.TestCase.addCleanup(callable)`.
- Produces: tests that close each workspace before its `TemporaryDirectory.cleanup()` runs.

- [ ] **Step 1: Make direct temporary-directory tests fail-safe**

For direct `with tempfile.TemporaryDirectory()` tests that construct
`ws = HabitatWorkspace.create(...)`, wrap the workspace in its existing
context-manager contract:

```python
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    src = self.make_project(root)
    with HabitatWorkspace.create(src, root / "hab") as ws:
        # existing assertions and transaction work
```

Apply this to the two alpha.4 tests and
`WorkspaceTests.test_transaction_syncs_to_external_source`.

- [ ] **Step 2: Fix helper cleanup ordering**

For a shared helper, register the temporary directory first and the workspace
second because `unittest` runs cleanups LIFO:

```python
td = tempfile.TemporaryDirectory()
self.addCleanup(td.cleanup)
ws = HabitatWorkspace.create(root, habitat)
self.addCleanup(ws.close)
```

Apply this ordering to alpha.10, alpha.11, alpha.12, alpha.15, and alpha.16
helpers. In alpha.13, register those same two cleanups in `make_ws` so every
caller is protected; retained explicit `finally: ws.close(); td.cleanup()`
calls remain valid because both operations are idempotent.

- [ ] **Step 3: Run previously affected tests**

Run:

```powershell
python -m unittest -q tests.test_alpha4_agent_residency tests.test_alpha4_schema_contracts tests.test_alpha10_deep_evolution tests.test_alpha11_observatory_runtime tests.test_alpha12_observatory_cinematic tests.test_alpha13_microdepth_resilience tests.test_alpha15_ai_operator tests.test_alpha16_forensic_nearlive tests.test_workspace
```

Expected: no `WinError 32` is emitted during temporary-directory cleanup.

- [ ] **Step 4: Commit the test lifecycle repair**

```powershell
git add -- tests/test_alpha4_agent_residency.py tests/test_alpha4_schema_contracts.py tests/test_workspace.py tests/test_alpha10_deep_evolution.py tests/test_alpha11_observatory_runtime.py tests/test_alpha12_observatory_cinematic.py tests/test_alpha13_microdepth_resilience.py tests/test_alpha15_ai_operator.py tests/test_alpha16_forensic_nearlive.py
git diff --cached --check
git commit -m "test: close Habitat workspaces before temporary cleanup"
```

## Task 5: Package Codex skills and a repository marketplace

**Files:**

- Create: `plugins/nolane-habitat/.codex-plugin/plugin.json`
- Create: `plugins/nolane-habitat/skills/nolane-habitat/SKILL.md`
- Create: `plugins/nolane-habitat/skills/nolane-habitat/agents/openai.yaml`
- Create: `plugins/nolane-habitat/skills/nolane-habitat-maintainer/SKILL.md`
- Create: `plugins/nolane-habitat/skills/nolane-habitat-maintainer/agents/openai.yaml`
- Create: `.agents/plugins/marketplace.json`

**Interfaces:**

- Consumes: the existing MCP tool catalog in `habitat/mcp_adapter.py` and stable documentation under `docs/`.
- Produces: plugin `nolane-habitat`, marketplace `nolane-habitat`, and skills automatically discoverable after Codex plugin installation.

- [ ] **Step 1: Scaffold the plugin with the maintained generator**

Run the plugin creator with a repository-local marketplace because GitHub
distribution is an explicit release goal:

```powershell
python C:\Users\admin\.codex\skills\.system\plugin-creator\scripts\create_basic_plugin.py nolane-habitat --path .\plugins --marketplace-path .\.agents\plugins\marketplace.json --with-skills --with-marketplace
```

The maintained scaffold seeds the new repository marketplace with the default
`personal` name, because no personal marketplace exists on this workstation.
Do not pass a custom marketplace name or overwrite a pre-existing entry.

- [ ] **Step 2: Write the operator skill**

Use only the two required frontmatter fields:

```yaml
---
name: nolane-habitat
description: Use Nolane Habitat to orient, inspect, change, verify, or checkpoint work in a software project through its MCP workspace. Trigger when a user asks to use Habitat, semantic project context, governed code changes, task checkpoints, or the Nolane Habitat MCP tools.
---
```

In imperative prose, direct the agent to:

1. verify the `nolane-habitat` MCP tools are available;
2. call `habitat_start_task` before broad source reading;
3. use the returned handles with context, inspect, and references tools;
4. stage/commit a source change only under the surrounding task's authority;
5. call `habitat_verify` for changed paths;
6. create a checkpoint when handing off or compacting context;
7. explain how to create an existing Habitat workspace if the MCP server is
   not registered.

Add an `agents/openai.yaml` using only interface metadata and
`allow_implicit_invocation: true`; its default prompt must mention
`$nolane-habitat`.

- [ ] **Step 3: Write the maintainer skill**

Use this exact trigger-oriented frontmatter:

```yaml
---
name: nolane-habitat-maintainer
description: Maintain, debug, test, document, package, or release the Nolane Habitat repository. Use when changing Habitat's workspace, storage, semantic, policy, mutation, MCP, observatory, tests, Codex integration, or release artifacts.
---
```

Map these implementation boundaries in concise bullets:

- `habitat/workspace.py`: façade and lifecycle;
- `habitat/storage.py`: SQLite persistence;
- `habitat/compiler.py` and `habitat/semantic/`: project cognition;
- `habitat/mutation.py` and `habitat/source_bridge.py`: governed change;
- `habitat/mcp_adapter.py`: Codex-facing MCP server;
- `tests/` and `tools/run_test_matrix.py`: release verification.

Require focused tests before a full matrix, an explicit workspace close in
temporary tests, and product-led documentation that names only shipped
capabilities. Generate matching `agents/openai.yaml` metadata with a prompt
that mentions `$nolane-habitat-maintainer`.

- [ ] **Step 4: Set factual manifest and marketplace metadata**

Set the manifest to this complete strict-semver and factual metadata, retaining
no empty scaffold fields:

```json
{
  "name": "nolane-habitat",
  "version": "0.1.0-alpha.18",
  "description": "Semantic project intelligence and governed workflow for Codex agents.",
  "author": {
    "name": "Nolane-x",
    "email": "noreply@github.com",
    "url": "https://github.com/Nolane-x"
  },
  "homepage": "https://github.com/Nolane-x/Nolane-habitat",
  "repository": "https://github.com/Nolane-x/Nolane-habitat",
  "license": "Proprietary",
  "keywords": ["mcp", "ai-agents", "code-intelligence", "python"],
  "skills": "./skills/",
  "interface": {
    "displayName": "Nolane Habitat",
    "shortDescription": "Project intelligence for Codex agents",
    "longDescription": "Bounded semantic project context and governed development workflows for Codex agents.",
    "developerName": "Nolane-x",
    "category": "Productivity",
    "capabilities": ["Skills"],
    "defaultPrompt": [
      "Use Nolane Habitat to orient this task and verify the affected code."
    ]
  }
}
```

Keep `mcpServers` out of the manifest because the existing server needs a
user-selected workspace path.

- [ ] **Step 5: Validate skills and plugin**

Run:

```powershell
python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\plugins\nolane-habitat\skills\nolane-habitat
python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\plugins\nolane-habitat\skills\nolane-habitat-maintainer
python C:\Users\admin\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .\plugins\nolane-habitat
```

Expected: all three validators return success with no placeholder text.

- [ ] **Step 6: Commit the portable Codex package**

```powershell
git add -- .agents/plugins/marketplace.json plugins/nolane-habitat
git diff --cached --check
git commit -m "feat: add Nolane Habitat Codex plugin"
```

## Task 6: Add in-repository agent guidance and Codex installation documentation

**Files:**

- Create: `AGENTS.md`
- Create: `docs/CODEX-INTEGRATION.md`
- Modify: `docs/INSTALLATION.md`

**Interfaces:**

- Consumes: package scripts `habitat`, `habitat-mcp-server`, and the twelve tools from `habitat.mcp_adapter.tool_catalog`.
- Produces: an agent can install the package, create a workspace, register an MCP server, install the plugin, and use its tool lifecycle without relying on hidden local state.

- [ ] **Step 1: Write source-root AGENTS.md**

Keep it under 150 lines. Include the architecture map from the maintainer
skill, source-of-truth locations, the required fast-to-full verification
sequence, and these constraints:

```text
Use a Habitat workspace for project cognition; do not treat context as authorization.
Close every HabitatWorkspace created by tests or scripts.
Keep transaction IDs public and filesystem paths private.
Use the MCP adapter against an existing workspace.
```

- [ ] **Step 2: Write copy-and-run Codex instructions**

Document these command shapes with concrete placeholders and Windows/POSIX
variants:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,mcp,python-semantic]"
.\.venv\Scripts\habitat create <project-path> <project-path>\.habitat
codex mcp add nolane-habitat -- <absolute-venv-python> -m habitat.mcp_adapter <absolute-workspace> --no-open-observatory
codex plugin marketplace add Nolane-x/Nolane-habitat --ref v0.1.0-alpha.18
codex plugin add nolane-habitat@personal
```

Explain that the MCP server binds to the named workspace, that a project uses
its own `.habitat` directory, and that a fresh Codex task loads newly
installed plugin skills.

- [ ] **Step 3: Document the actual MCP workflow**

List the twelve currently exported tools and provide a short normal flow:

```text
habitat_start_task -> habitat_context_step / habitat_inspect / habitat_references
-> habitat_change_symbol or habitat_rename_symbol -> habitat_verify
-> habitat_checkpoint -> habitat_resume
```

Describe `habitat_ui_*` as UI/runtime tools and make no claim that they are
required for every task.

- [ ] **Step 4: Verify command paths and document links**

Run:

```powershell
python -m habitat.mcp_adapter --help
codex mcp add --help
codex plugin marketplace add --help
codex plugin add --help
```

Check all local Markdown links resolve and each command uses an installed
console command or `python -m` entry point.

- [ ] **Step 5: Commit the agent onboarding documentation**

```powershell
git add -- AGENTS.md docs/CODEX-INTEGRATION.md docs/INSTALLATION.md
git diff --cached --check
git commit -m "docs: add Codex onboarding workflow"
```

## Task 7: Rewrite the public README and prepare release metadata

**Files:**

- Modify: `README.md`
- Modify: `VERSION`
- Modify: `pyproject.toml:6-8`
- Modify: `CHANGELOG.md`

**Interfaces:**

- Consumes: verified capability names, installation commands, and release version.
- Produces: a concise public landing page and internally consistent alpha.18 metadata.

- [ ] **Step 1: Replace README release-history copy with product-led content**

Use this section order:

```markdown
# Nolane Habitat

## Project intelligence for coding agents
## What Habitat gives an agent
## A governed development loop
## Quick start
## Use with Codex
## Architecture and documentation
```

Describe only shipped capabilities: semantic workspace, bounded task context,
source inspection/references, governed mutations, verification/checkpoints,
MCP tools, and Observatory. Link to `docs/CODEX-INTEGRATION.md`,
`docs/INSTALLATION.md`, `docs/IMPLEMENTATION-STATUS.md`, and
`docs/AGENT-PROTOCOL.md`. Do not include alpha chronology, speculative
executive/AGI framing, roadmap promises, or a list of missing features.

- [ ] **Step 2: Update version sources**

Set:

```text
VERSION: 0.1.0-alpha.18
pyproject project.version: 0.1.0a18
```

Add one `0.1.0-alpha.18` changelog section dated 2026-08-09 with factual
entries for Codex plugin/skills, Windows mutation reliability, development
dependency alignment, and fresh verification.

- [ ] **Step 3: Review public copy for truthfulness**

Run:

```powershell
rg -n -i "not implemented|future work|roadmap|AGI|executive trajectory|coming soon" README.md
rg -n "0\.1\.0-alpha\.17|0\.1\.0a17" README.md VERSION pyproject.toml CHANGELOG.md
```

Expected: README has none of the excluded negative/speculative phrases; version
references use alpha.18 except intentionally preserved historical changelog
entries.

- [ ] **Step 4: Commit release-facing documentation and metadata**

```powershell
git add -- README.md VERSION pyproject.toml CHANGELOG.md
git diff --cached --check
git commit -m "docs: present Nolane Habitat alpha.18"
```

## Task 8: Install locally, verify the full release, publish, tag, and release

**Files:**

- Modify local Codex configuration through `codex mcp add`, `codex plugin marketplace add`, and `codex plugin add`; do not hand-edit unrelated configuration.
- Create: Git commit/tag and GitHub Release in `Nolane-x/Nolane-habitat`.

**Interfaces:**

- Consumes: completed source commits, packaged plugin, an installed `.[dev,mcp,python-semantic]` environment, and the authorized `Nolane-x/Nolane-habitat` remote.
- Produces: a public `main` branch, `v0.1.0-alpha.18` tag, GitHub Release, repository topics, and local usable Codex integration.

- [ ] **Step 1: Create a local workspace and register the MCP server**

Use absolute paths and the current environment:

```powershell
$source = (Resolve-Path .).Path
$workspace = Join-Path $source ".habitat"
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
& $python -m habitat.cli create $source $workspace
codex mcp add nolane-habitat -- $python -m habitat.mcp_adapter $workspace --no-open-observatory
codex mcp list
```

Expected: `nolane-habitat` appears in the MCP list. If a prior server with
that exact name exists, inspect it and replace only that named entry using the
Codex MCP command path.

- [ ] **Step 2: Install the repository plugin locally**

Register the source repository as the default-named marketplace, then install
exactly its plugin:

```powershell
$repo = (Resolve-Path .).Path
codex plugin marketplace add $repo
codex plugin add nolane-habitat@personal
codex plugin list
```

Expected: the marketplace and `nolane-habitat` plugin are listed. Start a new
Codex task after installation to exercise skill discovery.

- [ ] **Step 3: Run release verification**

Run:

```powershell
python -m compileall -q habitat tests tools
python tools/run_test_matrix.py --workers 1 --timeout 180 --out $env:TEMP\nolane-habitat-alpha18-matrix.json
python -m habitat.mcp_adapter --help
python C:\Users\admin\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .\plugins\nolane-habitat
```

Expected: compilation succeeds, every matrix group passes, MCP help exits
successfully, and plugin validation succeeds.

- [ ] **Step 4: Inspect the release candidate**

Run:

```powershell
git status --short
git log --oneline --decorate -8
git diff main~1..main --check
git ls-files | rg "\.habitat|\.venv|habitat\.sqlite3"
```

Expected: no runtime workspace, virtual environment, or SQLite state is
tracked; every working-tree file is committed before publishing.

- [ ] **Step 5: Publish source, tag, release, and topics**

Configure the empty authorized remote, push `main`, and create the annotated
tag:

```powershell
git remote add origin https://github.com/Nolane-x/Nolane-habitat.git
git push -u origin main
git tag -a v0.1.0-alpha.18 -m "Nolane Habitat v0.1.0-alpha.18"
git push origin v0.1.0-alpha.18
```

Create a GitHub Release titled `Nolane Habitat v0.1.0-alpha.18` whose body
states:

```markdown
Nolane Habitat alpha.18 brings its semantic project workspace and governed
development loop directly into Codex through a portable plugin, operator and
maintainer skills, and a documented MCP setup flow.

Highlights:
- Codex plugin and skills for task orientation, inspection, governed changes,
  verification, and checkpoints.
- Fast setup documentation for a project-scoped Habitat MCP workspace.
- Windows-safe transaction journal storage and resilient concurrent atomic file
  replacement.
- Development dependency alignment for the Python semantic provider.
```

Set repository topics to `mcp`, `ai-agents`, `python`,
`code-intelligence`, and `developer-tools`. Read back the pushed tag,
release URL, release target, and topics before reporting completion.
