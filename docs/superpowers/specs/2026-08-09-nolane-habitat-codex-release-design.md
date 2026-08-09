# Nolane Habitat: Codex integration and alpha.18 release

**Status:** approved for implementation by the repository owner on 2026-08-09
**Target:** `0.1.0-alpha.18`

## Purpose

Make Nolane Habitat immediately useful to Codex agents while presenting the
product clearly and truthfully to new users. The release must also repair the
Windows failures found in the fresh test baseline before it is published.

Nolane Habitat already provides a semantic project workspace, bounded task
orientation, inspected source/context handles, governed mutations, verification
plans, checkpoints, and an MCP adapter. This work connects those capabilities
to Codex without inventing a second execution model.

## Decisions

### Deliver a portable Codex plugin and local workstation installation

The repository will include a Codex plugin at
`plugins/nolane-habitat/` with two focused skills:

1. **Nolane Habitat operator** — for an agent working in a project through a
   Habitat workspace. It explains the deliberate workflow:
   create or open a workspace, start a task, use bounded context and inspection
   tools, make governed changes only when authorized, verify affected work, and
   checkpoint durable progress.
2. **Nolane Habitat maintainer** — for an agent changing Nolane Habitat itself.
   It maps the package architecture, identifies the relevant test and release
   commands, and keeps changes aligned with the source-of-truth storage,
   semantic, policy, mutation, and MCP layers.

The plugin makes the system discoverable in future Codex sessions. A
repository-local marketplace at `.agents/plugins/marketplace.json` will make
the published plugin installable from a clone. A concise root `AGENTS.md`
will provide in-repository orientation even when the plugin is not installed.

For this workstation, Codex will be configured with a `nolane-habitat` MCP
server that targets a real Habitat workspace. The configuration will use the
installed Python executable and explicit workspace path, avoiding PATH- and
working-directory-dependent startup.

The server continues to use Habitat's existing contract: it opens one existing
workspace. A setup flow will create that workspace before the MCP server is
registered. This preserves the product's clear source authority and storage
boundaries rather than adding an unbounded dynamic-project broker.

### Make onboarding copy-and-run

The README will expose a short path from clone to useful Codex tools:

1. create a Python environment;
2. install the package with MCP and semantic extras;
3. create a Habitat workspace for the project;
4. register the existing `habitat-mcp-server` command with Codex;
5. restart or open Codex in the project and begin with
   `habitat_start_task`.

A dedicated Codex integration document will contain platform-specific command
examples, the MCP tool map, workspace lifecycle guidance, and the minimal
troubleshooting information needed to recover a local setup. The README will
link to it instead of carrying lengthy operational detail.

### Refresh the README around shipped value

The new README will be product-led and factual:

- a concise statement of the project intelligence and governed workflow it
  offers to coding agents;
- the concrete capability groups currently implemented;
- a short task flow showing how an agent uses the system;
- quick start and Codex setup;
- direct links to architecture, installation, integration, and API/protocol
  documents.

It will remove release-history narration, speculative executive/AGI language,
and long negative-boundary lists from the main page. Detailed technical
boundaries remain in their dedicated documentation, where they are useful
without diluting onboarding. The README and GitHub release notes will be in
English, matching the repository and broad GitHub audience.

### Fix the observed Windows release blockers

The baseline on Python 3.14/Windows produced failures in all seven test shards.
The implementation will repair the following mechanisms and add/retain
regressions for each:

| Finding | Corrective design |
| --- | --- |
| Transaction identifiers contain `:`, which Windows rejects in a directory component. | Keep the public transaction identifier unchanged; map it through one private, deterministic, filesystem-safe directory-name helper before writing journal backups. |
| Concurrent `atomic_write` calls can receive Windows access-denied failures at replacement time. | Preserve unique same-directory temporary files and add a bounded, short retry around the replace operation for transient sharing violations. Cleanup and metadata behavior stay intact. |
| The development test path expects Jedi while `.[dev]` does not install it. | Add the tested semantic provider to the development extra so the default development environment matches its test contract. |
| Tests that keep a workspace alive while a `TemporaryDirectory` exits leave SQLite open on Windows. | Add explicit cleanup only to the affected test lifecycle paths, using the existing `HabitatWorkspace.close()` contract; do not change production storage lifetime merely to mask a test leak. |

No public transaction ID, protocol shape, or source mutation semantics will
change as a result of these fixes.

## Repository shape after the change

```text
AGENTS.md
.agents/plugins/marketplace.json
plugins/
  nolane-habitat/
    .codex-plugin/plugin.json
    skills/
      nolane-habitat/
        SKILL.md
      nolane-habitat-maintainer/
        SKILL.md
docs/
  CODEX-INTEGRATION.md
  superpowers/specs/2026-08-09-nolane-habitat-codex-release-design.md
habitat/
  mutation.py
  source_bridge.py
tests/
  ... focused regression and lifecycle updates ...
```

The exact plugin layout and manifest will follow Codex's current plugin and
skill conventions. The skills will reference repository documentation rather
than duplicate source implementation details that can drift.

## Interaction model

```text
Codex agent
  -> Nolane Habitat operator skill
  -> existing MCP adapter
  -> existing Habitat workspace
  -> bounded orientation / inspect / change / verify / checkpoint
```

Read-oriented operations stay read-only. A change is staged and committed only
through Habitat's existing authorization and verification path. The skill will
not instruct agents to bypass those controls or treat a context answer as
permission for an external action.

## Validation plan

1. Add a focused regression test for safe transaction backup directory mapping.
2. Run the atomic-write concurrency test repeatedly on Windows.
3. Install the development/MCP/semantic dependencies in an isolated
   environment and run the Jedi semantic test.
4. Run each previously failing shard, then the full test matrix serially.
5. Run schema validation and Python compilation checks.
6. Smoke-test the MCP adapter and confirm the registered Codex server is
   visible and starts against the local workspace.
7. Inspect the final Git diff, test output, package metadata, and README links
   before committing and publishing.

## Release plan

- Update package metadata, `VERSION`, and changelog to
  `0.1.0-alpha.18`.
- Commit only reviewed project files; runtime workspaces, SQLite data, virtual
  environments, and generated local state remain ignored.
- Push the completed source to `Nolane-x/Nolane-habitat`.
- Create annotated Git tag `v0.1.0-alpha.18`.
- Publish a GitHub Release with factual notes covering Codex integration,
  portable skills, Windows reliability repairs, and the verified test result.
- Add repository topics that describe the actual product:
  `mcp`, `ai-agents`, `python`, `code-intelligence`, and
  `developer-tools`.

## Non-goals for this release

- Replacing Habitat's existing MCP contract with a multi-project broker.
- Adding unaudited autonomous execution behavior.
- Claiming broad production readiness beyond the verification performed for
  this release.
