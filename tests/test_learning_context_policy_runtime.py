from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.context import ContextCompiler
from habitat.learning_plane import ContextPolicy
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


def make_policy(
    version: str,
    *,
    lexical_weight: float = 1.0,
    structural_weight: float = 1.0,
    evidence_weight: float = 1.0,
    graph_depth: int = 2,
    max_roots: int = 8,
    source_prefetch_budget: int = 18,
    abstention_threshold: float = 0.25,
) -> ContextPolicy:
    return ContextPolicy(
        version=version,
        lexical_weight=lexical_weight,
        structural_weight=structural_weight,
        evidence_weight=evidence_weight,
        graph_depth=graph_depth,
        max_roots=max_roots,
        source_prefetch_budget=source_prefetch_budget,
        abstention_threshold=abstention_threshold,
    )


class LearningContextPolicyRuntimeTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "target.py").write_text(
            "def target():\n    return helper()\n\ndef helper():\n    return 1\n",
            encoding="utf-8",
        )
        return HabitatWorkspace.create(source, root / "habitat")

    def activate(self, ws: HabitatWorkspace, policy: ContextPolicy) -> None:
        ws._learning().register_context_policy(
            policy,
            parent_version=None,
            created_by="runtime-test",
        )
        ws.store._learning_repository().set_active_context_policy_version(
            policy.version,
            updated_at="2026-08-29T00:00:00+00:00",
        )

    def deterministic_candidates(self) -> dict[str, dict]:
        # Deliberately use distinct object kinds so this fixture exercises learning-policy behavior
        # rather than the compiler's existing per-kind/file diversity caps.
        return {
            "fake:lexical": {
                "object_id": "fake:lexical",
                "score": 0.40,
                "reason": "lexical fixture",
                "lane": "lexical",
                "kind": "artifact",
                "path": "lexical.txt",
                "trust": "exact",
            },
            "fake:structural": {
                "object_id": "fake:structural",
                "score": 0.50,
                "reason": "structural fixture",
                "lane": "symbol",
                "kind": "symbol",
                "path": "structural.txt",
                "trust": "semantic",
            },
            "fake:evidence": {
                "object_id": "fake:evidence",
                "score": 0.30,
                "reason": "evidence fixture",
                "lane": "evidence",
                "kind": "evidence",
                "path": "evidence.txt",
                "trust": "derived",
            },
            "fake:mixed": {
                "object_id": "fake:mixed",
                "score": 0.20,
                "reason": "mixed fixture",
                "lane": "lexical+graph+diagnostic",
                "kind": "diagnostic",
                "path": "mixed.txt",
                "trust": "heuristic",
            },
        }

    def candidate_patch(self):
        fixture = self.deterministic_candidates()

        def primary(_compiler, _task, _task_class, _agent_id=None):
            return {key: dict(value) for key, value in fixture.items()}

        return patch.object(ContextCompiler, "_primary_candidates", new=primary)

    def test_no_active_policy_preserves_existing_selection_shape_and_authority_warnings(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                compiler = ContextCompiler(ws)
                with self.candidate_patch(), patch.object(
                    ContextCompiler,
                    "_expand_graph",
                    new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
                ), patch.object(
                    ContextCompiler,
                    "_apply_utility_prior",
                    new=lambda _self, _candidates, _task, _agent_id=None: 0,
                ):
                    result = compiler.compile("target", budget=4)

                self.assertEqual(
                    [
                        "fake:structural",
                        "fake:lexical",
                        "fake:evidence",
                        "fake:mixed",
                    ],
                    [obj.object_id for obj in result.objects],
                )
                self.assertEqual(4, result.budget)
                self.assertNotIn("learning_policy_version", result.decision_packet)
                self.assertNotIn("learning_policy_fingerprint", result.decision_packet)
                self.assertIn("fake:mixed", result.decision_packet["exact_source_required_before_mutation"])
                self.assertTrue(any("heuristic" in item for item in result.unknowns))
                stored = ws.store.load_json("context_slices", result.handle)
                self.assertNotIn("learning_policy_version", stored)
                self.assertNotIn("learning_policy_fingerprint", stored)
            finally:
                ws.close()

    def test_active_policy_caps_budget_weights_existing_candidates_and_records_exact_receipt(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                policy = make_policy(
                    "context-runtime-v1",
                    lexical_weight=2.0,
                    structural_weight=0.5,
                    evidence_weight=1.5,
                    source_prefetch_budget=2,
                )
                self.activate(ws, policy)
                compiler = ContextCompiler(ws)
                with self.candidate_patch(), patch.object(
                    ContextCompiler,
                    "_expand_graph",
                    new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
                ), patch.object(
                    ContextCompiler,
                    "_apply_utility_prior",
                    new=lambda _self, _candidates, _task, _agent_id=None: 0,
                ):
                    result = compiler.compile("target", budget=5)

                self.assertEqual(2, result.budget)
                self.assertEqual(2, len(result.objects))
                stored = ws.store.load_json("context_slices", result.handle)
                ranked = {row["object_id"]: row for row in stored["ranked"]}
                self.assertEqual(
                    {
                        "fake:lexical",
                        "fake:structural",
                        "fake:evidence",
                        "fake:mixed",
                    },
                    set(ranked),
                )
                self.assertAlmostEqual(0.80, ranked["fake:lexical"]["score"])
                self.assertAlmostEqual(0.25, ranked["fake:structural"]["score"])
                self.assertAlmostEqual(0.45, ranked["fake:evidence"]["score"])
                self.assertAlmostEqual(0.30, ranked["fake:mixed"]["score"])
                self.assertIn("learning policy", ranked["fake:mixed"]["reason"])
                self.assertEqual(policy.version, result.decision_packet["learning_policy_version"])
                self.assertEqual(policy.fingerprint, result.decision_packet["learning_policy_fingerprint"])
                self.assertEqual(policy.version, stored["learning_policy_version"])
                self.assertEqual(policy.fingerprint, stored["learning_policy_fingerprint"])
            finally:
                ws.close()

    def test_active_policy_never_suppresses_authority_warnings(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                policy = make_policy(
                    "context-runtime-authority-v1",
                    lexical_weight=2.0,
                    structural_weight=0.5,
                    evidence_weight=1.5,
                    source_prefetch_budget=4,
                )
                self.activate(ws, policy)
                compiler = ContextCompiler(ws)
                with self.candidate_patch(), patch.object(
                    ContextCompiler,
                    "_expand_graph",
                    new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
                ), patch.object(
                    ContextCompiler,
                    "_apply_utility_prior",
                    new=lambda _self, _candidates, _task, _agent_id=None: 0,
                ):
                    result = compiler.compile("target", budget=4)

                self.assertIn(
                    "fake:mixed",
                    result.decision_packet["exact_source_required_before_mutation"],
                )
                self.assertTrue(any("heuristic" in item for item in result.unknowns))
                mixed = next(obj for obj in result.objects if obj.object_id == "fake:mixed")
                self.assertEqual("heuristic", mixed.trust)
            finally:
                ws.close()

    def test_source_prefetch_budget_never_raises_caller_budget(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                policy = make_policy(
                    "context-runtime-budget-v1",
                    source_prefetch_budget=20,
                )
                self.activate(ws, policy)
                compiler = ContextCompiler(ws)
                with self.candidate_patch(), patch.object(
                    ContextCompiler,
                    "_expand_graph",
                    new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
                ), patch.object(
                    ContextCompiler,
                    "_apply_utility_prior",
                    new=lambda _self, _candidates, _task, _agent_id=None: 0,
                ):
                    result = compiler.compile("target", budget=2)
                self.assertEqual(2, result.budget)
                self.assertEqual(2, len(result.objects))
            finally:
                ws.close()

    def test_active_policy_threads_graph_depth_and_root_limit_into_existing_expansion(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                policy = make_policy(
                    "context-runtime-graph-v1",
                    graph_depth=1,
                    max_roots=3,
                )
                self.activate(ws, policy)
                compiler = ContextCompiler(ws)
                observed: list[tuple[int, int]] = []

                def capture_expand(
                    _compiler,
                    _candidates,
                    _task_class,
                    max_roots=8,
                    depth=2,
                ):
                    observed.append((max_roots, depth))

                with self.candidate_patch(), patch.object(
                    ContextCompiler,
                    "_expand_graph",
                    new=capture_expand,
                ), patch.object(
                    ContextCompiler,
                    "_apply_utility_prior",
                    new=lambda _self, _candidates, _task, _agent_id=None: 0,
                ):
                    compiler.compile("target", budget=4)

                self.assertEqual([(3, 1)], observed)
            finally:
                ws.close()

    def test_learning_abstention_can_only_add_to_existing_safety_floor(self):
        def high_confidence_candidates(_compiler, _task, _task_class, _agent_id=None):
            return {
                "fake:target": {
                    "object_id": "fake:target",
                    "score": 0.80,
                    "reason": "target fixture",
                    "lane": "lexical+symbol",
                    "kind": "artifact",
                    "path": "target.py",
                    "trust": "exact",
                }
            }

        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                compiler = ContextCompiler(ws)
                patches = (
                    patch.object(ContextCompiler, "_primary_candidates", new=high_confidence_candidates),
                    patch.object(
                        ContextCompiler,
                        "_expand_graph",
                        new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
                    ),
                    patch.object(
                        ContextCompiler,
                        "_apply_utility_prior",
                        new=lambda _self, _candidates, _task, _agent_id=None: 0,
                    ),
                )
                with patches[0], patches[1], patches[2]:
                    baseline = compiler.compile("target", budget=1)
                self.assertFalse(baseline.decision_packet["abstention_recommended"])

                policy = make_policy(
                    "context-runtime-abstention-v1",
                    abstention_threshold=0.90,
                )
                self.activate(ws, policy)
                with patch.object(ContextCompiler, "_primary_candidates", new=high_confidence_candidates), patch.object(
                    ContextCompiler,
                    "_expand_graph",
                    new=lambda _self, _candidates, _task_class, max_roots=8, depth=2: None,
                ), patch.object(
                    ContextCompiler,
                    "_apply_utility_prior",
                    new=lambda _self, _candidates, _task, _agent_id=None: 0,
                ):
                    learned = compiler.compile("target", budget=1)

                self.assertTrue(learned.decision_packet["abstention_recommended"])
                self.assertEqual("high", learned.decision_packet["retrieval_confidence"])
                self.assertEqual(policy.version, learned.decision_packet["learning_policy_version"])
            finally:
                ws.close()
