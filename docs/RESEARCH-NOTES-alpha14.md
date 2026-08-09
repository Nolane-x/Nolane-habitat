# Research Notes — Alpha.14 AGI-Control Translation

## Source read
Nolane-AGI Cognitive System 4.0 was treated as an architectural source, not as a label to copy. The most relevant material was the V4 architecture/research plus the world-model, hierarchical-planning, strategy-switching, memory-retrieval and memory-consolidation skill protocols.

## Useful principles retained
- explicit versioned world state with uncertainty/invalidation;
- bounded information gathering instead of endless thinking;
- hierarchical decomposition with verifier-oriented postconditions;
- failure/stagnation detection that changes strategy rather than merely rephrasing;
- negative evidence and failed paths retained for future control decisions;
- close only after an assurance/oracle step, not self-declared completion;
- separate control artifacts from private model reasoning.

## Habitat-specific interpretation
Habitat already possessed source authority, semantic/effect/dataflow/runtime/project/counterfactual worlds, evidence, epistemic records, memory, experiments, transactions and observer telemetry. The missing composition layer was a durable executive trajectory that could bind those artifacts into one inspectable long-horizon control record.

Alpha.14 therefore focuses on orchestration/assurance depth rather than adding another world graph. The key measure of success is not feature count; it is whether stale proof, repeated failure, contradictions and incomplete postconditions can still be mistaken for completion. The new gate is designed to fail closed on those cases.
