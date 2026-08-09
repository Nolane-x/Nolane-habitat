# Codex integration

Nolane Habitat connects a single initialized workspace to Codex through MCP, then adds two portable skills that teach future agents how to use and maintain the system.

## One-time setup on Windows

From the repository checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev,mcp,python-semantic]"

$source = (Resolve-Path .).Path
$workspace = "$source.habitat"
.\.venv\Scripts\habitat.exe create $source $workspace
```

The workspace path is separate from the source path. It holds the durable Habitat state for that project.

## Register the MCP server

Use the virtual environment's Python executable so Codex launches the same verified installation:

```powershell
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
codex mcp add nolane-habitat -- $python -m habitat.mcp_adapter $workspace --no-open-observatory
codex mcp list
```

The adapter exposes these Codex tools:

| Workflow | Tools |
| --- | --- |
| Task and context | `habitat_start_task`, `habitat_context_step` |
| Understanding | `habitat_inspect`, `habitat_references` |
| Source evolution | `habitat_change_symbol`, `habitat_rename_symbol` |
| Verification | `habitat_verify` |
| UI investigation | `habitat_ui_open`, `habitat_ui_act`, `habitat_ui_assert` |
| Handoff | `habitat_checkpoint`, `habitat_resume` |

## Install the skills

For a checkout on this machine:

```powershell
$repo = (Resolve-Path .).Path
codex plugin marketplace add $repo
codex plugin add nolane-habitat@personal
```

For the published release:

```powershell
codex plugin marketplace add Nolane-x/Nolane-habitat --ref v0.1.0-alpha.18
codex plugin add nolane-habitat@personal
```

The plugin supplies:

- `$nolane-habitat` — use a Habitat workspace for grounded project work.
- `$nolane-habitat-maintainer` — change, test, document, package, and release Habitat itself.

## Recommended Codex workflow

1. Start with `$nolane-habitat` and the user's concrete task.
2. Begin with `habitat_start_task`, then inspect returned objects and references.
3. Make only changes authorized by the user and verify the affected paths.
4. Create a checkpoint containing the task goal, evidence, result, and next action.

The MCP workspace adds context and evidence. User scope remains the authority for consequential changes.
