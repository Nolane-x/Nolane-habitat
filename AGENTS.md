# Nolane Habitat contributor guide

## Project map

- `habitat/workspace.py` is the public workspace façade and lifecycle owner.
- `habitat/storage.py` owns SQLite persistence.
- `habitat/compiler.py` and `habitat/semantic/` produce project evidence.
- `habitat/mutation.py` and `habitat/source_bridge.py` manage journaled source changes.
- `habitat/mcp_adapter.py` exposes the MCP surface.
- `habitat/observatory.py` and `habitat/observatory_assets/` build the read-only observatory.
- `tests/` defines behavioral contracts; `tools/run_test_matrix.py` runs the complete balanced matrix.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,mcp,python-semantic]"
.\.venv\Scripts\python tools\run_test_matrix.py --workers 1 --timeout 180
```

Run a focused `unittest` module before the full matrix when changing a narrow behavior.

## Engineering rules

- Keep an external transaction ID separate from its filesystem directory name; Windows path components cannot contain `:`.
- Close every `HabitatWorkspace` before deleting its backing temporary directory.
- Preserve the distinction between context evidence and authority to mutate a project.
- Keep MCP workspace configuration explicit: `habitat.mcp_adapter` accepts an existing Habitat workspace path.
- Add a regression test before repairing a behavior, then verify focused and matrix coverage.

## Codex distribution

The portable plugin is in `plugins/nolane-habitat/`; its marketplace entry is `.agents/plugins/marketplace.json`. Validate both skills and the plugin after edits, then keep `VERSION`, `pyproject.toml`, `CHANGELOG.md`, plugin metadata, and the release tag aligned.
