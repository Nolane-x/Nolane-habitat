from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.learning_plane import ContextPolicy, EvaluationPacket, OutcomeRecord
from habitat.repositories.learning import LearningRepository
from habitat.services import LearningService
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_policy(version: str, *, lexical_weight: float = 1.0) -> ContextPolicy:
    return ContextPolicy(
        version=version,
        lexical_weight=lexical_weight,
        structural_weight=1.0,
        evidence_weight=1.0,
        graph_depth=2,
        max_roots=8,
        source_prefetch_budget=12,
        abstention_threshold=0.25,
    )


def make_evaluation(
    *,
    candidate_id: str,
    policy_fingerprint: str,
    evaluator_id: str = "independent-evaluator",
    improved: bool = True,
    baseline_benchmark_fingerprint: str | None = None,
    candidate_benchmark_fingerprint: str | None = None,
    reproduction_tolerance: float | None = 0.0,
) -> EvaluationPacket:
    return EvaluationPacket(
        candidate_id=candidate_id,
        policy_fingerprint=policy_fingerprint,
        evaluator_id=evaluator_id,
        heldout_suite_id="heldout-context-policy-v1",
        baseline_benchmark_fingerprint=(
            baseline_benchmark_fingerprint or digest("baseline-benchmark")
        ),
        candidate_benchmark_fingerprint=(
            candidate_benchmark_fingerprint or digest("candidate-benchmark")
        ),
        improved=improved,
        evidence_refs=("evidence:heldout:1",),
        reproduction_tolerance=reproduction_tolerance,
    )


class LearningServiceTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> HabitatWorkspace:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        (source / "sample.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        return HabitatWorkspace.create(source, root / "habitat")

    def register_pair(self, service: LearningService) -> tuple[ContextPolicy, ContextPolicy]:
        baseline = make_policy("context-v1")
        candidate = make_policy("context-v2", lexical_weight=1.25)
        service.register_context_policy(baseline, parent_version=None, created_by="seed")
        service.register_context_policy(candidate, parent_version=baseline.version, created_by="generator")
        return baseline, candidate

    def create_candidate(
        self,
        service: LearningService,
        baseline: ContextPolicy,
        candidate: ContextPolicy,
        *,
        generator_id: str = "generator",
    ) -> dict:
        created = service.create_policy_candidate(
            candidate.version,
            baseline_version=baseline.version,
            generator_id=generator_id,
        )
        self.assertIsInstance(created["candidate_id"], str)
        self.assertTrue(created["candidate_id"])
        self.assertEqual("candidate", created["state"])
        return created

    def advance_to_experiment(
        self,
        service: LearningService,
        candidate_id: str,
    ) -> None:
        self.assertEqual("shadow", service.transition_candidate(candidate_id, "shadow")["state"])
        self.assertEqual(
            "experiment",
            service.transition_candidate(candidate_id, "experiment")["state"],
        )

    def advance_to_canary(
        self,
        service: LearningService,
        candidate_id: str,
        evaluation: EvaluationPacket,
    ) -> dict:
        self.advance_to_experiment(service, candidate_id)
        admitted = service.admit_evaluation(candidate_id, evaluation)
        self.assertGreater(admitted["evaluation_id"], 0)
        self.assertEqual(
            "evaluated",
            service.transition_candidate(candidate_id, "evaluated")["state"],
        )
        self.assertEqual(
            "canary",
            service.transition_candidate(candidate_id, "canary")["state"],
        )
        return admitted

    def seed_active_policy(
        self,
        workspace: HabitatWorkspace,
        policy: ContextPolicy,
    ) -> None:
        workspace.store._learning_repository().set_active_context_policy_version(
            policy.version,
            updated_at="2026-08-29T00:00:00+00:00",
        )

    def test_workspace_learning_service_is_lazy_and_stable(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                self.assertIsNone(getattr(ws, "_learning_service", None))
                service = ws._learning()
                self.assertIsInstance(service, LearningService)
                self.assertIs(service, ws._learning())
            finally:
                ws.close()

    def test_lifecycle_rejects_skips_requires_independent_evaluation_and_honors_terminals(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]

                with self.assertRaisesRegex(ValueError, "illegal.*candidate.*experiment"):
                    service.transition_candidate(candidate_id, "experiment")

                self.advance_to_experiment(service, candidate_id)
                with self.assertRaisesRegex(ValueError, "evaluation"):
                    service.transition_candidate(candidate_id, "evaluated")

                self_eval = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    evaluator_id="generator",
                )
                with self.assertRaisesRegex(ValueError, "independent"):
                    service.admit_evaluation(candidate_id, self_eval)

                wrong_policy_eval = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                )
                with self.assertRaisesRegex(ValueError, "policy fingerprint"):
                    service.admit_evaluation(candidate_id, wrong_policy_eval)

                evaluation = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                )
                service.admit_evaluation(candidate_id, evaluation)
                self.assertEqual(
                    "evaluated",
                    service.transition_candidate(candidate_id, "evaluated")["state"],
                )
                self.assertEqual(
                    "canary",
                    service.transition_candidate(candidate_id, "canary")["state"],
                )

                rejected_policy = make_policy("context-v3")
                service.register_context_policy(
                    rejected_policy,
                    parent_version=candidate.version,
                    created_by="generator",
                )
                rejected = self.create_candidate(service, candidate, rejected_policy)
                rejected_id = rejected["candidate_id"]
                self.assertEqual(
                    "rejected",
                    service.transition_candidate(rejected_id, "rejected")["state"],
                )
                with self.assertRaisesRegex(ValueError, "terminal|illegal"):
                    service.transition_candidate(rejected_id, "shadow")
            finally:
                ws.close()

    def test_outcome_recording_is_bound_to_candidate_policy(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]
                outcome = OutcomeRecord(
                    policy_version=candidate.version,
                    task_fingerprint="task:heldout:1",
                    benchmark_class="retrieval/orientation",
                    provider_fingerprints=("provider:fixture",),
                    context_refs=("ctx:1",),
                    action_refs=("action:1",),
                    verification_refs=("verify:1",),
                    independent_outcome={"success": True},
                    resource_metrics={"tool_calls": 1, "wall_ms": None},
                    errors=(),
                    rollbacks=(),
                    revision="rev:fixture",
                    created_at="2026-08-29T00:00:01+00:00",
                )
                recorded = service.record_policy_outcome(candidate_id, outcome)
                self.assertGreater(recorded["outcome_id"], 0)
                rows = ws.store._learning_repository().outcomes(candidate_id)
                self.assertEqual(1, len(rows))
                self.assertEqual(candidate.version, rows[0]["policy_version"])
            finally:
                ws.close()

    def test_canary_and_promotion_require_latest_independent_improvement(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                self.seed_active_policy(ws, baseline)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]
                self.advance_to_experiment(service, candidate_id)

                not_improved = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=False,
                )
                service.admit_evaluation(candidate_id, not_improved)
                service.transition_candidate(candidate_id, "evaluated")
                service.transition_candidate(candidate_id, "canary")
                with self.assertRaisesRegex(ValueError, "improv"):
                    service.promote_candidate(candidate_id)

                improved = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=True,
                )
                service.admit_evaluation(candidate_id, improved)
                promoted = service.promote_candidate(candidate_id)
                self.assertEqual("promoted", promoted["state"])
                self.assertEqual(candidate.version, promoted["active_version"])
                self.assertEqual(
                    candidate.version,
                    ws.store._learning_repository().active_context_policy_version(),
                )
                self.assertEqual(candidate, service.active_context_policy())
            finally:
                ws.close()

    def test_promotion_is_atomic_under_failure_after_activation_write(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                self.seed_active_policy(ws, baseline)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]
                evaluation = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=True,
                )
                self.advance_to_canary(service, candidate_id, evaluation)
                repository = ws.store._learning_repository()
                original_append_activation = LearningRepository.append_activation

                def fail_after_activation(repo, *args, **kwargs):
                    activation_id = original_append_activation(repo, *args, **kwargs)
                    self.assertGreater(activation_id, 0)
                    raise RuntimeError("injected promotion failure after activation")

                with patch.object(
                    LearningRepository,
                    "append_activation",
                    new=fail_after_activation,
                ):
                    with self.assertRaisesRegex(RuntimeError, "injected promotion failure"):
                        service.promote_candidate(candidate_id)

                self.assertEqual("canary", repository.candidate(candidate_id)["state"])
                self.assertEqual(baseline.version, repository.active_context_policy_version())
                self.assertEqual([], repository.activations(candidate_id))
            finally:
                ws.close()

    def test_promotion_records_exact_previous_active_and_evaluation_bindings(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                self.seed_active_policy(ws, baseline)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]
                evaluation = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=True,
                    reproduction_tolerance=0.05,
                )
                admitted = self.advance_to_canary(service, candidate_id, evaluation)
                promoted = service.promote_candidate(candidate_id)
                self.assertEqual("promoted", promoted["state"])

                activations = ws.store._learning_repository().activations(candidate_id)
                self.assertEqual(1, len(activations))
                row = activations[0]
                self.assertEqual("promote", row["action"])
                self.assertEqual(baseline.version, row["previous_version"])
                self.assertEqual(baseline.fingerprint, row["previous_fingerprint"])
                self.assertEqual(candidate.version, row["active_version"])
                self.assertEqual(candidate.fingerprint, row["active_fingerprint"])
                self.assertEqual(admitted["evaluation_id"], row["evaluation_id"])
                self.assertEqual(
                    evaluation.baseline_benchmark_fingerprint,
                    row["baseline_benchmark_fingerprint"],
                )
                self.assertEqual(
                    evaluation.candidate_benchmark_fingerprint,
                    row["candidate_benchmark_fingerprint"],
                )
            finally:
                ws.close()

    def test_rollback_requires_exact_previous_policy_and_benchmark_binding(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                self.seed_active_policy(ws, baseline)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]
                evaluation = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=True,
                    reproduction_tolerance=0.05,
                )
                self.advance_to_canary(service, candidate_id, evaluation)
                service.promote_candidate(candidate_id)

                wrong_policy = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=False,
                    baseline_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    candidate_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    reproduction_tolerance=0.0,
                )
                with self.assertRaisesRegex(ValueError, "previous policy fingerprint"):
                    service.rollback_candidate(candidate_id, wrong_policy)

                wrong_benchmark = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    improved=False,
                    baseline_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    candidate_benchmark_fingerprint=digest("tampered-reproduction"),
                    reproduction_tolerance=0.0,
                )
                with self.assertRaisesRegex(ValueError, "benchmark fingerprint"):
                    service.rollback_candidate(candidate_id, wrong_benchmark)

                too_loose = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    improved=False,
                    baseline_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    candidate_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    reproduction_tolerance=0.06,
                )
                with self.assertRaisesRegex(ValueError, "tolerance"):
                    service.rollback_candidate(candidate_id, too_loose)

                reproduction = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    improved=False,
                    baseline_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    candidate_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    reproduction_tolerance=0.0,
                )
                rolled_back = service.rollback_candidate(candidate_id, reproduction)
                self.assertEqual("rolled_back", rolled_back["state"])
                self.assertEqual(baseline.version, rolled_back["active_version"])
                repository = ws.store._learning_repository()
                self.assertEqual(baseline.version, repository.active_context_policy_version())
                self.assertEqual(baseline, service.active_context_policy())

                activations = repository.activations(candidate_id)
                self.assertEqual(2, len(activations))
                rollback = activations[-1]
                self.assertEqual("rollback", rollback["action"])
                self.assertEqual(candidate.version, rollback["previous_version"])
                self.assertEqual(candidate.fingerprint, rollback["previous_fingerprint"])
                self.assertEqual(baseline.version, rollback["active_version"])
                self.assertEqual(baseline.fingerprint, rollback["active_fingerprint"])
                self.assertEqual(
                    evaluation.baseline_benchmark_fingerprint,
                    rollback["reproduction_benchmark_fingerprint"],
                )
            finally:
                ws.close()

    def test_rollback_is_atomic_under_failure_after_activation_write(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws = self.make_workspace(temp)
            try:
                service = ws._learning()
                baseline, candidate = self.register_pair(service)
                self.seed_active_policy(ws, baseline)
                created = self.create_candidate(service, baseline, candidate)
                candidate_id = created["candidate_id"]
                evaluation = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=candidate.fingerprint,
                    improved=True,
                    reproduction_tolerance=0.0,
                )
                self.advance_to_canary(service, candidate_id, evaluation)
                service.promote_candidate(candidate_id)
                repository = ws.store._learning_repository()
                before = repository.activations(candidate_id)
                self.assertEqual(1, len(before))

                reproduction = make_evaluation(
                    candidate_id=candidate_id,
                    policy_fingerprint=baseline.fingerprint,
                    improved=False,
                    baseline_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    candidate_benchmark_fingerprint=evaluation.baseline_benchmark_fingerprint,
                    reproduction_tolerance=0.0,
                )
                original_append_activation = LearningRepository.append_activation

                def fail_after_activation(repo, *args, **kwargs):
                    activation_id = original_append_activation(repo, *args, **kwargs)
                    self.assertGreater(activation_id, 0)
                    raise RuntimeError("injected rollback failure after activation")

                with patch.object(
                    LearningRepository,
                    "append_activation",
                    new=fail_after_activation,
                ):
                    with self.assertRaisesRegex(RuntimeError, "injected rollback failure"):
                        service.rollback_candidate(candidate_id, reproduction)

                self.assertEqual("promoted", repository.candidate(candidate_id)["state"])
                self.assertEqual(candidate.version, repository.active_context_policy_version())
                self.assertEqual(1, len(repository.activations(candidate_id)))
            finally:
                ws.close()
