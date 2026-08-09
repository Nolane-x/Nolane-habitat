from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .util import utc_now

if TYPE_CHECKING:
    from .workspace import HabitatWorkspace


class ContextResidency:
    """Persistent semantic working set for an agent.

    Residency stores *references and provenance*, never copied source bodies. Exact source is paged in
    when materialized and bounded by the caller's byte budget. This makes the mechanism closer to
    virtual memory than to a second context database.
    """

    DEFAULT_MAX_OBJECTS = 32
    DEFAULT_MAX_SOURCE_BYTES = 120_000

    def __init__(self, workspace: "HabitatWorkspace"):
        self.workspace = workspace
        self.store = workspace.store

    def _config(self) -> dict:
        return {
            "max_objects": int(self.store.get_meta("residency.max_objects", str(self.DEFAULT_MAX_OBJECTS)) or self.DEFAULT_MAX_OBJECTS),
            "max_source_bytes": int(self.store.get_meta("residency.max_source_bytes", str(self.DEFAULT_MAX_SOURCE_BYTES)) or self.DEFAULT_MAX_SOURCE_BYTES),
        }

    def configure(self, max_objects: int = DEFAULT_MAX_OBJECTS, max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES) -> dict:
        if max_objects < 1 or max_objects > 500:
            raise ValueError("max_objects must be in [1, 500]")
        if max_source_bytes < 0 or max_source_bytes > 20_000_000:
            raise ValueError("max_source_bytes must be in [0, 20000000]")
        self.store.set_meta("residency.max_objects", str(max_objects))
        self.store.set_meta("residency.max_source_bytes", str(max_source_bytes))
        result = self._enforce_capacity()
        result["configured"] = self._config()
        return result

    def _next_seq(self) -> int:
        seq = int(self.store.get_meta("residency.access_seq", "0") or 0) + 1
        self.store.set_meta("residency.access_seq", str(seq))
        return seq

    def _object_info(self, oid: str) -> dict | None:
        s = self.store.symbol_by_id(oid)
        if s:
            fr = self.store.file_by_path(s["path"])
            # Residency status/capacity is a metadata operation. Never read authoritative
            # source merely to estimate a symbol's footprint; remote authorities may turn
            # such a read into an expensive network transfer. Use compiler line-count
            # metadata and the indexed file size as a bounded estimate instead.
            estimate = 0
            if fr:
                cache = self.store.load_compile_cache(fr["id"]) or {}
                source_io = ((cache.get("metadata") or {}).get("source_io") or {})
                total_lines = max(1, int(source_io.get("line_count") or 1))
                span = max(1, int(s["end_line"]) - int(s["start_line"]) + 1)
                estimate = min(int(fr["size"]), max(1, int(int(fr["size"]) * span / total_lines))) if int(fr["size"]) else 0
            return {"object_id": oid, "kind": "symbol", "path": s["path"], "source_digest": fr["digest"] if fr else None,
                    "source_bytes_estimate": estimate, "source_bytes_estimate_method": "compiler-line-density"}
        d = self.store.diagnostic_by_id(oid)
        if d:
            fr = self.store.file_by_path(d["path"])
            return {"object_id": oid, "kind": "diagnostic", "path": d["path"], "source_digest": fr["digest"] if fr else None, "source_bytes_estimate": 0}
        f = self.store.file_by_id(oid)
        if f:
            return {"object_id": oid, "kind": "file", "path": f["path"], "source_digest": f["digest"], "source_bytes_estimate": 0}
        return None

    def _row_state(self, row) -> str:
        info = self._object_info(row["object_id"])
        if not info:
            return "missing"
        if info.get("source_digest") != row["source_digest"]:
            return "stale"
        return "fresh"

    def admit(self, handle: str, *, pin_top: int = 0, max_admit: int | None = None) -> dict:
        self.workspace.reconcile()
        record = self.store.load_json("context_slices", handle)
        if not record:
            raise KeyError(handle)
        if record.get("revision") != self.workspace.revision:
            return {"handle": handle, "admitted": [], "stale": True, "revision": self.workspace.revision,
                    "reason": "context handle revision does not match workspace revision"}
        ids = list(record.get("selected_ids") or [])
        if max_admit is not None:
            if max_admit < 1 or max_admit > 500:
                raise ValueError("max_admit must be in [1, 500]")
            ids = ids[:max_admit]
        ranked = {x.get("object_id"): float(x.get("score") or 0.0) for x in record.get("ranked", []) if x.get("object_id")}
        now = utc_now(); admitted=[]; skipped=[]
        for idx, oid in enumerate(ids):
            info = self._object_info(oid)
            if not info:
                skipped.append({"object_id": oid, "reason": "object-missing"}); continue
            seq = self._next_seq()
            value = {**info, "admitted_revision": self.workspace.revision, "relevance": ranked.get(oid, 0.0),
                     "pinned": idx < max(0, pin_top), "access_count": 1, "last_access_seq": seq,
                     "admitted_at": now, "last_touched_at": now}
            self.store.upsert_resident(value); admitted.append(oid)
        self.store.commit()
        capacity = self._enforce_capacity()
        return {"handle": handle, "stale": False, "revision": self.workspace.revision, "admitted": admitted,
                "skipped": skipped, "capacity": capacity, "status": self.status(reconcile=False)}

    def _enforce_capacity(self) -> dict:
        cfg = self._config(); evicted=[]
        rows = list(self.store.resident_rows())
        def totals(rs):
            return len(rs), sum(int(r["source_bytes_estimate"] or 0) for r in rs)
        count, source_bytes = totals(rows)
        if count <= cfg["max_objects"] and source_bytes <= cfg["max_source_bytes"]:
            return {"evicted": [], "overcommitted": False, "resident_objects": count, "source_bytes_estimate": source_bytes, **cfg}
        # Stale/missing first, then least-recent/least-relevant non-pinned. Pinned objects are never silently evicted.
        candidates = []
        for r in rows:
            if r["pinned"]:
                continue
            state = self._row_state(r)
            state_rank = 0 if state in {"missing", "stale"} else 1
            candidates.append((state_rank, int(r["last_access_seq"]), float(r["relevance"]), int(r["access_count"]), r["object_id"]))
        candidates.sort()
        for _, _, _, _, oid in candidates:
            if count <= cfg["max_objects"] and source_bytes <= cfg["max_source_bytes"]:
                break
            row = self.store.resident_by_id(oid)
            if not row: continue
            source_bytes -= int(row["source_bytes_estimate"] or 0); count -= 1
            self.store.delete_resident(oid); evicted.append(oid)
        self.store.commit()
        over = count > cfg["max_objects"] or source_bytes > cfg["max_source_bytes"]
        return {"evicted": evicted, "overcommitted": over, "resident_objects": count, "source_bytes_estimate": source_bytes, **cfg,
                "overcommit_reason": "pinned residents exceed capacity" if over else None}

    def status(self, reconcile: bool = True) -> dict:
        if reconcile:
            self.workspace.reconcile()
        cfg = self._config(); rows=[]; counts={"fresh":0,"stale":0,"missing":0}
        for r in self.store.resident_rows():
            d=dict(r); state=self._row_state(r); d["state"]=state; counts[state]+=1; rows.append(d)
        return {"revision": self.workspace.revision, "config": cfg, "count": len(rows),
                "source_bytes_estimate": sum(int(r.get("source_bytes_estimate") or 0) for r in rows),
                "state_counts": counts, "objects": rows}

    def touch(self, object_ids: list[str]) -> dict:
        now=utc_now(); touched=[]; missing=[]
        for oid in object_ids:
            if not self.store.resident_by_id(oid): missing.append(oid); continue
            self.store.touch_resident(oid, self._next_seq(), now); touched.append(oid)
        self.store.commit(); return {"touched": touched, "missing": missing, "revision": self.workspace.revision}

    def pin(self, object_ids: list[str], pinned: bool = True) -> dict:
        changed=[]; missing=[]
        for oid in object_ids:
            if not self.store.resident_by_id(oid): missing.append(oid); continue
            self.store.set_resident_pin(oid, pinned); changed.append(oid)
        self.store.commit(); cap=self._enforce_capacity()
        return {"pinned": bool(pinned), "changed": changed, "missing": missing, "capacity": cap}

    def evict(self, object_ids: list[str] | None = None, *, stale_only: bool = False) -> dict:
        rows=list(self.store.resident_rows()); evicted=[]; refused=[]
        selected=set(object_ids or [])
        for r in rows:
            if object_ids is not None and r["object_id"] not in selected: continue
            state=self._row_state(r)
            if stale_only and state == "fresh": continue
            if r["pinned"]:
                refused.append({"object_id":r["object_id"],"reason":"pinned"}); continue
            self.store.delete_resident(r["object_id"]); evicted.append(r["object_id"])
        self.store.commit(); return {"evicted":evicted,"refused":refused,"status":self.status(reconcile=False)}

    def materialize(self, max_source_bytes: int | None = None, max_objects: int | None = None) -> dict:
        self.workspace.reconcile(); cfg=self._config()
        max_source_bytes = cfg["max_source_bytes"] if max_source_bytes is None else max_source_bytes
        max_objects = cfg["max_objects"] if max_objects is None else max_objects
        if max_source_bytes < 0 or max_source_bytes > 20_000_000: raise ValueError("invalid source byte budget")
        if max_objects < 1 or max_objects > 500: raise ValueError("invalid object budget")
        objects=[]; omissions=[]; source_bytes=0; authority_bytes_read=0; touched=[]
        for r in self.store.resident_rows():
            if len(objects) >= max_objects: break
            state=self._row_state(r)
            if state != "fresh":
                omissions.append({"object_id":r["object_id"],"reason":state}); continue
            oid=r["object_id"]; sr=self.store.symbol_by_id(oid); dr=self.store.diagnostic_by_id(oid); fr=self.store.file_by_id(oid)
            if sr:
                item={k:sr[k] for k in ("id","path","name","qualified_name","kind","start_line","end_line","trust")}
                item["resident"]={"pinned":bool(r["pinned"]),"relevance":r["relevance"],"access_count":r["access_count"]}
                inspected=self.workspace._inspect_object(oid,"body"); exact=inspected.get("source",""); b=len(exact.encode("utf-8"))
                accounting=inspected.get("source_accounting") or {}; authority_bytes_read += int(accounting.get("backend_authority_bytes_read") or 0)
                if source_bytes+b <= max_source_bytes:
                    item["source"]=exact; item["source_authority"]="exact-source"; item["source_accounting"]=accounting; source_bytes+=b
                else:
                    item["source_omitted_reason"]="source-byte-budget"; omissions.append({"object_id":oid,"reason":"source-byte-budget"})
                objects.append(item)
            elif dr:
                item={k:dr[k] for k in ("id","path","severity","message","line","column","source","trust")}; objects.append(item)
            elif fr:
                objects.append({k:fr[k] for k in ("id","path","language","size","digest","parse_complete","index_truncated")})
            else:
                omissions.append({"object_id":oid,"reason":"missing"}); continue
            touched.append(oid)
        if touched: self.touch(touched)
        packet={"revision":self.workspace.revision,"objects":objects,"object_count":len(objects),"source_bytes":source_bytes,
                "agent_visible_source_bytes":source_bytes,"backend_authority_bytes_read":authority_bytes_read,
                "max_source_bytes":max_source_bytes,"max_objects":max_objects,"omissions":omissions,
                "policy":"persistent semantic references; exact source paged in on materialization; no copied source bodies at rest"}
        packet["packet_bytes"]=len(json.dumps(packet,ensure_ascii=False,default=str).encode("utf-8"))
        return packet
