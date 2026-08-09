from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

EXECUTIVE_PHASES = (
    "OBSERVE", "UPDATE", "DIAGNOSE", "RETRIEVE", "COMPOSE",
    "DISPATCH", "VERIFY", "REFLECT", "RECOVER", "CONTINUE", "CLOSE",
)

STRATEGY_FAMILIES = (
    "direct-analysis",
    "reframe",
    "causal-intervention",
    "rival-hypothesis",
    "external-oracle",
    "dependency-replan",
    "scope-reduction",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def executive_event_hash(*, trajectory_id: str, seq: int, phase: str, operation: str,
                         status: str, revision: str, ref_id: str | None,
                         data: dict, created_at: str, previous_hash: str | None) -> str:
    payload = {
        "trajectory_id": trajectory_id,
        "seq": int(seq),
        "phase": phase,
        "operation": operation,
        "status": status,
        "revision": revision,
        "ref_id": ref_id,
        "data": data,
        "created_at": created_at,
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def verify_event_chain(events: Iterable[dict]) -> dict:
    previous = None
    checked = 0
    failure = None
    for raw in events:
        row = dict(raw)
        data = row.get("data")
        if data is None:
            try:
                data = json.loads(row.get("data_json") or "{}")
            except Exception:
                data = {}
        expected = executive_event_hash(
            trajectory_id=str(row["trajectory_id"]), seq=int(row["seq"]),
            phase=str(row["phase"]), operation=str(row["operation"]), status=str(row["status"]),
            revision=str(row["revision"]), ref_id=row.get("ref_id"), data=data,
            created_at=str(row["created_at"]), previous_hash=previous,
        )
        if row.get("previous_hash") != previous or row.get("record_hash") != expected:
            failure = {
                "seq": int(row["seq"]),
                "expected_previous_hash": previous,
                "stored_previous_hash": row.get("previous_hash"),
                "expected_record_hash": expected,
                "stored_record_hash": row.get("record_hash"),
            }
            break
        previous = expected
        checked += 1
    return {"valid": failure is None, "checked": checked, "head_hash": previous, "failure": failure}


_CONTROL_SUCCESSORS = {
    "OBSERVE": ("UPDATE",),
    "UPDATE": ("DIAGNOSE",),
    "DIAGNOSE": ("RETRIEVE",),
    "RETRIEVE": ("COMPOSE",),
    "COMPOSE": ("DISPATCH",),
    "DISPATCH": ("VERIFY",),
    "VERIFY": ("REFLECT",),
    "REFLECT": ("CONTINUE",),
    "RECOVER": ("CONTINUE",),
    "CONTINUE": ("OBSERVE",),
    "CLOSE": (),
}


def _event_data(row: dict) -> dict:
    data=row.get("data")
    if isinstance(data,dict): return data
    try: return json.loads(row.get("data_json") or "{}")
    except Exception: return {}


def control_events(events: Iterable[dict]) -> list[dict]:
    rows=[]
    for raw in events:
        row=dict(raw); data=_event_data(row)
        if row.get("operation")=="trajectory-start" or row.get("operation")=="trajectory-complete" or data.get("control_step") is True:
            row["data"]=data; rows.append(row)
    return rows


def expected_control_phases(events: Iterable[dict]) -> dict:
    rows=control_events(events)
    if not rows:
        return {"last_phase":None,"last_status":None,"allowed":["OBSERVE"],"close_allowed":False}
    last=rows[-1]; phase=str(last.get("phase") or ""); status=str(last.get("status") or "")
    if phase=="CLOSE": allowed=[]
    elif status in {"failed","inconclusive"}: allowed=["RECOVER"]
    elif status=="running": allowed=[phase]
    else:
        allowed=[phase,*_CONTROL_SUCCESSORS.get(phase,())]
    close_allowed=(phase in {"REFLECT","CONTINUE"} and status=="passed") or phase=="CLOSE"
    return {"last_phase":phase,"last_status":status,"allowed":list(dict.fromkeys(allowed)),"close_allowed":close_allowed}


def verify_phase_sequence(events: Iterable[dict]) -> dict:
    rows=control_events(events); failure=None
    if not rows:
        return {"valid":False,"checked":0,"failure":{"code":"CONTROL_START_MISSING"},"state":expected_control_phases([])}
    first=rows[0]
    if first.get("phase")!="OBSERVE" or first.get("operation")!="trajectory-start":
        return {"valid":False,"checked":0,"failure":{"code":"CONTROL_START_INVALID","phase":first.get("phase")},"state":expected_control_phases(rows)}
    checked=1
    for previous,current in zip(rows,rows[1:]):
        state=expected_control_phases(rows[:checked])
        phase=str(current.get("phase") or "")
        if phase=="CLOSE":
            forced=bool((current.get("data") or {}).get("forced_stop"))
            if not forced and not state.get("close_allowed"):
                failure={"code":"CONTROL_CLOSE_OUT_OF_SEQUENCE","previous_phase":state.get("last_phase"),"phase":phase}
                break
        elif phase not in state.get("allowed",[]):
            failure={"code":"CONTROL_PHASE_SKIP","previous_phase":state.get("last_phase"),"previous_status":state.get("last_status"),"phase":phase,"allowed":state.get("allowed",[])}
            break
        checked+=1
    return {"valid":failure is None,"checked":checked,"failure":failure,"state":expected_control_phases(rows)}


def classify_strategy_failure(*, loop_risk: str, pending_invalidations: int,
                              contradictions: int, unknowns: int,
                              unverified_critical_invariants: int,
                              failed_steps: int, verification_failures: int) -> dict:
    """Return an explicit failure diagnosis and a structurally different strategy family.

    The mapping is intentionally ordinal. It is an observable control heuristic, not a claim
    about hidden model reasoning or calibrated expected utility.
    """
    if pending_invalidations:
        return {
            "failure_class": "stale-state",
            "strategy": "dependency-replan",
            "reason": "Observed source/world invalidation makes the current plan unsafe to continue.",
        }
    if contradictions:
        return {
            "failure_class": "wrong-frame-or-conflicting-evidence",
            "strategy": "rival-hypothesis",
            "reason": "Recorded contradictions require a discriminator rather than more of the same search.",
        }
    if unverified_critical_invariants:
        return {
            "failure_class": "weak-oracle",
            "strategy": "external-oracle",
            "reason": "Critical invariants lack verifier linkage; stronger observation is required.",
        }
    if verification_failures:
        return {
            "failure_class": "failed-postcondition",
            "strategy": "causal-intervention",
            "reason": "A verifier rejected the current candidate; isolate the mechanism and vary one cause at a time.",
        }
    if loop_risk in {"medium", "high"} or failed_steps >= 2:
        return {
            "failure_class": "stagnation",
            "strategy": "reframe",
            "reason": "Visible operations repeat or fail without admitted progress; the current framing is exhausted.",
        }
    if unknowns:
        return {
            "failure_class": "missing-information",
            "strategy": "direct-analysis",
            "reason": "Open unknowns still have decision value; gather bounded discriminating evidence.",
        }
    return {
        "failure_class": "none",
        "strategy": "direct-analysis",
        "reason": "No explicit control-plane failure requires a strategy switch.",
    }


def structural_recovery_strategy(current: str, diagnosis: dict) -> dict:
    """Guarantee that an admitted recovery changes strategy family when failure requires adaptation."""
    failure_class=str(diagnosis.get("failure_class") or "none")
    preferred=str(diagnosis.get("strategy") or "direct-analysis")
    if failure_class in {"none","missing-information"}:
        return {**diagnosis,"target_strategy":current,"switch_required":False}
    if preferred != current:
        return {**diagnosis,"target_strategy":preferred,"switch_required":True}
    fallbacks=("scope-reduction","external-oracle","rival-hypothesis","causal-intervention","reframe","dependency-replan")
    target=next((x for x in fallbacks if x!=current),current)
    return {**diagnosis,"target_strategy":target,"switch_required":target!=current,
            "reason":str(diagnosis.get("reason") or "")+" Repeating the same strategy is rejected as cosmetic recovery."}


def milestone_topology(milestones: list[dict]) -> dict:
    ids = {str(m["id"]) for m in milestones}
    deps: dict[str, list[str]] = {}
    missing: list[dict] = []
    for m in milestones:
        mid = str(m["id"])
        raw = m.get("dependencies")
        if raw is None:
            try:
                raw = json.loads(m.get("dependencies_json") or "[]")
            except Exception:
                raw = []
        ds = [str(x) for x in raw]
        deps[mid] = ds
        for dep in ds:
            if dep not in ids:
                missing.append({"milestone_id": mid, "missing_dependency": dep})

    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: list[str] | None = None

    def visit(node: str, path: list[str]) -> None:
        nonlocal cycle
        if cycle is not None or node in visited:
            return
        if node in visiting:
            try:
                i = path.index(node)
                cycle = path[i:] + [node]
            except ValueError:
                cycle = path + [node]
            return
        visiting.add(node)
        for dep in deps.get(node, []):
            if dep in ids:
                visit(dep, path + [node])
        visiting.remove(node)
        visited.add(node)

    for mid in sorted(ids):
        visit(mid, [])
        if cycle is not None:
            break
    return {"acyclic": cycle is None, "cycle": cycle, "missing_dependencies": missing}
