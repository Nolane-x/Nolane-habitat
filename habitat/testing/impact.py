from __future__ import annotations

from collections import deque
from pathlib import Path

TRUST_FACTOR = {"exact": 1.0, "semantic": 0.98, "parser": 0.88, "derived": 0.76, "heuristic": 0.48}
REL_FACTOR = {"calls": 1.0, "imports_symbol": 0.95, "imports": 0.82, "tests": 1.0}


def is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    name = Path(p).name
    return "/tests/" in f"/{p}" or name.startswith("test_") or name.endswith("_test.py") or ".test." in name or ".spec." in name


def _row_for_id(store, oid: str):
    return store.symbol_by_id(oid) or store.file_by_id(oid)


def _seed_ids(store, changed_paths: list[str], object_ids: list[str]) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    paths: set[str] = set(changed_paths)
    for oid in object_ids:
        row = _row_for_id(store, oid)
        if not row:
            raise KeyError(oid)
        ids.add(oid); paths.add(row["path"])
    for path in list(paths):
        f = store.file_by_path(path)
        if not f:
            continue
        ids.add(f["id"])
        for s in store.symbols_for_file(f["id"]):
            ids.add(s["id"])
    return ids, paths


def affected_tests(store, changed_paths: list[str] | None = None, object_ids: list[str] | None = None, max_depth: int = 5) -> dict:
    seeds, paths = _seed_ids(store, list(changed_paths or []), list(object_ids or []))
    queue = deque((oid, 1.0, 0, [oid]) for oid in seeds)
    best: dict[str, float] = {oid: 1.0 for oid in seeds}
    candidates: dict[str, dict] = {}
    traversed = 0

    while queue:
        target, score, depth, chain = queue.popleft()
        if depth >= max_depth:
            continue
        for rel in store.incoming_relations(target):
            if rel["kind"] not in REL_FACTOR:
                continue
            source = rel["source_id"]
            if source == target:
                continue
            row = _row_for_id(store, source)
            if not row:
                continue
            traversed += 1
            next_score = score * REL_FACTOR[rel["kind"]] * TRUST_FACTOR.get(rel["trust"], 0.6) * (0.93 ** depth)
            evidence = {
                "source_id": source, "target_id": target, "relation": rel["kind"], "trust": rel["trust"],
                "evidence": rel["evidence"], "path": row["path"],
            }
            if is_test_path(row["path"]):
                cur = candidates.get(row["path"])
                item = {"path": row["path"], "score": round(next_score, 6), "depth": depth + 1,
                        "terminal_object_id": source, "evidence_chain": [*chain, evidence]}
                if cur is None or item["score"] > cur["score"]:
                    candidates[row["path"]] = item
            if next_score > best.get(source, 0.0) + 1e-9:
                best[source] = next_score
                queue.append((source, next_score, depth + 1, [*chain, evidence]))

    # Coarse direct test relations are useful fallback evidence if symbol-level semantics are absent.
    for path in paths:
        f = store.file_by_path(path)
        if not f:
            continue
        for rel in store.incoming_relations(f["id"], "tests"):
            row = _row_for_id(store, rel["source_id"])
            if row and is_test_path(row["path"]):
                score = 0.72 * TRUST_FACTOR.get(rel["trust"], 0.6)
                candidates.setdefault(row["path"], {
                    "path": row["path"], "score": round(score, 6), "depth": 1,
                    "terminal_object_id": rel["source_id"],
                    "evidence_chain": [{"source_id": rel["source_id"], "target_id": f["id"], "relation": "tests",
                                        "trust": rel["trust"], "evidence": rel["evidence"], "path": row["path"]}],
                })

    ranked = sorted(candidates.values(), key=lambda x: (-x["score"], x["path"]))
    semantic = any(any(isinstance(e, dict) and e.get("trust") == "semantic" for e in c["evidence_chain"]) for c in ranked)
    return {
        "changed_paths": sorted(paths), "seed_object_ids": sorted(seeds), "ranked_test_files": ranked,
        "graph_edges_examined": traversed, "max_depth": max_depth,
        "confidence": "semantic" if semantic else "structural" if ranked else "unknown",
        "unknowns": [] if ranked else ["No affected test file was linked by the current semantic graph."],
    }
