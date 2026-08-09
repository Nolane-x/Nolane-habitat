# Research Notes — alpha.7

## External signal
2026 repository-agent evaluation increasingly distinguishes line-level localization and context efficiency rather than only file recall. SWE-Explore evaluates ranked code regions under a line budget; ContextBench studies the gap between gathered and actually utilized context; FastContext reports benefits from separating exploration from solver history in its evaluated settings; Agent Retrieval Bench includes no-gold/selective retrieval calibration.

Habitat does **not** import those results as proof of its own performance. They motivate falsifiable interfaces:
- line-budget region exploration;
- zero-source-byte exploration;
- explicit no-gold abstention;
- exact-source page-fault accounting;
- context utilization feedback with uncertainty.

References:
- SWE-Explore, arXiv:2606.07297
- ContextBench, arXiv:2602.05892
- FastContext, arXiv:2606.14066
- Agent Retrieval Bench, arXiv:2607.24882

## Cloudflare Computer boundary
Cloudflare Computer is treated as evidence that persistent workspace/execution substrates are useful, not as a blueprint to clone. Alpha.7 therefore separates SourceAuthority and ExecutionProvider so a future Cloudflare-like backend can sit below Habitat while Semantic Twin, Context VM, Evidence and semantic mutation remain Habitat-owned.

No Cloudflare network adapter is implemented or claimed.

## Rejected hypotheses
1. **Every language provider should keep a persistent project object.** Rejected. Unbounded Jedi Project retention created hidden lifecycle pressure. Alpha.7 uses bounded LRU + persistent semantic partitions; TypeScript keeps a real LanguageService process because its session model is explicit and measurable.
2. **Alpha releases can freely repurpose manifest fields.** Rejected. `source_authority` retained its old string meaning; schema 4 adds new provider fields.
3. **A detached executor can safely write back its checkout implicitly.** Rejected. Source mutation fails closed without an explicit durable write-back contract.
4. **Green unit tests are enough for runtime admission.** Rejected. The full suite exposed shutdown/lifecycle behavior invisible in isolated tests; host-level service cleanup became a first-class API.

## Claim boundary
Alpha.7 establishes deterministic substrate, localization, source-page and provenance plumbing. It does not establish universal token savings, model-quality uplift, coding success superiority, production remote execution safety, or AGI capability.
