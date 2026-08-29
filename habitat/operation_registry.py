from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .protocol import HabitatProtocol


OperationHandler = Callable[["HabitatProtocol", dict[str, Any]], Any]


@dataclass(frozen=True)
class OperationDescriptor:
    name: str
    handler: OperationHandler
    read_only: bool = False


class OperationRegistry:
    def __init__(self, descriptors: tuple[OperationDescriptor, ...]):
        by_name: dict[str, OperationDescriptor] = {}
        names: list[str] = []
        read_only_names: set[str] = set()
        for descriptor in descriptors:
            if descriptor.name in by_name:
                raise ValueError(f"duplicate operation: {descriptor.name}")
            by_name[descriptor.name] = descriptor
            names.append(descriptor.name)
            if descriptor.read_only:
                read_only_names.add(descriptor.name)
        self._by_name = MappingProxyType(by_name)
        self.names = tuple(names)
        self.read_only_names = frozenset(read_only_names)

    def get(self, name: str) -> OperationDescriptor | None:
        return self._by_name.get(name)


def _handle_protocol_capabilities(protocol, params):
    return {"protocol": "habitat.agent.v1alpha2", "methods": list(OPERATION_REGISTRY.names), "generic_shell": False}


def _handle_workspace_enter(protocol, params): return protocol.workspace.enter()
def _handle_workspace_refresh(protocol, params): return protocol.workspace.refresh(params.get("reason","agent-refresh"))
def _handle_workspace_orient(protocol, params): return protocol.workspace.orient(protocol._required(params,"task",str),protocol._int(params,"budget",18),protocol._optional(params,"agent_id",str))
def _handle_workspace_explore(protocol, params): return protocol.workspace.explore(protocol._required(params,"task",str),protocol._int(params,"line_budget",120),protocol._int(params,"max_regions",12),protocol._int(params,"context_budget",40),protocol._optional(params,"agent_id",str))
def _handle_workspace_context_page(protocol, params): return protocol.workspace.context_page(protocol._required(params,"handle",str),protocol._int(params,"offset",0),protocol._int(params,"limit",20))
def _handle_workspace_context_refresh(protocol, params): return protocol.workspace.context_refresh(protocol._required(params,"handle",str),protocol._int(params,"budget") if "budget" in params else None)
def _handle_workspace_query(protocol, params): return protocol.workspace.query(protocol._required(params,"query",str),protocol._int(params,"limit",20))
def _handle_workspace_inspect(protocol, params):
    protocol._optional(params,"agent_id",str)
    return protocol.workspace.inspect_snapshot(protocol._required(params,"object_id",str),params.get("include_source","none"))
def _handle_workspace_inspect_batch(protocol, params): return protocol.workspace.inspect_many(protocol._required(params,"object_ids",list),params.get("include_source","none"),protocol._int(params,"max_objects",50))
def _handle_workspace_context_materialize(protocol, params): return protocol.workspace.context_materialize(protocol._required(params,"handle",str),protocol._int(params,"max_source_bytes",60000),protocol._int(params,"max_objects",12))
def _handle_workspace_context_address_space(protocol, params): return protocol.workspace.context_address_space(protocol._required(params,"handle",str),protocol._int(params,"max_pages",100))
def _handle_workspace_context_fetch(protocol, params): return protocol.workspace.context_fetch_pages(protocol._required(params,"handle",str),protocol._required(params,"page_ids",list),protocol._int(params,"max_source_bytes",60000))
def _handle_workspace_context_prefetch(protocol, params): return protocol.workspace.context_prefetch(protocol._required(params,"handle",str),protocol._int(params,"max_source_bytes",20000),protocol._int(params,"max_pages",8))
def _handle_workspace_context_plan_next(protocol, params): return protocol.workspace.context_plan_next(protocol._required(params,"handle",str),params.get("fetched_page_ids"),protocol._int(params,"max_pages",3),protocol._int(params,"max_estimated_bytes",20000))
def _handle_workspace_context_feedback(protocol, params): return protocol.workspace.context_feedback(protocol._required(params,"handle",str),params.get("used_object_ids"),params.get("unhelpful_object_ids"),protocol._float(params,"weight",1.0),protocol._optional(params,"agent_id",str))
def _handle_workspace_context_efficiency(protocol, params): return protocol.workspace.context_efficiency(protocol._required(params,"handle",str))
def _handle_workspace_references(protocol, params): return protocol.workspace.references_snapshot(protocol._required(params,"object_id",str),protocol._int(params,"limit",200))
def _handle_workspace_impact(protocol, params): return protocol.workspace.impact(params.get("changed_paths"),params.get("object_ids"),protocol._int(params,"max_depth",5))
def _handle_workspace_source_read(protocol, params): return protocol.workspace.read_source(protocol._required(params,"path",str),protocol._int(params,"start_line",1),protocol._int(params,"max_lines",200))
def _handle_workspace_change_plan(protocol, params): return protocol.workspace.change_plan(protocol._required(params,"operations",list))
def _handle_workspace_change_stage(protocol, params): return protocol.workspace.stage_change(protocol._required(params,"operations",list),protocol._optional(params,"episode_id",str),protocol._optional(params,"agent_id",str),protocol._float(params,"lease_ttl_s",120.0),protocol._optional(params,"approval_id",str))
def _handle_workspace_change_stage_symbol(protocol, params): return protocol.workspace.stage_symbol_change(protocol._required(params,"symbol_id",str),protocol._required(params,"new_source",str),protocol._optional(params,"episode_id",str),protocol._optional(params,"agent_id",str))
def _handle_workspace_change_stage_rename_symbol(protocol, params): return protocol.workspace.stage_symbol_rename(protocol._required(params,"symbol_id",str),protocol._required(params,"new_name",str),protocol._optional(params,"episode_id",str),protocol._optional(params,"agent_id",str))
def _handle_workspace_change_commit(protocol, params): return protocol.workspace.commit_change(protocol._required(params,"transaction_id",str),protocol._optional(params,"agent_id",str))
def _handle_workspace_change_rollback(protocol, params): return protocol.workspace.rollback_change(protocol._required(params,"transaction_id",str),protocol._optional(params,"agent_id",str))
def _handle_workspace_verification_plan(protocol, params): return protocol.workspace.verification_plan(params.get("changed_paths"),params.get("object_ids"))
def _handle_workspace_verification_run(protocol, params): return protocol.workspace.verify(params.get("changed_paths"),params.get("object_ids"),protocol._int(params,"timeout_s",60),params.get("episode_id"))
def _handle_workspace_events_poll(protocol, params): return protocol.workspace.events_poll(protocol._int(params,"since_seq",0),protocol._int(params,"limit",200),protocol._bool(params,"reconcile",True))
def _handle_workspace_diff_since(protocol, params): return protocol.workspace.diff_since(protocol._required(params,"revision_id",str))
def _handle_workspace_state_merkle(protocol, params): return protocol.workspace.state_merkle(params.get("revision_id"),params.get("prefix",""))
def _handle_workspace_state_merkle_diff(protocol, params): return protocol.workspace.state_merkle_diff(protocol._required(params,"from_revision",str),params.get("to_revision"),params.get("prefix",""))
def _handle_workspace_watch_start(protocol, params): return protocol.workspace.watch_start(protocol._float(params,"interval_s",0.25))
def _handle_workspace_watch_poll(protocol, params): return protocol.workspace.watch_poll(protocol._int(params,"limit",64))
def _handle_workspace_watch_wait(protocol, params): return protocol.workspace.watch_wait(protocol._float(params,"timeout_s",5.0),protocol._int(params,"limit",64))
def _handle_workspace_watch_status(protocol, params): return protocol.workspace.watch_status()
def _handle_workspace_watch_stop(protocol, params): return protocol.workspace.watch_stop()
def _handle_workspace_backend_info(protocol, params): return protocol.workspace.backend_info()
def _handle_workspace_semantic_providers(protocol, params): return protocol.workspace.semantic_provider_report()
def _handle_workspace_semantic_fabric(protocol, params): return protocol.workspace.semantic_fabric()
def _handle_workspace_evidence_active(protocol, params): return protocol.workspace.evidence_active(params.get("kind"),protocol._int(params,"limit",100))
def _handle_workspace_episode_start(protocol, params): return protocol.workspace.episode_start(protocol._required(params,"task",str),params.get("context_handle"))
def _handle_workspace_episode_status(protocol, params): return protocol.workspace.episode_status(protocol._required(params,"episode_id",str))
def _handle_workspace_episode_finish(protocol, params): return protocol.workspace.episode_finish(protocol._required(params,"episode_id",str),params.get("status","completed"),params.get("outcome"))
def _handle_workspace_episode_efficiency(protocol, params): return protocol.workspace.episode_efficiency(protocol._required(params,"episode_id",str))
def _handle_workspace_invariant_create(protocol, params): return protocol.workspace.invariant_create(protocol._required(params,"statement",str),severity=params.get("severity","error"),metadata=params.get("metadata"))
def _handle_workspace_invariant_status(protocol, params): return protocol.workspace.invariant_status(protocol._required(params,"invariant_id",str))
def _handle_workspace_invariant_link(protocol, params): return protocol.workspace.invariant_link(protocol._required(params,"invariant_id",str),protocol._required(params,"ref_kind",str),protocol._required(params,"ref_id",str),relation=params.get("relation","witness"),details=params.get("details"))
def _handle_workspace_invariant_update(protocol, params): return protocol.workspace.invariant_update(protocol._required(params,"invariant_id",str),protocol._required(params,"status",str))
def _handle_workspace_hypothesis_create(protocol, params): return protocol.workspace.hypothesis_create(protocol._required(params,"statement",str),episode_id=params.get("episode_id"),task=params.get("task"),prior_confidence=protocol._float(params,"prior_confidence",0.5))
def _handle_workspace_hypothesis_status(protocol, params): return protocol.workspace.hypothesis_status(protocol._required(params,"hypothesis_id",str))
def _handle_workspace_hypothesis_link_evidence(protocol, params): return protocol.workspace.hypothesis_link_evidence(protocol._required(params,"hypothesis_id",str),params.get("evidence_id"),protocol._required(params,"polarity",str),protocol._float(params,"weight",1.0),params.get("note"))
def _handle_workspace_hypothesis_update(protocol, params): return protocol.workspace.hypothesis_update(protocol._required(params,"hypothesis_id",str),status=params.get("status"),confidence=protocol._float(params,"confidence") if "confidence" in params else None,reason=params.get("reason"))
def _handle_workspace_hypothesis_compare(protocol, params): return protocol.workspace.hypothesis_compare(protocol._required(params,"hypothesis_ids",list))
def _handle_workspace_hypothesis_next_experiment(protocol, params): return protocol.workspace.hypothesis_next_experiment(protocol._required(params,"hypothesis_ids",list))
def _handle_workspace_agent_belief_update(protocol, params): return protocol.workspace.agent_belief_update(protocol._required(params,"agent_id",str),protocol._required(params,"hypothesis_id",str),stance=params.get("stance","uncertain"),confidence=params.get("confidence",0.5),rationale=params.get("rationale"))
def _handle_workspace_agent_belief_status(protocol, params): return protocol.workspace.agent_belief_status(protocol._required(params,"agent_id",str),protocol._required(params,"hypothesis_id",str))
def _handle_workspace_agent_belief_portfolio(protocol, params): return protocol.workspace.agent_belief_portfolio(protocol._required(params,"agent_id",str),protocol._int(params,"limit",200))
def _handle_workspace_experiment_plan(protocol, params): return protocol.workspace.experiment_plan(protocol._required(params,"description",str),hypothesis_id=params.get("hypothesis_id"),episode_id=params.get("episode_id"),discriminator=params.get("discriminator"),capability=params.get("capability"),expected=params.get("expected"))
def _handle_workspace_experiment_status(protocol, params): return protocol.workspace.experiment_status(protocol._required(params,"experiment_id",str))
def _handle_workspace_experiment_complete(protocol, params): return protocol.workspace.experiment_complete(protocol._required(params,"experiment_id",str),protocol._required(params,"result",dict),params.get("status","completed"))
def _handle_workspace_causality_explain(protocol, params): return protocol.workspace.causality_explain(protocol._required(params,"ref_id",str))
def _handle_workspace_causality_graph(protocol, params): return protocol.workspace.causality_graph(protocol._required(params,"ref_id",str),protocol._int(params,"max_depth",4),protocol._int(params,"max_edges",300))
def _handle_workspace_checkpoint(protocol, params): return protocol.workspace.checkpoint(protocol._required(params,"task",str),params.get("resident_object_ids"),params.get("notes"),params.get("next_action"),params.get("episode_id"))
def _handle_workspace_resume(protocol, params): return protocol.workspace.resume(protocol._required(params,"session_id",str))
def _handle_workspace_context_residency_configure(protocol, params): return protocol.workspace.residency_configure(protocol._int(params,"max_objects",32),protocol._int(params,"max_source_bytes",120000))
def _handle_workspace_context_residency_admit(protocol, params): return protocol.workspace.residency_admit(protocol._required(params,"handle",str),protocol._int(params,"pin_top",0),protocol._int(params,"max_admit") if "max_admit" in params else None)
def _handle_workspace_context_residency_status(protocol, params): return protocol.workspace.residency_status()
def _handle_workspace_context_residency_materialize(protocol, params): return protocol.workspace.residency_materialize(protocol._int(params,"max_source_bytes") if "max_source_bytes" in params else None,protocol._int(params,"max_objects") if "max_objects" in params else None)
def _handle_workspace_context_residency_touch(protocol, params): return protocol.workspace.residency_touch(protocol._required(params,"object_ids",list))
def _handle_workspace_context_residency_pin(protocol, params): return protocol.workspace.residency_pin(protocol._required(params,"object_ids",list),protocol._bool(params,"pinned",True))
def _handle_workspace_context_residency_evict(protocol, params): return protocol.workspace.residency_evict(params.get("object_ids"),protocol._bool(params,"stale_only",False))
def _handle_workspace_trace_start(protocol, params): return protocol.workspace.trace_start(params.get("label","agent-run"))
def _handle_workspace_trace_status(protocol, params): return protocol.workspace.trace_status(params.get("trace_id"))
def _handle_workspace_trace_stop(protocol, params): return protocol.workspace.trace_stop(params.get("trace_id"))
def _handle_workspace_activity_since(protocol, params): return protocol.workspace.activity_since(protocol._int(params,"since_seq",0),protocol._int(params,"limit",500))
def _handle_workspace_observatory_start(protocol, params): return protocol.workspace.observatory_start(host=params.get("host","127.0.0.1"),port=protocol._int(params,"port",0),open_browser=protocol._bool(params,"open_browser",True))
def _handle_workspace_observatory_status(protocol, params): return protocol.workspace.observatory_status()
def _handle_workspace_observatory_stop(protocol, params): return protocol.workspace.observatory_stop()
def _handle_workspace_epistemic_create(protocol, params): return protocol.workspace.epistemic_create(protocol._required(params,"kind",str),protocol._required(params,"statement",str),status=params.get("status","open"),confidence=protocol._float(params,"confidence") if "confidence" in params and params.get("confidence") is not None else None,scope=params.get("scope","workspace"),agent_id=protocol._optional(params,"agent_id",str),episode_id=protocol._optional(params,"episode_id",str),provenance=params.get("provenance"),invalidation_conditions=params.get("invalidation_conditions"))
def _handle_workspace_epistemic_state(protocol, params): return protocol.workspace.epistemic_state(protocol._optional(params,"agent_id",str),params.get("status","open"),protocol._int(params,"limit",200))
def _handle_workspace_epistemic_update(protocol, params): return protocol.workspace.epistemic_update(protocol._required(params,"item_id",str),status=params.get("status"),confidence=protocol._float(params,"confidence") if "confidence" in params and params.get("confidence") is not None else None,provenance=params.get("provenance"))
def _handle_workspace_cognition_next(protocol, params): return protocol.workspace.cognition_next(protocol._optional(params,"agent_id",str),protocol._optional(params,"episode_id",str))
def _handle_workspace_cognition_probe_unknowns(protocol, params): return protocol.workspace.cognition_probe_unknowns(protocol._optional(params,"agent_id",str),record=protocol._bool(params,"record",False))
def _handle_workspace_cognition_plan(protocol, params): return protocol.workspace.cognition_plan(protocol._optional(params,"agent_id",str),protocol._optional(params,"episode_id",str),protocol._int(params,"limit",8))
def _handle_workspace_cognition_health(protocol, params): return protocol.workspace.cognition_health(protocol._optional(params,"agent_id",str))
def _handle_workspace_executive_start(protocol, params): return protocol.workspace.executive_start(protocol._required(params,"goal",str),agent_id=protocol._optional(params,"agent_id",str),episode_id=protocol._optional(params,"episode_id",str),budget=params.get("budget"),initial_strategy=protocol._optional(params,"initial_strategy",str) or "direct-analysis")
def _handle_workspace_executive_status(protocol, params): return protocol.workspace.executive_status(protocol._required(params,"trajectory_id",str))
def _handle_workspace_executive_plan(protocol, params): return protocol.workspace.executive_plan(protocol._required(params,"trajectory_id",str),limit=protocol._int(params,"limit",8))
def _handle_workspace_executive_advance(protocol, params): return protocol.workspace.executive_advance(protocol._required(params,"trajectory_id",str),protocol._required(params,"phase",str),protocol._required(params,"operation",str),status=protocol._optional(params,"status",str) or "passed",progress=protocol._bool(params,"progress",False),ref_id=protocol._optional(params,"ref_id",str),data=params.get("data"))
def _handle_workspace_executive_milestone_add(protocol, params): return protocol.workspace.executive_milestone_add(protocol._required(params,"trajectory_id",str),protocol._required(params,"title",str),protocol._required(params,"postcondition",str),priority=protocol._optional(params,"priority",str) or "high",dependencies=params.get("dependencies"),verifier_ref=protocol._optional(params,"verifier_ref",str),rollback=protocol._optional(params,"rollback",str))
def _handle_workspace_executive_milestone_update(protocol, params): return protocol.workspace.executive_milestone_update(protocol._required(params,"trajectory_id",str),protocol._required(params,"milestone_id",str),status=protocol._required(params,"status",str),verifier_ref=protocol._optional(params,"verifier_ref",str),result=params.get("result"))
def _handle_workspace_executive_complete(protocol, params): return protocol.workspace.executive_complete(protocol._required(params,"trajectory_id",str),outcome=params.get("outcome"))
def _handle_workspace_executive_stop(protocol, params): return protocol.workspace.executive_stop(protocol._required(params,"trajectory_id",str),status=protocol._optional(params,"status",str) or "abandoned",reason=protocol._required(params,"reason",str),outcome=params.get("outcome"))
def _handle_workspace_project_world(protocol, params): return protocol.workspace.project_world()
def _handle_workspace_effect_refresh(protocol, params): return protocol.workspace.effect_refresh(params.get("paths"))
def _handle_workspace_effect_snapshot(protocol, params): return protocol.workspace.effect_snapshot(path=protocol._optional(params,"path",str),symbol_id=protocol._optional(params,"symbol_id",str),kind=protocol._optional(params,"kind",str),limit=protocol._int(params,"limit",1000))
def _handle_workspace_dataflow_refresh(protocol, params): return protocol.workspace.dataflow_refresh(params.get("paths"))
def _handle_workspace_dataflow_snapshot(protocol, params): return protocol.workspace.dataflow_snapshot(path=protocol._optional(params,"path",str),symbol_id=protocol._optional(params,"symbol_id",str),kind=protocol._optional(params,"kind",str),source=protocol._optional(params,"source",str),target=protocol._optional(params,"target",str),limit=protocol._int(params,"limit",1000))
def _handle_workspace_runtime_topology(protocol, params): return protocol.workspace.runtime_topology(agent_id=protocol._optional(params,"agent_id",str),limit=protocol._int(params,"limit",500))
def _handle_workspace_counterfactual_fork(protocol, params): return protocol.workspace.counterfactual_fork(protocol._required(params,"label",str),agent_id=protocol._optional(params,"agent_id",str),metadata=params.get("metadata"))
def _handle_workspace_counterfactual_status(protocol, params): return protocol.workspace.counterfactual_status(protocol._required(params,"world_id",str))
def _handle_workspace_counterfactual_apply(protocol, params): return protocol.workspace.counterfactual_apply(protocol._required(params,"world_id",str),protocol._required(params,"changes",list))
def _handle_workspace_counterfactual_evaluate(protocol, params): return protocol.workspace.counterfactual_evaluate(protocol._required(params,"world_id",str))
def _handle_workspace_counterfactual_compare(protocol, params): return protocol.workspace.counterfactual_compare(protocol._required(params,"world_ids",list))
def _handle_workspace_counterfactual_verify(protocol, params): return protocol.workspace.counterfactual_verify(protocol._required(params,"world_id",str),timeout_s=protocol._int(params,"timeout_s",60))
def _handle_workspace_counterfactual_promote(protocol, params): return protocol.workspace.counterfactual_promote(protocol._required(params,"world_id",str),agent_id=protocol._optional(params,"agent_id",str),episode_id=protocol._optional(params,"episode_id",str),approval_id=protocol._optional(params,"approval_id",str))
def _handle_workspace_counterfactual_discard(protocol, params): return protocol.workspace.counterfactual_discard(protocol._required(params,"world_id",str))
def _handle_workspace_memory_record(protocol, params): return protocol.workspace.memory_record(protocol._required(params,"kind",str),protocol._required(params,"statement",str),agent_id=protocol._optional(params,"agent_id",str),episode_id=protocol._optional(params,"episode_id",str),confidence=protocol._float(params,"confidence") if "confidence" in params and params.get("confidence") is not None else None,provenance=params.get("provenance"),evidence_ids=params.get("evidence_ids"),supersedes=protocol._optional(params,"supersedes",str),valid_until_revision=protocol._optional(params,"valid_until_revision",str))
def _handle_workspace_memory_status(protocol, params): return protocol.workspace.memory_status(protocol._required(params,"memory_id",str))
def _handle_workspace_memory_recall(protocol, params): return protocol.workspace.memory_recall(protocol._required(params,"query",str),agent_id=protocol._optional(params,"agent_id",str),kinds=params.get("kinds"),limit=protocol._int(params,"limit",20))
def _handle_workspace_memory_invalidate(protocol, params): return protocol.workspace.memory_invalidate(protocol._required(params,"memory_id",str),protocol._required(params,"reason",str),invalidated_by=protocol._optional(params,"invalidated_by",str))
def _handle_workspace_runtime_ingest(protocol, params): return protocol.workspace.runtime_ingest(protocol._required(params,"signal",str),protocol._required(params,"records",list),agent_id=protocol._optional(params,"agent_id",str),episode_id=protocol._optional(params,"episode_id",str))
def _handle_workspace_runtime_timeline(protocol, params): return protocol.workspace.runtime_timeline(trace_id=protocol._optional(params,"trace_id",str),agent_id=protocol._optional(params,"agent_id",str),limit=protocol._int(params,"limit",200))
def _handle_workspace_policy_status(protocol, params): return protocol.workspace.policy_status()
def _handle_workspace_policy_update(protocol, params): return protocol.workspace.policy_update(protocol._required(params,"patch",dict))
def _handle_workspace_policy_evaluate(protocol, params): return protocol.workspace.policy_evaluate(protocol._required(params,"action",str),path=protocol._optional(params,"path",str),capability_id=protocol._optional(params,"capability_id",str),structural=protocol._bool(params,"structural",False))
def _handle_workspace_execution_security(protocol, params): return protocol.workspace.execution_security()
def _handle_workspace_execution_configure(protocol, params): return protocol.workspace.execution_configure(protocol._required(params,"containment_profile",str))
def _handle_workspace_sandbox_status(protocol, params): return protocol.workspace.sandbox_status()
def _handle_workspace_retention_status(protocol, params): return protocol.workspace.retention_status(params.get("policy"))
def _handle_workspace_retention_compact(protocol, params): return protocol.workspace.retention_compact(params.get("policy"),dry_run=protocol._bool(params,"dry_run",True))
def _handle_workspace_state_security(protocol, params): return protocol.workspace.state_security()
def _handle_workspace_world_summary(protocol, params): return protocol.workspace.world_summary()
def _handle_workspace_world_health(protocol, params): return protocol.workspace.world_health(protocol._optional(params,"agent_id",str))
def _handle_workspace_guidance_discover(protocol, params): return protocol.workspace.guidance_discover()
def _handle_workspace_guidance_read(protocol, params): return protocol.workspace.guidance_read(protocol._required(params,"path",str),protocol._int(params,"start_line",1),protocol._int(params,"max_lines",200))
def _handle_workspace_git_status(protocol, params): return protocol.workspace.git_status()
def _handle_workspace_git_history(protocol, params): return protocol.workspace.git_history(protocol._optional(params,"path",str),protocol._int(params,"limit",20))
def _handle_workspace_git_blame(protocol, params): return protocol.workspace.git_blame(protocol._required(params,"path",str),protocol._int(params,"start_line",1),protocol._int(params,"end_line") if "end_line" in params else None)
def _handle_workspace_git_explain_line(protocol, params): return protocol.workspace.git_explain_line(protocol._required(params,"path",str),protocol._int(params,"line"))
def _handle_workspace_git_diff(protocol, params): return protocol.workspace.git_diff(protocol._optional(params,"commit",str),protocol._optional(params,"path",str),protocol._int(params,"context",3))
def _handle_workspace_git_changed_files(protocol, params): return protocol.workspace.git_changed_files(params.get("commit","HEAD"),protocol._int(params,"limit",500))
def _handle_workspace_git_churn(protocol, params): return protocol.workspace.git_churn(protocol._required(params,"path",str),protocol._int(params,"limit",200))
def _handle_workspace_git_explain_symbol(protocol, params): return protocol.workspace.git_explain_symbol(protocol._required(params,"object_id",str))
def _handle_workspace_git_branches(protocol, params): return protocol.workspace.git_branches(protocol._int(params,"limit",200))
def _handle_workspace_git_worktrees(protocol, params): return protocol.workspace.git_worktrees()
def _handle_workspace_git_conflicts(protocol, params): return protocol.workspace.git_conflicts()
def _handle_workspace_git_commit_impact(protocol, params): return protocol.workspace.git_commit_impact(params.get("commit","HEAD"),protocol._int(params,"limit",1000))
def _handle_workspace_dependencies_snapshot(protocol, params): return protocol.workspace.dependencies_snapshot()
def _handle_workspace_dependencies_query(protocol, params): return protocol.workspace.dependencies_query(protocol._required(params,"term",str))
def _handle_workspace_dependencies_world(protocol, params): return protocol.workspace.dependencies_world()
def _handle_workspace_agent_open(protocol, params): return protocol.workspace.agent_open(protocol._required(params,"name",str),params.get("metadata"))
def _handle_workspace_agent_status(protocol, params): return protocol.workspace.agent_status(protocol._required(params,"agent_id",str))
def _handle_workspace_agent_close(protocol, params): return protocol.workspace.agent_close(protocol._required(params,"agent_id",str))
def _handle_workspace_agent_observe(protocol, params): return protocol.workspace.agent_observe(protocol._required(params,"agent_id",str),protocol._required(params,"path",str),object_id=params.get("object_id","") or "",kind=params.get("kind","source"))
def _handle_workspace_agent_notifications(protocol, params): return protocol.workspace.agent_notifications(protocol._required(params,"agent_id",str),params.get("status","pending"),protocol._int(params,"limit",100))
def _handle_workspace_agent_notifications_ack(protocol, params): return protocol.workspace.agent_ack_notification(protocol._required(params,"agent_id",str),protocol._required(params,"notification_id",str))
def _handle_workspace_agent_revalidate(protocol, params): return protocol.workspace.agent_revalidate_notification(protocol._required(params,"agent_id",str),protocol._required(params,"notification_id",str))
def _handle_workspace_agent_residency_admit(protocol, params): return protocol.workspace.agent_residency_admit(protocol._required(params,"agent_id",str),protocol._required(params,"handle",str),protocol._int(params,"max_admit",8),protocol._int(params,"pin_top",0))
def _handle_workspace_agent_residency_status(protocol, params): return protocol.workspace.agent_residency_status(protocol._required(params,"agent_id",str))
def _handle_workspace_agent_residency_evict(protocol, params): return protocol.workspace.agent_residency_evict(protocol._required(params,"agent_id",str),protocol._required(params,"object_ids",list))
def _handle_workspace_lease_acquire(protocol, params): return protocol.workspace.lease_acquire(protocol._required(params,"agent_id",str),protocol._required(params,"resource_kind",str),protocol._required(params,"resource_id",str),protocol._float(params,"ttl_s",120.0),protocol._optional(params,"transaction_id",str))
def _handle_workspace_lease_release(protocol, params): return protocol.workspace.lease_release(protocol._required(params,"agent_id",str),protocol._required(params,"resource_kind",str),protocol._required(params,"resource_id",str))
def _handle_workspace_lease_status(protocol, params): return protocol.workspace.lease_status(protocol._optional(params,"agent_id",str))
def _handle_action_run(protocol, params): return protocol.workspace.run(protocol._required(params,"capability",str),protocol._int(params,"timeout_s",60),protocol._optional(params,"approval_id",str))
def _handle_ui_observe(protocol, params): return protocol.workspace.observe_ui(protocol._required(params,"path",str))
def _handle_ui_runtime_open(protocol, params): return protocol.workspace.open_ui_runtime(protocol._required(params,"target",str),protocol._bool(params,"screenshot",False),protocol._optional(params,"viewport",dict),protocol._bool(params,"allow_external",False))
def _handle_ui_runtime_observe(protocol, params): return protocol.workspace.observe_ui_runtime(protocol._required(params,"session_id",str),protocol._bool(params,"screenshot",False))
def _handle_ui_runtime_act(protocol, params): return protocol.workspace.act_ui_runtime(protocol._required(params,"session_id",str),protocol._required(params,"action",str),protocol._required(params,"handle",str),protocol._optional(params,"value",str),protocol._bool(params,"screenshot",False))
def _handle_ui_runtime_assert(protocol, params): return protocol.workspace.assert_ui_runtime(protocol._required(params,"session_id",str),protocol._required(params,"assertions",list))
def _handle_ui_runtime_close(protocol, params): return protocol.workspace.close_ui_runtime(protocol._required(params,"session_id",str))


OPERATION_DESCRIPTORS = (
    OperationDescriptor("protocol.capabilities", _handle_protocol_capabilities, read_only=True),
    OperationDescriptor("workspace.enter", _handle_workspace_enter),
    OperationDescriptor("workspace.refresh", _handle_workspace_refresh),
    OperationDescriptor("workspace.orient", _handle_workspace_orient),
    OperationDescriptor("workspace.explore", _handle_workspace_explore),
    OperationDescriptor("workspace.context.page", _handle_workspace_context_page),
    OperationDescriptor("workspace.context.refresh", _handle_workspace_context_refresh),
    OperationDescriptor("workspace.query", _handle_workspace_query),
    OperationDescriptor("workspace.inspect", _handle_workspace_inspect, read_only=True),
    OperationDescriptor("workspace.inspect.batch", _handle_workspace_inspect_batch, read_only=True),
    OperationDescriptor("workspace.context.materialize", _handle_workspace_context_materialize),
    OperationDescriptor("workspace.context.address_space", _handle_workspace_context_address_space),
    OperationDescriptor("workspace.context.fetch", _handle_workspace_context_fetch),
    OperationDescriptor("workspace.context.prefetch", _handle_workspace_context_prefetch),
    OperationDescriptor("workspace.context.plan_next", _handle_workspace_context_plan_next),
    OperationDescriptor("workspace.context.feedback", _handle_workspace_context_feedback),
    OperationDescriptor("workspace.context.efficiency", _handle_workspace_context_efficiency),
    OperationDescriptor("workspace.references", _handle_workspace_references, read_only=True),
    OperationDescriptor("workspace.impact", _handle_workspace_impact),
    OperationDescriptor("workspace.source.read", _handle_workspace_source_read, read_only=True),
    OperationDescriptor("workspace.change.plan", _handle_workspace_change_plan),
    OperationDescriptor("workspace.change.stage", _handle_workspace_change_stage),
    OperationDescriptor("workspace.change.stage_symbol", _handle_workspace_change_stage_symbol),
    OperationDescriptor("workspace.change.stage_rename_symbol", _handle_workspace_change_stage_rename_symbol),
    OperationDescriptor("workspace.change.commit", _handle_workspace_change_commit),
    OperationDescriptor("workspace.change.rollback", _handle_workspace_change_rollback),
    OperationDescriptor("workspace.verification.plan", _handle_workspace_verification_plan),
    OperationDescriptor("workspace.verification.run", _handle_workspace_verification_run),
    OperationDescriptor("workspace.events.poll", _handle_workspace_events_poll),
    OperationDescriptor("workspace.diff.since", _handle_workspace_diff_since),
    OperationDescriptor("workspace.state.merkle", _handle_workspace_state_merkle),
    OperationDescriptor("workspace.state.merkle.diff", _handle_workspace_state_merkle_diff),
    OperationDescriptor("workspace.watch.start", _handle_workspace_watch_start),
    OperationDescriptor("workspace.watch.poll", _handle_workspace_watch_poll),
    OperationDescriptor("workspace.watch.wait", _handle_workspace_watch_wait),
    OperationDescriptor("workspace.watch.status", _handle_workspace_watch_status),
    OperationDescriptor("workspace.watch.stop", _handle_workspace_watch_stop),
    OperationDescriptor("workspace.backend.info", _handle_workspace_backend_info),
    OperationDescriptor("workspace.semantic.providers", _handle_workspace_semantic_providers),
    OperationDescriptor("workspace.semantic.fabric", _handle_workspace_semantic_fabric),
    OperationDescriptor("workspace.evidence.active", _handle_workspace_evidence_active),
    OperationDescriptor("workspace.episode.start", _handle_workspace_episode_start),
    OperationDescriptor("workspace.episode.status", _handle_workspace_episode_status),
    OperationDescriptor("workspace.episode.finish", _handle_workspace_episode_finish),
    OperationDescriptor("workspace.episode.efficiency", _handle_workspace_episode_efficiency),
    OperationDescriptor("workspace.invariant.create", _handle_workspace_invariant_create),
    OperationDescriptor("workspace.invariant.status", _handle_workspace_invariant_status),
    OperationDescriptor("workspace.invariant.link", _handle_workspace_invariant_link),
    OperationDescriptor("workspace.invariant.update", _handle_workspace_invariant_update),
    OperationDescriptor("workspace.hypothesis.create", _handle_workspace_hypothesis_create),
    OperationDescriptor("workspace.hypothesis.status", _handle_workspace_hypothesis_status),
    OperationDescriptor("workspace.hypothesis.link_evidence", _handle_workspace_hypothesis_link_evidence),
    OperationDescriptor("workspace.hypothesis.update", _handle_workspace_hypothesis_update),
    OperationDescriptor("workspace.hypothesis.compare", _handle_workspace_hypothesis_compare),
    OperationDescriptor("workspace.hypothesis.next_experiment", _handle_workspace_hypothesis_next_experiment),
    OperationDescriptor("workspace.agent.belief.update", _handle_workspace_agent_belief_update),
    OperationDescriptor("workspace.agent.belief.status", _handle_workspace_agent_belief_status),
    OperationDescriptor("workspace.agent.belief.portfolio", _handle_workspace_agent_belief_portfolio),
    OperationDescriptor("workspace.experiment.plan", _handle_workspace_experiment_plan),
    OperationDescriptor("workspace.experiment.status", _handle_workspace_experiment_status),
    OperationDescriptor("workspace.experiment.complete", _handle_workspace_experiment_complete),
    OperationDescriptor("workspace.causality.explain", _handle_workspace_causality_explain),
    OperationDescriptor("workspace.causality.graph", _handle_workspace_causality_graph),
    OperationDescriptor("workspace.checkpoint", _handle_workspace_checkpoint),
    OperationDescriptor("workspace.resume", _handle_workspace_resume),
    OperationDescriptor("workspace.context.residency.configure", _handle_workspace_context_residency_configure),
    OperationDescriptor("workspace.context.residency.admit", _handle_workspace_context_residency_admit),
    OperationDescriptor("workspace.context.residency.status", _handle_workspace_context_residency_status),
    OperationDescriptor("workspace.context.residency.materialize", _handle_workspace_context_residency_materialize),
    OperationDescriptor("workspace.context.residency.touch", _handle_workspace_context_residency_touch),
    OperationDescriptor("workspace.context.residency.pin", _handle_workspace_context_residency_pin),
    OperationDescriptor("workspace.context.residency.evict", _handle_workspace_context_residency_evict),
    OperationDescriptor("workspace.trace.start", _handle_workspace_trace_start),
    OperationDescriptor("workspace.trace.status", _handle_workspace_trace_status),
    OperationDescriptor("workspace.trace.stop", _handle_workspace_trace_stop),
    OperationDescriptor("workspace.activity.since", _handle_workspace_activity_since),
    OperationDescriptor("workspace.observatory.start", _handle_workspace_observatory_start),
    OperationDescriptor("workspace.observatory.status", _handle_workspace_observatory_status),
    OperationDescriptor("workspace.observatory.stop", _handle_workspace_observatory_stop),
    OperationDescriptor("workspace.epistemic.create", _handle_workspace_epistemic_create),
    OperationDescriptor("workspace.epistemic.state", _handle_workspace_epistemic_state),
    OperationDescriptor("workspace.epistemic.update", _handle_workspace_epistemic_update),
    OperationDescriptor("workspace.cognition.next", _handle_workspace_cognition_next),
    OperationDescriptor("workspace.cognition.probe_unknowns", _handle_workspace_cognition_probe_unknowns),
    OperationDescriptor("workspace.cognition.plan", _handle_workspace_cognition_plan),
    OperationDescriptor("workspace.cognition.health", _handle_workspace_cognition_health),
    OperationDescriptor("workspace.executive.start", _handle_workspace_executive_start),
    OperationDescriptor("workspace.executive.status", _handle_workspace_executive_status),
    OperationDescriptor("workspace.executive.plan", _handle_workspace_executive_plan),
    OperationDescriptor("workspace.executive.advance", _handle_workspace_executive_advance),
    OperationDescriptor("workspace.executive.milestone.add", _handle_workspace_executive_milestone_add),
    OperationDescriptor("workspace.executive.milestone.update", _handle_workspace_executive_milestone_update),
    OperationDescriptor("workspace.executive.complete", _handle_workspace_executive_complete),
    OperationDescriptor("workspace.executive.stop", _handle_workspace_executive_stop),
    OperationDescriptor("workspace.project.world", _handle_workspace_project_world),
    OperationDescriptor("workspace.effect.refresh", _handle_workspace_effect_refresh),
    OperationDescriptor("workspace.effect.snapshot", _handle_workspace_effect_snapshot),
    OperationDescriptor("workspace.dataflow.refresh", _handle_workspace_dataflow_refresh),
    OperationDescriptor("workspace.dataflow.snapshot", _handle_workspace_dataflow_snapshot),
    OperationDescriptor("workspace.runtime.topology", _handle_workspace_runtime_topology),
    OperationDescriptor("workspace.counterfactual.fork", _handle_workspace_counterfactual_fork),
    OperationDescriptor("workspace.counterfactual.status", _handle_workspace_counterfactual_status),
    OperationDescriptor("workspace.counterfactual.apply", _handle_workspace_counterfactual_apply),
    OperationDescriptor("workspace.counterfactual.evaluate", _handle_workspace_counterfactual_evaluate),
    OperationDescriptor("workspace.counterfactual.compare", _handle_workspace_counterfactual_compare),
    OperationDescriptor("workspace.counterfactual.verify", _handle_workspace_counterfactual_verify),
    OperationDescriptor("workspace.counterfactual.promote", _handle_workspace_counterfactual_promote),
    OperationDescriptor("workspace.counterfactual.discard", _handle_workspace_counterfactual_discard),
    OperationDescriptor("workspace.memory.record", _handle_workspace_memory_record),
    OperationDescriptor("workspace.memory.status", _handle_workspace_memory_status),
    OperationDescriptor("workspace.memory.recall", _handle_workspace_memory_recall),
    OperationDescriptor("workspace.memory.invalidate", _handle_workspace_memory_invalidate),
    OperationDescriptor("workspace.runtime.ingest", _handle_workspace_runtime_ingest),
    OperationDescriptor("workspace.runtime.timeline", _handle_workspace_runtime_timeline),
    OperationDescriptor("workspace.policy.status", _handle_workspace_policy_status),
    OperationDescriptor("workspace.policy.update", _handle_workspace_policy_update),
    OperationDescriptor("workspace.policy.evaluate", _handle_workspace_policy_evaluate),
    OperationDescriptor("workspace.execution.security", _handle_workspace_execution_security),
    OperationDescriptor("workspace.execution.configure", _handle_workspace_execution_configure),
    OperationDescriptor("workspace.sandbox.status", _handle_workspace_sandbox_status),
    OperationDescriptor("workspace.retention.status", _handle_workspace_retention_status),
    OperationDescriptor("workspace.retention.compact", _handle_workspace_retention_compact),
    OperationDescriptor("workspace.state.security", _handle_workspace_state_security),
    OperationDescriptor("workspace.world.summary", _handle_workspace_world_summary),
    OperationDescriptor("workspace.world.health", _handle_workspace_world_health),
    OperationDescriptor("workspace.guidance.discover", _handle_workspace_guidance_discover),
    OperationDescriptor("workspace.guidance.read", _handle_workspace_guidance_read),
    OperationDescriptor("workspace.git.status", _handle_workspace_git_status),
    OperationDescriptor("workspace.git.history", _handle_workspace_git_history),
    OperationDescriptor("workspace.git.blame", _handle_workspace_git_blame),
    OperationDescriptor("workspace.git.explain_line", _handle_workspace_git_explain_line),
    OperationDescriptor("workspace.git.diff", _handle_workspace_git_diff),
    OperationDescriptor("workspace.git.changed_files", _handle_workspace_git_changed_files),
    OperationDescriptor("workspace.git.churn", _handle_workspace_git_churn),
    OperationDescriptor("workspace.git.explain_symbol", _handle_workspace_git_explain_symbol),
    OperationDescriptor("workspace.git.branches", _handle_workspace_git_branches),
    OperationDescriptor("workspace.git.worktrees", _handle_workspace_git_worktrees),
    OperationDescriptor("workspace.git.conflicts", _handle_workspace_git_conflicts),
    OperationDescriptor("workspace.git.commit_impact", _handle_workspace_git_commit_impact),
    OperationDescriptor("workspace.dependencies.snapshot", _handle_workspace_dependencies_snapshot),
    OperationDescriptor("workspace.dependencies.query", _handle_workspace_dependencies_query),
    OperationDescriptor("workspace.dependencies.world", _handle_workspace_dependencies_world),
    OperationDescriptor("workspace.agent.open", _handle_workspace_agent_open),
    OperationDescriptor("workspace.agent.status", _handle_workspace_agent_status),
    OperationDescriptor("workspace.agent.close", _handle_workspace_agent_close),
    OperationDescriptor("workspace.agent.observe", _handle_workspace_agent_observe),
    OperationDescriptor("workspace.agent.notifications", _handle_workspace_agent_notifications),
    OperationDescriptor("workspace.agent.notifications.ack", _handle_workspace_agent_notifications_ack),
    OperationDescriptor("workspace.agent.revalidate", _handle_workspace_agent_revalidate),
    OperationDescriptor("workspace.agent.residency.admit", _handle_workspace_agent_residency_admit),
    OperationDescriptor("workspace.agent.residency.status", _handle_workspace_agent_residency_status),
    OperationDescriptor("workspace.agent.residency.evict", _handle_workspace_agent_residency_evict),
    OperationDescriptor("workspace.lease.acquire", _handle_workspace_lease_acquire),
    OperationDescriptor("workspace.lease.release", _handle_workspace_lease_release),
    OperationDescriptor("workspace.lease.status", _handle_workspace_lease_status),
    OperationDescriptor("action.run", _handle_action_run),
    OperationDescriptor("ui.observe", _handle_ui_observe),
    OperationDescriptor("ui.runtime.open", _handle_ui_runtime_open),
    OperationDescriptor("ui.runtime.observe", _handle_ui_runtime_observe),
    OperationDescriptor("ui.runtime.act", _handle_ui_runtime_act),
    OperationDescriptor("ui.runtime.assert", _handle_ui_runtime_assert),
    OperationDescriptor("ui.runtime.close", _handle_ui_runtime_close),
)

OPERATION_REGISTRY = OperationRegistry(OPERATION_DESCRIPTORS)
