---
name: nolane-habitat
description: Use Nolane Habitat to orient, inspect, change, verify, or checkpoint work in a software project through its MCP workspace. Trigger when a user asks for semantic project context, governed code changes, task checkpoints, or Nolane Habitat MCP tools.
---

# Nolane Habitat

Use Habitat as the project-intelligence layer for a coding task. It gives an agent bounded, revision-aware context; it does not grant permission to alter source, services, accounts, or data.

## Start a task

1. Confirm that the `nolane-habitat` MCP server and its tools are available.
2. Begin with `habitat_start_task` using the user's goal. Keep its returned task and context handles.
3. Use `habitat_context_step` when the task needs more focused context rather than repeatedly broadening source reads.
4. Use `habitat_inspect` for a returned object and `habitat_references` to follow its relationships.

Treat the workspace revision, source anchors, and trust labels as evidence. Ask for authority or follow the user's stated scope before taking a side-effecting action.

## Work with the project

- Use `habitat_change_symbol` or `habitat_rename_symbol` for a scoped source change when the change is authorized.
- Use `habitat_ui_open`, `habitat_ui_act`, and `habitat_ui_assert` only for an authorized local UI investigation.
- Use `habitat_verify` for the affected paths before claiming a change works.
- Use `habitat_checkpoint` to create a durable handoff, and `habitat_resume` to continue it with current-source revalidation.

Prefer the smallest relevant query, inspection, change, and verification set. If Habitat reports stale context, refresh the task context before relying on it.

## When Habitat is not configured

Create a workspace beside the project and register its MCP command using the repository's `docs/CODEX-INTEGRATION.md`. The MCP server needs the path to an existing Habitat workspace; do not point it at a source folder that has not been initialized.

## Good handoff

Before ending a nontrivial task, record the goal, inspected objects, changed paths, verification result, and next action in a checkpoint. This lets the next agent resume from verified project state instead of reconstructing context from memory.
