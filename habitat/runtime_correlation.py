from __future__ import annotations

import json
from collections import Counter
from typing import Iterable


def _event_dict(row) -> dict:
    d=dict(row)
    attrs=d.get("attributes")
    if attrs is None:
        try: attrs=json.loads(d.get("attributes_json") or "{}")
        except Exception: attrs={}
    d["attributes"]=dict(attrs or {})
    return d


def correlate_runtime_fact(fact: dict, runtime_events: Iterable[dict], revision: str, *, max_refs: int = 12) -> dict:
    """Correlate one static fact with revision-compatible observed runtime provenance.

    Exact symbol provenance outranks path provenance. This is intentionally *support*, not confidence or causality.
    """
    path=str(fact.get("path") or "")
    symbol=str(fact.get("symbol_id") or "")
    candidates=[]
    for raw in runtime_events:
        ev=_event_dict(raw)
        if str(ev.get("revision") or "") != str(revision):
            continue
        dims=[]; score=0
        if symbol and str(ev.get("symbol_id") or "")==symbol:
            dims.append("symbol"); score+=4
        if path and str(ev.get("path") or "")==path:
            dims.append("path"); score+=1
        if not dims:
            continue
        candidates.append((score,ev,dims))
    candidates.sort(key=lambda x:(-x[0],str(x[1].get("started_at") or "")))
    refs=[]; traces=set(); max_score=0; dims=Counter()
    for score,ev,ds in candidates[:max_refs]:
        max_score=max(max_score,score)
        if ev.get("trace_id"): traces.add(str(ev["trace_id"]))
        dims.update(ds)
        refs.append({"id":ev.get("id"),"trace_id":ev.get("trace_id"),"span_id":ev.get("span_id"),"kind":ev.get("kind"),"name":ev.get("name"),"path":ev.get("path"),"symbol_id":ev.get("symbol_id"),"started_at":ev.get("started_at"),"dimensions":ds})
    grade="strong" if max_score>=4 else "weak" if max_score else "none"
    return {"grade":grade,"observed":bool(refs),"runtime_refs":refs,"runtime_ref_count":len(candidates),"independent_trace_count":len(traces),"dimensions":dict(dims),
            "claim_boundary":"Revision-compatible runtime provenance support. Symbol match is stronger than path match; neither establishes dynamic value identity or causal necessity."}
