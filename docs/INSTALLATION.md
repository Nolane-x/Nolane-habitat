# Install Nolane Habitat

Nolane Habitat runs locally with Python 3.10 or newer.

## Development installation

```bash
python -m venv .venv
```

On Windows:

```powershell
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev,mcp,python-semantic]"
```

On macOS or Linux:

```bash
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e '.[dev,mcp,python-semantic]'
```

## Create a project workspace

Create the Habitat state directory beside the source project:

```bash
habitat create ./project ./project.habitat
habitat enter ./project.habitat
habitat orient ./project.habitat "map the login and authentication flow"
```

## Core commands

```bash
habitat refresh ./project.habitat
habitat query ./project.habitat "credential validation"
habitat inspect ./project.habitat <object-id>
```

## Codex

Follow [Codex integration](CODEX-INTEGRATION.md) to register the MCP server and install the bundled skills.
