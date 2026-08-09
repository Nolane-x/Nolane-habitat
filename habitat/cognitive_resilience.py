from __future__ import annotations

from collections import Counter
from typing import Iterable

_PROGRESS_KINDS = {
    "transaction.committed", "verification.completed", "experiment.completed",
    "runtime.observed", "epistemic.updated", "memory.recorded", "agent.revalidated",
    "world.promoted", "source.file-modified", "source.file-created", "source.file-deleted",
}


def activity_fingerprint(event: dict) -> tuple[str, str, str, str]:
    return (
        str(event.get("kind") or ""), str(event.get("ref_id") or ""),
        str(event.get("path") or ""), str(event.get("status") or ""),
    )


def analyze_cognitive_loop(events: Iterable[dict], *, window: int = 40) -> dict:
    """Detect repeated visible operations without admitted world progress.

    This is deliberately an environment-level loop signal. It does not inspect private model reasoning.
    """
    recent = list(events)[-max(4, int(window)):]
    if not recent:
        return {"risk": "none", "score": 0, "repeat_ratio": 0.0, "no_progress_streak": 0, "dominant": None}
    fingerprints = [activity_fingerprint(e) for e in recent]
    counts = Counter(fingerprints)
    dominant, dominant_count = counts.most_common(1)[0]
    repeat_ratio = dominant_count / max(1, len(recent))
    last_progress = -1
    for i, e in enumerate(recent):
        if str(e.get("kind") or "") in _PROGRESS_KINDS:
            last_progress = i
    no_progress_streak = len(recent) if last_progress < 0 else len(recent) - last_progress - 1
    # Require both repetition and lack of admitted world progress. One noisy tool is not automatically a loop.
    score = 0
    if repeat_ratio >= 0.35: score += 2
    elif repeat_ratio >= 0.22: score += 1
    if no_progress_streak >= 16: score += 2
    elif no_progress_streak >= 8: score += 1
    same_tail = 0
    if fingerprints:
        tail = fingerprints[-1]
        for fp in reversed(fingerprints):
            if fp != tail: break
            same_tail += 1
    if same_tail >= 4: score += 2
    risk = "high" if score >= 5 else "medium" if score >= 3 else "low" if score else "none"
    return {
        "risk": risk, "score": score, "repeat_ratio": round(repeat_ratio, 4),
        "no_progress_streak": no_progress_streak, "same_operation_tail": same_tail,
        "dominant": {"kind": dominant[0], "ref_id": dominant[1] or None, "path": dominant[2] or None,
                     "status": dominant[3] or None, "count": dominant_count},
        "window": len(recent),
        "claim_boundary": "Visible Habitat operation repetition only; not access to private chain-of-thought.",
    }


def epistemic_pressure(items: Iterable[dict], notifications: Iterable[dict] = (), invariants: Iterable[dict] = ()) -> dict:
    rows = list(items); pending = list(notifications); invs = list(invariants)
    weights = {"contradiction": 5, "unknown": 3, "assumption": 1, "prediction": 1, "constraint": 1, "fact": 0}
    score = 0; blockers = []
    for x in rows:
        if str(x.get("status") or "open") != "open": continue
        kind = str(x.get("kind") or "unknown")
        stale = bool(x.get("stale"))
        w = weights.get(kind, 1) + (2 if stale else 0)
        score += w
        if kind == "contradiction" or stale:
            blockers.append({"kind": kind, "id": x.get("id"), "statement": x.get("statement"), "stale": stale, "weight": w})
    score += 5 * len(pending)
    for n in pending[:10]:
        blockers.append({"kind": "stale-observation", "id": n.get("id"), "statement": n.get("resource_id"), "weight": 5})
    unverifiable = [i for i in invs if str(i.get("severity") or "").lower() in {"critical", "error"} and int(i.get("verifier_count") or 0) == 0]
    score += 4 * len(unverifiable)
    for i in unverifiable[:10]:
        blockers.append({"kind": "unverified-invariant", "id": i.get("id"), "statement": i.get("statement"), "weight": 4})
    level = "critical" if score >= 20 else "high" if score >= 10 else "medium" if score >= 4 else "low"
    return {"score": score, "level": level, "blockers": blockers[:20], "unverified_critical_invariants": len(unverifiable)}
