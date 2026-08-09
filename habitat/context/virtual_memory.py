from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..util import stable_id, sha256_bytes, utc_now


class ContextVirtualMemory:
    """Virtual source address space bound to one context artifact and source revision.

    Pages are pointers, never source copies. Exact bytes are read only on `fetch`, after digest/revision
    validation. This lets an agent reason about a large relevant address space without paying the source
    cost until a particular page is demanded.
    """
    def __init__(self, workspace):
        self.workspace = workspace
        self.store = workspace.store

    def _slice(self, handle: str) -> dict:
        value = self.store.load_json("context_slices", handle)
        if not value:
            raise KeyError(handle)
        return value

    def _resident_state(self, oid: str, path: str, digest: str) -> str:
        row = self.store.resident_by_id(oid)
        if not row:
            return "cold"
        return "resident" if row["source_digest"] == digest else "stale-resident"

    def _page_for_candidate(self, handle: str, c: dict) -> dict:
        oid = c["object_id"]; path = c["path"]
        fr = self.store.file_by_path(path)
        if not fr:
            return {"page_id": stable_id("vpage", handle, oid, "missing"), "virtual_address": f"ctx://{handle}/missing/{oid}",
                    "object_id": oid, "path": path, "page_class": "missing", "state": "missing", "source_range": None,
                    "source_bytes_estimate": 0, "relevance": min(float(c.get("score",0)),1.0), "trust": c.get("trust"),
                    "lane": c.get("lane"), "reason": c.get("reason"), "fetchable": False}
        sr = self.store.symbol_by_id(oid); dr = self.store.diagnostic_by_id(oid)
        start = end = None; page_class = "metadata"; fetchable = False
        if sr:
            start, end = int(sr["start_line"]), int(sr["end_line"]); page_class = "symbol-source"; fetchable = True
        elif dr and dr["line"]:
            start = max(1, int(dr["line"]) - 3); end = int(dr["line"]) + 3; page_class = "diagnostic-window"; fetchable = True
        # File candidates remain metadata-only. Whole-file source is intentionally not a virtual page;
        # the agent must select a symbol/page or explicitly use source.read as an escape hatch.
        estimate = 0
        if fetchable and start and end:
            total_lines = max(1, end-start+1)
            # Estimate from file density; exact bytes are measured only if fetched.
            estimate = max(1, int(fr["size"] * min(total_lines, 5000) / max(total_lines, self._line_count_hint(path))))
        pid = stable_id("vpage", fr["digest"], oid, str(start or 0), str(end or 0), page_class)
        return {
            "page_id": pid, "virtual_address": f"ctx://{handle}/{pid}", "object_id": oid, "path": path,
            "page_class": page_class, "state": self._resident_state(oid,path,fr["digest"]),
            "source_range": [start,end] if fetchable else None, "source_digest": fr["digest"],
            "source_bytes_estimate": estimate, "relevance": min(float(c.get("score",0)),1.0),
            "trust": c.get("trust"), "lane": c.get("lane"), "reason": c.get("reason"), "fetchable": fetchable,
        }

    def _line_count_hint(self, path: str) -> int:
        fr = self.store.file_by_path(path)
        if not fr:
            return 1
        symbols = self.store.symbols_for_file(fr["id"])
        if symbols:
            return max(int(s["end_line"]) for s in symbols)
        return max(1, min(int(fr["size"]) // 40, 100_000))

    def address_space(self, handle: str, max_pages: int = 100) -> dict:
        if max_pages < 1 or max_pages > 1000:
            raise ValueError("max_pages must be in [1, 1000]")
        value = self._slice(handle)
        stale = value.get("revision") != self.workspace.revision
        ranked = value.get("ranked", [])[:max_pages]
        pages = [self._page_for_candidate(handle,c) for c in ranked]
        if stale:
            for page in pages:
                page["state"] = "stale-context"
                page["fetchable"] = False
        source_pages = sum(1 for p in pages if p["source_range"])
        return {
            "handle": handle, "compiled_revision": value.get("revision"), "current_revision": self.workspace.revision,
            "stale": stale, "task": value.get("task"), "task_class": value.get("task_class"), "pages": pages,
            "page_count": len(pages), "source_page_count": source_pages,
            "address_space_semantics": "metadata is mapped eagerly; exact source faults in only through fetch",
            "whole_file_dump_default": False,
        }

    def plan_next(self, handle: str, fetched_page_ids: list[str] | None = None, max_pages: int = 3, max_estimated_bytes: int = 20_000) -> dict:
        """Plan the next source page faults without reading source bytes.

        The planner is intentionally selective. Low-confidence/no-gold contexts return an abstention
        plan rather than filling the model's attention budget with the least-bad repository text.
        """
        if fetched_page_ids is None:
            fetched_page_ids = []
        if not isinstance(fetched_page_ids, list) or not all(isinstance(x, str) and x for x in fetched_page_ids):
            raise TypeError("fetched_page_ids must be a list of non-empty strings")
        if max_pages < 1 or max_pages > 50:
            raise ValueError("max_pages must be in [1, 50]")
        if max_estimated_bytes < 1 or max_estimated_bytes > 5_000_000:
            raise ValueError("max_estimated_bytes must be in [1, 5000000]")
        value = self._slice(handle)
        address = self.address_space(handle, max_pages=1000)
        decision = dict(value.get("decision_packet") or {})
        if address["stale"]:
            return {
                "handle": handle, "stale": True, "revision": self.workspace.revision, "planned_pages": [],
                "action": "refresh-context", "reason": "context-revision-stale", "estimated_source_bytes": 0,
            }
        if decision.get("abstention_recommended") and decision.get("retrieval_confidence") == "low":
            return {
                "handle": handle, "stale": False, "revision": self.workspace.revision, "planned_pages": [],
                "action": "abstain-or-broaden-query", "reason": "low retrieval confidence",
                "unsupported_concepts": list(decision.get("unsupported_concepts") or []),
                "estimated_source_bytes": 0, "source_bytes_read": 0,
            }
        fetched = set(fetched_page_ids)
        trust_bonus = {"exact": 0.10, "semantic": 0.08, "parser": 0.045, "derived": 0.0, "heuristic": -0.08}
        lane_bonus = {"evidence": 0.10, "diagnostic": 0.08, "graph": 0.07, "symbol": 0.055, "resident": 0.04, "utility": 0.025, "lexical": 0.0}
        ranked = []
        for page in address["pages"]:
            if page["page_id"] in fetched or not page.get("fetchable"):
                continue
            lanes = set(str(page.get("lane") or "").split("+"))
            score = float(page.get("relevance") or 0.0) + trust_bonus.get(page.get("trust"), 0.0)
            score += sum(lane_bonus.get(l, 0.0) for l in lanes)
            if page.get("state") == "resident":
                score += 0.05
            size = max(1, int(page.get("source_bytes_estimate") or 1))
            score -= min(0.16, (size / max_estimated_bytes) * 0.10)
            ranked.append((score, size, page))
        ranked.sort(key=lambda x: (-x[0], x[1], x[2]["path"], x[2]["page_id"]))
        selected = []
        used = 0
        path_counts: dict[str, int] = {}
        for score, size, page in ranked:
            if len(selected) >= max_pages:
                break
            # Prefer distinct source regions before taking a second page from one path.
            effective = score - (0.07 * path_counts.get(page["path"], 0))
            if selected and used + size > max_estimated_bytes:
                continue
            selected.append({**page, "planner_score": round(effective, 6)})
            used += size
            path_counts[page["path"]] = path_counts.get(page["path"], 0) + 1
        return {
            "handle": handle, "stale": False, "revision": self.workspace.revision,
            "retrieval_confidence": decision.get("retrieval_confidence"),
            "action": "fault-pages" if selected else "no-useful-page",
            "planned_pages": selected, "page_ids": [p["page_id"] for p in selected],
            "estimated_source_bytes": used, "source_bytes_read": 0,
            "planner_policy": "evidence/trust/relevance + bounded residency/utility priors - source-cost; path diversity; low-confidence abstention",
        }

    def fetch(self, handle: str, page_ids: list[str], max_source_bytes: int = 60_000) -> dict:
        if not isinstance(page_ids,list) or not page_ids or not all(isinstance(x,str) and x for x in page_ids):
            raise TypeError("page_ids must be a non-empty list of strings")
        if max_source_bytes < 1 or max_source_bytes > 5_000_000:
            raise ValueError("max_source_bytes must be in [1, 5000000]")
        address = self.address_space(handle, max_pages=1000)
        if address["stale"]:
            return {"handle":handle,"stale":True,"compiled_revision":address["compiled_revision"],"current_revision":self.workspace.revision,
                    "pages":[],"faults":[{"page_id":x,"reason":"context-revision-stale"} for x in page_ids],"source_bytes":0}
        by_id={p["page_id"]:p for p in address["pages"]}
        out=[]; faults=[]; used=0; authority_read=0
        for pid in page_ids:
            page=by_id.get(pid)
            if not page:
                faults.append({"page_id":pid,"reason":"unknown-page"}); continue
            if not page.get("fetchable") or not page.get("source_range"):
                faults.append({"page_id":pid,"reason":"metadata-only-page"}); continue
            fr=self.store.file_by_path(page["path"])
            if not fr or fr["digest"] != page.get("source_digest"):
                faults.append({"page_id":pid,"reason":"source-digest-drift"}); continue
            start,end=page["source_range"]
            try:
                ranged=self.workspace.read_source_line_range(page["path"], int(start), int(end))
            except Exception as exc:
                faults.append({"page_id":pid,"reason":"source-range-read-failed","error":str(exc)}); continue
            authority_read += int(ranged.get("backend_authority_bytes_read") or 0)
            source=str(ranged["text"])
            data=bytes(ranged["raw"])
            if used + len(data) > max_source_bytes:
                faults.append({"page_id":pid,"reason":"byte-budget","needed_bytes":len(data),"remaining_bytes":max_source_bytes-used}); continue
            used += len(data)
            out.append({**page,"source":source,"authority":"exact-source","io_mode":"authoritative-range-read",
                        "actual_source_bytes":len(data),"backend_authority_bytes_read":int(ranged.get("backend_authority_bytes_read") or 0),
                        "encoding":ranged.get("encoding"),"lossy_text":bool(ranged.get("lossy_text")),"newline":ranged.get("newline")})
            active_episode = self.store.active_episode_for_context(handle)
            self.store.append_context_fault(
                handle, pid, page["object_id"], page["path"], len(data), int(ranged.get("backend_authority_bytes_read") or 0), self.workspace.revision,
                active_episode["id"] if active_episode else None, utc_now(),
            )
            self.workspace.residency_touch([page["object_id"]]) if self.store.resident_by_id(page["object_id"]) else None
        self.store.commit()
        return {"handle":handle,"stale":False,"revision":self.workspace.revision,"pages":out,"faults":faults,
                "source_bytes":used,"agent_visible_source_bytes":used,"backend_authority_bytes_read":authority_read,
                "max_source_bytes":max_source_bytes,"remaining_bytes":max_source_bytes-used,
                "io_accounting":"agent-visible source bytes are distinct from authority bytes read"}

    def prefetch(self, handle: str, max_source_bytes: int = 20_000, max_pages: int = 8) -> dict:
        plan = self.plan_next(handle, [], max_pages=max_pages, max_estimated_bytes=max_source_bytes)
        ids = list(plan.get("page_ids") or [])
        if not ids:
            return {
                "handle": handle, "stale": bool(plan.get("stale")), "pages": [],
                "faults": [{"reason": plan.get("reason") or plan.get("action") or "no-fetchable-pages"}],
                "source_bytes": 0, "plan": plan,
            }
        result = self.fetch(handle, ids, max_source_bytes)
        result["plan"] = plan
        result["prefetch_policy"] = "context plan-next followed by exact digest-bound page faults"
        return result
