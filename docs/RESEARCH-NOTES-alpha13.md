# Alpha.13 Research Notes

## AGI-method consequence

Nolane AGI command-attack and self-audit methods were used as design methodology: sequence/reconnect, stale-state, provenance collision, hostile-input, concurrency, rollback and claim-boundary attacks were turned into regressions. Successful attacks are preserved in `reports/SELF-AUDIT-alpha13.md` rather than erased after fixes.

## Realtime graph/UI consequence

- Kiali demonstrates that motion is useful when tied to real traffic/error signals rather than decorative terminal noise.
- Grafana Node Graph documents scale/layout pressure at hundreds of nodes; Habitat therefore discloses a bounded focus+context projection and clusters omitted state instead of pretending all nodes are visible.
- Pixi/Sigma/WebGL remain candidate renderers when a real frame-time benchmark proves Canvas2D is insufficient. Alpha.13 does not add a frontend build/CDN dependency prematurely.

## Telemetry consequence

OpenTelemetry GenAI semantic-convention material explicitly warns that input/output messages and related content can contain sensitive data. Runtime Twin therefore redacts and bounds telemetry *before* persistence and Observatory projection. Debugger `name/value` pairs require structural redaction, not only sensitive-key regexes.
