from __future__ import annotations

# Keep the exact alpha.19 implementation as the compatibility base.  The subclass below changes
# only active promoted-policy compilation; with no active Learning Plane policy it delegates
# directly to the preserved base implementation.
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

    def _apply_learning_policy_weights(self, candidates: dict[str, dict], policy) -> None:
        """Boundedly reweight already-admitted candidate lanes without creating evidence."""

        weights = (
            (_LEARNING_LEXICAL_LANES, min(float(policy.lexical_weight), _LEARNING_WEIGHT_HARD_CAP)),
            (_LEARNING_STRUCTURAL_LANES, min(float(policy.structural_weight), _LEARNING_WEIGHT_HARD_CAP)),
            (_LEARNING_EVIDENCE_LANES, min(float(policy.evidence_weight), _LEARNING_WEIGHT_HARD_CAP)),
        )
        for candidate in candidates.values():
            lanes = {lane for lane in str(candidate.get("lane") or "").split("+") if lane}
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
                min(1.5, float(candidate["score"]) * multiplier),
            )
            candidate["reason"] = (
                str(candidate.get("reason") or "")
                + f"; bounded learning policy multiplier:{multiplier:.6g}"
            )

    def compile(self, task: str, budget: int = 18, agent_id: str | None = None) -> ContextSlice:
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1 or budget > 200:
            raise ValueError("budget must be in [1, 200]")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        learning_policy = self._active_learning_context_policy()
        if learning_policy is None:
            return super().compile(task, budget, agent_id)
        effective_budget = budget
        graph_max_roots = _LEARNING_MAX_ROOTS_HARD_CAP
        graph_depth = _LEARNING_GRAPH_DEPTH_HARD_CAP
        if learning_policy is not None:
            effective_budget = min(budget, learning_policy.source_prefetch_budget)
            graph_max_roots = min(
                learning_policy.max_roots,
                _LEARNING_MAX_ROOTS_HARD_CAP,
            )
            graph_depth = min(
                learning_policy.graph_depth,
                _LEARNING_GRAPH_DEPTH_HARD_CAP,
            )

        task_class = self.classify(task)
        candidates = self._primary_candidates(task, task_class, agent_id)
        self._expand_graph(
            candidates,
            task_class,
            max_roots=graph_max_roots,
            depth=graph_depth,
        )
        if learning_policy is not None:
            self._apply_learning_policy_weights(candidates, learning_policy)
        utility_priors_applied = self._apply_utility_prior(candidates, task, agent_id)
        objects, ranked = self._select(candidates, task_class, effective_budget)
        handle = stable_id("ctx", self.workspace.revision, task, utc_now())
        stored_header = {
            "task": task,
            "revision": self.workspace.revision,
            "task_class": task_class,
            "ranked": ranked,
            "budget": effective_budget,
            "selected_ids": [o.object_id for o in objects],
            "created_at": utc_now(),
            "agent_id": agent_id,
        }
        if learning_policy is not None:
            stored_header.update({
                "learning_policy_version": learning_policy.version,
                "learning_policy_fingerprint": learning_policy.fingerprint,
            })
        self.store.save_json("context_slices", handle, stored_header)
        unknowns: list[str] = []
        if not objects:
            unknowns.append("No indexed object strongly matched the task; exact-source exploration may be required.")
        if any(o.trust == "heuristic" for o in objects):
            unknowns.append("Selected context includes heuristic objects; inspect exact source before consequential edits.")
        selected_paths = {o.path for o in objects if o.path}
        if any((self.store.file_by_path(p) and self.store.file_by_path(p)["index_truncated"]) for p in selected_paths):
            unknowns.append("Selected files include truncated lexical indexes; a missing lexical hit is not absence evidence.")
        if any((self.store.file_by_path(p) and not self.store.file_by_path(p)["parse_complete"]) for p in selected_paths):
            unknowns.append("Selected files include incomplete syntax parses; exact-source inspection may be required.")
        lane_counts = Counter()
        trust_counts = Counter()
        for o in objects:
            for lane in o.lane.split("+"):
                lane_counts[lane] += 1
            trust_counts[o.trust or "unknown"] += 1
        top_score = min(1.0, float(ranked[0]["score"])) if ranked else 0.0
        top_lanes = set()
        for c in ranked[: min(5, len(ranked))]:
            top_lanes.update(str(c.get("lane") or "").split("+"))
        content_terms=self._content_terms(task)
        evaluated_terms=content_terms[:64]
        coverage_truncated=len(content_terms)>len(evaluated_terms)
        supported_terms=[]
        term_paths: dict[str,set[str]] = {}
        for term in evaluated_terms:
            paths=set()
            for hit in self.store.search(term,limit=8):
                if hit["path"]:
                    paths.add(str(hit["path"]))
            if not paths:
                for row in self.store.symbols_matching_terms([term],limit=64):
                    tokens = _identifier_terms(row["qualified_name"]) + _identifier_terms(row["path"])
                    if any(_near(term, token) >= 0.76 for token in tokens):
                        paths.add(str(row["path"]))
                        if len(paths)>=8: break
            if paths:
                supported_terms.append(term); term_paths[term]=paths
        concept_coverage=(len(supported_terms)/len(evaluated_terms)) if evaluated_terms else 0.0
        path_support=Counter()
        for paths in term_paths.values():
            for path in paths:
                path_support[path]+=1
        coherent_count=max(path_support.values(), default=0)
        coherent_coverage=(coherent_count/len(evaluated_terms)) if evaluated_terms else 0.0
        if not objects or top_score < 0.28 or concept_coverage < 0.34:
            retrieval_confidence = "low"
        elif top_score >= 0.66 and concept_coverage >= 0.60 and (len(evaluated_terms) <= 1 or coherent_coverage >= 0.34) and len(top_lanes & {"symbol","graph","evidence","diagnostic","resident"}) >= 1:
            retrieval_confidence = "high"
        else:
            retrieval_confidence = "medium"
        safety_floor_abstention = not objects or retrieval_confidence == "low"
        learned_abstention = (
            learning_policy is not None
            and top_score < learning_policy.abstention_threshold
        )
        abstention_recommended = safety_floor_abstention or learned_abstention
        if safety_floor_abstention:
            unknowns.append("Retrieval confidence is low; prefer explicit exploration or ask for a narrower target before loading broad source context.")
        elif learned_abstention:
            unknowns.append("Active learning policy recommends conservative abstention; inspect stronger evidence before broad source loading.")
        decision_packet = {
            "objective": task,
            "revision": self.workspace.revision,
            "retrieval_confidence": retrieval_confidence,
            "top_candidate_score": round(top_score, 4),
            "concept_coverage": round(concept_coverage, 4),
            "concept_neighborhood_coverage": round(coherent_coverage, 4),
            "coverage_evaluated_concepts": len(evaluated_terms),
            "coverage_truncated": coverage_truncated,
            "supported_concepts": supported_terms,
            "unsupported_concepts": [x for x in evaluated_terms if x not in supported_terms],
            "abstention_recommended": abstention_recommended,
            "top_evidence_lanes": sorted(x for x in top_lanes if x),
            "context_utility_priors_applied": utility_priors_applied,
            "context_utility_is_non_authoritative": True,
            "inspect_first": [o.object_id for o in objects[: min(6, len(objects))]],
            "exact_source_required_before_mutation": [o.object_id for o in objects if o.trust in {"heuristic", "derived"}],
            "context_is_orientation_not_authority": True,
            "omitted_candidates": max(0, len(ranked) - len(objects)),
        }
        if learning_policy is not None:
            decision_packet.update({
                "learning_policy_version": learning_policy.version,
                "learning_policy_fingerprint": learning_policy.fingerprint,
            })
        stored_slice = self.store.load_json("context_slices", handle) or {}
        stored_slice.update({
            "decision_packet": decision_packet,
            "unknowns": unknowns,
            "lane_counts": dict(lane_counts),
            "trust_counts": dict(trust_counts),
            "selected_ids": [o.object_id for o in objects],
        })
        self.store.save_json("context_slices", handle, stored_slice)
        return ContextSlice(task, self.workspace.revision, objects, unknowns,
                            max(0, len(ranked) - len(objects)), effective_budget, task_class, handle, dict(lane_counts), dict(trust_counts), decision_packet)
