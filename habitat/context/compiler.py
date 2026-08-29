from __future__ import annotations

# Preserve the exact alpha.19 compiler implementation as the compatibility base.  This module adds
# only the bounded Learning Plane runtime seam; no learned value becomes source/authority truth.
from . import _compiler_base as _base

for _name, _value in vars(_base).items():
    if _name != "ContextCompiler" and not _name.startswith("__"):
        globals()[_name] = _value

_BaseContextCompiler = _base.ContextCompiler

_LEARNING_GRAPH_DEPTH_HARD_CAP = 2
_LEARNING_MAX_ROOTS_HARD_CAP = 8
_LEARNING_WEIGHT_HARD_CAP = 2.0
_LEARNING_LEXICAL_LANES = frozenset({"lexical"})
_LEARNING_STRUCTURAL_LANES = frozenset({"symbol", "graph"})
_LEARNING_EVIDENCE_LANES = frozenset({"evidence", "diagnostic"})


class ContextCompiler(_BaseContextCompiler):
    """Alpha.19 context compiler with an optional bounded promoted-policy overlay."""

    def _active_learning_context_policy(self):
        learning = getattr(self.workspace, "_learning", None)
        if not callable(learning):
            return None
        return learning().active_context_policy()

    def _runtime_learning_policy(self):
        return getattr(self, "_learning_policy_in_compile", None)

    def _apply_learning_policy_weights(self, candidates: dict[str, dict], policy) -> None:
        """Reweight already-admitted candidates without creating evidence or changing trust."""

        weights = (
            (
                _LEARNING_LEXICAL_LANES,
                min(float(policy.lexical_weight), _LEARNING_WEIGHT_HARD_CAP),
            ),
            (
                _LEARNING_STRUCTURAL_LANES,
                min(float(policy.structural_weight), _LEARNING_WEIGHT_HARD_CAP),
            ),
            (
                _LEARNING_EVIDENCE_LANES,
                min(float(policy.evidence_weight), _LEARNING_WEIGHT_HARD_CAP),
            ),
        )
        for candidate in candidates.values():
            lanes = {
                lane
                for lane in str(candidate.get("lane") or "").split("+")
                if lane
            }
            multiplier = 1.0
            matched = False
            for lane_group, weight in weights:
                if lanes & lane_group:
                    multiplier *= weight
                    matched = True
            if not matched:
                continue
            multiplier = min(multiplier, _LEARNING_WEIGHT_HARD_CAP)
            candidate["score"] = max(
                0.0,
                min(
                    1.5,
                    float(candidate["score"]) * multiplier,
                ),
            )
            candidate["reason"] = (
                str(candidate.get("reason") or "")
                + f"; bounded learning policy multiplier:{multiplier:.6g}"
            )

    def _expand_graph(
        self,
        candidates: dict[str, dict],
        task_class: str,
        max_roots: int = 8,
        depth: int = 2,
    ) -> None:
        policy = self._runtime_learning_policy()
        if policy is not None:
            max_roots = min(
                max_roots,
                int(policy.max_roots),
                _LEARNING_MAX_ROOTS_HARD_CAP,
            )
            depth = min(
                depth,
                int(policy.graph_depth),
                _LEARNING_GRAPH_DEPTH_HARD_CAP,
            )
        return super()._expand_graph(
            candidates,
            task_class,
            max_roots=max_roots,
            depth=depth,
        )

    def _apply_utility_prior(
        self,
        candidates: dict[str, dict],
        task: str,
        agent_id: str | None = None,
    ) -> int:
        policy = self._runtime_learning_policy()
        if policy is not None:
            self._apply_learning_policy_weights(candidates, policy)
        return super()._apply_utility_prior(candidates, task, agent_id)

    def compile(
        self,
        task: str,
        budget: int = 18,
        agent_id: str | None = None,
    ) -> ContextSlice:
        # Preserve the base compiler's exact validation/failure behavior before applying any soft
        # policy cap.  In particular, an invalid caller budget must never become valid by truncation.
        if (
            not isinstance(budget, int)
            or isinstance(budget, bool)
            or budget < 1
            or budget > 200
            or not isinstance(task, str)
            or not task.strip()
        ):
            return super().compile(task, budget, agent_id)

        policy = self._active_learning_context_policy()
        if policy is None:
            return super().compile(task, budget, agent_id)

        effective_budget = min(budget, int(policy.source_prefetch_budget))
        sentinel = object()
        previous = getattr(self, "_learning_policy_in_compile", sentinel)
        self._learning_policy_in_compile = policy
        try:
            result = super().compile(task, effective_budget, agent_id)
        finally:
            if previous is sentinel:
                del self._learning_policy_in_compile
            else:
                self._learning_policy_in_compile = previous

        packet = result.decision_packet
        packet["learning_policy_version"] = policy.version
        packet["learning_policy_fingerprint"] = policy.fingerprint

        # Existing retrieval-confidence abstention remains the hard safety floor.  The learned
        # threshold can only add a conservative abstention recommendation; it can never remove one.
        top_score = float(packet.get("top_candidate_score", 0.0))
        learned_abstention = top_score < float(policy.abstention_threshold)
        if learned_abstention and not bool(packet.get("abstention_recommended")):
            packet["abstention_recommended"] = True
            result.unknowns.append(
                "Active learning policy recommends conservative abstention; "
                "inspect stronger evidence before broad source loading."
            )

        if result.handle is not None:
            stored = self.store.load_json("context_slices", result.handle) or {}
            stored.update(
                {
                    "learning_policy_version": policy.version,
                    "learning_policy_fingerprint": policy.fingerprint,
                    "decision_packet": packet,
                    "unknowns": result.unknowns,
                }
            )
            self.store.save_json("context_slices", result.handle, stored)
        return result
