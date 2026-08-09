from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from typing import Any

from .util import utc_now



_SENSITIVE_ATTR_RE = re.compile(r"(?i)(prompt|completion|message[s]?|content|input_text|output_text|arguments?|api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret|credential|private[_-]?key|db\.statement|query\.text|request\.body|response\.body|headers?|cookie|url\.(?:full|query))")
_SECRET_VALUE_RE = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b\s*[:=]\s*[^\s,;]+")
_OPAQUE_CREDENTIAL_RE = re.compile(r"(?i)(?:bearer\s+)[A-Za-z0-9._~+/=-]{12,}|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}\b|\bAKIA[0-9A-Z]{16}\b")

def _sanitize_value(value: Any, *, depth: int = 0) -> tuple[Any, int, int]:
    if depth > 3:
        return "[TRUNCATED_DEPTH]", 0, 1
    if value is None or isinstance(value,(bool,int,float)):
        return value,0,0
    if isinstance(value,str):
        redacted=0; truncated=0; text=value
        if _SECRET_VALUE_RE.search(text):
            text=_SECRET_VALUE_RE.sub(lambda m: m.group(1)+"=[REDACTED]",text); redacted+=1
        if _OPAQUE_CREDENTIAL_RE.search(text):
            text=_OPAQUE_CREDENTIAL_RE.sub("[REDACTED_CREDENTIAL]",text); redacted+=1
        if len(text)>2048:
            text=text[:2048]+"…[TRUNCATED]"; truncated+=1
        return text,redacted,truncated
    if isinstance(value,(list,tuple)):
        out=[];r=t=0
        for item in list(value)[:64]:
            v,rr,tt=_sanitize_value(item,depth=depth+1);out.append(v);r+=rr;t+=tt
        if len(value)>64:t+=1
        return out,r,t
    if isinstance(value,dict):
        out={};r=t=0
        # Common debugger/environment shape: {name: "API_KEY", value: "..."}. Sensitivity is
        # carried by a sibling field rather than the literal key "value".
        semantic_name=str(value.get("name") or value.get("key") or "")
        sibling_secret=bool(semantic_name and _SENSITIVE_ATTR_RE.search(semantic_name))
        for k,v in list(value.items())[:128]:
            key_raw=str(k); key,_kr,_kt=_sanitize_value(key_raw,depth=depth+1); key=str(key)[:160];r+=_kr;t+=_kt
            if _SENSITIVE_ATTR_RE.search(key_raw) or (sibling_secret and key_raw.casefold() in {"value","val","data"}):
                out[key]="[REDACTED_BY_HABITAT]";r+=1;continue
            vv,rr,tt=_sanitize_value(v,depth=depth+1);out[key]=vv;r+=rr;t+=tt
        if len(value)>128:t+=1
        return out,r,t
    text=str(value)
    if len(text)>2048:return text[:2048]+"…[TRUNCATED]",0,1
    return text,0,0

def sanitize_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    clean,redacted,truncated=_sanitize_value(dict(attrs or {}))
    assert isinstance(clean,dict)
    if redacted: clean["habitat.telemetry.redacted_count"]=redacted
    if truncated: clean["habitat.telemetry.truncated_count"]=truncated
    return clean

@dataclass
class RuntimeObservation:
    id: str
    trace_id: str | None
    span_id: str | None
    parent_span_id: str | None
    kind: str
    name: str
    status: str
    path: str | None
    line: int | None
    symbol_id: str | None
    agent_id: str | None
    episode_id: str | None
    revision: str
    started_at: str
    duration_ms: float | None
    attributes: dict[str, Any]
    source: str

    def as_dict(self) -> dict:
        return asdict(self)


def _id(*parts: Any) -> str:
    raw="\0".join(str(p or "") for p in parts).encode("utf-8",errors="replace")
    return "rt_"+hashlib.sha256(raw).hexdigest()[:24]


def _pick(attrs: dict, *names: str):
    for name in names:
        if name in attrs and attrs[name] not in (None, ""):
            return attrs[name]
    return None


def normalize_otel_span(span: dict[str, Any], revision: str, *, agent_id: str | None = None, episode_id: str | None = None) -> RuntimeObservation:
    if not isinstance(span,dict): raise TypeError("span must be an object")
    attrs=sanitize_attributes(dict(span.get("attributes") or {}))
    trace_id=str(span.get("trace_id") or span.get("traceId") or "") or None
    span_id=str(span.get("span_id") or span.get("spanId") or "") or None
    parent=str(span.get("parent_span_id") or span.get("parentSpanId") or "") or None
    name_raw=span.get("name") or _pick(attrs,"gen_ai.operation.name","http.route","db.operation.name") or "runtime-span"
    name,_,_=_sanitize_value(str(name_raw)); name=str(name)[:240]
    kind=str(span.get("kind") or _pick(attrs,"span.kind","gen_ai.operation.name") or "span")
    status_obj=span.get("status")
    if isinstance(status_obj,dict): status=str(status_obj.get("code") or status_obj.get("status_code") or "observed")
    else: status=str(status_obj or "observed")
    path=_pick(attrs,"code.file.path","source.file","file.path","code.filepath")
    line=_pick(attrs,"code.line.number","source.line","line")
    try: line=int(line) if line is not None else None
    except Exception: line=None
    started=str(span.get("started_at") or span.get("start_time") or span.get("startTime") or utc_now())
    duration=span.get("duration_ms")
    if duration is None:
        duration=span.get("duration")
    try: duration=float(duration) if duration is not None else None
    except Exception: duration=None
    if duration is not None and duration < 0: duration=None
    return RuntimeObservation(
        id=_id(trace_id,span_id,name,started),trace_id=trace_id,span_id=span_id,parent_span_id=parent,
        kind=kind,name=name,status=status,path=str(path) if path else None,line=line,symbol_id=None,
        agent_id=agent_id or _pick(attrs,"gen_ai.agent.id","agent.id"),episode_id=episode_id or _pick(attrs,"habitat.episode.id"),
        revision=revision,started_at=started,duration_ms=duration,attributes=attrs,source="opentelemetry",
    )



def normalize_otel_record(record: dict[str, Any], revision: str, *, agent_id: str | None = None, episode_id: str | None = None) -> RuntimeObservation:
    """Normalize a small vendor-neutral subset of OpenTelemetry span/log/metric-shaped records.

    Habitat does not require the OTel SDK here: collectors/agent adapters may forward decoded JSON.
    Unknown fields stay in attributes so provenance is retained rather than silently discarded.
    """
    if not isinstance(record,dict): raise TypeError("OpenTelemetry record must be an object")
    rtype=str(record.get("record_type") or record.get("type") or "").casefold()
    if rtype in {"log","logrecord"} or "severity_text" in record or ("body" in record and "span_id" not in record and "spanId" not in record):
        attrs=sanitize_attributes(dict(record.get("attributes") or {}))
        body=record.get("body"); severity=str(record.get("severity_text") or record.get("severity") or "observed")
        name=str(record.get("name") or "runtime-log")[:240]
        path=_pick(attrs,"code.file.path","source.file","file.path","code.filepath"); line=_pick(attrs,"code.line.number","source.line","line")
        try: line=int(line) if line is not None else None
        except Exception: line=None
        now=str(record.get("timestamp") or record.get("time_unix_nano") or utc_now())
        safe_body,rb,tb=_sanitize_value(body)
        attrs={**attrs,"otel.body":safe_body,"otel.severity":severity}
        if rb: attrs["habitat.telemetry.redacted_count"]=int(attrs.get("habitat.telemetry.redacted_count",0))+rb
        if tb: attrs["habitat.telemetry.truncated_count"]=int(attrs.get("habitat.telemetry.truncated_count",0))+tb
        return RuntimeObservation(_id("log",record.get("trace_id"),record.get("span_id"),name,now),str(record.get("trace_id") or "") or None,str(record.get("span_id") or "") or None,None,"log",name,severity,str(path) if path else None,line,None,agent_id or _pick(attrs,"gen_ai.agent.id","agent.id"),episode_id or _pick(attrs,"habitat.episode.id"),revision,now,None,attrs,"opentelemetry")
    if rtype in {"metric","gauge","counter","histogram"} or "metric_name" in record:
        attrs=sanitize_attributes(dict(record.get("attributes") or {})); metric=str(record.get("metric_name") or record.get("name") or "runtime-metric")
        val,rv,tv=_sanitize_value(record.get("value")); unit,ru,tu=_sanitize_value(record.get("unit")); now=str(record.get("timestamp") or utc_now()); attrs={**attrs,"otel.metric.value":val,"otel.metric.unit":unit}
        if rv+ru: attrs["habitat.telemetry.redacted_count"]=int(attrs.get("habitat.telemetry.redacted_count",0))+rv+ru
        if tv+tu: attrs["habitat.telemetry.truncated_count"]=int(attrs.get("habitat.telemetry.truncated_count",0))+tv+tu
        return RuntimeObservation(_id("metric",metric,now,val),None,None,None,"metric",metric,"observed",None,None,None,agent_id,episode_id,revision,now,None,attrs,"opentelemetry")
    return normalize_otel_span(record,revision,agent_id=agent_id,episode_id=episode_id)


def normalize_dap_event(event: dict[str, Any], revision: str, *, agent_id: str | None = None, episode_id: str | None = None) -> RuntimeObservation:
    if not isinstance(event,dict): raise TypeError("event must be an object")
    body=dict(event.get("body") or {})
    ev=str(event.get("event") or event.get("command") or "dap-event")
    source_obj=body.get("source") if isinstance(body.get("source"),dict) else {}
    path=source_obj.get("path") or body.get("path")
    line=body.get("line")
    try: line=int(line) if line is not None else None
    except Exception: line=None
    safe_body,rb,tb=_sanitize_value(body)
    attrs={"dap.seq":event.get("seq"),"dap.type":event.get("type"),"dap.event":ev,"body":safe_body}
    if rb: attrs["habitat.telemetry.redacted_count"]=rb
    if tb: attrs["habitat.telemetry.truncated_count"]=tb
    thread_id=body.get("threadId")
    name=ev+(f" thread={thread_id}" if thread_id is not None else "")
    now=str(event.get("timestamp") or event.get("time") or utc_now())
    session_identity=(event.get("session_id") or event.get("sessionId") or body.get("sessionId") or body.get("processId") or episode_id or agent_id)
    seq=event.get("seq")
    if session_identity is not None and seq is not None:
        replay_identity=f"{session_identity}:{seq}:{ev}"
        event_id=_id("dap",session_identity,seq,ev)
        attrs["habitat.dap.replay_identity"]="session-seq-event"
        attrs["habitat.dap.replay_key"]=replay_identity
    else:
        event_id=_id("dap",seq,ev,now)
        attrs["habitat.dap.replay_identity"]="unavailable"
    return RuntimeObservation(
        id=event_id,trace_id=None,span_id=None,parent_span_id=None,kind="debug-event",
        name=name,status="observed",path=str(path) if path else None,line=line,symbol_id=None,agent_id=agent_id,
        episode_id=episode_id,revision=revision,started_at=now,duration_ms=None,attributes=attrs,source="dap",
    )


def event_to_store_dict(obs: RuntimeObservation) -> dict:
    d=obs.as_dict(); d.pop("line",None); return d


def build_runtime_topology(rows: list[dict[str, Any]], *, max_events: int = 500) -> dict:
    """Build a bounded observed runtime/service topology from normalized runtime rows.

    The topology is evidence from observed telemetry only. It does not infer unobserved calls or causal
    direction beyond parent/child span ordering and explicit semantic-convention attributes.
    """
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}
    span_nodes: dict[tuple[str, str], str] = {}

    def add_node(kind: str, key: str, label: str, *, status: str = "observed", metadata: dict | None = None) -> str:
        nid=_id("topology",kind,key)
        cur=nodes.get(nid)
        if cur is None:
            cur={"id":nid,"type":kind,"label":label,"status":status,"observations":0,"metadata":metadata or {}}
            nodes[nid]=cur
        cur["observations"]+=1
        if status and status.casefold() in {"error","failed","fail"}: cur["status"]=status
        return nid

    def add_edge(source: str | None, target: str | None, kind: str, *, duration_ms: float | None = None, status: str = "observed"):
        if not source or not target or source==target: return
        k=(source,target,kind); e=edges.get(k)
        if e is None:
            e={"source":source,"target":target,"kind":kind,"count":0,"error_count":0,"duration_ms_total":0.0,"duration_ms_max":None}
            edges[k]=e
        e["count"]+=1
        if status.casefold() in {"error","failed","fail"}: e["error_count"]+=1
        if duration_ms is not None:
            d=float(duration_ms);e["duration_ms_total"]+=d;e["duration_ms_max"]=d if e["duration_ms_max"] is None else max(e["duration_ms_max"],d)

    selected=rows[:max_events]
    for row in selected:
        attrs=row.get("attributes")
        if attrs is None:
            raw=row.get("attributes_json")
            try: attrs=json.loads(raw or "{}")
            except Exception: attrs={}
        attrs=dict(attrs or {})
        status=str(row.get("status") or "observed")
        trace=str(row.get("trace_id") or "")
        span=str(row.get("span_id") or "")
        duration=row.get("duration_ms")
        service=_pick(attrs,"service.name","service.namespace","peer.service","server.address","server.domain")
        route=_pick(attrs,"http.route","url.path","http.target","rpc.method")
        db_system=_pick(attrs,"db.system.name","db.system")
        db_name=_pick(attrs,"db.namespace","db.name","db.collection.name")
        msg_system=_pick(attrs,"messaging.system")
        msg_dest=_pick(attrs,"messaging.destination.name","messaging.destination","messaging.destination.template")
        code_path=row.get("path") or _pick(attrs,"code.file.path","source.file")
        event_label=str(row.get("name") or row.get("kind") or "runtime")
        event_node=add_node("runtime-span" if row.get("kind") not in {"log","metric"} else f"runtime-{row.get('kind')}",
                            str(row.get("id") or event_label),event_label,status=status,
                            metadata={"trace_id":row.get("trace_id"),"span_id":row.get("span_id"),"path":code_path,"duration_ms":duration})
        if trace and span: span_nodes[(trace,span)]=event_node
        svc_node=None
        if service:
            svc_node=add_node("service",str(service),str(service),status=status);add_edge(svc_node,event_node,"observed-operation",duration_ms=duration,status=status)
        if route:
            route_node=add_node("runtime-route",str(route),str(route),status=status);add_edge(svc_node or event_node,route_node,"serves",duration_ms=duration,status=status)
        if db_system or db_name:
            label="/".join(str(x) for x in (db_system,db_name) if x)
            db_node=add_node("database",label,label,status=status,metadata={"system":db_system,"namespace":db_name});add_edge(event_node,db_node,"db-access",duration_ms=duration,status=status)
        if msg_system or msg_dest:
            label="/".join(str(x) for x in (msg_system,msg_dest) if x)
            q_node=add_node("message-bus",label,label,status=status);add_edge(event_node,q_node,"message-flow",duration_ms=duration,status=status)
        if code_path:
            code_node=add_node("runtime-source",str(code_path),str(code_path),status=status);add_edge(event_node,code_node,"observed-at",status=status)
    for row in selected:
        trace=str(row.get("trace_id") or ""); span=str(row.get("span_id") or ""); parent=str(row.get("parent_span_id") or "")
        if trace and span and parent:
            add_edge(span_nodes.get((trace,parent)),span_nodes.get((trace,span)),"span-child",duration_ms=row.get("duration_ms"),status=str(row.get("status") or "observed"))
    out_edges=[]
    for e in edges.values():
        e=dict(e)
        e["duration_ms_avg"]=(e["duration_ms_total"]/e["count"]) if e["count"] else None
        out_edges.append(e)
    return {"nodes":list(nodes.values()),"edges":out_edges,"observations":len(selected),
            "claim_boundary":"Observed telemetry topology. Parent-child spans and explicit attributes are evidence of observed execution, not complete causal inference or proof of unobserved dependencies."}
