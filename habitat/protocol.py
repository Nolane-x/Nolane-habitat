from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Any
from .model import to_dict
from .workspace import HabitatWorkspace

PROTOCOL_VERSION = "habitat.agent.v1alpha2"
MAX_REQUEST_BYTES = 256 * 1024

@dataclass
class ProtocolError(Exception):
    code: str; message: str; details: dict[str, Any] | None = None
    def __str__(self): return self.message


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _reject_nonstandard_number(_value: str) -> None:
    raise ValueError("non-standard number")


def _contains_unpaired_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    if isinstance(value, dict):
        return any(_contains_unpaired_surrogate(key) or _contains_unpaired_surrogate(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_unpaired_surrogate(item) for item in value)
    return False


def parse_json_request(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8", errors="surrogatepass")) > MAX_REQUEST_BYTES:
        raise ProtocolError("REQUEST_TOO_LARGE", "request exceeds the protocol size limit")
    try:
        request = json.loads(raw, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonstandard_number)
    except (json.JSONDecodeError, ValueError):
        raise ProtocolError("INVALID_JSON", "request must be strict JSON") from None
    if not isinstance(request, dict):
        raise ProtocolError("INVALID_REQUEST", "request must be a JSON object")
    if _contains_unpaired_surrogate(request):
        raise ProtocolError("INVALID_REQUEST", "request contains an unpaired surrogate")
    return request

class HabitatProtocol:
    # These operations are safe projections. They must not create activity or trace rows merely
    # because a client observed state; additions require logical-state conformance evidence.
    READ_ONLY_METHODS = frozenset({
        "protocol.capabilities", "workspace.enter", "workspace.query", "workspace.inspect",
        "workspace.inspect.batch", "workspace.references", "workspace.impact",
        "workspace.source.read", "workspace.verification.plan", "workspace.diff.since",
        "workspace.state.merkle", "workspace.state.merkle.diff", "workspace.backend.info",
        "workspace.semantic.providers", "workspace.semantic.fabric", "workspace.evidence.active",
    })
    METHODS = [
        "protocol.capabilities","workspace.enter","workspace.refresh","workspace.orient","workspace.explore","workspace.context.page","workspace.context.refresh",
        "workspace.query","workspace.inspect","workspace.inspect.batch","workspace.context.materialize","workspace.context.address_space","workspace.context.fetch","workspace.context.prefetch","workspace.context.plan_next","workspace.context.feedback","workspace.context.efficiency","workspace.references","workspace.impact","workspace.source.read",
        "workspace.change.plan","workspace.change.stage","workspace.change.stage_symbol","workspace.change.stage_rename_symbol","workspace.change.commit","workspace.change.rollback",
        "workspace.verification.plan","workspace.verification.run","workspace.events.poll","workspace.diff.since","workspace.state.merkle","workspace.state.merkle.diff",
        "workspace.watch.start","workspace.watch.poll","workspace.watch.wait","workspace.watch.status","workspace.watch.stop",
        "workspace.backend.info","workspace.semantic.providers","workspace.semantic.fabric","workspace.evidence.active","workspace.episode.start","workspace.episode.status","workspace.episode.finish","workspace.episode.efficiency",
        "workspace.invariant.create","workspace.invariant.status","workspace.invariant.link","workspace.invariant.update",
        "workspace.hypothesis.create","workspace.hypothesis.status","workspace.hypothesis.link_evidence","workspace.hypothesis.update","workspace.hypothesis.compare","workspace.hypothesis.next_experiment","workspace.agent.belief.update","workspace.agent.belief.status","workspace.agent.belief.portfolio",
        "workspace.experiment.plan","workspace.experiment.status","workspace.experiment.complete",
        "workspace.causality.explain","workspace.causality.graph","workspace.checkpoint","workspace.resume",
        "workspace.context.residency.configure","workspace.context.residency.admit","workspace.context.residency.status",
        "workspace.context.residency.materialize","workspace.context.residency.touch","workspace.context.residency.pin","workspace.context.residency.evict",
        "workspace.trace.start","workspace.trace.status","workspace.trace.stop",
        "workspace.activity.since","workspace.observatory.start","workspace.observatory.status","workspace.observatory.stop",
        "workspace.epistemic.create","workspace.epistemic.state","workspace.epistemic.update","workspace.cognition.next","workspace.cognition.probe_unknowns","workspace.cognition.plan","workspace.cognition.health",
        "workspace.executive.start","workspace.executive.status","workspace.executive.plan","workspace.executive.advance","workspace.executive.milestone.add","workspace.executive.milestone.update","workspace.executive.complete","workspace.executive.stop",
        "workspace.project.world","workspace.effect.refresh","workspace.effect.snapshot","workspace.dataflow.refresh","workspace.dataflow.snapshot","workspace.runtime.topology",
        "workspace.counterfactual.fork","workspace.counterfactual.status","workspace.counterfactual.apply","workspace.counterfactual.evaluate","workspace.counterfactual.compare","workspace.counterfactual.verify","workspace.counterfactual.promote","workspace.counterfactual.discard",
        "workspace.memory.record","workspace.memory.status","workspace.memory.recall","workspace.memory.invalidate",
        "workspace.runtime.ingest","workspace.runtime.timeline",
        "workspace.policy.status","workspace.policy.update","workspace.policy.evaluate",
        "workspace.execution.security","workspace.execution.configure","workspace.sandbox.status",
        "workspace.retention.status","workspace.retention.compact","workspace.state.security","workspace.world.summary","workspace.world.health","workspace.guidance.discover","workspace.guidance.read",
        "workspace.git.status","workspace.git.history","workspace.git.blame","workspace.git.explain_line","workspace.git.diff","workspace.git.changed_files","workspace.git.churn","workspace.git.explain_symbol","workspace.git.branches","workspace.git.worktrees","workspace.git.conflicts","workspace.git.commit_impact",
        "workspace.dependencies.snapshot","workspace.dependencies.query","workspace.dependencies.world",
        "workspace.agent.open","workspace.agent.status","workspace.agent.close","workspace.agent.observe","workspace.agent.notifications","workspace.agent.notifications.ack","workspace.agent.revalidate",
        "workspace.agent.residency.admit","workspace.agent.residency.status","workspace.agent.residency.evict",
        "workspace.lease.acquire","workspace.lease.release","workspace.lease.status",
        "action.run","ui.observe","ui.runtime.open","ui.runtime.observe","ui.runtime.act","ui.runtime.assert","ui.runtime.close"
    ]
    def __init__(self, workspace: HabitatWorkspace): self.workspace=workspace
    @staticmethod
    def _exact_source_bytes(value: Any) -> int:
        total = 0
        if isinstance(value, dict):
            source = value.get("source")
            authority = str(value.get("source_authority") or value.get("authority") or "").lower()
            if isinstance(source, str) and ("exact" in authority or authority == "exact-source"):
                total += len(source.encode("utf-8"))
            for k, v in value.items():
                if k == "source":
                    continue
                total += HabitatProtocol._exact_source_bytes(v)
        elif isinstance(value, list):
            total += sum(HabitatProtocol._exact_source_bytes(v) for v in value)
        return total

    def handle(self, request: Any) -> dict[str, Any]:
        started = time.perf_counter()
        if not isinstance(request, dict):
            return self._error(None, "INVALID_REQUEST", "request must be a JSON object")
        if _contains_unpaired_surrogate(request):
            return self._error(request.get("id"), "INVALID_REQUEST", "request contains an unpaired surrogate")
        rid=request.get("id"); method=request.get("method"); params=request.get("params") or {}
        if not isinstance(method,str):
            response=self._error(rid,"INVALID_REQUEST","method must be a string")
        elif not isinstance(params,dict):
            response=self._error(rid,"INVALID_REQUEST","params must be an object")
        else:
            activity_allowed=(
                method not in self.READ_ONLY_METHODS
                and not method.startswith(("workspace.activity.","workspace.observatory.","workspace.trace."))
            )
            agent_id=params.get("agent_id") if isinstance(params.get("agent_id"),str) else None
            episode_id=params.get("episode_id") if isinstance(params.get("episode_id"),str) else None
            path=params.get("path") if isinstance(params.get("path"),str) else None
            if activity_allowed:
                try: self.workspace.activity_emit("tool.started","tool",agent_id=agent_id,episode_id=episode_id,ref_id=method,path=path,status="running",summary=method,data={"request_id":rid})
                except Exception: pass
            try:
                result=self._dispatch(method,params)
                response={"protocol":PROTOCOL_VERSION,"id":rid,"ok":True,"revision":self.workspace.revision,"result":to_dict(result)}
            except KeyError as exc: response=self._error(rid,"NOT_FOUND",str(exc))
            except (ValueError,TypeError) as exc: response=self._error(rid,"INVALID_PARAMS",str(exc))
            except Exception as exc: response=self._error(rid,type(exc).__name__.upper(),str(exc))
            if activity_allowed:
                try:
                    r=response.get("result") if isinstance(response,dict) else None
                    changed=(r.get("changed_paths") if isinstance(r,dict) else None) or ((r.get("transaction") or {}).get("changed_paths") if isinstance(r,dict) and isinstance(r.get("transaction"),dict) else None) or []
                    self.workspace.activity_emit("tool.completed","tool",agent_id=agent_id,episode_id=episode_id,ref_id=method,path=(changed[0] if changed else path),status="passed" if response.get("ok") else "failed",summary=method+(" completed" if response.get("ok") else " failed"),data={"request_id":rid,"changed_paths":changed[:20],"error":response.get("error") if not response.get("ok") else None})
                except Exception: pass
        # Trace is measurement infrastructure, not a source-state mutation. Control calls are excluded so
        # start/stop do not bias the measured workload they bracket.
        if isinstance(method,str) and method not in self.READ_ONLY_METHODS and not method.startswith("workspace.trace."):
            try:
                req_bytes=len(json.dumps(request,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8"))
                resp_bytes=len(json.dumps(response,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8"))
                source_bytes=self._exact_source_bytes(response)
                self.workspace.record_trace_call(method,bool(response.get("ok")),int((time.perf_counter()-started)*1000),req_bytes,resp_bytes,source_bytes)
            except Exception:
                # Telemetry must never change the agent operation result.
                pass
        return response
    @staticmethod
    def _int(p,k,default=None):
        if k not in p:
            if default is None: raise ValueError(f"missing required parameter: {k}")
            return default
        v=p[k]
        if not isinstance(v,int) or isinstance(v,bool): raise TypeError(f"{k} must be int")
        return v
    @staticmethod
    def _bool(p,k,default=None):
        if k not in p:
            if default is None: raise ValueError(f"missing required parameter: {k}")
            return default
        v=p[k]
        if not isinstance(v,bool): raise TypeError(f"{k} must be bool")
        return v
    @staticmethod
    def _float(p,k,default=None):
        if k not in p:
            if default is None: raise ValueError(f"missing required parameter: {k}")
            return default
        v=p[k]
        if not isinstance(v,(int,float)) or isinstance(v,bool): raise TypeError(f"{k} must be number")
        return float(v)

    @staticmethod
    def _optional(p,k,t):
        if k not in p or p[k] is None: return None
        if not isinstance(p[k],t): raise TypeError(f"{k} must be {t.__name__}")
        return p[k]

    def _dispatch(self,m,p):
        if m=="protocol.capabilities": return {"protocol":PROTOCOL_VERSION,"methods":self.METHODS,"generic_shell":False}
        if m=="workspace.enter": return self.workspace.enter()
        if m=="workspace.refresh": return self.workspace.refresh(p.get("reason","agent-refresh"))
        if m=="workspace.orient": return self.workspace.orient(self._required(p,"task",str),self._int(p,"budget",18),self._optional(p,"agent_id",str))
        if m=="workspace.explore": return self.workspace.explore(self._required(p,"task",str),self._int(p,"line_budget",120),self._int(p,"max_regions",12),self._int(p,"context_budget",40),self._optional(p,"agent_id",str))
        if m=="workspace.context.page": return self.workspace.context_page(self._required(p,"handle",str),self._int(p,"offset",0),self._int(p,"limit",20))
        if m=="workspace.context.refresh": return self.workspace.context_refresh(self._required(p,"handle",str),self._int(p,"budget") if "budget" in p else None)
        if m=="workspace.query": return self.workspace.query(self._required(p,"query",str),self._int(p,"limit",20))
        if m=="workspace.inspect": return self.workspace.inspect(self._required(p,"object_id",str),p.get("include_source","none"),self._optional(p,"agent_id",str))
        if m=="workspace.inspect.batch": return self.workspace.inspect_many(self._required(p,"object_ids",list),p.get("include_source","none"),self._int(p,"max_objects",50))
        if m=="workspace.context.materialize": return self.workspace.context_materialize(self._required(p,"handle",str),self._int(p,"max_source_bytes",60000),self._int(p,"max_objects",12))
        if m=="workspace.context.address_space": return self.workspace.context_address_space(self._required(p,"handle",str),self._int(p,"max_pages",100))
        if m=="workspace.context.fetch": return self.workspace.context_fetch_pages(self._required(p,"handle",str),self._required(p,"page_ids",list),self._int(p,"max_source_bytes",60000))
        if m=="workspace.context.prefetch": return self.workspace.context_prefetch(self._required(p,"handle",str),self._int(p,"max_source_bytes",20000),self._int(p,"max_pages",8))
        if m=="workspace.context.plan_next": return self.workspace.context_plan_next(self._required(p,"handle",str),p.get("fetched_page_ids"),self._int(p,"max_pages",3),self._int(p,"max_estimated_bytes",20000))
        if m=="workspace.context.feedback": return self.workspace.context_feedback(self._required(p,"handle",str),p.get("used_object_ids"),p.get("unhelpful_object_ids"),self._float(p,"weight",1.0),self._optional(p,"agent_id",str))
        if m=="workspace.context.efficiency": return self.workspace.context_efficiency(self._required(p,"handle",str))
        if m=="workspace.references": return self.workspace.references(self._required(p,"object_id",str),self._int(p,"limit",200))
        if m=="workspace.impact": return self.workspace.impact(p.get("changed_paths"),p.get("object_ids"),self._int(p,"max_depth",5))
        if m=="workspace.source.read": return self.workspace.read_source(self._required(p,"path",str),self._int(p,"start_line",1),self._int(p,"max_lines",200))
        if m=="workspace.change.plan": return self.workspace.change_plan(self._required(p,"operations",list))
        if m=="workspace.change.stage": return self.workspace.stage_change(self._required(p,"operations",list),self._optional(p,"episode_id",str),self._optional(p,"agent_id",str),self._float(p,"lease_ttl_s",120.0),self._optional(p,"approval_id",str))
        if m=="workspace.change.stage_symbol": return self.workspace.stage_symbol_change(self._required(p,"symbol_id",str),self._required(p,"new_source",str),self._optional(p,"episode_id",str),self._optional(p,"agent_id",str))
        if m=="workspace.change.stage_rename_symbol": return self.workspace.stage_symbol_rename(self._required(p,"symbol_id",str),self._required(p,"new_name",str),self._optional(p,"episode_id",str),self._optional(p,"agent_id",str))
        if m=="workspace.change.commit": return self.workspace.commit_change(self._required(p,"transaction_id",str),self._optional(p,"agent_id",str))
        if m=="workspace.change.rollback": return self.workspace.rollback_change(self._required(p,"transaction_id",str),self._optional(p,"agent_id",str))
        if m=="workspace.verification.plan": return self.workspace.verification_plan(p.get("changed_paths"),p.get("object_ids"))
        if m=="workspace.verification.run": return self.workspace.verify(p.get("changed_paths"),p.get("object_ids"),self._int(p,"timeout_s",60),p.get("episode_id"))
        if m=="workspace.events.poll": return self.workspace.events_poll(self._int(p,"since_seq",0),self._int(p,"limit",200),self._bool(p,"reconcile",True))
        if m=="workspace.diff.since": return self.workspace.diff_since(self._required(p,"revision_id",str))
        if m=="workspace.state.merkle": return self.workspace.state_merkle(p.get("revision_id"),p.get("prefix",""))
        if m=="workspace.state.merkle.diff": return self.workspace.state_merkle_diff(self._required(p,"from_revision",str),p.get("to_revision"),p.get("prefix",""))
        if m=="workspace.watch.start": return self.workspace.watch_start(self._float(p,"interval_s",0.25))
        if m=="workspace.watch.poll": return self.workspace.watch_poll(self._int(p,"limit",64))
        if m=="workspace.watch.wait": return self.workspace.watch_wait(self._float(p,"timeout_s",5.0),self._int(p,"limit",64))
        if m=="workspace.watch.status": return self.workspace.watch_status()
        if m=="workspace.watch.stop": return self.workspace.watch_stop()
        if m=="workspace.backend.info": return self.workspace.backend_info()
        if m=="workspace.semantic.providers": return self.workspace.semantic_provider_report()
        if m=="workspace.semantic.fabric": return self.workspace.semantic_fabric()
        if m=="workspace.evidence.active": return self.workspace.evidence_active(p.get("kind"),self._int(p,"limit",100))
        if m=="workspace.episode.start": return self.workspace.episode_start(self._required(p,"task",str),p.get("context_handle"))
        if m=="workspace.episode.status": return self.workspace.episode_status(self._required(p,"episode_id",str))
        if m=="workspace.episode.finish": return self.workspace.episode_finish(self._required(p,"episode_id",str),p.get("status","completed"),p.get("outcome"))
        if m=="workspace.episode.efficiency": return self.workspace.episode_efficiency(self._required(p,"episode_id",str))
        if m=="workspace.invariant.create": return self.workspace.invariant_create(self._required(p,"statement",str),severity=p.get("severity","error"),metadata=p.get("metadata"))
        if m=="workspace.invariant.status": return self.workspace.invariant_status(self._required(p,"invariant_id",str))
        if m=="workspace.invariant.link": return self.workspace.invariant_link(self._required(p,"invariant_id",str),self._required(p,"ref_kind",str),self._required(p,"ref_id",str),relation=p.get("relation","witness"),details=p.get("details"))
        if m=="workspace.invariant.update": return self.workspace.invariant_update(self._required(p,"invariant_id",str),self._required(p,"status",str))
        if m=="workspace.hypothesis.create": return self.workspace.hypothesis_create(self._required(p,"statement",str),episode_id=p.get("episode_id"),task=p.get("task"),prior_confidence=self._float(p,"prior_confidence",0.5))
        if m=="workspace.hypothesis.status": return self.workspace.hypothesis_status(self._required(p,"hypothesis_id",str))
        if m=="workspace.hypothesis.link_evidence": return self.workspace.hypothesis_link_evidence(self._required(p,"hypothesis_id",str),p.get("evidence_id"),self._required(p,"polarity",str),self._float(p,"weight",1.0),p.get("note"))
        if m=="workspace.hypothesis.update": return self.workspace.hypothesis_update(self._required(p,"hypothesis_id",str),status=p.get("status"),confidence=self._float(p,"confidence") if "confidence" in p else None,reason=p.get("reason"))
        if m=="workspace.agent.belief.update": return self.workspace.agent_belief_update(self._required(p,"agent_id",str),self._required(p,"hypothesis_id",str),stance=p.get("stance","uncertain"),confidence=p.get("confidence",0.5),rationale=p.get("rationale"))
        if m=="workspace.agent.belief.status": return self.workspace.agent_belief_status(self._required(p,"agent_id",str),self._required(p,"hypothesis_id",str))
        if m=="workspace.agent.belief.portfolio": return self.workspace.agent_belief_portfolio(self._required(p,"agent_id",str),self._int(p,"limit",200))
        if m=="workspace.hypothesis.compare": return self.workspace.hypothesis_compare(self._required(p,"hypothesis_ids",list))
        if m=="workspace.hypothesis.next_experiment": return self.workspace.hypothesis_next_experiment(self._required(p,"hypothesis_ids",list))
        if m=="workspace.experiment.plan": return self.workspace.experiment_plan(self._required(p,"description",str),hypothesis_id=p.get("hypothesis_id"),episode_id=p.get("episode_id"),discriminator=p.get("discriminator"),capability=p.get("capability"),expected=p.get("expected"))
        if m=="workspace.experiment.status": return self.workspace.experiment_status(self._required(p,"experiment_id",str))
        if m=="workspace.experiment.complete": return self.workspace.experiment_complete(self._required(p,"experiment_id",str),self._required(p,"result",dict),p.get("status","completed"))
        if m=="workspace.causality.explain": return self.workspace.causality_explain(self._required(p,"ref_id",str))
        if m=="workspace.causality.graph": return self.workspace.causality_graph(self._required(p,"ref_id",str),self._int(p,"max_depth",4),self._int(p,"max_edges",300))
        if m=="workspace.checkpoint": return self.workspace.checkpoint(self._required(p,"task",str),p.get("resident_object_ids"),p.get("notes"),p.get("next_action"),p.get("episode_id"))
        if m=="workspace.resume": return self.workspace.resume(self._required(p,"session_id",str))
        if m=="workspace.context.residency.configure": return self.workspace.residency_configure(self._int(p,"max_objects",32),self._int(p,"max_source_bytes",120000))
        if m=="workspace.context.residency.admit": return self.workspace.residency_admit(self._required(p,"handle",str),self._int(p,"pin_top",0),self._int(p,"max_admit") if "max_admit" in p else None)
        if m=="workspace.context.residency.status": return self.workspace.residency_status()
        if m=="workspace.context.residency.materialize": return self.workspace.residency_materialize(self._int(p,"max_source_bytes") if "max_source_bytes" in p else None,self._int(p,"max_objects") if "max_objects" in p else None)
        if m=="workspace.context.residency.touch": return self.workspace.residency_touch(self._required(p,"object_ids",list))
        if m=="workspace.context.residency.pin": return self.workspace.residency_pin(self._required(p,"object_ids",list),self._bool(p,"pinned",True))
        if m=="workspace.context.residency.evict": return self.workspace.residency_evict(p.get("object_ids"),self._bool(p,"stale_only",False))
        if m=="workspace.trace.start": return self.workspace.trace_start(p.get("label","agent-run"))
        if m=="workspace.trace.status": return self.workspace.trace_status(p.get("trace_id"))
        if m=="workspace.trace.stop": return self.workspace.trace_stop(p.get("trace_id"))
        if m=="workspace.activity.since": return self.workspace.activity_since(self._int(p,"since_seq",0),self._int(p,"limit",500))
        if m=="workspace.observatory.start": return self.workspace.observatory_start(host=p.get("host","127.0.0.1"),port=self._int(p,"port",0),open_browser=self._bool(p,"open_browser",True))
        if m=="workspace.observatory.status": return self.workspace.observatory_status()
        if m=="workspace.observatory.stop": return self.workspace.observatory_stop()
        if m=="workspace.epistemic.create": return self.workspace.epistemic_create(self._required(p,"kind",str),self._required(p,"statement",str),status=p.get("status","open"),confidence=self._float(p,"confidence") if "confidence" in p and p.get("confidence") is not None else None,scope=p.get("scope","workspace"),agent_id=self._optional(p,"agent_id",str),episode_id=self._optional(p,"episode_id",str),provenance=p.get("provenance"),invalidation_conditions=p.get("invalidation_conditions"))
        if m=="workspace.epistemic.state": return self.workspace.epistemic_state(self._optional(p,"agent_id",str),p.get("status","open"),self._int(p,"limit",200))
        if m=="workspace.epistemic.update": return self.workspace.epistemic_update(self._required(p,"item_id",str),status=p.get("status"),confidence=self._float(p,"confidence") if "confidence" in p and p.get("confidence") is not None else None,provenance=p.get("provenance"))
        if m=="workspace.cognition.next": return self.workspace.cognition_next(self._optional(p,"agent_id",str),self._optional(p,"episode_id",str))
        if m=="workspace.cognition.plan": return self.workspace.cognition_plan(self._optional(p,"agent_id",str),self._optional(p,"episode_id",str),self._int(p,"limit",8))
        if m=="workspace.cognition.health": return self.workspace.cognition_health(self._optional(p,"agent_id",str))
        if m=="workspace.cognition.probe_unknowns": return self.workspace.cognition_probe_unknowns(self._optional(p,"agent_id",str),record=self._bool(p,"record",False))
        if m=="workspace.executive.start": return self.workspace.executive_start(self._required(p,"goal",str),agent_id=self._optional(p,"agent_id",str),episode_id=self._optional(p,"episode_id",str),budget=p.get("budget"),initial_strategy=self._optional(p,"initial_strategy",str) or "direct-analysis")
        if m=="workspace.executive.status": return self.workspace.executive_status(self._required(p,"trajectory_id",str))
        if m=="workspace.executive.plan": return self.workspace.executive_plan(self._required(p,"trajectory_id",str),limit=self._int(p,"limit",8))
        if m=="workspace.executive.advance": return self.workspace.executive_advance(self._required(p,"trajectory_id",str),self._required(p,"phase",str),self._required(p,"operation",str),status=self._optional(p,"status",str) or "passed",progress=self._bool(p,"progress",False),ref_id=self._optional(p,"ref_id",str),data=p.get("data"))
        if m=="workspace.executive.milestone.add": return self.workspace.executive_milestone_add(self._required(p,"trajectory_id",str),self._required(p,"title",str),self._required(p,"postcondition",str),priority=self._optional(p,"priority",str) or "high",dependencies=p.get("dependencies"),verifier_ref=self._optional(p,"verifier_ref",str),rollback=self._optional(p,"rollback",str))
        if m=="workspace.executive.milestone.update": return self.workspace.executive_milestone_update(self._required(p,"trajectory_id",str),self._required(p,"milestone_id",str),status=self._required(p,"status",str),verifier_ref=self._optional(p,"verifier_ref",str),result=p.get("result"))
        if m=="workspace.executive.complete": return self.workspace.executive_complete(self._required(p,"trajectory_id",str),outcome=p.get("outcome"))
        if m=="workspace.executive.stop": return self.workspace.executive_stop(self._required(p,"trajectory_id",str),status=self._optional(p,"status",str) or "abandoned",reason=self._required(p,"reason",str),outcome=p.get("outcome"))
        if m=="workspace.memory.record": return self.workspace.memory_record(self._required(p,"kind",str),self._required(p,"statement",str),agent_id=self._optional(p,"agent_id",str),episode_id=self._optional(p,"episode_id",str),confidence=self._float(p,"confidence") if "confidence" in p and p.get("confidence") is not None else None,provenance=p.get("provenance"),evidence_ids=p.get("evidence_ids"),supersedes=self._optional(p,"supersedes",str),valid_until_revision=self._optional(p,"valid_until_revision",str))
        if m=="workspace.memory.status": return self.workspace.memory_status(self._required(p,"memory_id",str))
        if m=="workspace.memory.recall": return self.workspace.memory_recall(self._required(p,"query",str),agent_id=self._optional(p,"agent_id",str),kinds=p.get("kinds"),limit=self._int(p,"limit",20))
        if m=="workspace.memory.invalidate": return self.workspace.memory_invalidate(self._required(p,"memory_id",str),self._required(p,"reason",str),invalidated_by=self._optional(p,"invalidated_by",str))
        if m=="workspace.runtime.ingest": return self.workspace.runtime_ingest(self._required(p,"signal",str),self._required(p,"records",list),agent_id=self._optional(p,"agent_id",str),episode_id=self._optional(p,"episode_id",str))
        if m=="workspace.runtime.timeline": return self.workspace.runtime_timeline(trace_id=self._optional(p,"trace_id",str),agent_id=self._optional(p,"agent_id",str),limit=self._int(p,"limit",200))
        if m=="workspace.runtime.topology": return self.workspace.runtime_topology(agent_id=self._optional(p,"agent_id",str),limit=self._int(p,"limit",500))
        if m=="workspace.effect.refresh": return self.workspace.effect_refresh(p.get("paths"))
        if m=="workspace.effect.snapshot": return self.workspace.effect_snapshot(path=self._optional(p,"path",str),symbol_id=self._optional(p,"symbol_id",str),kind=self._optional(p,"kind",str),limit=self._int(p,"limit",1000))
        if m=="workspace.dataflow.refresh": return self.workspace.dataflow_refresh(p.get("paths"))
        if m=="workspace.dataflow.snapshot": return self.workspace.dataflow_snapshot(path=self._optional(p,"path",str),symbol_id=self._optional(p,"symbol_id",str),kind=self._optional(p,"kind",str),source=self._optional(p,"source",str),target=self._optional(p,"target",str),limit=self._int(p,"limit",1000))
        if m=="workspace.project.world": return self.workspace.project_world()
        if m=="workspace.counterfactual.fork": return self.workspace.counterfactual_fork(self._required(p,"label",str),agent_id=self._optional(p,"agent_id",str),metadata=p.get("metadata"))
        if m=="workspace.counterfactual.status": return self.workspace.counterfactual_status(self._required(p,"world_id",str))
        if m=="workspace.counterfactual.apply": return self.workspace.counterfactual_apply(self._required(p,"world_id",str),self._required(p,"changes",list))
        if m=="workspace.counterfactual.evaluate": return self.workspace.counterfactual_evaluate(self._required(p,"world_id",str))
        if m=="workspace.counterfactual.compare": return self.workspace.counterfactual_compare(self._required(p,"world_ids",list))
        if m=="workspace.counterfactual.verify": return self.workspace.counterfactual_verify(self._required(p,"world_id",str),timeout_s=self._int(p,"timeout_s",60))
        if m=="workspace.counterfactual.promote": return self.workspace.counterfactual_promote(self._required(p,"world_id",str),agent_id=self._optional(p,"agent_id",str),episode_id=self._optional(p,"episode_id",str),approval_id=self._optional(p,"approval_id",str))
        if m=="workspace.counterfactual.discard": return self.workspace.counterfactual_discard(self._required(p,"world_id",str))
        if m=="workspace.policy.status": return self.workspace.policy_status()
        if m=="workspace.policy.update": return self.workspace.policy_update(self._required(p,"patch",dict))
        if m=="workspace.policy.evaluate": return self.workspace.policy_evaluate(self._required(p,"action",str),path=self._optional(p,"path",str),capability_id=self._optional(p,"capability_id",str),structural=self._bool(p,"structural",False))
        if m=="workspace.execution.security": return self.workspace.execution_security()
        if m=="workspace.execution.configure": return self.workspace.execution_configure(self._required(p,"containment_profile",str))
        if m=="workspace.sandbox.status": return self.workspace.sandbox_status()
        if m=="workspace.retention.status": return self.workspace.retention_status(p.get("policy"))
        if m=="workspace.retention.compact": return self.workspace.retention_compact(p.get("policy"),dry_run=self._bool(p,"dry_run",True))
        if m=="workspace.state.security": return self.workspace.state_security()
        if m=="workspace.world.summary": return self.workspace.world_summary()
        if m=="workspace.world.health": return self.workspace.world_health(self._optional(p,"agent_id",str))
        if m=="workspace.guidance.discover": return self.workspace.guidance_discover()
        if m=="workspace.guidance.read": return self.workspace.guidance_read(self._required(p,"path",str),self._int(p,"start_line",1),self._int(p,"max_lines",200))
        if m=="workspace.dependencies.snapshot": return self.workspace.dependencies_snapshot()
        if m=="workspace.dependencies.query": return self.workspace.dependencies_query(self._required(p,"term",str))
        if m=="workspace.dependencies.world": return self.workspace.dependencies_world()
        if m=="workspace.git.status": return self.workspace.git_status()
        if m=="workspace.git.history": return self.workspace.git_history(self._optional(p,"path",str),self._int(p,"limit",20))
        if m=="workspace.git.blame": return self.workspace.git_blame(self._required(p,"path",str),self._int(p,"start_line",1),self._int(p,"end_line") if "end_line" in p else None)
        if m=="workspace.git.explain_line": return self.workspace.git_explain_line(self._required(p,"path",str),self._int(p,"line"))
        if m=="workspace.git.diff": return self.workspace.git_diff(self._optional(p,"commit",str),self._optional(p,"path",str),self._int(p,"context",3))
        if m=="workspace.git.changed_files": return self.workspace.git_changed_files(p.get("commit","HEAD"),self._int(p,"limit",500))
        if m=="workspace.git.churn": return self.workspace.git_churn(self._required(p,"path",str),self._int(p,"limit",200))
        if m=="workspace.git.explain_symbol": return self.workspace.git_explain_symbol(self._required(p,"object_id",str))
        if m=="workspace.git.branches": return self.workspace.git_branches(self._int(p,"limit",200))
        if m=="workspace.git.worktrees": return self.workspace.git_worktrees()
        if m=="workspace.git.conflicts": return self.workspace.git_conflicts()
        if m=="workspace.git.commit_impact": return self.workspace.git_commit_impact(p.get("commit","HEAD"),self._int(p,"limit",1000))
        if m=="workspace.agent.open": return self.workspace.agent_open(self._required(p,"name",str),p.get("metadata"))
        if m=="workspace.agent.status": return self.workspace.agent_status(self._required(p,"agent_id",str))
        if m=="workspace.agent.close": return self.workspace.agent_close(self._required(p,"agent_id",str))
        if m=="workspace.agent.observe": return self.workspace.agent_observe(self._required(p,"agent_id",str),self._required(p,"path",str),object_id=p.get("object_id","") or "",kind=p.get("kind","source"))
        if m=="workspace.agent.notifications": return self.workspace.agent_notifications(self._required(p,"agent_id",str),p.get("status","pending"),self._int(p,"limit",100))
        if m=="workspace.agent.notifications.ack": return self.workspace.agent_ack_notification(self._required(p,"agent_id",str),self._required(p,"notification_id",str))
        if m=="workspace.agent.revalidate": return self.workspace.agent_revalidate_notification(self._required(p,"agent_id",str),self._required(p,"notification_id",str))
        if m=="workspace.agent.residency.admit": return self.workspace.agent_residency_admit(self._required(p,"agent_id",str),self._required(p,"handle",str),self._int(p,"max_admit",8),self._int(p,"pin_top",0))
        if m=="workspace.agent.residency.status": return self.workspace.agent_residency_status(self._required(p,"agent_id",str))
        if m=="workspace.agent.residency.evict": return self.workspace.agent_residency_evict(self._required(p,"agent_id",str),self._required(p,"object_ids",list))
        if m=="workspace.lease.acquire": return self.workspace.lease_acquire(self._required(p,"agent_id",str),self._required(p,"resource_kind",str),self._required(p,"resource_id",str),self._float(p,"ttl_s",120.0),self._optional(p,"transaction_id",str))
        if m=="workspace.lease.release": return self.workspace.lease_release(self._required(p,"agent_id",str),self._required(p,"resource_kind",str),self._required(p,"resource_id",str))
        if m=="workspace.lease.status": return self.workspace.lease_status(self._optional(p,"agent_id",str))
        if m=="action.run": return self.workspace.run(self._required(p,"capability",str),self._int(p,"timeout_s",60),self._optional(p,"approval_id",str))
        if m=="ui.observe": return self.workspace.observe_ui(self._required(p,"path",str))
        if m=="ui.runtime.open": return self.workspace.open_ui_runtime(self._required(p,"target",str),self._bool(p,"screenshot",False),self._optional(p,"viewport",dict),self._bool(p,"allow_external",False))
        if m=="ui.runtime.observe": return self.workspace.observe_ui_runtime(self._required(p,"session_id",str),self._bool(p,"screenshot",False))
        if m=="ui.runtime.act": return self.workspace.act_ui_runtime(self._required(p,"session_id",str),self._required(p,"action",str),self._required(p,"handle",str),self._optional(p,"value",str),self._bool(p,"screenshot",False))
        if m=="ui.runtime.assert": return self.workspace.assert_ui_runtime(self._required(p,"session_id",str),self._required(p,"assertions",list))
        if m=="ui.runtime.close": return self.workspace.close_ui_runtime(self._required(p,"session_id",str))
        raise KeyError(f"unknown method: {m}")
    @staticmethod
    def _required(p,k,t):
        if k not in p: raise ValueError(f"missing required parameter: {k}")
        v=p[k]
        if not isinstance(v,t): raise TypeError(f"{k} must be {t.__name__}")
        return v
    def _error(self,rid,code,message,details=None):
        return {"protocol":PROTOCOL_VERSION,"id":rid,"ok":False,"revision":self.workspace.revision,"error":{"code":code,"message":message,"details":details or {}}}
