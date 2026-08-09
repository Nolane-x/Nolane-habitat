# Alpha.5 Research Notes — 2026-08-07

Research was used to discriminate architecture choices, not as proof that Habitat itself achieves the reported external results.

## Repository exploration / context

- **SWE-Explore** (2026, arXiv:2606.07297) evaluates repository exploration at line level under fixed budgets. It reinforces the importance of ranking the *right lines*, not merely finding a relevant file.
- **Agent Retrieval Bench** (2026, arXiv:2607.24882) evaluates multiple retrieval tasks plus no-gold controls and reports that no single retrieval family dominates. The no-gold/calibration setting motivated Habitat's explicit abstention lane.
- **ContextBench** (2026, arXiv:2602.05892) studies explored versus actually utilized context and reports a precision gap. Habitat therefore treats source-byte loading and irrelevant context as first-class costs rather than maximizing recall by default.

Architecture consequence: alpha.5 prioritizes concept coverage, calibration, exact page faults and source-byte accounting over adding a larger indiscriminate index.

## Browser semantics

Playwright's accessibility/ARIA snapshot model supports the principle that web UI can be observed as semantic structure rather than exclusively as screenshots. Habitat still retains pixels as a secondary oracle for genuinely visual defects.

## MCP

The Model Context Protocol specification line current during alpha.5 research is **2026-07-28**. The official Python SDK v2 documentation exposes `MCPServer`, decorated tools/resources and stdio `run()` behavior.

Architecture consequence: Habitat exposes a compact optional MCP adapter while retaining its internal protocol. The release host used to build alpha.5 does not have the MCP package installed; therefore real SDK runtime behavior is a disclosed environment gap, and only the adapter's contract-double integration is locally admitted.

## Research URLs

- https://arxiv.org/abs/2606.07297
- https://arxiv.org/abs/2607.24882
- https://arxiv.org/abs/2602.05892
- https://playwright.dev/docs/aria-snapshots
- https://modelcontextprotocol.io/
