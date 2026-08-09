---
name: nolane-habitat-maintainer
description: Maintain, debug, test, document, package, or release the Nolane Habitat repository. Trigger when work changes Habitat workspace lifecycle, storage, semantic providers, mutation safety, MCP, Observatory, tests, Codex integration, or release artifacts.
---

# Nolane Habitat Maintainer

Use this skill when changing Habitat itself. Start with the narrowest architecture slice that can explain the requested behavior, then verify the change at the relevant boundary.

## Architecture map

- `habitat/workspace.py` is the public workspace façade and lifecycle owner.
- `habitat/storage.py` persists project state in SQLite.
- `habitat/compiler.py` and `habitat/semantic/` build semantic project evidence.
- `habitat/mutation.py` and `habitat/source_bridge.py` apply journaled source changes.
- `habitat/mcp_adapter.py` exposes the workspace through MCP.
- `habitat/observatory.py` and `habitat/observatory_assets/` provide the read-only observatory.
- `tests/` is the behavioral contract; `tools/run_test_matrix.py` runs its balanced test matrix.

## Maintenance workflow

1. Reproduce the failure with the smallest relevant test.
2. Localize the mechanism before changing code; do not substitute a symptom-only workaround.
3. Add or adjust a regression test, make it fail for the known reason, then implement the smallest repair.
4. Run focused tests, then run the matrix for any change that affects workspace, storage, mutation, semantic, MCP, or release behavior.

## Cross-platform rules

- Keep externally visible transaction IDs separate from filesystem directory names; Windows path components cannot contain `:`.
- Close `HabitatWorkspace` instances before deleting their temporary directories. Tests use `tests/support.py` to preserve that lifecycle on Windows.
- Preserve `shell=False` for benchmark agent commands and parse Windows command paths without treating `\` as an escape.

## Release discipline

Keep `VERSION`, `pyproject.toml`, `CHANGELOG.md`, plugin metadata, documentation, and the Git tag aligned. Verify the package with `.[dev,mcp,python-semantic]`, validate the plugin and skills, then publish only the verified commit.
