# Installation — 0.1.0-alpha.17

Python 3.10+ is required.

```bash
python -m pip install .
```

Optional surfaces are explicit capabilities:

```bash
python -m pip install '.[python-semantic,ui,mcp]'
```

The `ui` extra installs Playwright bindings plus the WebSocket transport used by the continuous CDP AI Operator mirror. Habitat still capability-probes the system Chromium/Chrome executable; a missing browser must report unavailable instead of pretending the UI runtime exists.

## CLI quick start

```bash
habitat create ./project ./project.habitat
habitat enter ./project.habitat
habitat orient ./project.habitat "fix login validation"
```

## Agent server and Observatory

```bash
habitat-agent-server ./project.habitat
```

The agent server may start the read-only Observatory on loopback. Its URL is written to stderr so stdout remains clean NDJSON. Use `--no-open-observatory` or `--no-observatory` when appropriate.

The standalone spectator surface is also available:

```bash
habitat-observatory ./project.habitat --no-open
```

`127.0.0.1`, `localhost`, and `::1` are accepted loopback hosts. IPv6 URLs are emitted in bracketed form such as `http://[::1]:PORT/`.

## MCP

```bash
python -m pip install 'nolane-habitat[mcp]'
habitat-mcp-server ./project.habitat
```

The internal Habitat protocol remains canonical; MCP is a compact adapter rather than a second source of truth.

Core source/workspace operation has no mandatory semantic/browser/MCP dependency. Optional providers are capability-probed and must fail explicitly when unavailable.
