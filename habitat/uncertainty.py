from __future__ import annotations

from collections import defaultdict
from typing import Any

TRUST_WEIGHT={"exact":1.0,"semantic":0.9,"parser":0.72,"derived":0.45,"heuristic":0.25}


def assess_hypothesis(evidence_links: list[dict[str,Any]], evidence_rows: dict[str,dict[str,Any]]) -> dict[str,Any]:
    """Correlation-aware heuristic evidence fusion, explicitly not a probability model."""
    grouped=defaultdict(lambda:{"support":0.0,"against":0.0,"items":[]})
    unresolved=[]
    for link in evidence_links:
        eid=link.get("evidence_id")
        row=evidence_rows.get(eid) if eid else None
        if row is None:
            source="agent-annotation"; trust="heuristic"
        else:
            source=str(row.get("source") or row.get("kind") or "unknown")
            trust=str(row.get("trust") or "derived")
        polarity=str(link.get("polarity") or "support")
        magnitude=min(1.0,max(0.0,float(link.get("weight",1.0))))*TRUST_WEIGHT.get(trust,0.35)
        group=grouped[source]
        key="against" if polarity in {"against","contradict","refute"} else "support"
        # Diminishing returns inside a correlated source group; repeated receipts from one runner are not independent votes.
        group[key]=max(group[key],magnitude)
        group["items"].append({"evidence_id":eid,"polarity":polarity,"trust":trust,"weight":magnitude})
        if row is not None and not bool(row.get("active",1)): unresolved.append(eid)
    support=sum(g["support"] for g in grouped.values())
    against=sum(g["against"] for g in grouped.values())
    denom=max(1.0,support+against)
    signed=(support-against)/denom
    if abs(signed)<0.15: label="contested" if support and against else "insufficient"
    elif signed>0: label="supported"
    else: label="contradicted"
    return {
        "assessment":label,
        "support_strength":round(support,4),
        "contradiction_strength":round(against,4),
        "signed_balance":round(signed,4),
        "independent_source_groups":len(grouped),
        "source_groups":dict(grouped),
        "inactive_evidence_ids":sorted(set(x for x in unresolved if x)),
        "calibrated_probability":False,
        "claim_boundary":"Heuristic evidence fusion with diminishing returns per source group; not a calibrated probability and not causal proof.",
    }
