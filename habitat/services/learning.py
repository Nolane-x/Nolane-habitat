from __future__ import annotations

import json
from typing import Any

from ..learning_plane import (
    LEGAL_CANDIDATE_TRANSITIONS,
    ContextPolicy,
    EvaluationPacket,
    OutcomeRecord,
    PolicyCandidate,
)
from ..repositories.learning import LearningRepository
from ..util import stable_id, utc_now


class LearningService:
    """Workspace-owned authority for bounded Learning Plane lifecycle decisions."""

    __slots__ = ("workspace", "repository")

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace
        self.repository: LearningRepository = workspace.store._learning_repository()

    @staticmethod
    def _require_text(value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be str")
        if not value.strip():
            raise ValueError(f"{field_name} must not be empty")
        return value

    @staticmethod
    def _candidate_dict(row) -> dict:
        return {key: row[key] for key in row.keys()}

    def _candidate_row(self, candidate_id: str):
        candidate_id = self._require_text(candidate_id, "candidate_id")
        row = self.repository.candidate(candidate_id)
        if row is None:
            raise KeyError(candidate_id)
        return row

    def _policy_from_row(self, row) -> ContextPolicy:
        try:
            payload = json.loads(row["policy_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("stored learning policy JSON is invalid") from exc
        policy = ContextPolicy.from_mapping(payload)
        if policy.version != row["version"]:
            raise ValueError("stored learning policy version mismatch")
        if policy.fingerprint != row["fingerprint"]:
            raise ValueError("stored learning policy fingerprint mismatch")
        return policy

    def _latest_independent_evaluation(self, candidate_row):
        evaluation = self.repository.latest_evaluation(candidate_row["candidate_id"])
        if evaluation is None:
            raise ValueError("independent evaluation is required for this lifecycle transition")
        if evaluation["policy_fingerprint"] != candidate_row["policy_fingerprint"]:
            raise ValueError("evaluation policy fingerprint does not match candidate")
        if evaluation["evaluator_id"] == candidate_row["generator_id"]:
            raise ValueError("independent evaluator identity must differ from generator identity")
        return evaluation

    def register_context_policy(
        self,
        policy: ContextPolicy,
        *,
        parent_version: str | None,
        created_by: str,
    ) -> dict:
        if not isinstance(policy, ContextPolicy):
            raise TypeError("policy must be ContextPolicy")
        created_by = self._require_text(created_by, "created_by")
        if parent_version is not None:
            parent_version = self._require_text(parent_version, "parent_version")
        existing = self.repository.policy_version(policy.version)
        if existing is not None:
            raise ValueError(f"learning policy version already exists: {policy.version}")
        created_at = utc_now()
        self.repository.create_policy_version(
            policy,
            parent_version=parent_version,
            created_by=created_by,
            created_at=created_at,
        )
        return {
            "version": policy.version,
            "fingerprint": policy.fingerprint,
            "parent_version": parent_version,
            "created_by": created_by,
            "created_at": created_at,
        }

    def create_policy_candidate(
        self,
        policy_version: str,
        *,
        baseline_version: str,
        generator_id: str,
    ) -> dict:
        policy_version = self._require_text(policy_version, "policy_version")
        baseline_version = self._require_text(baseline_version, "baseline_version")
        generator_id = self._require_text(generator_id, "generator_id")
        policy = self.repository.policy_version(policy_version)
        baseline = self.repository.policy_version(baseline_version)
        if policy is None:
            raise KeyError(policy_version)
        if baseline is None:
            raise KeyError(baseline_version)
        active_version = self.repository.active_context_policy_version()
        if active_version is not None and active_version != baseline_version:
            raise ValueError(
                "candidate baseline does not match the active context policy version"
            )
        created_at = utc_now()
        candidate = PolicyCandidate(
            candidate_id=stable_id(
                "learning-candidate",
                policy_version,
                baseline_version,
                generator_id,
                created_at,
            ),
            policy_version=policy_version,
            policy_fingerprint=policy["fingerprint"],
            baseline_version=baseline_version,
            baseline_fingerprint=baseline["fingerprint"],
            generator_id=generator_id,
            state="candidate",
            created_at=created_at,
            updated_at=created_at,
        )
        self.repository.create_candidate(candidate)
        return self._candidate_dict(self._candidate_row(candidate.candidate_id))

    def record_policy_outcome(self, candidate_id: str, outcome: OutcomeRecord) -> dict:
        candidate = self._candidate_row(candidate_id)
        if not isinstance(outcome, OutcomeRecord):
            raise TypeError("outcome must be OutcomeRecord")
        if outcome.policy_version != candidate["policy_version"]:
            raise ValueError("outcome policy version does not match candidate")
        outcome_id = self.repository.append_outcome(candidate_id, outcome)
        return {"candidate_id": candidate_id, "outcome_id": outcome_id}

    def transition_candidate(self, candidate_id: str, target_state: str) -> dict:
        target_state = self._require_text(target_state, "target_state")
        candidate = self._candidate_row(candidate_id)
        current_state = candidate["state"]
        if target_state not in LEGAL_CANDIDATE_TRANSITIONS:
            raise ValueError(f"unknown candidate lifecycle state: {target_state}")
        if target_state == "promoted":
            raise ValueError("promotion requires promote_candidate so activation is atomic")
        if target_state == "rolled_back":
            raise ValueError("rollback requires rollback_candidate so activation is atomic")
        if target_state not in LEGAL_CANDIDATE_TRANSITIONS[current_state]:
            raise ValueError(
                f"illegal candidate lifecycle transition: {current_state} -> {target_state}"
            )
        if target_state in {"evaluated", "canary"}:
            self._latest_independent_evaluation(candidate)
        updated_at = utc_now()
        self.repository.update_candidate_state(
            candidate_id,
            expected_state=current_state,
            new_state=target_state,
            updated_at=updated_at,
        )
        return self._candidate_dict(self._candidate_row(candidate_id))

    def admit_evaluation(self, candidate_id: str, packet: EvaluationPacket) -> dict:
        candidate = self._candidate_row(candidate_id)
        if not isinstance(packet, EvaluationPacket):
            raise TypeError("packet must be EvaluationPacket")
        if candidate["state"] not in {"experiment", "evaluated", "canary"}:
            raise ValueError("evaluation may be admitted only after experiment begins")
        if packet.candidate_id != candidate_id:
            raise ValueError("evaluation candidate identity mismatch")
        if packet.policy_fingerprint != candidate["policy_fingerprint"]:
            raise ValueError("evaluation policy fingerprint does not match candidate")
        packet.require_independent(candidate["generator_id"])
        created_at = utc_now()
        evaluation_id = self.repository.append_evaluation(
            candidate_id,
            packet,
            created_at=created_at,
        )
        return {
            "candidate_id": candidate_id,
            "evaluation_id": evaluation_id,
            "improved": packet.improved,
            "created_at": created_at,
        }

    def promote_candidate(self, candidate_id: str) -> dict:
        candidate_id = self._require_text(candidate_id, "candidate_id")
        with self.workspace.store.atomic():
            candidate = self._candidate_row(candidate_id)
            if candidate["state"] != "canary":
                raise ValueError("candidate promotion requires current canary state")
            evaluation = self._latest_independent_evaluation(candidate)
            if not bool(evaluation["improved"]):
                raise ValueError("candidate promotion requires independent improvement evidence")

            previous_version = self.repository.active_context_policy_version()
            if previous_version is not None and previous_version != candidate["baseline_version"]:
                raise ValueError(
                    "candidate baseline no longer matches the active context policy version"
                )
            previous_fingerprint = None
            if previous_version is not None:
                previous = self.repository.policy_version(previous_version)
                if previous is None:
                    raise ValueError("active context policy version is not registered")
                previous_fingerprint = previous["fingerprint"]
                if previous_fingerprint != candidate["baseline_fingerprint"]:
                    raise ValueError(
                        "candidate baseline fingerprint no longer matches active context policy"
                    )

            updated_at = utc_now()
            self.repository.update_candidate_state(
                candidate_id,
                expected_state="canary",
                new_state="promoted",
                updated_at=updated_at,
            )
            activation_id = self.repository.append_activation(
                candidate_id=candidate_id,
                action="promote",
                previous_version=previous_version,
                previous_fingerprint=previous_fingerprint,
                active_version=candidate["policy_version"],
                active_fingerprint=candidate["policy_fingerprint"],
                evaluation_id=int(evaluation["id"]),
                baseline_benchmark_fingerprint=evaluation[
                    "baseline_benchmark_fingerprint"
                ],
                candidate_benchmark_fingerprint=evaluation[
                    "candidate_benchmark_fingerprint"
                ],
                reproduction_benchmark_fingerprint=None,
                reproduction_tolerance=evaluation["reproduction_tolerance"],
                created_at=updated_at,
            )
            self.repository.set_active_context_policy_version(
                candidate["policy_version"],
                updated_at=updated_at,
            )

        result = self._candidate_dict(self._candidate_row(candidate_id))
        result["activation_id"] = activation_id
        result["active_version"] = candidate["policy_version"]
        result["active_fingerprint"] = candidate["policy_fingerprint"]
        result["previous_version"] = previous_version
        result["previous_fingerprint"] = previous_fingerprint
        return result

    def rollback_candidate(
        self,
        candidate_id: str,
        reproduction: EvaluationPacket,
    ) -> dict:
        candidate_id = self._require_text(candidate_id, "candidate_id")
        if not isinstance(reproduction, EvaluationPacket):
            raise TypeError("reproduction must be EvaluationPacket")
        with self.workspace.store.atomic():
            candidate = self._candidate_row(candidate_id)
            if candidate["state"] != "promoted":
                raise ValueError("rollback requires current promoted candidate state")
            if self.repository.active_context_policy_version() != candidate["policy_version"]:
                raise ValueError("promoted candidate is not the active context policy")

            promotion = None
            for activation in reversed(self.repository.activations(candidate_id)):
                if activation["action"] == "promote":
                    promotion = activation
                    break
            if promotion is None or promotion["previous_version"] is None:
                raise ValueError("rollback requires an exact recorded previous activation")

            previous_version = promotion["previous_version"]
            previous_fingerprint = promotion["previous_fingerprint"]
            previous = self.repository.policy_version(previous_version)
            if previous is None or previous["fingerprint"] != previous_fingerprint:
                raise ValueError("recorded previous policy fingerprint is not reproducible")

            if reproduction.candidate_id != candidate_id:
                raise ValueError("rollback reproduction candidate identity mismatch")
            reproduction.require_independent(candidate["generator_id"])
            if reproduction.policy_fingerprint != previous_fingerprint:
                raise ValueError("rollback reproduction previous policy fingerprint mismatch")

            expected_benchmark = promotion["baseline_benchmark_fingerprint"]
            if (
                reproduction.baseline_benchmark_fingerprint != expected_benchmark
                or reproduction.candidate_benchmark_fingerprint != expected_benchmark
            ):
                raise ValueError("rollback reproduction benchmark fingerprint mismatch")

            declared_tolerance = promotion["reproduction_tolerance"]
            reproduction_tolerance = reproduction.reproduction_tolerance
            if declared_tolerance is None:
                if reproduction_tolerance not in {None, 0, 0.0}:
                    raise ValueError("rollback reproduction tolerance exceeds declared tolerance")
            else:
                if (
                    reproduction_tolerance is None
                    or float(reproduction_tolerance) > float(declared_tolerance)
                ):
                    raise ValueError("rollback reproduction tolerance exceeds declared tolerance")

            updated_at = utc_now()
            self.repository.update_candidate_state(
                candidate_id,
                expected_state="promoted",
                new_state="rolled_back",
                updated_at=updated_at,
            )
            activation_id = self.repository.append_activation(
                candidate_id=candidate_id,
                action="rollback",
                previous_version=candidate["policy_version"],
                previous_fingerprint=candidate["policy_fingerprint"],
                active_version=previous_version,
                active_fingerprint=previous_fingerprint,
                evaluation_id=int(promotion["evaluation_id"]),
                baseline_benchmark_fingerprint=promotion[
                    "baseline_benchmark_fingerprint"
                ],
                candidate_benchmark_fingerprint=promotion[
                    "candidate_benchmark_fingerprint"
                ],
                reproduction_benchmark_fingerprint=reproduction.candidate_benchmark_fingerprint,
                reproduction_tolerance=reproduction_tolerance,
                created_at=updated_at,
            )
            self.repository.set_active_context_policy_version(
                previous_version,
                updated_at=updated_at,
            )

        result = self._candidate_dict(self._candidate_row(candidate_id))
        result["activation_id"] = activation_id
        result["active_version"] = previous_version
        result["active_fingerprint"] = previous_fingerprint
        return result

    def active_context_policy(self) -> ContextPolicy | None:
        version = self.repository.active_context_policy_version()
        if version is None:
            return None
        row = self.repository.policy_version(version)
        if row is None:
            raise ValueError("active context policy version is not registered")
        return self._policy_from_row(row)
