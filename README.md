# Nolane Habitat

> Project intelligence for coding agents.

Nolane Habitat gives an agent a durable, revision-aware workspace for understanding and evolving a software project. It combines semantic project context, governed source changes, verification, task checkpoints, an MCP interface, and a read-only Observatory in one local system.

## What Habitat brings to an agent

- **Durable project memory** — a SQLite-backed workspace records source identity, semantic evidence, context, checkpoints, and verification history.
- **Focused semantic context** — agents can start a task, inspect relevant objects, follow references, and continue with bounded context instead of rebuilding understanding from scratch.
- **Governed source evolution** — journaled mutations, source anchors, transaction recovery, and path-scoped verification support deliberate code changes.
- **Live project awareness** — Habitat reconciles source revisions and keeps task context aligned with the working project.
- **Codex-native operation** — an MCP adapter exposes task, context, inspection, change, verification, UI, checkpoint, and resume workflows to Codex.
- **Clear observability** — the loopback Observatory presents project and agent activity through a read-only runtime surface.

## Quick start on Windows

Python 3.10+ is required. Clone the repository, then create a virtual environment with the development, MCP, and Python semantic capabilities:

```powershell
git clone https://github.com/Nolane-x/Nolane-habitat.git
cd Nolane-habitat
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -U "setuptools>=68"
.\.venv\Scripts\python -m pip install -e ".[dev,mcp,python-semantic]"
```

Create a Habitat workspace beside the source project, then orient a task:

```powershell
$source = (Resolve-Path .).Path
$workspace = "$source.habitat"
.\.venv\Scripts\habitat.exe create $source $workspace
.\.venv\Scripts\habitat.exe enter $workspace
.\.venv\Scripts\habitat.exe orient $workspace "map the authentication flow"
```

The workspace is intentionally separate from the source directory, keeping Habitat state independent from the project it understands.

Before handing an existing workspace to an agent, inspect its local state without refreshing or migrating it:

```powershell
.\.venv\Scripts\habitat.exe doctor $workspace
```

The report exposes schema version, SQLite integrity, foreign-key violations, and journal mode so a damaged or stale workspace is visible before it becomes agent context.

Inspect the effective execution boundary before asking an agent to run verification or a provider action:

```powershell
.\.venv\Scripts\habitat.exe capabilities $workspace
```

The report is intentionally conservative. The normal local-process provider is shown as `trusted-local-process`, not as a sandbox; sandbox, network, filesystem, and process-isolation claims appear only when the active provider supplies all required containment evidence.

## Use it with Codex

Register the initialized workspace as an MCP server:

```powershell
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
codex mcp add nolane-habitat -- $python -m habitat.mcp_adapter $workspace --no-open-observatory
codex mcp list
```

Install the bundled Codex skills from the local checkout:

```powershell
$repo = (Resolve-Path .).Path
codex plugin marketplace add $repo
codex plugin add nolane-habitat@personal
```

Start a Codex task with `$nolane-habitat` to use the project workspace, or `$nolane-habitat-maintainer` when improving Habitat itself. The full setup and day-to-day workflow are in [Codex integration](docs/CODEX-INTEGRATION.md).

## A practical development loop

1. Create or open a Habitat workspace for the project.
2. Start a task and gather bounded semantic context.
3. Inspect symbols and references before editing.
4. Apply an authorized source change through the governed workflow.
5. Verify affected paths and checkpoint the result for the next agent.

This loop makes context, changes, evidence, and handoffs durable across longer-running agent work.

## Core surfaces

| Surface | What it provides |
| --- | --- |
| CLI | Workspace creation, health and capability inspection, orientation, mutation, verification, checkpoints, and resume. |
| MCP | Codex tools for task context, source understanding, governed changes, verification, and handoff. |
| Semantic providers | Python and TypeScript project evidence with source anchors and relationship data. |
| Mutation engine | Journaled source writes, rollback support, and recovery-aware transaction handling. |
| Observatory | A loopback, read-only view of project and agent activity. |

## Documentation

- [Install and run Habitat](docs/INSTALLATION.md)
- [Connect Habitat to Codex](docs/CODEX-INTEGRATION.md)
- [Understand execution capability boundaries](docs/security/CAPABILITY-MATRIX.md)
- [Evaluate release admission without publishing](docs/runbooks/RELEASE-ADMISSION.md)
- [Use the agent protocol](docs/AGENT-PROTOCOL.md)
- [Explore the architecture](docs/architecture/ALPHA17-ARCHITECTURE.md)
- [Review the changelog](CHANGELOG.md)

## Verify a checkout

```powershell
.\.venv\Scripts\python tools\run_test_matrix.py --workers 1 --timeout 180
```

Nolane Habitat 0.1.0-alpha.19 is ready for local project cognition, governed agent workflows, and Codex integration.
