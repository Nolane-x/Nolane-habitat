from __future__ import annotations

import json
import os
import re
import shutil
import time
from collections import Counter
from functools import wraps
from pathlib import Path

from .compiler import COMPILE_CACHE_VERSION, CompiledFile, compile_cache_fingerprint, compile_file
from .context import ContextCompiler
from .context.virtual_memory import ContextVirtualMemory
from .model import DiagnosticRecord, EventRecord, FileRecord, Revision, SymbolRecord, to_dict
from .merkle import build_snapshot as build_merkle_snapshot, resolve_store_path as resolve_merkle_path, diff_store_roots as diff_merkle_roots
from .mutation import MutationEngine, TransactionConflict
from .residency import ContextResidency
from .semantic.fabric import semantic_fabric_report
from .effect_twin import compile_effects, effect_snapshot, analyze_effect_text
from .dataflow_twin import compile_dataflow, dataflow_snapshot, analyze_dataflow_text
from .project_world import build_project_world
from .runtime_twin import normalize_otel_record, normalize_dap_event, event_to_store_dict, build_runtime_topology
from .semantic.python_jedi import python_rename_sites, close_jedi_project, jedi_project_status
from .semantic.typescript import TypeScriptCompilerProvider
from .semantic.ts_language_service import close_typescript_session, typescript_session_status
from .semantic.project import compile_project_semantics
from .source_bridge import prepare_source
from .backends import LocalProjectBackend, DirectoryMirrorBackend, backend_from_manifest
from .testing.impact import affected_tests
from .storage import Store
from .ui import BrowserRuntime
from .ui_semantic import observe_html
from .util import detect_language, iter_project_files, root_digest, sha256_bytes, sha256_file, stable_id, utc_now
from .watcher import PollingSourceWatcher
from .policy import PolicyEngine
from .git_cognition import (status as git_status_view, history as git_history_view, blame as git_blame_view, explain_line as git_explain_line,
    diff as git_diff_view, changed_files as git_changed_files_view, churn as git_churn_view, explain_symbol as git_explain_symbol_view,
    branches as git_branches_view, worktrees as git_worktrees_view, conflicts as git_conflicts_view, commit_impact as git_commit_impact_view)
from .uncertainty import assess_hypothesis
from .cognitive_resilience import analyze_cognitive_loop, epistemic_pressure
from .executive import (EXECUTIVE_PHASES, STRATEGY_FAMILIES, verify_event_chain, verify_phase_sequence, expected_control_phases,
    classify_strategy_failure, structural_recovery_strategy, milestone_topology)
from .dependency_cognition import snapshot as dependency_snapshot, query as dependency_query, world as dependency_world
from .execution import containment_probe
from .sandbox import bubblewrap_probe, sandbox_capability_summary
from .retention import RetentionPolicy, plan as retention_plan, compact as retention_compact, harden_state_permissions


def _atomic_workspace_refresh(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.store.atomic():
            return method(self, *args, **kwargs)
    return wrapped


class HabitatWorkspace:
    MANIFEST = "workspace.json"

    def __init__(self, habitat_dir: Path):
        self.habitat_dir = habitat_dir.resolve()
        manifest_path = self.habitat_dir / self.MANIFEST
        if not manifest_path.exists():
            raise FileNotFoundError(f"not a Habitat workspace: {self.habitat_dir}")
        self.manifest_path = manifest_path
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.backend = backend_from_manifest(self.manifest, self.habitat_dir)
        # `source_root` is the local semantic materialization, not necessarily the source authority.
        self.source_root = self.backend.materialized_root.resolve()
        authority_root = Path(self.backend.source_authority.info.authoritative_root).resolve()
        if self.habitat_dir == authority_root or authority_root in self.habitat_dir.parents:
            raise ValueError("invalid Habitat workspace: persistent state is inside canonical source and would self-index")
        self.store = Store(self.habitat_dir / "habitat.sqlite3")
        self.policy = PolicyEngine(self.habitat_dir)
        self._state_permission_hardening = harden_state_permissions(self.habitat_dir)
        self._startup_recovery = MutationEngine(self).recover_pending()
        self._browser_runtime: BrowserRuntime | None = None
        self._source_watcher: PollingSourceWatcher | None = None
        self._observatory = None

    def close(self) -> None:
        if self._observatory is not None:
            try: self._observatory.close()
            except Exception: pass
            self._observatory = None
        if self._source_watcher is not None:
            self._source_watcher.close(); self._source_watcher = None
        if self._browser_runtime is not None:
            self._browser_runtime.close(); self._browser_runtime = None
        try:
            close_typescript_session(self.source_root)
            close_jedi_project(self.source_root)
        except Exception:
            pass
        try:
            self.backend.close()
        finally:
            self.store.close()

    def storage_doctor(self) -> dict:
        """Inspect the local Habitat database without refreshing project state."""

        return self.store.doctor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    @classmethod
    def create(cls, source: str | Path, habitat_dir: str | Path, *, backend: str = "local", reset: bool = False) -> "HabitatWorkspace":
        source_path = Path(source).expanduser().resolve()
        habitat_dir = Path(habitat_dir).resolve()
        if source_path.is_dir() and (habitat_dir == source_path or source_path in habitat_dir.parents):
            raise ValueError("habitat_dir must live outside the canonical source tree; self-indexing is forbidden")
        if (habitat_dir / cls.MANIFEST).exists() and not reset:
            raise FileExistsError("Habitat workspace already exists; pass reset=True to intentionally replace its identity")
        if reset and habitat_dir.exists():
            import shutil
            shutil.rmtree(habitat_dir)
        habitat_dir.mkdir(parents=True, exist_ok=True)
        authority_root, mode = prepare_source(source_path, habitat_dir)
        backend_kind = str(backend).strip().lower()
        if backend_kind in {"local", "local-filesystem"}:
            b = LocalProjectBackend(authority_root, mode=mode)
        elif backend_kind in {"mirror", "directory-mirror"}:
            b = DirectoryMirrorBackend(authority_root, habitat_dir / "backend-mirror")
        else:
            raise ValueError(f"unsupported backend: {backend}")
        info = b.info.as_dict()
        manifest = {
            "schema": 10,
            "created_at": utc_now(),
            "mode": mode,
            # Retained for compatibility. In schema 3 this is the authoritative source root.
            "source_root": info["authoritative_root"],
            "source_authority": info["authority"],
            "semantic_twin_role": "derived-agent-representation",
            "backend": {
                "type": info["kind"], "id": info["backend_id"],
                "authoritative_root": info["authoritative_root"],
                "materialized_root": info["materialized_root"],
                "execution_kind": info["execution_kind"],
            },
            "source_authority_provider": {
                "type": b.source_authority.info.kind, "id": b.source_authority.info.authority_id,
                "authoritative_root": b.source_authority.info.authoritative_root,
                "materialized_root": b.source_authority.info.materialized_root,
            },
            "execution_provider": {
                "type": b.execution_provider.info.kind, "id": b.execution_provider.info.provider_id,
                "execution_root": b.execution_provider.info.execution_root, "containment_profile": "trusted-local",
            },
            "source_policy": {
                "respect_gitignore": True, "respect_habitatignore": True,
                "persistent_state_outside_source": True,
                "hard_ignore_scope": "vcs-cache-control-only"
            },
            "observatory": {
                "mode": "observer-only", "auto_start_on_agent_server": True, "auto_open_browser": True,
                "bind": "127.0.0.1", "control_actions": False,
                "reasoning_surface": "task/hypothesis/evidence/action summaries only; raw private chain-of-thought is not exposed",
                "visual_mode": "cinematic-realtime-world-v2", "event_transport": "sse-resumable", "auto_camera": True,
                "snapshot_consistency": "sqlite-read-transaction", "adaptive_lod": True
            },
            "world_model": {
                "semantic_twin": True, "effect_twin": True, "runtime_twin": True, "project_world": True,
                "counterfactual_worlds": True, "epistemic_runtime": True, "cognitive_scheduler": True, "executive_trajectory": True,
                "claim_boundary": "typed project/runtime/effect evidence and alternative worlds; not a complete causal or production-world proof"
            },
            "execution_policy": {
                "profile": "trusted-local-process", "sandboxed": False,
                "network_restricted": False, "filesystem_restricted": False,
                "policy_file": "policy.json",
                "warning": "not suitable for untrusted repositories without a filesystem-confined sandbox execution provider"
            },
        }
        (habitat_dir / cls.MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        b.close()
        ws = cls(habitat_dir)
        ws.refresh(reason="initial-ingest")
        return ws

    @property
    def revision(self) -> str:
        return self.store.head_revision() or "none"

    def resolve_source_path(self, rel: str) -> Path:
        p = (self.source_root / rel).resolve()
        root = self.source_root.resolve()
        if p != root and root not in p.parents:
            raise ValueError("path escapes source root")
        return p

    def backend_info(self) -> dict:
        info = self.backend.info.as_dict()
        info["source_authority"] = self.backend.source_authority.info.as_dict()
        info["execution_provider"] = self.backend.execution_provider.info.as_dict()
        info["semantic_twin_authority"] = False
        info["semantic_materialization_role"] = "compiler-mirror" if info["materialized_root"] != info["authoritative_root"] else "shared-source-view"
        info["substrate_composable"] = True
        return info

    def capability_report(self) -> dict:
        from .security.capabilities import build_capability_report

        return build_capability_report(
            source_authority=self.backend.source_authority.info.as_dict(),
            execution_provider=self.backend.execution_provider.info.as_dict(),
            generated_at_revision=self.revision,
        ).as_dict()

    def agent_open(self, name: str, metadata: dict | None = None) -> dict:
        if not isinstance(name,str) or not name.strip(): raise ValueError("agent name must be a non-empty string")
        if metadata is not None and not isinstance(metadata,dict): raise TypeError("metadata must be an object")
        now=utc_now(); aid=stable_id("agent",name.strip(),now)
        self.store.create_agent_session(aid,name.strip(),now,metadata or {})
        self._activity_safe("agent.connected","agent",agent_id=aid,status="active",summary=f"agent connected: {name.strip()}",data={"name":name.strip()})
        return self.agent_status(aid)

    def agent_status(self, agent_id: str) -> dict:
        row=self.store.agent_session(agent_id)
        if not row: raise KeyError(agent_id)
        value=dict(row); value["metadata"]=json.loads(value.pop("metadata_json") or "{}")
        value["leases"]=[dict(r) for r in self.store.lease_rows(agent_id)]
        return value

    def agent_close(self, agent_id: str) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        released=self.store.release_agent_leases(agent_id)
        self.store.close_agent_session(agent_id,utc_now())
        self._activity_safe("agent.disconnected","agent",agent_id=agent_id,status="closed",summary="agent disconnected",data={"released_leases":released})
        return {"agent_id":agent_id,"status":"closed","released_leases":released}

    def agent_forget(self, agent_id: str) -> dict:
        counts=self.store.forget_agent_session(agent_id)
        return {"agent_id":agent_id,"forgotten":True,"private_state_deleted":counts,
                "preserved_shared_world":["revisions","transactions","evidence","project_invariants","causal_edges"],
                "claim_boundary":"Deletes agent-private cognitive state after session closure; shared project provenance and verified world history are intentionally preserved."}

    def lease_acquire(self, agent_id: str, resource_kind: str, resource_id: str, ttl_s: float = 120.0, transaction_id: str | None = None) -> dict:
        if not isinstance(ttl_s,(int,float)) or isinstance(ttl_s,bool) or ttl_s<=0 or ttl_s>3600: raise ValueError("ttl_s must be in (0,3600]")
        if resource_kind not in {"path","symbol","subsystem"}: raise ValueError("unsupported lease resource kind")
        import time
        return self.store.acquire_lease(resource_kind,resource_id,agent_id,self.revision,utc_now(),time.time()+float(ttl_s),transaction_id)

    def lease_release(self, agent_id: str, resource_kind: str, resource_id: str) -> dict:
        return {"released":self.store.release_lease(resource_kind,resource_id,agent_id),"agent_id":agent_id,"resource_kind":resource_kind,"resource_id":resource_id}

    def lease_status(self, agent_id: str | None = None) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        return {"revision":self.revision,"leases":[dict(r) for r in self.store.lease_rows(agent_id)]}

    def agent_observe(self, agent_id: str, path: str, *, object_id: str = "", kind: str = "source") -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        self.reconcile()
        fr=self.store.file_by_path(path)
        if not fr: raise FileNotFoundError(path)
        self.store.record_agent_observation(agent_id,path,fr["digest"],self.revision,kind,object_id,utc_now())
        return {"agent_id":agent_id,"path":path,"object_id":object_id,"digest":fr["digest"],"revision":self.revision,"kind":kind}

    def agent_notifications(self, agent_id: str, status: str | None = "pending", limit: int = 100) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if limit<1 or limit>1000: raise ValueError("limit must be in [1,1000]")
        out=[]
        for row in self.store.agent_notifications(agent_id,status,limit):
            d=dict(row)
            try: d["data"]=json.loads(d.pop("data_json") or "{}")
            except Exception: d["data"]={}; d.pop("data_json",None)
            out.append(d)
        return {"agent_id":agent_id,"revision":self.revision,"notifications":out,"count":len(out)}

    def agent_ack_notification(self, agent_id: str, notification_id: str) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        return {"agent_id":agent_id,"notification_id":notification_id,"acked":self.store.ack_agent_notification(notification_id,agent_id,utc_now())}

    def agent_revalidate_notification(self, agent_id: str, notification_id: str) -> dict:
        """Refresh the invalidated source fact and explicitly consume one coordination notification.

        This is a world-state revalidation primitive, not proof that the agent has re-run its full
        reasoning. The caller remains responsible for re-judging dependent plan steps.
        """
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        matches=[r for r in self.store.agent_notifications(agent_id,"pending",1000) if r["id"]==notification_id]
        if not matches: raise KeyError(notification_id)
        row=matches[0]
        if row["kind"]!="source-invalidated" or row["resource_kind"]!="path":
            raise ValueError("only pending source-invalidated path notifications can be revalidated")
        path=row["resource_id"]
        self.reconcile()
        fr=self.store.file_by_path(path)
        current_digest=fr["digest"] if fr else None
        if fr:
            self.store.record_agent_observation(agent_id,path,current_digest,self.revision,"source","",utc_now())
        acked=self.store.ack_agent_notification(notification_id,agent_id,utc_now())
        self._activity_safe("agent.revalidated","coordination",agent_id=agent_id,ref_id=notification_id,path=path,status="fresh",summary=f"revalidated {path}",data={"current_digest":current_digest})
        return {"agent_id":agent_id,"notification_id":notification_id,"path":path,"revision":self.revision,
                "current_digest":current_digest,"acked":acked,"action":"selective-revalidate",
                "claim_boundary":"world-state observation refreshed; caller must still re-judge any dependent plan or hypothesis"}

    def _notify_observers(self, changed_paths: list[str], *, owner_agent_id: str | None, transaction_id: str | None) -> list[str]:
        created=[]
        for path in sorted(set(changed_paths or [])):
            # One agent may have several object-level observations for the same path. A world change creates
            # one path invalidation per agent, not one duplicate notification per observed object.
            observations={}
            for row in self.store.agent_observations(path=path):
                aid=row["agent_id"]
                prev=observations.get(aid)
                if prev is None or str(row["observed_at"]) > str(prev["observed_at"]): observations[aid]=row
            fr=self.store.file_by_path(path); current_digest=fr["digest"] if fr else None
            for aid,row in observations.items():
                if owner_agent_id is not None and aid==owner_agent_id: continue
                session=self.store.agent_session(aid)
                if not session or session["status"]!="active": continue
                nid=stable_id("notify",aid,path,self.revision,transaction_id or "")
                existing=next((n for n in self.store.agent_notifications(aid,None,1000) if n["id"]==nid),None)
                if existing is not None:
                    continue
                self.store.append_agent_notification({
                    "id":nid,"agent_id":aid,"kind":"source-invalidated","resource_kind":"path","resource_id":path,
                    "revision":self.revision,"caused_by_transaction":transaction_id,"created_at":utc_now(),
                    "data":{"observed_revision":row["revision"],"observed_digest":row["digest"],"current_digest":current_digest,
                            "action":"selective-revalidate","claim_boundary":"advisory invalidation; the agent must re-judge plan dependencies"},
                }); created.append(nid)
                self._activity_safe("agent.source-invalidated","coordination",agent_id=aid,ref_id=nid,path=path,status="stale",summary=f"agent cognition invalidated: {path}",data={"caused_by_transaction":transaction_id,"action":"selective-revalidate"})
        return created

    def agent_residency_admit(self, agent_id: str, handle: str, max_admit: int = 8, pin_top: int = 0) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if max_admit<1 or max_admit>100: raise ValueError("max_admit must be in [1,100]")
        if pin_top<0 or pin_top>max_admit: raise ValueError("pin_top must be in [0,max_admit]")
        record=self.store.load_json("context_slices",handle)
        if not record: raise KeyError(handle)
        if record.get("revision")!=self.revision: raise TransactionConflict("cannot admit stale context into agent residency")
        if record.get("agent_id") not in {None,agent_id}: raise PermissionError("context belongs to another agent namespace")
        admitted=[]; seq=self.store.latest_event_seq()
        for idx,c in enumerate((record.get("ranked") or [])[:max_admit]):
            oid=c.get("object_id"); sr=self.store.symbol_by_id(oid); dr=self.store.diagnostic_by_id(oid); fr0=self.store.file_by_id(oid)
            row=sr or dr or fr0
            if not row: continue
            path=row["path"]; fr=self.store.file_by_path(path)
            self.store.upsert_agent_resident({"agent_id":agent_id,"object_id":oid,"kind":"symbol" if sr else "diagnostic" if dr else "file",
                "path":path,"admitted_revision":self.revision,"source_digest":fr["digest"] if fr else None,"relevance":float(c.get("score") or 0),
                "pinned":idx<pin_top,"access_count":1,"last_access_seq":seq,"admitted_at":utc_now(),"last_touched_at":utc_now()})
            admitted.append(oid)
        self._activity_safe("memory.admitted","memory",agent_id=agent_id,ref_id=handle,status="resident",summary=f"admitted {len(admitted)} context objects",data={"object_ids":admitted,"pinned":min(pin_top,len(admitted))})
        return {"agent_id":agent_id,"handle":handle,"admitted":admitted,"status":self.agent_residency_status(agent_id)}

    def agent_residency_status(self, agent_id: str) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        out=[]
        for r in self.store.agent_resident_rows(agent_id):
            d=dict(r); fr=self.store.file_by_path(d["path"]); d["fresh"]=bool(fr and fr["digest"]==d["source_digest"]); d["pinned"]=bool(d["pinned"]); out.append(d)
        return {"agent_id":agent_id,"revision":self.revision,"objects":out,"count":len(out),"scope":"agent-private attention state; shared source/evidence remain workspace-global"}

    def agent_residency_evict(self, agent_id: str, object_ids: list[str]) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        for oid in object_ids: self.store.delete_agent_resident(agent_id,oid)
        self._activity_safe("memory.evicted","memory",agent_id=agent_id,status="evicted",summary=f"evicted {len(object_ids)} context objects",data={"object_ids":object_ids})
        return self.agent_residency_status(agent_id)

    def approval_grant(self, action: str, *, resource: str | None = None, agent_id: str | None = None, granted_by: str, ttl_s: float = 300.0, metadata: dict | None = None) -> dict:
        if not isinstance(granted_by,str) or not granted_by.strip(): raise ValueError("granted_by must be non-empty")
        if not isinstance(ttl_s,(int,float)) or isinstance(ttl_s,bool) or ttl_s<=0 or ttl_s>86400: raise ValueError("ttl_s must be in (0,86400]")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        import time
        aid=stable_id("approval",action,resource or "",agent_id or "",utc_now())
        value={"id":aid,"action":action,"resource":resource,"agent_id":agent_id,"granted_by":granted_by.strip(),"expires_at":time.time()+float(ttl_s),"created_at":utc_now(),"metadata":metadata or {}}
        self.store.create_approval(value)
        self._activity_safe("policy.approval-granted","policy",agent_id=agent_id,ref_id=aid,status="approved",summary=f"approval granted for {action}",data={"resource":resource,"granted_by":granted_by.strip(),"ttl_s":float(ttl_s)})
        return {**value,"status":"active"}

    def _consume_approval(self, approval_id: str | None, *, action: str, resource: str | None, agent_id: str | None) -> bool:
        if not approval_id: return False
        import time
        return bool(self.store.consume_approval(approval_id,action=action,resource=resource,agent_id=agent_id,consumed_at=utc_now(),now_ts=time.time()))

    def policy_status(self) -> dict:
        return {"revision":self.revision,"policy":self.policy.status()}

    def policy_update(self, patch: dict) -> dict:
        return {"revision":self.revision,"policy":self.policy.update(patch)}

    def policy_evaluate(self, action: str, *, path: str | None = None, capability_id: str | None = None, structural: bool = False) -> dict:
        if action in {"read","edit"}:
            if not path: raise ValueError("path required for source policy evaluation")
            decision=self.policy.evaluate_source(action,path,structural=structural)
        elif action == "execute":
            if not capability_id: raise ValueError("capability_id required for execution policy evaluation")
            caps={c["id"]:c for c in self.backend.discover_capabilities()}
            if capability_id not in caps: raise KeyError(capability_id)
            probe=containment_probe(); provider_caps=set(self.backend.execution_provider.info.capabilities)
            sandboxed="full-sandbox" in provider_caps
            decision=self.policy.evaluate_execution(caps[capability_id],sandboxed=sandboxed)
        elif action == "browser.external":
            decision=self.policy.evaluate_browser_external()
        else:
            raise ValueError("unknown policy action")
        return {"revision":self.revision,"decision":decision.as_dict()}

    def execution_security(self) -> dict:
        provider=self.backend.execution_provider
        caps=set(provider.info.capabilities); containment=getattr(provider,"containment_profile","filesystem-contained" if "full-sandbox" in caps else "trusted-local")
        probe=containment_probe(); bwrap=bubblewrap_probe()
        return {
            "revision":self.revision,"provider":provider.info.as_dict(),"containment_profile":containment,
            "host_probe":probe,"bubblewrap_probe":bwrap,"full_sandbox":"full-sandbox" in caps,
            "filesystem_restricted":"filesystem-confinement" in caps,"network_restricted":"network-confinement" in caps or containment=="network-contained",
            "claim_boundary":"full_sandbox is true only for a provider that advertises filesystem + network confinement after host probing; it is not a proof against kernel/runtime vulnerabilities."
        }

    def execution_configure(self, containment_profile: str) -> dict:
        if containment_profile not in {"trusted-local","network-contained","filesystem-contained"}: raise ValueError("unsupported containment profile")
        if containment_profile == "network-contained":
            probe=containment_probe()
            if not probe.get("network_namespace_available"):
                raise RuntimeError("network-contained profile unavailable: "+str(probe.get("reason")))
        if containment_profile == "filesystem-contained":
            probe=bubblewrap_probe()
            if not probe.get("available"):
                raise RuntimeError("filesystem-contained profile unavailable: "+str(probe.get("reason")))
        cfg=dict(self.manifest.get("execution_provider") or {})
        if cfg.get("type") not in {"local-process","authority-local-process","bubblewrap","bubblewrap-sandbox",None}:
            raise ValueError("containment profile configuration is only supported by local/bubblewrap execution providers")
        if containment_profile=="filesystem-contained":
            cfg["type"]="bubblewrap-sandbox"; cfg["containment_profile"]="filesystem-contained"
        else:
            cfg["type"]="local-process" if self.backend.source_authority.info.authoritative_root==str(self.source_root) else "authority-local-process"
            cfg["containment_profile"]=containment_profile
        self.manifest["execution_provider"]=cfg
        self.manifest.setdefault("execution_policy",{})["profile"]=containment_profile
        self.manifest["execution_policy"]["network_restricted"]=containment_profile in {"network-contained","filesystem-contained"}
        self.manifest["execution_policy"]["sandboxed"]=containment_profile=="filesystem-contained"
        self.manifest_path.write_text(json.dumps(self.manifest,indent=2),encoding="utf-8")
        self.backend.close(); self.backend=backend_from_manifest(self.manifest,self.habitat_dir); self.source_root=self.backend.materialized_root.resolve()
        return self.execution_security()

    def dependencies_snapshot(self) -> dict:
        self.reconcile(); return dependency_snapshot(Path(self.backend.source_authority.info.authoritative_root))

    def dependencies_query(self, term: str) -> dict:
        self.reconcile(); return dependency_query(Path(self.backend.source_authority.info.authoritative_root),term)

    def dependencies_world(self) -> dict:
        self.reconcile(); return dependency_world(Path(self.backend.source_authority.info.authoritative_root))

    def retention_status(self, policy: dict | None = None) -> dict:
        cfg=RetentionPolicy(**(policy or {})); return {"revision":self.revision,"plan":retention_plan(self.store,cfg),"state_permissions":harden_state_permissions(self.habitat_dir)}

    def retention_compact(self, policy: dict | None = None, *, dry_run: bool = True) -> dict:
        if not isinstance(dry_run,bool): raise TypeError("dry_run must be boolean")
        cfg=RetentionPolicy(**(policy or {})); result=retention_compact(self.store,cfg,dry_run=dry_run); result["revision"]=self.revision; result["state_permissions"]=harden_state_permissions(self.habitat_dir); return result

    def git_status(self) -> dict:
        self.reconcile(); return git_status_view(Path(self.backend.source_authority.info.authoritative_root))

    def git_history(self, path: str | None = None, limit: int = 20) -> dict:
        self.reconcile(); return git_history_view(Path(self.backend.source_authority.info.authoritative_root),path,limit)

    def git_blame(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict:
        self.reconcile(); return git_blame_view(Path(self.backend.source_authority.info.authoritative_root),path,start_line,end_line)

    def git_explain_line(self, path: str, line: int) -> dict:
        self.reconcile(); return git_explain_line(Path(self.backend.source_authority.info.authoritative_root),path,line)

    def git_diff(self, commit: str | None = None, path: str | None = None, context: int = 3) -> dict:
        self.reconcile(); return git_diff_view(Path(self.backend.source_authority.info.authoritative_root),commit=commit,path=path,context=context)

    def git_changed_files(self, commit: str = "HEAD", limit: int = 500) -> dict:
        self.reconcile(); return git_changed_files_view(Path(self.backend.source_authority.info.authoritative_root),commit,limit)

    def git_churn(self, path: str, limit: int = 200) -> dict:
        self.reconcile(); return git_churn_view(Path(self.backend.source_authority.info.authoritative_root),path,limit)

    def git_explain_symbol(self, object_id: str) -> dict:
        self.reconcile(); sym=self.store.symbol_by_id(object_id)
        if not sym: raise KeyError(object_id)
        return git_explain_symbol_view(Path(self.backend.source_authority.info.authoritative_root),sym["path"],int(sym["start_line"]),int(sym["end_line"]))

    def git_branches(self, limit: int = 200) -> dict:
        self.reconcile(); return git_branches_view(Path(self.backend.source_authority.info.authoritative_root),limit)

    def git_worktrees(self) -> dict:
        self.reconcile(); return git_worktrees_view(Path(self.backend.source_authority.info.authoritative_root))

    def git_conflicts(self) -> dict:
        self.reconcile(); return git_conflicts_view(Path(self.backend.source_authority.info.authoritative_root))

    def git_commit_impact(self, commit: str = "HEAD", limit: int = 1000) -> dict:
        self.reconcile(); return git_commit_impact_view(Path(self.backend.source_authority.info.authoritative_root),commit,limit)

    def state_security(self) -> dict:
        db=self.habitat_dir/"habitat.sqlite3"; mode=None
        if os.name!="nt" and db.exists():
            import stat as _stat
            mode=oct(_stat.S_IMODE(db.stat().st_mode))
        return {"habitat_dir":str(self.habitat_dir),"state_db":str(db),"posix_mode":mode,
                "encryption_at_rest":False,"secret_redaction":"execution-output best-effort",
                "retention":self.retention_status(),
                "claim_boundary":"File permissions and retention reduce exposure; Habitat state is not encrypted at rest and may contain sensitive diffs, backups, evidence, or logs."}

    def world_summary(self) -> dict:
        self.reconcile()
        git=git_status_view(Path(self.backend.source_authority.info.authoritative_root))
        deps=dependency_world(Path(self.backend.source_authority.info.authoritative_root))
        inv_rows=self.store.conn.execute("SELECT status,COUNT(*) AS n FROM project_invariants GROUP BY status").fetchall()
        agent_rows=self.store.conn.execute("SELECT status,COUNT(*) AS n FROM agent_sessions GROUP BY status").fetchall()
        pending=self.store.conn.execute("SELECT COUNT(*) AS n FROM agent_notifications WHERE status='pending'").fetchone()["n"]
        evidence=self.store.conn.execute("SELECT COUNT(*) AS n FROM evidence WHERE active=1").fetchone()["n"]
        effects=int(self.store.conn.execute("SELECT COUNT(*) AS n FROM effect_facts WHERE revision=?",(self.revision,)).fetchone()["n"])
        dataflows=int(self.store.conn.execute("SELECT COUNT(*) AS n FROM dataflow_facts WHERE revision=?",(self.revision,)).fetchone()["n"])
        runtime_events=int(self.store.conn.execute("SELECT COUNT(*) AS n FROM runtime_events").fetchone()["n"])
        cf_rows=self.store.conn.execute("SELECT status,COUNT(*) AS n FROM counterfactual_worlds GROUP BY status").fetchall()
        epistemic_rows=self.store.conn.execute("SELECT kind,COUNT(*) AS n FROM epistemic_items WHERE status='open' GROUP BY kind").fetchall()
        executive_rows=self.store.conn.execute("SELECT status,COUNT(*) AS n FROM executive_trajectories GROUP BY status").fetchall()
        strategy_rows=self.store.conn.execute("SELECT current_strategy,COUNT(*) AS n FROM executive_trajectories WHERE status='active' GROUP BY current_strategy").fetchall()
        return {"revision":self.revision,"backend":self.backend_info(),"policy":self.policy_status(),
                "execution_security":self.execution_security(),"git":git,
                "dependencies":{"direct":len(deps.get("direct_dependencies") or []),"locked":len(deps.get("locked_dependencies") or []),"unlocked_direct":len(deps.get("unlocked_direct") or [])},
                "active_evidence":int(evidence),"agents":{r["status"]:int(r["n"]) for r in agent_rows},
                "pending_coordination_notifications":int(pending),"invariants":{r["status"]:int(r["n"]) for r in inv_rows},
                "guidance_files":self.guidance_discover()["count"],
                "effect_facts":effects,"dataflow_facts":dataflows,"runtime_observations":runtime_events,
                "counterfactual_worlds":{r["status"]:int(r["n"]) for r in cf_rows},
                "epistemic_open":{r["kind"]:int(r["n"]) for r in epistemic_rows},
                "executive":{"trajectories":{r["status"]:int(r["n"]) for r in executive_rows},"active_strategies":{r["current_strategy"]:int(r["n"]) for r in strategy_rows}},
                "project_world":self.project_world(),
                "claim_boundary":"Bounded world-state orientation assembled from admitted Habitat state, Git, policy, dependency metadata, static effect evidence, runtime observations, counterfactual worlds, and selected project manifests; not a complete production/runtime or causal world model."}

    def world_health(self, agent_id: str | None = None) -> dict:
        """Aggregate bounded world/cognition health without pretending to prove program correctness."""
        self.reconcile()
        cognition=self.cognition_health(agent_id)
        pending=int(self.store.conn.execute("SELECT COUNT(*) FROM agent_notifications WHERE status='pending'").fetchone()[0])
        leases=int(self.store.conn.execute("SELECT COUNT(*) FROM resource_leases").fetchone()[0])
        active_evidence=int(self.store.conn.execute("SELECT COUNT(*) FROM evidence WHERE active=1").fetchone()[0])
        stale_worlds=0; failed_worlds=0; open_worlds=0
        for r in self.store.counterfactual_worlds(status='open',limit=500):
            open_worlds+=1
            d=self._counterfactual_row(r); meta=d.get('metadata') or {}; gen=int(meta.get('overlay_generation') or 0); verified=meta.get('verified_generation')
            vstatus=meta.get('verification_status') or 'never'
            if vstatus=='stale' or (verified is not None and (int(verified)!=gen or d.get('base_revision')!=self.revision)):
                stale_worlds+=1
            if verified is not None and vstatus not in {'passed','stale'}:
                failed_worlds+=1
        unverified=int(self.store.conn.execute("SELECT COUNT(*) FROM project_invariants i WHERE i.status!='retired' AND lower(i.severity) IN ('error','critical') AND NOT EXISTS (SELECT 1 FROM invariant_links l WHERE l.invariant_id=i.id AND l.relation='verifier')").fetchone()[0])
        active_trajectories=[self._executive_row(r) for r in self.store.executive_trajectories(status='active',agent_id=agent_id,limit=100)]
        invalid_trajectory_chains=0; invalid_phase_sequences=0; exhausted_trajectory_budgets=0; strategy_thrash=0
        for tr in active_trajectories:
            events=[self._executive_event_row(x) for x in self.store.executive_events(tr['id'])]
            if not verify_event_chain(events)['valid']: invalid_trajectory_chains+=1
            if not verify_phase_sequence(events)['valid']: invalid_phase_sequences+=1
            if self._executive_budget_state(tr)['exhausted']: exhausted_trajectory_budgets+=1
            metrics=tr.get('metrics') or {}; steps=max(1,int(metrics.get('steps',0))); switches=int(metrics.get('strategy_switches',0))
            if switches>=3 and switches/steps>=0.4: strategy_thrash+=1
        blockers=[]
        if pending: blockers.append({'kind':'pending-agent-invalidation','count':pending})
        if stale_worlds: blockers.append({'kind':'stale-counterfactual-verification','count':stale_worlds})
        if failed_worlds: blockers.append({'kind':'failed-counterfactual-verification','count':failed_worlds})
        if unverified: blockers.append({'kind':'critical-invariant-without-verifier','count':unverified})
        if cognition['loop']['risk'] in {'medium','high'}: blockers.append({'kind':'cognitive-loop-risk','risk':cognition['loop']['risk']})
        if cognition['epistemic_pressure']['level'] in {'high','critical'}: blockers.append({'kind':'epistemic-pressure','level':cognition['epistemic_pressure']['level'],'score':cognition['epistemic_pressure']['score']})
        if cognition['context']['refetch_ratio']>=0.35: blockers.append({'kind':'context-thrash','ratio':cognition['context']['refetch_ratio']})
        if invalid_trajectory_chains: blockers.append({'kind':'executive-trajectory-chain-invalid','count':invalid_trajectory_chains})
        if invalid_phase_sequences: blockers.append({'kind':'executive-phase-sequence-invalid','count':invalid_phase_sequences})
        if exhausted_trajectory_budgets: blockers.append({'kind':'executive-budget-exhausted','count':exhausted_trajectory_budgets})
        if strategy_thrash: blockers.append({'kind':'executive-strategy-thrash','count':strategy_thrash})
        status='critical' if any(b.get('kind') in {'pending-agent-invalidation','cognitive-loop-risk','executive-trajectory-chain-invalid','executive-phase-sequence-invalid'} and (b.get('risk')=='high' or b.get('count',0)>0) for b in blockers) else 'degraded' if blockers else 'healthy'
        return {'revision':self.revision,'agent_id':agent_id,'status':status,'blockers':blockers,
                'coordination':{'pending_invalidations':pending,'active_leases':leases},
                'counterfactuals':{'open':open_worlds,'stale_verifications':stale_worlds,'failed_verifications':failed_worlds},
                'invariants':{'unverified_error_or_critical':unverified},'executive':{'active_trajectories':len(active_trajectories),'invalid_chains':invalid_trajectory_chains,'invalid_phase_sequences':invalid_phase_sequences,'budget_exhausted':exhausted_trajectory_budgets,'strategy_thrash':strategy_thrash},'active_evidence':active_evidence,'cognition':cognition,
                'claim_boundary':'Operational world-health aggregation from explicit Habitat state; not a proof that the program or agent plan is correct.'}

    # ---- alpha.12 project/effect/counterfactual cognition ----
    def project_world(self) -> dict:
        self.reconcile()
        value=build_project_world(Path(self.backend.source_authority.info.authoritative_root), self.store)
        value["revision"]=self.revision
        return value

    def effect_refresh(self, paths: list[str] | None = None) -> dict:
        self.reconcile()
        wanted=paths
        if wanted is None:
            wanted=[r["path"] for r in self.store.all_files()]
        result=compile_effects(self.source_root,self.store,self.revision,wanted)
        self._activity_safe("effect.refresh","effect",status="observed",summary=f"Effect Twin refreshed: {result['facts']} facts",data={"paths":result["paths_compiled"],"facts":result["facts"]})
        return result

    def effect_snapshot(self, *, path: str | None = None, symbol_id: str | None = None, kind: str | None = None, limit: int = 1000) -> dict:
        self.reconcile()
        count=int(self.store.conn.execute("SELECT COUNT(*) FROM effect_facts").fetchone()[0])
        if count==0 and self.store.all_files():
            compile_effects(self.source_root,self.store,self.revision,[r["path"] for r in self.store.all_files()])
        runtime=[dict(x) for x in self.store.runtime_events(limit=min(1000,limit))]
        return effect_snapshot(self.store,self.revision,path=path,symbol_id=symbol_id,kind=kind,limit=limit,runtime_events=runtime)

    def dataflow_refresh(self, paths: list[str] | None = None) -> dict:
        self.reconcile()
        wanted=paths if paths is not None else [r["path"] for r in self.store.all_files()]
        result=compile_dataflow(self.source_root,self.store,self.revision,wanted)
        self._activity_safe("dataflow.refresh","effect",status="observed",summary=f"Dataflow Twin refreshed: {result['facts']} facts",data={"paths":result["paths_compiled"],"facts":result["facts"]})
        return result

    def dataflow_snapshot(self, *, path: str | None = None, symbol_id: str | None = None, kind: str | None = None, source: str | None = None, target: str | None = None, limit: int = 1000) -> dict:
        self.reconcile()
        count=int(self.store.conn.execute("SELECT COUNT(*) FROM dataflow_facts").fetchone()[0])
        if count==0 and self.store.all_files():
            compile_dataflow(self.source_root,self.store,self.revision,[r["path"] for r in self.store.all_files()])
        runtime=[dict(x) for x in self.store.runtime_events(limit=min(1000,limit))]
        return dataflow_snapshot(self.store,self.revision,path=path,symbol_id=symbol_id,kind=kind,source=source,target=target,limit=limit,runtime_events=runtime)

    def runtime_topology(self, *, agent_id: str | None = None, limit: int = 500) -> dict:
        timeline=self.runtime_timeline(agent_id=agent_id,limit=limit)
        value=build_runtime_topology(timeline["events"],max_events=limit)
        value["revision"]=self.revision; value["agent_id"]=agent_id
        return value

    def cognition_plan(self, agent_id: str | None = None, episode_id: str | None = None, limit: int = 8) -> dict:
        """Rank explicit next cognitive operations by ordinal information value, decision sensitivity, and cost.

        This is environment-level metacognition. It never exposes or claims access to hidden model chain-of-thought.
        """
        if limit < 1 or limit > 30: raise ValueError("limit must be in [1,30]")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        epi=self.epistemic_state(agent_id,status="open",limit=300)
        hy=[dict(r) for r in self.store.hypotheses(episode_id=episode_id,status="active",limit=100)]
        pending=[] if agent_id is None else [dict(r) for r in self.store.agent_notifications(agent_id,"pending",100)]
        recent=[]
        for r in self.store.recent_activity(60,agent_id=agent_id):
            d=dict(r)
            try: d["data"]=json.loads(d.pop("data_json") or "{}")
            except Exception: d["data"]={}
            recent.append(d)
        loop_health=analyze_cognitive_loop(recent)
        active_evidence=len(self.store.active_evidence(limit=500)); runtime_count=len(self.store.runtime_events(agent_id=agent_id,limit=500))
        candidates=[]
        def add(op,reason,info,impact,cost,ref=None,gate=None):
            rank={"low":1,"medium":2,"high":3,"critical":4}
            score=rank[info]*3+rank[impact]*2-rank[cost]
            candidates.append({"operation":op,"reason":reason,"expected_information_gain":info,"decision_sensitivity":impact,"cost":cost,"score":score,"ref_id":ref,"gate":gate})
        for n in pending[:3]: add("selective-revalidate",f"Observed world changed at {n.get('resource_id')}; current plan may be stale.","high","critical","low",n.get("id"),"must-resolve-before-consequential-commit")
        for x in [i for i in epi["items"] if i["kind"]=="contradiction"][:3]: add("discriminate-contradiction",x["statement"],"high","critical","medium",x["id"])
        experiments=[]
        for h in hy:
            experiments.extend(dict(x) for x in self.store.experiments_for_hypothesis(h["id"],50) if x["status"] in {"planned","running"})
        if len(hy)>=2 and not experiments: add("plan-discriminating-experiment","Multiple live hypotheses remain without an active discriminator.","high","high","medium",hy[0]["id"])
        for x in [i for i in epi["items"] if i["kind"]=="unknown"][:3]: add("probe-unknown",x["statement"],"medium","high","medium",x["id"])
        for x in [i for i in epi["items"] if i["kind"]=="assumption"][:2]: add("verify-assumption",x["statement"],"medium","medium","low",x["id"])
        if hy and active_evidence==0: add("acquire-independent-evidence","Live hypotheses have no active admitted evidence.","high","high","medium",hy[0]["id"])
        if hy and runtime_count==0: add("observe-runtime","Static hypotheses exist without observed runtime evidence.","medium","high","high",hy[0]["id"])
        if not hy and episode_id: add("form-rival-hypotheses","Active episode has no explicit rival hypothesis portfolio.","medium","high","low",episode_id)
        if loop_health.get("risk") in {"medium","high"}: add("break-cognitive-loop",f"Visible Habitat operations repeat without admitted progress (risk={loop_health['risk']}, streak={loop_health['no_progress_streak']}).","high","high","low",loop_health.get("dominant",{}).get("ref_id"),"broaden-or-discriminate-before-repeating")
        if not candidates: add("bounded-explore-or-act","No explicit epistemic blocker dominates; continue bounded exploration/action and verify consequences.","low","medium","low",episode_id)
        candidates=sorted(candidates,key=lambda x:(-x["score"],x["operation"]))[:limit]
        debt=sum(3 for x in epi["items"] if x["kind"]=="contradiction")+sum(2 for x in epi["items"] if x["kind"]=="unknown")+sum(1 for x in epi["items"] if x["kind"]=="assumption")+len(pending)*3
        invrows=[]
        for inv in self.store.conn.execute("SELECT i.*, (SELECT COUNT(*) FROM invariant_links l WHERE l.invariant_id=i.id AND l.relation='verifier') AS verifier_count FROM project_invariants i WHERE i.status!='retired'").fetchall(): invrows.append(dict(inv))
        pressure=epistemic_pressure(epi["items"],pending,invrows)
        return {"revision":self.revision,"agent_id":agent_id,"episode_id":episode_id,"operations":candidates,"next":candidates[0],
                "epistemic_debt":{"score":debt,"open_items":len(epi["items"]),"pending_invalidations":len(pending)},"epistemic_pressure":pressure,"cognitive_loop":loop_health,
                "stop_policy":{"can_converge":not any(x["operation"] in {"selective-revalidate","discriminate-contradiction"} for x in candidates),
                               "rule":"Converge only when critical contradictions/stale cognition are cleared and the remaining next operation has low expected decision value relative to cost."},
                "claim_boundary":"Ordinal value-of-information scheduling over explicit Habitat state; not calibrated expected utility and not hidden chain-of-thought."}

    def cognition_health(self, agent_id: str | None = None) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        recent=[]
        for r in self.store.recent_activity(80,agent_id=agent_id):
            d=dict(r)
            try: d["data"]=json.loads(d.pop("data_json") or "{}")
            except Exception: d["data"]={}
            recent.append(d)
        loop=analyze_cognitive_loop(recent)
        epi=self.epistemic_state(agent_id,status="open",limit=400)
        pending=[] if agent_id is None else [dict(r) for r in self.store.agent_notifications(agent_id,"pending",200)]
        invrows=[dict(r) for r in self.store.conn.execute("SELECT i.*, (SELECT COUNT(*) FROM invariant_links l WHERE l.invariant_id=i.id AND l.relation='verifier') AS verifier_count FROM project_invariants i WHERE i.status!='retired'").fetchall()]
        pressure=epistemic_pressure(epi["items"],pending,invrows)
        fault=self.store.conn.execute("SELECT COUNT(*),COUNT(DISTINCT handle||':'||page_id),COALESCE(SUM(source_bytes),0),COALESCE(SUM(authority_bytes_read),0) FROM context_faults").fetchone()
        faults,unique_pages,visible,authority=(int(fault[0] or 0),int(fault[1] or 0),int(fault[2] or 0),int(fault[3] or 0))
        repeats=max(0,faults-unique_pages)
        echo_count=sum(1 for e in recent if e.get("kind")=="memory.echo-suppressed")
        return {"revision":self.revision,"agent_id":agent_id,"loop":loop,"epistemic_pressure":pressure,
                "context":{"faults":faults,"unique_pages":unique_pages,"duplicate_faults":repeats,"refetch_ratio":round(repeats/max(1,faults),4),
                           "agent_visible_source_bytes":visible,"backend_authority_bytes_read":authority,"io_amplification":round(authority/max(1,visible),4) if visible else None},
                "memory_echoes_suppressed_recently":echo_count,
                "status":"degraded" if loop.get("risk") in {"medium","high"} or pressure.get("level") in {"high","critical"} else "healthy",
                "claim_boundary":"Operational/cognitive health from explicit Habitat telemetry; does not inspect private model reasoning."}

    # ---- alpha.14 trajectory-bound executive control ----
    @staticmethod
    def _executive_row(row) -> dict:
        d=dict(row)
        for src,dst,default in (("budget_json","budget",{}),("metrics_json","metrics",{}),("outcome_json","outcome",{})):
            try: d[dst]=json.loads(d.pop(src) or json.dumps(default))
            except Exception: d[dst]=default; d.pop(src,None)
        return d

    @staticmethod
    def _executive_milestone_row(row) -> dict:
        d=dict(row)
        for src,dst,default in (("dependencies_json","dependencies",[]),("result_json","result",{})):
            try: d[dst]=json.loads(d.pop(src) or json.dumps(default))
            except Exception: d[dst]=default; d.pop(src,None)
        return d

    @staticmethod
    def _executive_event_row(row) -> dict:
        d=dict(row)
        try: d["data"]=json.loads(d.pop("data_json") or "{}")
        except Exception: d["data"]={}; d.pop("data_json",None)
        return d

    def _require_active_trajectory(self, trajectory_id: str) -> dict:
        row=self.store.executive_trajectory(trajectory_id)
        if not row: raise KeyError(trajectory_id)
        d=self._executive_row(row)
        if d.get("status")!="active": raise ValueError(f"executive trajectory is not active: {d.get('status')}")
        return d

    @staticmethod
    def _executive_budget_state(tr: dict) -> dict:
        budget=dict(tr.get("budget") or {}); metrics=dict(tr.get("metrics") or {})
        consumed={
            "steps":int(metrics.get("steps",0)),
            "failed_steps":int(metrics.get("failed_steps",0)),
            "strategy_switches":int(metrics.get("strategy_switches",0)),
        }
        limits={k:budget.get(k) for k in ("max_steps","max_failed_steps","max_strategy_switches") if budget.get(k) is not None}
        reasons=[]
        max_steps=limits.get("max_steps")
        if max_steps is not None and consumed["steps"]>=int(max_steps): reasons.append("STEP_BUDGET_EXHAUSTED")
        max_failed=limits.get("max_failed_steps")
        if max_failed is not None:
            lim=int(max_failed); used=consumed["failed_steps"]
            if (lim==0 and used>0) or (lim>0 and used>=lim): reasons.append("FAILURE_BUDGET_EXHAUSTED")
        max_switch=limits.get("max_strategy_switches")
        switch_exhausted=False
        if max_switch is not None:
            switch_exhausted=consumed["strategy_switches"]>=int(max_switch)
            if switch_exhausted and int(metrics.get("consecutive_failures",0))>0:
                reasons.append("STRATEGY_SWITCH_BUDGET_EXHAUSTED")
        unmetered={k:v for k,v in budget.items() if k not in {"max_steps","max_failed_steps","max_strategy_switches"}}
        return {"limits":limits,"consumed":consumed,"exhausted":bool(reasons),"reasons":list(dict.fromkeys(reasons)),
                "strategy_switch_exhausted":switch_exhausted,"unmetered":unmetered,
                "claim_boundary":"Hard enforcement currently meters executive steps, failed steps and strategy switches. Additional declared budget fields are preserved but not represented as measured consumption."}

    def executive_start(self, goal: str, *, agent_id: str | None = None, episode_id: str | None = None,
                        budget: dict | None = None, initial_strategy: str = "direct-analysis") -> dict:
        if not isinstance(goal,str) or not goal.strip(): raise ValueError("goal must be a non-empty string")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if episode_id is not None: self._require_active_episode(episode_id)
        if budget is not None and not isinstance(budget,dict): raise TypeError("budget must be an object")
        normalized_budget=dict(budget or {})
        for key,minimum in (("max_steps",1),("max_failed_steps",0),("max_strategy_switches",0)):
            if key not in normalized_budget: continue
            value=normalized_budget[key]
            if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
                raise ValueError(f"{key} must be an integer >= {minimum}")
        if initial_strategy not in STRATEGY_FAMILIES: raise ValueError("unsupported executive strategy")
        self.reconcile(); now=utc_now()
        tid=stable_id("trajectory",self.revision,goal.strip(),agent_id or "shared",episode_id or "none",str(time.time_ns()))
        value={"id":tid,"goal":goal.strip(),"agent_id":agent_id,"episode_id":episode_id,"status":"active",
               "base_revision":self.revision,"current_strategy":initial_strategy,"strategy_generation":0,
               "budget":normalized_budget,"metrics":{"steps":0,"failed_steps":0,"consecutive_failures":0,"progress_events":0,"strategy_switches":0},
               "created_at":now,"updated_at":now,"outcome":{}}
        self.store.create_executive_trajectory(value)
        self.store.append_executive_event({"trajectory_id":tid,"phase":"OBSERVE","operation":"trajectory-start","status":"passed",
                                           "revision":self.revision,"ref_id":episode_id,"data":{"goal":goal.strip(),"strategy":initial_strategy,"budget":normalized_budget,"control_step":True},"created_at":now})
        if episode_id:
            self.store.append_episode_link(episode_id,"executive-trajectory",tid,self.revision,{"goal":goal.strip()},now)
            self._causal_edge("episode",episode_id,"governed_by","trajectory",tid,{"goal":goal.strip()})
        self._activity_safe("executive.started","cognition",agent_id=agent_id,episode_id=episode_id,ref_id=tid,status="active",
                            summary=f"executive trajectory: {goal.strip()[:120]}",data={"strategy":initial_strategy})
        return self.executive_status(tid)

    def executive_milestone_add(self, trajectory_id: str, title: str, postcondition: str, *, priority: str = "high",
                                dependencies: list[str] | None = None, verifier_ref: str | None = None,
                                rollback: str | None = None) -> dict:
        tr=self._require_active_trajectory(trajectory_id)
        if not isinstance(title,str) or not title.strip(): raise ValueError("milestone title must be non-empty")
        if not isinstance(postcondition,str) or not postcondition.strip(): raise ValueError("milestone postcondition must be non-empty")
        if priority not in {"low","medium","high","critical"}: raise ValueError("invalid milestone priority")
        if dependencies is not None and (not isinstance(dependencies,list) or not all(isinstance(x,str) and x for x in dependencies)):
            raise TypeError("dependencies must be a list of milestone ids")
        existing={r["id"] for r in self.store.executive_milestones(trajectory_id)}
        for dep in dependencies or []:
            if dep not in existing: raise KeyError(dep)
        now=utc_now(); mid=stable_id("milestone",trajectory_id,title.strip(),str(time.time_ns()))
        value={"id":mid,"trajectory_id":trajectory_id,"title":title.strip(),"postcondition":postcondition.strip(),"status":"pending",
               "priority":priority,"dependencies":list(dict.fromkeys(dependencies or [])),"verifier_ref":verifier_ref,"rollback":rollback,
               "base_revision":self.revision,"result":{},"created_at":now,"updated_at":now}
        self.store.create_executive_milestone(value)
        self.store.append_executive_event({"trajectory_id":trajectory_id,"phase":"COMPOSE","operation":"milestone-added","status":"passed",
                                           "revision":self.revision,"ref_id":mid,"data":{"title":title.strip(),"postcondition":postcondition.strip(),"priority":priority,"dependencies":value["dependencies"]},"created_at":now})
        self._activity_safe("executive.milestone-added","cognition",agent_id=tr.get("agent_id"),episode_id=tr.get("episode_id"),ref_id=mid,status="pending",
                            summary=f"milestone: {title.strip()[:120]}",data={"trajectory_id":trajectory_id,"priority":priority})
        return self._executive_milestone_row(self.store.executive_milestone(mid))

    def _executive_verifier_artifact(self, ref_id: str | None) -> dict | None:
        if not ref_id: return None
        run=self.store.load_json("runs",ref_id)
        if run is not None:
            structured=run.get("structured") or {}; status=str(structured.get("status") or "").lower(); exit_code=run.get("exit_code")
            pass_states={"passed","pass","success","succeeded","completed","ok"}
            fail_states={"failed","fail","failure","error","errored","cancelled","canceled","timeout","timed_out"}
            if status in pass_states:
                passed=True
            elif status in fail_states:
                passed=False
            else:
                passed=exit_code==0
            return {"kind":"run","ref_id":ref_id,"passed":bool(passed),"status":status or ("passed" if exit_code==0 else "failed"),"revision":run.get("revision") or run.get("workspace_revision")}
        evidence=self.store.evidence_by_id(ref_id)
        if evidence is not None:
            return {"kind":"evidence","ref_id":ref_id,"passed":bool(evidence["active"]) and str(evidence["severity"]).lower() not in {"error","critical"},
                    "status":"active" if evidence["active"] else "inactive","revision":evidence["revision"]}
        experiment=self.store.experiment(ref_id)
        if experiment is not None:
            return {"kind":"experiment","ref_id":ref_id,"passed":experiment["status"]=="completed","status":experiment["status"],"revision":experiment["base_revision"]}
        return None

    def executive_milestone_update(self, trajectory_id: str, milestone_id: str, *, status: str,
                                   verifier_ref: str | None = None, result: dict | None = None) -> dict:
        tr=self._require_active_trajectory(trajectory_id)
        row=self.store.executive_milestone(milestone_id)
        if not row or row["trajectory_id"]!=trajectory_id: raise KeyError(milestone_id)
        if status not in {"pending","in_progress","passed","failed","skipped"}: raise ValueError("invalid milestone status")
        if result is not None and not isinstance(result,dict): raise TypeError("result must be an object")
        m=self._executive_milestone_row(row)
        if status in {"in_progress","passed"}:
            states={x["id"]:x["status"] for x in map(self._executive_milestone_row,self.store.executive_milestones(trajectory_id))}
            blocked=[d for d in m.get("dependencies",[]) if states.get(d)!="passed"]
            if blocked: raise ValueError(f"milestone dependencies not passed: {blocked[0]}")
        effective_verifier=verifier_ref if verifier_ref is not None else m.get("verifier_ref")
        if status=="passed" and m.get("priority") in {"high","critical"}:
            artifact=self._executive_verifier_artifact(effective_verifier)
            if artifact is None: raise ValueError("high/critical milestone cannot pass without a known verifier artifact")
            if not artifact.get("passed"): raise ValueError("high/critical milestone verifier artifact is not successful")
            if artifact.get("revision") is not None and str(artifact["revision"]) != str(self.revision):
                raise ValueError("high/critical milestone verifier artifact is stale for the current workspace revision")
        now=utc_now(); self.store.update_executive_milestone(milestone_id,status=status,verifier_ref=verifier_ref,result=result,updated_at=now)
        phase="VERIFY" if status in {"passed","failed"} else "DISPATCH"
        self.store.append_executive_event({"trajectory_id":trajectory_id,"phase":phase,"operation":"milestone-status","status":"passed" if status=="passed" else "failed" if status=="failed" else "running",
                                           "revision":self.revision,"ref_id":effective_verifier or milestone_id,"data":{"milestone_id":milestone_id,"milestone_status":status,"result":result or {}},"created_at":now})
        self._activity_safe("executive.milestone-updated","cognition",agent_id=tr.get("agent_id"),episode_id=tr.get("episode_id"),ref_id=milestone_id,status=status,
                            summary=f"milestone {status}: {m.get('title','')[:100]}",data={"trajectory_id":trajectory_id,"verifier_ref":effective_verifier})
        return self._executive_milestone_row(self.store.executive_milestone(milestone_id))

    def _executive_completion_gate(self, trajectory_id: str) -> dict:
        tr=self._executive_row(self.store.executive_trajectory(trajectory_id))
        milestones=[self._executive_milestone_row(x) for x in self.store.executive_milestones(trajectory_id)]
        events=[self._executive_event_row(x) for x in self.store.executive_events(trajectory_id)]
        chain=verify_event_chain(events)
        phase_sequence=verify_phase_sequence(events)
        topology=milestone_topology(milestones)
        blockers=[]
        if not chain["valid"]: blockers.append({"code":"TRAJECTORY_CHAIN_INVALID","details":chain.get("failure")})
        if not phase_sequence["valid"]: blockers.append({"code":"EXECUTIVE_PHASE_SEQUENCE_INVALID","details":phase_sequence.get("failure")})
        if not topology["acyclic"]: blockers.append({"code":"GOAL_DEPENDENCY_CYCLE","cycle":topology.get("cycle")})
        for x in topology.get("missing_dependencies") or []: blockers.append({"code":"MILESTONE_DEPENDENCY_MISSING",**x})
        for m in milestones:
            if m.get("priority") in {"high","critical"} and m.get("status")!="passed":
                blockers.append({"code":"MILESTONE_POSTCONDITION_UNSATISFIED","milestone_id":m["id"],"status":m.get("status")})
            if m.get("status")=="passed" and m.get("priority") in {"high","critical"}:
                artifact=self._executive_verifier_artifact(m.get("verifier_ref"))
                if artifact is None: blockers.append({"code":"MILESTONE_VERIFIER_MISSING","milestone_id":m["id"]})
                elif not artifact.get("passed"): blockers.append({"code":"MILESTONE_VERIFIER_FAILED","milestone_id":m["id"],"verifier_ref":m.get("verifier_ref")})
        agent_id=tr.get("agent_id")
        pending=[] if agent_id is None else [dict(r) for r in self.store.agent_notifications(agent_id,"pending",200)]
        if pending: blockers.append({"code":"STALE_AGENT_OBSERVATION","count":len(pending),"notification_id":pending[0].get("id")})
        epi=self.epistemic_state(agent_id,status="open",limit=500)
        contradictions=[x for x in epi["items"] if x.get("kind")=="contradiction"]
        if contradictions: blockers.append({"code":"UNRESOLVED_CONTRADICTION","count":len(contradictions),"item_id":contradictions[0].get("id")})
        unverified=int(self.store.conn.execute("SELECT COUNT(*) FROM project_invariants i WHERE i.status!='retired' AND lower(i.severity) IN ('error','critical') AND NOT EXISTS (SELECT 1 FROM invariant_links l WHERE l.invariant_id=i.id AND l.relation='verifier')").fetchone()[0])
        if unverified: blockers.append({"code":"CRITICAL_INVARIANT_VERIFIER_MISSING","count":unverified})
        verify_events=[e for e in events if e.get("phase")=="VERIFY" and e.get("status")=="passed" and (e.get("data") or {}).get("control_step") is True]
        if not verify_events:
            blockers.append({"code":"VERIFICATION_EVENT_MISSING"})
        elif verify_events[-1].get("revision")!=self.revision:
            blockers.append({"code":"VERIFICATION_STALE","verified_revision":verify_events[-1].get("revision"),"current_revision":self.revision})
        if verify_events and not phase_sequence.get("state",{}).get("close_allowed"):
            blockers.append({"code":"CONTROL_REFLECTION_REQUIRED","last_phase":phase_sequence.get("state",{}).get("last_phase"),"allowed":phase_sequence.get("state",{}).get("allowed",[])})
        return {"ready":not blockers,"blockers":blockers,"chain":chain,"phase_sequence":phase_sequence,"milestone_topology":topology,
                "verified_revision":verify_events[-1].get("revision") if verify_events else None,
                "current_revision":self.revision,
                "claim_boundary":"Completion gate validates explicit Habitat trajectory state, phase sequence, verifier linkage, revision freshness, coordination invalidations and contradictions; it does not prove universal program correctness."}

    def executive_status(self, trajectory_id: str) -> dict:
        row=self.store.executive_trajectory(trajectory_id)
        if not row: raise KeyError(trajectory_id)
        tr=self._executive_row(row)
        milestones=[self._executive_milestone_row(x) for x in self.store.executive_milestones(trajectory_id)]
        events=[self._executive_event_row(x) for x in self.store.executive_events(trajectory_id)]
        gate=self._executive_completion_gate(trajectory_id)
        counts=Counter(x.get("status") for x in milestones)
        return {**tr,"current_revision":self.revision,"revision_drift":tr.get("base_revision")!=self.revision,
                "milestones":milestones,"milestone_counts":dict(counts),"events":events,"event_count":len(events),
                "trajectory_chain":gate["chain"],"phase_sequence":gate["phase_sequence"],"budget_state":self._executive_budget_state(tr),"completion_gate":gate,
                "claim_boundary":"Hash-chained observable executive work products and gates; no raw private chain-of-thought is captured or exposed."}

    def executive_plan(self, trajectory_id: str, *, limit: int = 8) -> dict:
        tr=self._require_active_trajectory(trajectory_id)
        if limit<1 or limit>30: raise ValueError("limit must be in [1,30]")
        status=self.executive_status(trajectory_id)
        milestones=status["milestones"]; states={m["id"]:m["status"] for m in milestones}
        ready=[]
        rank={"critical":4,"high":3,"medium":2,"low":1}
        for m in milestones:
            if m["status"] not in {"pending","in_progress","failed"}: continue
            blocked=[d for d in m.get("dependencies",[]) if states.get(d)!="passed"]
            if not blocked: ready.append({**m,"dependency_blockers":[]})
        ready.sort(key=lambda m:(-rank.get(m.get("priority"),0),0 if m.get("status")=="failed" else 1,m.get("created_at","")))
        cognition=self.cognition_plan(tr.get("agent_id"),tr.get("episode_id"),limit=limit)
        health=self.cognition_health(tr.get("agent_id"))
        failure=classify_strategy_failure(loop_risk=health["loop"].get("risk","none"),pending_invalidations=cognition["epistemic_debt"].get("pending_invalidations",0),
                                          contradictions=sum(1 for x in self.epistemic_state(tr.get("agent_id"),status="open",limit=300)["items"] if x.get("kind")=="contradiction"),
                                          unknowns=sum(1 for x in self.epistemic_state(tr.get("agent_id"),status="open",limit=300)["items"] if x.get("kind")=="unknown"),
                                          unverified_critical_invariants=health["epistemic_pressure"].get("unverified_critical_invariants",0),
                                          failed_steps=int(tr.get("metrics",{}).get("consecutive_failures",0)),
                                          verification_failures=sum(1 for e in status["events"] if e.get("phase")=="VERIFY" and e.get("status")=="failed"))
        recovery=structural_recovery_strategy(tr.get("current_strategy"),failure)
        budget_state=self._executive_budget_state(tr); control=status["phase_sequence"].get("state",{})
        if budget_state["exhausted"]:
            next_op={"operation":"stop-budget-exhausted","reasons":budget_state["reasons"],"allowed_terminal":"workspace.executive.stop"}
        elif ready:
            next_op={"operation":"advance-milestone","milestone_id":ready[0]["id"],"title":ready[0]["title"],"postcondition":ready[0]["postcondition"],"priority":ready[0]["priority"]}
        else:
            next_op=dict(cognition["next"])
        switch_recommended=bool(recovery.get("switch_required")) and not budget_state.get("strategy_switch_exhausted",False)
        return {"trajectory_id":trajectory_id,"revision":self.revision,"goal":tr["goal"],"strategy":{"current":tr["current_strategy"],"generation":tr["strategy_generation"],
                                                                                                        "diagnosis":recovery,"switch_recommended":switch_recommended},
                "control":{"last_phase":control.get("last_phase"),"last_status":control.get("last_status"),"allowed_next_phases":control.get("allowed",[]),"close_allowed":control.get("close_allowed",False)},
                "budget":budget_state,
                "hierarchy":{"ready_milestones":ready[:limit],"ready_count":len(ready),"total_milestones":len(milestones)},
                "cognition":cognition,"next":next_op,"completion_gate":status["completion_gate"],
                "claim_boundary":"Dependency-aware executive scheduling over explicit milestones and Habitat cognitive state; ordinal, not calibrated expected utility."}

    def executive_advance(self, trajectory_id: str, phase: str, operation: str, *, status: str = "passed",
                          progress: bool = False, ref_id: str | None = None, data: dict | None = None) -> dict:
        tr=self._require_active_trajectory(trajectory_id)
        phase=str(phase).upper()
        if phase not in EXECUTIVE_PHASES: raise ValueError("unsupported executive phase")
        if phase=="CLOSE": raise ValueError("use workspace.executive.complete for CLOSE")
        if not isinstance(operation,str) or not operation.strip(): raise ValueError("operation must be non-empty")
        if status not in {"running","passed","failed","inconclusive"}: raise ValueError("invalid executive step status")
        if data is not None and not isinstance(data,dict): raise TypeError("data must be an object")
        budget_before=self._executive_budget_state(tr)
        if budget_before["exhausted"]:
            raise RuntimeError(f"executive budget exhausted: {budget_before['reasons'][0]}")
        prior_events=[self._executive_event_row(x) for x in self.store.executive_events(trajectory_id)]
        sequence=verify_phase_sequence(prior_events)
        if not sequence["valid"]: raise RuntimeError("executive phase sequence is already invalid")
        allowed=sequence.get("state",{}).get("allowed",[])
        if phase not in allowed:
            raise ValueError(f"executive phase out of sequence: {phase}; allowed={','.join(allowed)}")
        if phase=="VERIFY" and status=="passed":
            artifact=self._executive_verifier_artifact(ref_id)
            if artifact is None: raise ValueError("passed VERIFY requires ref_id to a known receipt/evidence/experiment artifact")
            if not artifact.get("passed"): raise ValueError("VERIFY artifact does not indicate success")
            if artifact.get("revision") is not None and str(artifact["revision"]) != str(self.revision):
                raise ValueError("VERIFY artifact is stale for the current workspace revision")
        now=utc_now(); payload=dict(data or {})
        payload["progress_admitted"]=bool(progress); payload["control_step"]=True
        event=self.store.append_executive_event({"trajectory_id":trajectory_id,"phase":phase,"operation":operation.strip(),"status":status,
                                                 "revision":self.revision,"ref_id":ref_id,"data":payload,"created_at":now})
        metrics=dict(tr.get("metrics") or {}); metrics["steps"]=int(metrics.get("steps",0))+1
        if status in {"failed","inconclusive"}:
            metrics["failed_steps"]=int(metrics.get("failed_steps",0))+1; metrics["consecutive_failures"]=int(metrics.get("consecutive_failures",0))+1
        elif progress:
            metrics["progress_events"]=int(metrics.get("progress_events",0))+1; metrics["consecutive_failures"]=0
        else:
            metrics["consecutive_failures"]=int(metrics.get("consecutive_failures",0))
        self.store.update_executive_trajectory(trajectory_id,metrics=metrics,updated_at=now)
        switched=None
        if status in {"failed","inconclusive"} or int(metrics.get("consecutive_failures",0))>=2:
            health=self.cognition_health(tr.get("agent_id")); epi=self.epistemic_state(tr.get("agent_id"),status="open",limit=300)
            diagnosis=classify_strategy_failure(loop_risk=health["loop"].get("risk","none"),pending_invalidations=len([] if tr.get("agent_id") is None else self.store.agent_notifications(tr.get("agent_id"),"pending",200)),
                                                 contradictions=sum(1 for x in epi["items"] if x.get("kind")=="contradiction"),unknowns=sum(1 for x in epi["items"] if x.get("kind")=="unknown"),
                                                 unverified_critical_invariants=health["epistemic_pressure"].get("unverified_critical_invariants",0),failed_steps=int(metrics.get("consecutive_failures",0)),
                                                 verification_failures=1 if phase=="VERIFY" and status=="failed" else 0)
            recovery=structural_recovery_strategy(tr.get("current_strategy"),diagnosis)
            budget_after_failure=self._executive_budget_state({**tr,"metrics":metrics})
            if recovery.get("switch_required") and not budget_after_failure.get("strategy_switch_exhausted",False):
                target=recovery["target_strategy"]; generation=int(tr.get("strategy_generation",0))+1
                metrics["strategy_switches"]=int(metrics.get("strategy_switches",0))+1; metrics["consecutive_failures"]=0
                self.store.update_executive_trajectory(trajectory_id,current_strategy=target,strategy_generation=generation,metrics=metrics,updated_at=now)
                switched=self.store.append_executive_event({"trajectory_id":trajectory_id,"phase":"RECOVER","operation":"strategy-switch","status":"passed", "revision":self.revision,
                                                             "ref_id":event.get("record_hash"),"data":{"from":tr.get("current_strategy"),"to":target,"generation":generation,"failure_class":recovery["failure_class"],"reason":recovery["reason"],"control_step":True},"created_at":now})
        if status in {"failed","inconclusive"}:
            reason=str(payload.get("error") or payload.get("reason") or operation).strip()[:500]
            try:
                self.memory_record("failure",f"Executive failure [{phase}/{operation.strip()}]: {reason}",agent_id=tr.get("agent_id"),episode_id=tr.get("episode_id"),
                                   provenance={"trajectory_id":trajectory_id,"event_hash":event.get("record_hash"),"phase":phase,"operation":operation.strip(),"ref_id":ref_id},
                                   evidence_ids=[ref_id] if ref_id and self.store.evidence_by_id(ref_id) else [])
            except Exception:
                pass
        self._activity_safe("executive.step","cognition",agent_id=tr.get("agent_id"),episode_id=tr.get("episode_id"),ref_id=trajectory_id,status=status,
                            summary=f"{phase} {operation.strip()[:100]}: {status}",data={"progress":bool(progress),"strategy_switch":(switched or {}).get("data")})
        return {"event":event,"strategy_switch":switched,"trajectory":self.executive_status(trajectory_id)}

    def executive_complete(self, trajectory_id: str, *, outcome: dict | None = None) -> dict:
        tr=self._require_active_trajectory(trajectory_id)
        if outcome is not None and not isinstance(outcome,dict): raise TypeError("outcome must be an object")
        gate=self._executive_completion_gate(trajectory_id)
        if not gate["ready"]:
            first=gate["blockers"][0]["code"] if gate["blockers"] else "UNKNOWN"
            raise ValueError(f"executive completion gate blocked: {first}")
        now=utc_now(); event=self.store.append_executive_event({"trajectory_id":trajectory_id,"phase":"CLOSE","operation":"trajectory-complete","status":"passed",
                                                                 "revision":self.revision,"ref_id":gate.get("verified_revision"),"data":{"outcome":outcome or {},"control_step":True},"created_at":now})
        self.store.update_executive_trajectory(trajectory_id,status="completed",outcome=outcome or {},updated_at=now,closed_at=now)
        if tr.get("episode_id"):
            self.store.append_episode_link(tr["episode_id"],"executive-completed",trajectory_id,self.revision,{"event_hash":event.get("record_hash"),"outcome":outcome or {}},now)
        self._activity_safe("executive.completed","cognition",agent_id=tr.get("agent_id"),episode_id=tr.get("episode_id"),ref_id=trajectory_id,status="completed",
                            summary=f"executive trajectory completed: {tr.get('goal','')[:120]}",data={"event_hash":event.get("record_hash")})
        return self.executive_status(trajectory_id)

    def executive_stop(self, trajectory_id: str, *, status: str = "abandoned", reason: str, outcome: dict | None = None) -> dict:
        tr=self._require_active_trajectory(trajectory_id)
        if status not in {"failed","abandoned"}: raise ValueError("executive stop status must be failed or abandoned")
        if not isinstance(reason,str) or not reason.strip(): raise ValueError("executive stop reason must be non-empty")
        if outcome is not None and not isinstance(outcome,dict): raise TypeError("outcome must be an object")
        now=utc_now(); payload={"reason":reason.strip(),"outcome":outcome or {},"control_step":True,"forced_stop":True}
        event=self.store.append_executive_event({"trajectory_id":trajectory_id,"phase":"CLOSE","operation":"trajectory-stop","status":"failed" if status=="failed" else "inconclusive",
                                                 "revision":self.revision,"ref_id":None,"data":payload,"created_at":now})
        self.store.update_executive_trajectory(trajectory_id,status=status,outcome={"reason":reason.strip(),**(outcome or {})},updated_at=now,closed_at=now)
        if tr.get("episode_id"):
            self.store.append_episode_link(tr["episode_id"],"executive-stopped",trajectory_id,self.revision,{"event_hash":event.get("record_hash"),"status":status,"reason":reason.strip()},now)
        self._activity_safe("executive.stopped","cognition",agent_id=tr.get("agent_id"),episode_id=tr.get("episode_id"),ref_id=trajectory_id,status=status,
                            summary=f"executive trajectory {status}: {reason.strip()[:120]}",data={"event_hash":event.get("record_hash")})
        return self.executive_status(trajectory_id)

    @staticmethod
    def _counterfactual_row(row) -> dict:
        d=dict(row)
        try:d["metadata"]=json.loads(d.pop("metadata_json") or "{}")
        except Exception:d["metadata"]={};d.pop("metadata_json",None)
        return d

    def counterfactual_fork(self, label: str, *, agent_id: str | None = None, metadata: dict | None = None) -> dict:
        if not isinstance(label,str) or not label.strip(): raise ValueError("label must be non-empty")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        self.reconcile(); now=utc_now(); wid=stable_id("world",self.revision,label.strip(),agent_id or "shared",str(time.time_ns()))
        overlay=(self.habitat_dir/"counterfactuals"/wid.replace(":","_")).resolve(); overlay.mkdir(parents=True,exist_ok=False)
        cfmeta=dict(metadata or {}); cfmeta.setdefault("overlay_generation",0); cfmeta.setdefault("verification_status","never"); cfmeta.setdefault("verified_generation",None); cfmeta.setdefault("verification_fingerprint",None)
        value={"id":wid,"label":label.strip(),"owner_agent_id":agent_id,"base_revision":self.revision,"status":"open","overlay_root":str(overlay),"created_at":now,"updated_at":now,"metadata":cfmeta}
        self.store.create_counterfactual_world(value)
        self._activity_safe("world.forked","counterfactual",agent_id=agent_id,ref_id=wid,status="open",summary=f"counterfactual world: {label.strip()[:100]}")
        return {**value,"changes":[],"claim_boundary":"Patch-overlay counterfactual world; canonical source is unchanged."}

    def counterfactual_status(self, world_id: str) -> dict:
        row=self.store.counterfactual_world(world_id)
        if not row: raise KeyError(world_id)
        value=self._counterfactual_row(row); changes=[]
        for r in self.store.counterfactual_changes(world_id):
            d=dict(r)
            try:d["metadata"]=json.loads(d.pop("metadata_json") or "{}")
            except Exception:d["metadata"]={};d.pop("metadata_json",None)
            changes.append(d)
        value["changes"]=changes; value["revision_drift"]=value["base_revision"]!=self.revision
        meta=value.get("metadata") or {}; generation=int(meta.get("overlay_generation") or 0); verified=meta.get("verified_generation")
        value["overlay_generation"]=generation; value["verification_status"]=meta.get("verification_status") or "never"
        value["verification_fresh"]=bool(value["verification_status"] in {"passed","failed"} and verified is not None and int(verified)==generation and not value["revision_drift"])
        return value

    def counterfactual_apply(self, world_id: str, changes: list[dict]) -> dict:
        if not isinstance(changes,list) or not changes: raise ValueError("changes must be a non-empty list")
        world=self.counterfactual_status(world_id)
        if world["status"]!="open": raise ValueError("counterfactual world is not open")
        if world["base_revision"]!=self.revision: raise TransactionConflict("counterfactual world base revision is stale; re-fork before applying new assumptions")
        overlay=Path(world["overlay_root"]); admitted=[]
        for ch in changes:
            if not isinstance(ch,dict): raise TypeError("change must be an object")
            op=ch.get("op"); raw=ch.get("path")
            if not isinstance(raw,str) or not raw or raw.startswith("/") or ".." in Path(raw).parts: raise ValueError("invalid counterfactual path")
            rel=Path(raw).as_posix(); target=overlay/rel; target.parent.mkdir(parents=True,exist_ok=True)
            base_row=self.store.file_by_path(rel); base_digest=base_row["digest"] if base_row else None
            existing_change=next((x for x in world["changes"] if x["path"]==rel),None)
            if existing_change and existing_change["op"]!="delete" and target.is_file(): current=target.read_text(encoding="utf-8",errors="strict")
            else: current=self.read_source_bytes(rel).decode("utf-8",errors="strict") if base_row else ""
            meta={}
            if op=="replace_text":
                old=ch.get("old");new=ch.get("new")
                if not isinstance(old,str) or not isinstance(new,str) or old==new: raise ValueError("replace_text requires distinct string old/new")
                if current.count(old)!=1: raise TransactionConflict(f"counterfactual replace_text requires exactly one match in {rel}")
                result=current.replace(old,new,1);target.write_text(result,encoding="utf-8",newline="")
                meta={"old":old,"new":new}; overlay_digest=sha256_bytes(result.encode("utf-8")); size=len(result.encode("utf-8"))
            elif op=="create_file":
                if base_row or target.exists(): raise TransactionConflict(f"counterfactual create target already exists: {rel}")
                text=ch.get("text")
                if not isinstance(text,str): raise TypeError("create_file text must be string")
                target.write_text(text,encoding="utf-8",newline="");meta={"text":text};overlay_digest=sha256_bytes(text.encode());size=len(text.encode())
            elif op=="delete_file":
                if not base_row and not target.exists(): raise FileNotFoundError(rel)
                if target.exists(): target.unlink()
                meta={};overlay_digest=None;size=0;op="delete_file"
            else: raise ValueError("counterfactual op must be replace_text, create_file, or delete_file")
            rec={"world_id":world_id,"path":rel,"op":op,"base_digest":base_digest,"overlay_digest":overlay_digest,"byte_size":size,"metadata":meta,"created_at":utc_now()}
            self.store.upsert_counterfactual_change(rec); admitted.append(rec)
            self._activity_safe("world.patch","counterfactual",agent_id=world.get("owner_agent_id"),ref_id=world_id,path=rel,status="staged",summary=f"counterfactual {op}: {rel}")
        prior_meta=world.get("metadata") or {}; next_generation=int(prior_meta.get("overlay_generation") or 0)+1
        stale_status="stale" if prior_meta.get("verification_status") in {"passed","failed"} else prior_meta.get("verification_status","never")
        self.store.update_counterfactual_world(world_id,updated_at=utc_now(),metadata={"overlay_generation":next_generation,"verification_status":stale_status})
        return {"world":self.counterfactual_status(world_id),"applied":admitted,"canonical_changed":False}

    def counterfactual_evaluate(self, world_id: str) -> dict:
        world=self.counterfactual_status(world_id); overlay=Path(world["overlay_root"]); results=[]; diagnostics=[]
        for ch in world["changes"]:
            rel=ch["path"]
            if ch["op"]=="delete_file":
                results.append({"path":rel,"op":"delete_file","compilable":None,"symbols":0}); continue
            p=overlay/rel
            try:
                cf=compile_file(overlay,p)
                text=p.read_text(encoding="utf-8",errors="replace")
                syms=[to_dict(x) for x in cf.symbols]
                effects,effect_provider=analyze_effect_text(rel,text,syms,world["base_revision"],cf.file.language)
                flows,flow_provider=analyze_dataflow_text(rel,text,syms,world["base_revision"],cf.file.language)
                results.append({"path":rel,"op":ch["op"],"language":cf.file.language,"provider":cf.provider,"symbols":len(cf.symbols),"diagnostics":len(cf.diagnostics),"parse_complete":cf.file.parse_complete,
                                "effects":len(effects),"dataflows":len(flows),"effect_provider":effect_provider.get("provider"),"dataflow_provider":flow_provider.get("provider"),
                                "effect_kinds":dict(Counter(x["kind"] for x in effects)),"dataflow_kinds":dict(Counter(x["kind"] for x in flows))})
                diagnostics.extend({"path":d.path,"severity":d.severity,"message":d.message,"line":d.line,"source":d.source} for d in cf.diagnostics)
            except Exception as exc:
                results.append({"path":rel,"op":ch["op"],"error":f"{type(exc).__name__}: {exc}","parse_complete":False})
        return {"revision":self.revision,"world_id":world_id,"base_revision":world["base_revision"],"revision_drift":world["base_revision"]!=self.revision,
                "paths":results,"diagnostics":diagnostics,"canonical_changed":False,
                "claim_boundary":"Counterfactual compilation plus isolated Effect/Dataflow analysis validates changed overlay files at provider-local scope; it is not full-project runtime verification or causal proof."}

    def counterfactual_compare(self, world_ids: list[str]) -> dict:
        if not isinstance(world_ids,list) or len(world_ids)<2: raise ValueError("world_ids must contain at least two worlds")
        worlds=[self.counterfactual_status(w) for w in world_ids]
        evals=[self.counterfactual_evaluate(w) for w in world_ids]
        all_paths=sorted({c["path"] for w in worlds for c in w["changes"]})
        matrix=[]
        for p in all_paths:
            matrix.append({"path":p,"worlds":{w["id"]:next((c["overlay_digest"] for c in w["changes"] if c["path"]==p),None) for w in worlds}})
        return {"revision":self.revision,"worlds":[{"id":w["id"],"label":w["label"],"base_revision":w["base_revision"],"change_count":len(w["changes"])} for w in worlds],
                "path_matrix":matrix,"evaluations":evals,
                "claim_boundary":"Compares explicit patch overlays and local compile evidence; does not decide which alternative is behaviorally correct."}

    def counterfactual_verify(self, world_id: str, *, timeout_s: int = 60) -> dict:
        """Materialize one alternative world into an isolated temporary project copy and run Habitat verification there.

        The copy isolates canonical source bytes from test-side writes. Execution containment is inherited from the
        child/local provider and is reported honestly; this is not a hostile-code sandbox unless that provider says so.
        """
        if not isinstance(timeout_s,int) or isinstance(timeout_s,bool) or timeout_s<1 or timeout_s>900: raise ValueError("timeout_s must be in [1,900]")
        world=self.counterfactual_status(world_id)
        if world["status"]!="open": raise ValueError("counterfactual world must be open for verification")
        if world["base_revision"]!=self.revision: raise TransactionConflict("counterfactual world base revision is stale; re-fork before verification")
        run_root=(self.habitat_dir/"counterfactual-runs"/(world_id.replace(":","_")+"-"+str(time.time_ns()))).resolve()
        project=run_root/"project"; child_state=run_root/"habitat"; project.mkdir(parents=True,exist_ok=False)
        try:
            copied=0
            for src in iter_project_files(self.source_root):
                rel=src.relative_to(self.source_root); dst=project/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst); copied+=1
            overlay=Path(world["overlay_root"])
            changed=[]
            for ch in world["changes"]:
                rel=Path(ch["path"]); dst=project/rel
                if ch["op"]=="delete_file":
                    if dst.exists(): dst.unlink()
                else:
                    src=overlay/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
                changed.append(rel.as_posix())
            child=HabitatWorkspace.create(project,child_state)
            try:
                verification=child.verify(changed_paths=changed,timeout_s=timeout_s)
                security=child.execution_security()
            finally:
                child.close()
            status=(verification.get("receipt") or {}).get("structured",{}).get("status") or "unknown"
            generation=int((world.get("metadata") or {}).get("overlay_generation") or 0)
            fingerprint=stable_id("cf-verified",world["base_revision"],str(generation),json.dumps([(x["path"],x["op"],x.get("overlay_digest")) for x in world["changes"]],sort_keys=True))
            self.store.update_counterfactual_world(world_id,updated_at=utc_now(),metadata={"verification_status":status,"verified_generation":generation,"verification_fingerprint":fingerprint,"verification_revision":self.revision})
            result={"world_id":world_id,"base_revision":world["base_revision"],"canonical_revision":self.revision,"canonical_changed":False,
                    "overlay_generation":generation,"verification_fingerprint":fingerprint,"materialized_files":copied,"changed_paths":changed,"verification":verification,"status":status,"execution_security":security,
                    "claim_boundary":"Verification ran in a disposable source copy and is bound to one overlay generation. Filesystem isolation protects canonical project bytes, but hostile-code containment is only as strong as the reported execution provider."}
            self._activity_safe("world.verified","counterfactual",agent_id=world.get("owner_agent_id"),ref_id=world_id,status=status,summary=f"counterfactual verification {status}: {world['label']}",data={"changed_paths":changed,"sandboxed":bool(security.get("sandboxed")),"overlay_generation":generation})
            return result
        finally:
            shutil.rmtree(run_root,ignore_errors=True)

    def counterfactual_promote(self, world_id: str, *, agent_id: str | None = None, episode_id: str | None = None, approval_id: str | None = None) -> dict:
        world=self.counterfactual_status(world_id)
        if world["status"]!="open": raise ValueError("counterfactual world is not open")
        owner=agent_id or world.get("owner_agent_id")
        verified_generation=(world.get("metadata") or {}).get("verified_generation")
        if world.get("verification_status")=="stale" or (verified_generation is not None and not world.get("verification_fresh")):
            raise TransactionConflict("counterfactual verification is stale for the current overlay generation; re-verify before promotion")
        if verified_generation is not None and world.get("verification_status")!="passed":
            raise TransactionConflict(f"counterfactual verification did not pass (status={world.get('verification_status')}); promotion is blocked")
        ops=[]
        for c in world["changes"]:
            meta=c.get("metadata") or {}
            if c["op"]=="replace_text": ops.append({"op":"replace_text","path":c["path"],"old":meta["old"],"new":meta["new"]})
            elif c["op"]=="create_file": ops.append({"op":"create_file","path":c["path"],"text":meta.get("text","")})
            elif c["op"]=="delete_file": ops.append({"op":"delete_file","path":c["path"]})
        if not ops: raise ValueError("counterfactual world has no changes")
        tx=self.stage_change(ops,episode_id=episode_id,agent_id=owner,approval_id=approval_id)
        committed=self.commit_change(tx["id"],owner)
        self.store.update_counterfactual_world(world_id,status="promoted",updated_at=utc_now(),metadata={"transaction_id":tx["id"],"promoted_revision":self.revision})
        self._activity_safe("world.promoted","counterfactual",agent_id=owner,episode_id=episode_id,ref_id=world_id,status="committed",summary=f"counterfactual promoted: {world['label']}",data={"transaction_id":tx["id"]})
        return {"world":self.counterfactual_status(world_id),"transaction":tx,"commit":committed}

    def counterfactual_discard(self, world_id: str) -> dict:
        world=self.counterfactual_status(world_id)
        if world["status"]=="promoted": raise ValueError("promoted counterfactual world cannot be discarded")
        try: shutil.rmtree(world["overlay_root"],ignore_errors=True)
        finally: self.store.update_counterfactual_world(world_id,status="discarded",updated_at=utc_now())
        self._activity_safe("world.discarded","counterfactual",agent_id=world.get("owner_agent_id"),ref_id=world_id,status="discarded",summary=f"counterfactual discarded: {world['label']}")
        return self.counterfactual_status(world_id)

    # ---- alpha.11 realtime activity / epistemic runtime / observatory ----
    def activity_emit(self, kind: str, category: str = "workspace", *, agent_id: str | None = None,
                      episode_id: str | None = None, ref_id: str | None = None, path: str | None = None,
                      status: str = "info", summary: str | None = None, data: dict | None = None) -> dict:
        if not isinstance(kind,str) or not kind.strip(): raise ValueError("activity kind must be non-empty")
        if not isinstance(category,str) or not category.strip(): raise ValueError("activity category must be non-empty")
        value={"kind":kind.strip(),"category":category.strip(),"agent_id":agent_id,"episode_id":episode_id,"ref_id":ref_id,
               "path":path,"revision":self.revision,"status":status,"summary":summary or kind,"data":data or {},"created_at":utc_now()}
        seq=self.store.append_activity(value); value["seq"]=seq
        return value

    def _activity_safe(self, kind: str, category: str = "workspace", **kwargs) -> dict | None:
        """Best-effort observability: telemetry must never become operation authority."""
        try:
            return self.activity_emit(kind, category, **kwargs)
        except Exception:
            return None

    def activity_since(self, since_seq: int = 0, limit: int = 500) -> dict:
        if since_seq < 0: raise ValueError("since_seq must be >= 0")
        if limit < 1 or limit > 2000: raise ValueError("limit must be in [1,2000]")
        out=[]
        for row in self.store.activity_since(since_seq,limit):
            d=dict(row)
            try: d["data"]=json.loads(d.pop("data_json") or "{}")
            except Exception: d["data"]={}; d.pop("data_json",None)
            out.append(d)
        oldest,latest=self.store.activity_bounds()
        last_returned=int(out[-1]["seq"]) if out else since_seq
        return {"revision":self.revision,"since_seq":since_seq,"oldest_seq":oldest,"latest_seq":latest,"last_returned_seq":last_returned,
                "gap_detected":bool(oldest and since_seq and since_seq < oldest-1),"has_more":bool(last_returned < latest),"events":out}

    def epistemic_create(self, kind: str, statement: str, *, status: str = "open", confidence: float | None = None,
                         scope: str = "workspace", agent_id: str | None = None, episode_id: str | None = None,
                         provenance: dict | None = None, invalidation_conditions: list | None = None) -> dict:
        allowed={"fact","assumption","unknown","contradiction","constraint","prediction"}
        if kind not in allowed: raise ValueError("unsupported epistemic kind")
        if not isinstance(statement,str) or not statement.strip(): raise ValueError("statement must be non-empty")
        if confidence is not None and (not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not 0<=float(confidence)<=1):
            raise ValueError("confidence must be in [0,1]")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if episode_id is not None: self._require_active_episode(episode_id)
        now=utc_now(); item_id=stable_id("epistemic",kind,statement.strip(),agent_id or "shared",str(time.time_ns()))
        value={"id":item_id,"kind":kind,"statement":statement.strip(),"status":status,"confidence":None if confidence is None else float(confidence),
               "scope":scope,"agent_id":agent_id,"episode_id":episode_id,"base_revision":self.revision,"provenance":provenance or {},
               "invalidation_conditions":invalidation_conditions or [],"created_at":now,"updated_at":now}
        self.store.create_epistemic_item(value)
        self.activity_emit("epistemic.created","cognition",agent_id=agent_id,episode_id=episode_id,ref_id=item_id,
                           status=status,summary=f"{kind}: {statement.strip()[:120]}",data={"kind":kind})
        return value

    @staticmethod
    def _epistemic_row(row) -> dict:
        d=dict(row)
        for src,dst,default in (("provenance_json","provenance",{}),("invalidation_json","invalidation_conditions",[])):
            try: d[dst]=json.loads(d.pop(src) or json.dumps(default))
            except Exception: d[dst]=default; d.pop(src,None)
        return d

    def epistemic_state(self, agent_id: str | None = None, status: str | None = "open", limit: int = 200) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        rows=[self._epistemic_row(r) for r in self.store.epistemic_items(status=status,agent_id=agent_id,limit=limit)]
        for r in rows: r["stale"] = r.get("base_revision") != self.revision
        counts=Counter(r["kind"] for r in rows)
        stale=sum(1 for r in rows if r.get("stale"))
        return {"revision":self.revision,"agent_id":agent_id,"items":rows,"counts":dict(counts),"stale_items":stale,
                "claim_boundary":"Epistemic items are explicit environment records. Assumptions, predictions and confidence annotations are not promoted to verified facts."}

    def epistemic_update(self, item_id: str, *, status: str | None = None, confidence: float | None = None, provenance: dict | None = None) -> dict:
        if confidence is not None and (not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not 0<=float(confidence)<=1):
            raise ValueError("confidence must be in [0,1]")
        self.store.update_epistemic_item(item_id,status=status,confidence=None if confidence is None else float(confidence),updated_at=utc_now(),provenance=provenance)
        row=self.store.epistemic_item(item_id)
        if not row: raise KeyError(item_id)
        value=self._epistemic_row(row)
        self.activity_emit("epistemic.updated","cognition",agent_id=value.get("agent_id"),episode_id=value.get("episode_id"),ref_id=item_id,
                           status=value.get("status") or "open",summary=f"{value.get('kind')}: {value.get('statement','')[:120]}")
        return value

    @staticmethod
    def _memory_row(row) -> dict:
        d=dict(row)
        for src,dst,default in (("provenance_json","provenance",{}),("evidence_json","evidence_ids",[])):
            try: d[dst]=json.loads(d.pop(src) or json.dumps(default))
            except Exception: d[dst]=default; d.pop(src,None)
        d["confidence_annotation"]=d.pop("confidence",None)
        return d

    def memory_record(self, kind: str, statement: str, *, agent_id: str | None = None, episode_id: str | None = None,
                      confidence: float | None = None, provenance: dict | None = None, evidence_ids: list[str] | None = None,
                      supersedes: str | None = None, valid_until_revision: str | None = None) -> dict:
        allowed={"semantic","episodic","procedural","failure","decision","experiment"}
        if kind not in allowed: raise ValueError("unsupported memory kind")
        if not isinstance(statement,str) or not statement.strip(): raise ValueError("memory statement must be non-empty")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if episode_id is not None: self._require_active_episode(episode_id)
        if confidence is not None and (not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not 0<=float(confidence)<=1): raise ValueError("confidence must be in [0,1]")
        ids=list(evidence_ids or [])
        for eid in ids:
            if not self.store.evidence_by_id(eid): raise KeyError(eid)
        if supersedes is not None and not self.store.project_memory(supersedes): raise KeyError(supersedes)
        # Exact same active memory in the same agent/revision is an echo, not new independent evidence.
        if supersedes is None:
            existing=self.store.find_active_memory(kind,statement.strip(),agent_id,self.revision)
            if existing is not None:
                value=self.memory_status(existing["id"]); value["deduplicated_echo"]=True
                self._activity_safe("memory.echo-suppressed","memory",agent_id=agent_id,episode_id=episode_id,ref_id=existing["id"],status="deduplicated",summary=f"memory echo suppressed: {statement.strip()[:120]}")
                return value
        now=utc_now(); mid=stable_id("memory",kind,statement.strip(),agent_id or "shared",str(time.time_ns()))
        value={"id":mid,"kind":kind,"statement":statement.strip(),"status":"active","scope":"agent" if agent_id else "workspace",
               "agent_id":agent_id,"episode_id":episode_id,"base_revision":self.revision,"confidence":None if confidence is None else float(confidence),
               "provenance":provenance or {},"evidence_ids":ids,"valid_until_revision":valid_until_revision,"supersedes":supersedes,"invalidated_by":None,
               "created_at":now,"updated_at":now}
        self.store.create_project_memory(value)
        if supersedes: self.store.update_project_memory(supersedes,status="superseded",invalidated_by=mid,updated_at=now)
        self._activity_safe("memory.recorded","memory",agent_id=agent_id,episode_id=episode_id,ref_id=mid,status="active",summary=f"{kind} memory: {statement.strip()[:120]}",data={"evidence_ids":ids,"supersedes":supersedes})
        return self.memory_status(mid)

    def memory_status(self, memory_id: str) -> dict:
        row=self.store.project_memory(memory_id)
        if not row: raise KeyError(memory_id)
        d=self._memory_row(row); d["current_revision"]=self.revision; d["revision_drift"]=d.get("base_revision")!=self.revision
        d["valid_now"]=d.get("status")=="active" and (not d.get("valid_until_revision") or d.get("valid_until_revision")==self.revision)
        d["claim_boundary"]="Project memory is provenance-bound remembered state, not canonical source truth. Revision drift and invalidation remain explicit."
        return d

    def memory_recall(self, query: str, *, agent_id: str | None = None, kinds: list[str] | None = None, limit: int = 20) -> dict:
        if not isinstance(query,str) or not query.strip(): raise ValueError("query must be non-empty")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if limit<1 or limit>200: raise ValueError("limit must be in [1,200]")
        allowed={"semantic","episodic","procedural","failure","decision","experiment"}
        if kinds is not None and (not isinstance(kinds,list) or not set(kinds)<=allowed): raise ValueError("invalid memory kinds")
        terms=set(ContextCompiler(self)._content_terms(query)); candidates=[]
        for row in self.store.project_memories(status="active",agent_id=None,limit=1000):
            d=self._memory_row(row)
            # Shared memory is visible to every agent. Agent-private memory is visible only to its owner.
            if d.get("agent_id") is not None and d.get("agent_id") != agent_id: continue
            if kinds and d["kind"] not in kinds: continue
            mt=set(ContextCompiler(self)._content_terms(d["statement"])); overlap=len(terms & mt); score=(overlap/max(1,len(terms))) if terms else 0.0
            if overlap or not terms: candidates.append((score,d))
        candidates.sort(key=lambda x:(-x[0],x[1]["updated_at"],x[1]["id"]))
        out=[]
        for score,d in candidates[:limit]:
            d["recall_score"]=round(score,4); d["revision_drift"]=d.get("base_revision")!=self.revision; out.append(d)
        return {"revision":self.revision,"agent_id":agent_id,"query":query,"memories":out,"count":len(out),
                "claim_boundary":"Lexical/identifier recall over provenance-bound project memory; recalled statements are not promoted to verified facts."}

    def memory_invalidate(self, memory_id: str, reason: str, *, invalidated_by: str | None = None) -> dict:
        if not isinstance(reason,str) or not reason.strip(): raise ValueError("reason must be non-empty")
        self.store.update_project_memory(memory_id,status="invalidated",invalidated_by=invalidated_by or reason.strip(),updated_at=utc_now())
        self._activity_safe("memory.invalidated","memory",ref_id=memory_id,status="invalidated",summary=f"memory invalidated: {reason.strip()[:120]}")
        return self.memory_status(memory_id)

    def cognition_probe_unknowns(self, agent_id: str | None = None, *, record: bool = False) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        probes=[]
        active_evidence=len(self.store.active_evidence(limit=500))
        runtime_count=len(self.store.runtime_events(agent_id=agent_id,limit=1))
        inv_count=self.store.conn.execute("SELECT COUNT(*) FROM project_invariants WHERE status!='retired'").fetchone()[0]
        hypotheses=len(self.store.hypotheses(status="active",limit=100))
        tests=sum(1 for f in self.store.all_files() if "test" in Path(f["path"]).name.casefold())
        if runtime_count==0: probes.append(("runtime-observation-gap","No runtime evidence has been observed for the current workspace/agent."))
        if inv_count==0: probes.append(("invariant-gap","No explicit project invariant is registered; important behavioral constraints may be implicit."))
        else:
            unverifiable=int(self.store.conn.execute("SELECT COUNT(*) FROM project_invariants i WHERE i.status!='retired' AND lower(i.severity) IN ('critical','error') AND NOT EXISTS (SELECT 1 FROM invariant_links l WHERE l.invariant_id=i.id AND l.relation='verifier')").fetchone()[0])
            if unverifiable: probes.append(("critical-invariant-verifier-gap",f"{unverifiable} high/critical project invariants have no linked verifier."))
        if hypotheses and active_evidence==0: probes.append(("hypothesis-oracle-gap","Active hypotheses exist without active evidence records."))
        if tests==0: probes.append(("verification-gap","No test-like source files are indexed; verification coverage may be weak or external."))
        unresolved=self.dependencies_snapshot().get("unlocked_direct") or []
        if unresolved: probes.append(("dependency-resolution-gap",f"{len(unresolved)} direct dependencies are not lock-resolved in the current dependency world."))
        world=self.epistemic_state(agent_id,status="open",limit=500)
        if world["stale_items"]: probes.append(("stale-epistemic-state",f"{world['stale_items']} epistemic records were created against an older revision."))
        created=[]
        if record:
            for code,statement in probes[:8]:
                created.append(self.epistemic_create("unknown",statement,agent_id=agent_id,provenance={"probe":code,"source":"unknown-unknown-audit"}))
        return {"revision":self.revision,"agent_id":agent_id,"probes":[{"code":c,"statement":v,"expected_information_gain":"medium"} for c,v in probes],
                "recorded":created,"stop_rule":"Stop when additional broad probes have low expected failure-reduction relative to their acquisition cost.",
                "claim_boundary":"Boundary audit for possible blind spots; not exhaustive unknown-unknown discovery."}

    def cognition_next(self, agent_id: str | None = None, episode_id: str | None = None) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        pending=[] if agent_id is None else [dict(r) for r in self.store.agent_notifications(agent_id,"pending",50)]
        epi=self.epistemic_state(agent_id,status="open",limit=200)
        contradictions=[x for x in epi["items"] if x["kind"]=="contradiction"]
        unknowns=[x for x in epi["items"] if x["kind"]=="unknown"]
        assumptions=[x for x in epi["items"] if x["kind"]=="assumption"]
        hy=[dict(r) for r in self.store.hypotheses(episode_id=episode_id,status="active",limit=50)]
        experiments=[]
        for h in hy:
            experiments.extend(dict(x) for x in self.store.experiments_for_hypothesis(h["id"],50) if x["status"] in {"planned","running"})
        if pending:
            action={"operation":"selective-revalidate","reason":"Agent read-set has pending invalidation notifications.","expected_information_gain":"high","cost":"low","ref_id":pending[0]["id"]}
        elif contradictions:
            action={"operation":"discriminate-contradiction","reason":contradictions[0]["statement"],"expected_information_gain":"high","cost":"medium","ref_id":contradictions[0]["id"]}
        elif len(hy)>=2 and not experiments:
            action={"operation":"plan-discriminating-experiment","reason":"Multiple live hypotheses remain without a planned discriminating experiment.","expected_information_gain":"high","cost":"medium","ref_id":hy[0]["id"]}
        elif unknowns:
            action={"operation":"probe-unknown","reason":unknowns[0]["statement"],"expected_information_gain":"medium","cost":"medium","ref_id":unknowns[0]["id"]}
        elif assumptions:
            action={"operation":"verify-assumption","reason":assumptions[0]["statement"],"expected_information_gain":"medium","cost":"low","ref_id":assumptions[0]["id"]}
        elif not hy and episode_id:
            action={"operation":"form-rival-hypotheses","reason":"Active work episode has no explicit live hypothesis portfolio.","expected_information_gain":"medium","cost":"low","ref_id":episode_id}
        else:
            action={"operation":"explore-or-act","reason":"No higher-priority epistemic blocker is recorded; continue with bounded exploration/action and verify consequences.","expected_information_gain":"low","cost":"low","ref_id":episode_id}
        debt=len(contradictions)*3+len(unknowns)*2+len(assumptions)+len(pending)*3
        return {"revision":self.revision,"agent_id":agent_id,"episode_id":episode_id,"next":action,
                "epistemic_debt":{"score":debt,"contradictions":len(contradictions),"unknowns":len(unknowns),"assumptions":len(assumptions),"pending_invalidations":len(pending)},
                "stop_policy":{"can_converge":not contradictions and not pending,"rule":"Do not converge while high-severity contradictions or known stale cognition remain unresolved."},
                "claim_boundary":"Metacognitive scheduling heuristic based on explicit Habitat state, not hidden model chain-of-thought or calibrated value-of-information probability."}

    def semantic_fabric(self) -> dict:
        return semantic_fabric_report(self.source_root)

    def runtime_ingest(self, signal: str, records: list[dict], *, agent_id: str | None = None, episode_id: str | None = None) -> dict:
        if signal not in {"opentelemetry","dap"}: raise ValueError("signal must be opentelemetry or dap")
        if not isinstance(records,list): raise TypeError("records must be a list")
        if len(records)>2000: raise ValueError("runtime ingestion batch exceeds 2000 records; split the batch so telemetry is never silently truncated")
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if episode_id is not None: self._require_active_episode(episode_id)
        root=Path(self.backend.source_authority.info.authoritative_root).resolve(); admitted=[]
        for raw in records:
            obs=normalize_otel_record(raw,self.revision,agent_id=agent_id,episode_id=episode_id) if signal=="opentelemetry" else normalize_dap_event(raw,self.revision,agent_id=agent_id,episode_id=episode_id)
            if obs.path:
                try:
                    pp=Path(obs.path)
                    if pp.is_absolute(): obs.path=pp.resolve().relative_to(root).as_posix()
                    else: obs.path=pp.as_posix()
                except Exception:
                    obs.path=None
            if obs.path and obs.line:
                fr=self.store.file_by_path(obs.path)
                if fr:
                    candidates=[r for r in self.store.symbols_for_file(fr["id"]) if int(r["start_line"])<=int(obs.line)<=int(r["end_line"])]
                    if candidates: obs.symbol_id=min(candidates,key=lambda r:int(r["end_line"])-int(r["start_line"]))["id"]
            store_value=event_to_store_dict(obs); existing=self.store.runtime_event(obs.id)
            if existing is not None:
                try: existing_attrs=json.loads(existing["attributes_json"] or "{}")
                except Exception: existing_attrs={}
                durable={"trace_id":obs.trace_id,"span_id":obs.span_id,"parent_span_id":obs.parent_span_id,"kind":obs.kind,"name":obs.name,"status":obs.status,
                         "path":obs.path,"symbol_id":obs.symbol_id,"agent_id":obs.agent_id,"episode_id":obs.episode_id,"revision":obs.revision,
                         "duration_ms":obs.duration_ms,"source":obs.source}
                same=all(existing[k]==v for k,v in durable.items()) and existing_attrs==obs.attributes
                stable_dap_replay=(obs.source=="dap" and obs.attributes.get("habitat.dap.replay_identity")=="session-seq-event")
                if same and not stable_dap_replay:
                    same=(existing["started_at"]==obs.started_at)
                if same:
                    continue
                raise TransactionConflict(f"runtime observation id collision with conflicting durable provenance: {obs.id}")
            self.store.append_runtime_event(store_value); value=obs.as_dict(); admitted.append(value)
            self.activity_emit("runtime.observed","runtime",agent_id=obs.agent_id,episode_id=obs.episode_id,ref_id=obs.symbol_id or obs.id,path=obs.path,
                               status=obs.status,summary=obs.name,data={"runtime_id":obs.id,"source":obs.source,"duration_ms":obs.duration_ms,"trace_id":obs.trace_id})
        return {"revision":self.revision,"signal":signal,"ingested":len(admitted),"events":admitted,
                "claim_boundary":"Observed runtime telemetry is distinct from static possibility. Ingestion preserves provenance but does not prove causal direction by itself."}

    def runtime_timeline(self, *, trace_id: str | None = None, agent_id: str | None = None, limit: int = 200) -> dict:
        rows=[]
        for r in self.store.runtime_events(trace_id=trace_id,agent_id=agent_id,limit=limit):
            d=dict(r)
            try: d["attributes"]=json.loads(d.pop("attributes_json") or "{}")
            except Exception: d["attributes"]={}; d.pop("attributes_json",None)
            rows.append(d)
        return {"revision":self.revision,"trace_id":trace_id,"agent_id":agent_id,"events":rows,
                "claim_boundary":"Runtime observation timeline, not a complete causal trace of all process/environment effects."}

    def observatory_start(self, *, host: str = "127.0.0.1", port: int = 0, open_browser: bool = True) -> dict:
        if self._observatory is not None:
            st=self._observatory.status()
            if st.get("running"): return st
        from .observatory import start_observatory
        self._observatory=start_observatory(self,host=host,port=port,open_browser=open_browser)
        return self._observatory.status()

    def observatory_status(self) -> dict:
        if self._observatory is None: return {"running":False,"read_only":True,"revision":self.revision}
        value=self._observatory.status(); value["revision"]=self.revision; return value

    def observatory_stop(self) -> dict:
        if self._observatory is None: return {"running":False,"stopped":False,"revision":self.revision}
        self._observatory.close(); self._observatory=None
        return {"running":False,"stopped":True,"revision":self.revision,"read_only":True}

    def observatory_snapshot(self) -> dict:
        # A bounded human-observer projection. It is deliberately not a control API and never includes raw private chain-of-thought.
        files=[dict(r) for r in self.store.all_files()]
        symbols=[dict(r) for r in self.store.all_symbols()]
        agents=[]
        for row in self.store.agent_sessions(limit=50):
            d=dict(row)
            try: d["metadata"]=json.loads(d.pop("metadata_json") or "{}")
            except Exception: d["metadata"]={}; d.pop("metadata_json",None)
            d["task"]=(d.get("metadata") or {}).get("task")
            agents.append(d)
        episodes=[]
        for row in self.store.conn.execute("SELECT * FROM work_episodes ORDER BY created_at DESC LIMIT 20").fetchall():
            d=dict(row)
            try: d["outcome"]=json.loads(d.pop("outcome_json") or "{}")
            except Exception: d["outcome"]={}; d.pop("outcome_json",None)
            episodes.append(d)
        hypotheses=[]
        for row in self.store.hypotheses(status="active",limit=30): hypotheses.append(dict(row))
        epistemic=[self._epistemic_row(r) for r in self.store.epistemic_items(status="open",limit=40)]
        evidence=[]
        for row in self.store.active_evidence(limit=50):
            d=dict(row)
            try: d["data"]=json.loads(d.pop("data_json") or "{}")
            except Exception: d["data"]={}; d.pop("data_json",None)
            evidence.append(d)
        runtime=self.runtime_timeline(limit=40)["events"]
        global_res=[dict(r) for r in self.store.resident_rows()]
        private=[]
        for a in agents:
            if a.get("status")!="active": continue
            for r in self.store.agent_resident_rows(a["id"]):
                d=dict(r); d["agent_id"]=a["id"]; d["label"]=d.get("path") or d.get("object_id"); private.append(d)
        faults=self.store.conn.execute("SELECT COALESCE(SUM(source_bytes),0) AS source,COALESCE(SUM(authority_bytes_read),0) AS authority FROM context_faults").fetchone()
        # Project graph is intentionally bounded so the observer never becomes an O(project) hot path.
        node=[]; edge=[]; node_ids=set()
        for fr in files[:90]:
            n={"id":fr["id"],"type":"file","label":fr["path"],"path":fr["path"]}; node.append(n); node_ids.add(fr["id"])
        for sr in symbols[:120]:
            n={"id":sr["id"],"type":"symbol","label":sr["qualified_name"],"path":sr["path"]}; node.append(n); node_ids.add(sr["id"])
        for a in agents:
            n={"id":a["id"],"type":"agent","label":a["name"],"agent_id":a["id"]}; node.append(n); node_ids.add(a["id"])
        for h in hypotheses[:20]:
            n={"id":h["id"],"type":"hypothesis","label":h["statement"][:80]}; node.append(n); node_ids.add(h["id"])
        for e in evidence[:20]:
            n={"id":e["id"],"type":"evidence","label":e["summary"][:80],"path":e.get("path")}; node.append(n); node_ids.add(e["id"])
        for rt in runtime[:20]:
            n={"id":rt["id"],"type":"runtime","label":rt["name"][:80],"path":rt.get("path")}; node.append(n); node_ids.add(rt["id"])
        for r in self.store.conn.execute("SELECT source_id,target_id,kind,trust FROM relations LIMIT 800").fetchall():
            if r["source_id"] in node_ids and r["target_id"] in node_ids: edge.append({"source":r["source_id"],"target":r["target_id"],"kind":r["kind"],"trust":r["trust"]})
        for h in hypotheses[:20]:
            for l in self.store.hypothesis_evidence(h["id"]):
                if h["id"] in node_ids and l["evidence_id"] in node_ids: edge.append({"source":h["id"],"target":l["evidence_id"],"kind":"evidence-"+l["polarity"],"trust":"derived"})
        return {"revision":self.revision,"generated_at":utc_now(),"read_only":True,"backend":self.backend_info(),"execution_security":self.execution_security(),
                "project":{"files":len(files),"symbols":len(symbols),"files_view":[{"path":f["path"],"language":f["language"],"size":f["size"]} for f in files[:180]]},
                "agents":agents,"episodes":episodes,"hypotheses":hypotheses,"epistemic":epistemic,"evidence":evidence,"runtime":runtime,
                "context_memory":{"residents":(private+global_res)[:60],"agent_visible_source_bytes":int(faults["source"] or 0),"authority_bytes_read":int(faults["authority"] or 0)},
                "graph":{"nodes":node,"edges":edge},"activity_seq":self.store.latest_activity_seq(),
                "activity":self.activity_since(max(0,self.store.latest_activity_seq()-80),100)["events"],
                "claim_boundary":"Human visual observatory only. Shows admitted task/hypothesis/evidence/action summaries and world state; raw private model chain-of-thought is intentionally not represented."}

    def guidance_discover(self) -> dict:
        self.reconcile()
        known={"AGENTS.md":"agents","CLAUDE.md":"claude","CONTRIBUTING.md":"contributing","copilot-instructions.md":"copilot"}
        rows=[]
        for fr in self.store.all_files():
            path=fr["path"]; name=Path(path).name
            if name not in known: continue
            if name=="copilot-instructions.md" and ".github" not in Path(path).parts: continue
            parent=Path(path).parent.as_posix(); scope="." if parent=="." else parent
            rows.append({"path":path,"kind":known[name],"scope":scope,"size":int(fr["size"]),"digest":fr["digest"],
                         "auto_injected":False})
        rows.sort(key=lambda x:(x["scope"].count("/"),x["scope"],x["path"]))
        return {"revision":self.revision,"count":len(rows),"guidance":rows,"automatic_context_injection":False,
                "claim_boundary":"Guidance is discoverable scoped repository input, not verified truth and not automatically injected into every solver context."}

    def guidance_read(self, path: str, start_line: int = 1, max_lines: int = 200) -> dict:
        allowed={g["path"] for g in self.guidance_discover()["guidance"]}
        if path not in allowed: raise ValueError("path is not a discovered guidance file")
        value=self.read_source(path,start_line,max_lines); value["guidance_only"]=True
        value["claim_boundary"]="Explicitly paged repository guidance; instructions remain unverified input and are subject to Habitat policy/safety boundaries."
        return value

    def sandbox_status(self) -> dict:
        return {"revision":self.revision,"execution":self.execution_security(),"host":sandbox_capability_summary(Path(self.backend.execution_provider.info.execution_root))}

    def _backend_binding(self) -> str:
        info = self.backend_info()
        return stable_id("backend-binding", json.dumps({
            "backend_id": info["backend_id"], "kind": info["kind"],
            "source_authority_id": info.get("source_authority_id"),
            "execution_provider_id": info.get("execution_provider_id"),
            "authority": info["authority"], "authoritative_root": info["authoritative_root"],
            "execution_kind": info["execution_kind"],
        }, sort_keys=True))

    def _source_authority_binding(self) -> str:
        info=self.backend.source_authority.info.as_dict()
        return stable_id("source-authority-binding",json.dumps(info,sort_keys=True))

    def _execution_provider_binding(self) -> str:
        info=self.backend.execution_provider.info.as_dict()
        return stable_id("execution-provider-binding",json.dumps(info,sort_keys=True))

    def read_source_bytes(self, rel: str) -> bytes:
        return self.backend.read_bytes(rel)

    def source_stat_fingerprint(self, rel: str) -> dict | None:
        fp = self.backend.stat_fingerprint(rel)
        return fp.as_dict() if fp else None

    def read_source_line_range(self, rel: str, start_line: int, end_line: int) -> dict:
        decision=self.policy.evaluate_source("read",rel)
        if not decision.allowed: raise PermissionError(decision.reason)
        if start_line < 1 or end_line < start_line:
            raise ValueError("invalid source line range")
        row = self.store.file_by_path(rel)
        if not row:
            raise FileNotFoundError(rel)
        cache = self.store.load_compile_cache(row["id"]) or {}
        sio = ((cache.get("metadata") or {}).get("source_io") or {})
        checkpoints = list(sio.get("checkpoints") or [[1, 0]])
        cp_line, cp_offset = 1, 0
        for item in checkpoints:
            try:
                ln, off = int(item[0]), int(item[1])
            except Exception:
                continue
            if ln <= start_line and ln >= cp_line:
                cp_line, cp_offset = ln, off
        expected_fp = (self.store.load_project_cache("source-os-fingerprints-v1") or {}).get(rel)
        receipt = self.backend.read_line_range(rel, start_line, end_line, checkpoint_line=cp_line, checkpoint_offset=cp_offset)
        before = receipt.fingerprint_before.as_dict() if receipt.fingerprint_before else None
        after = receipt.fingerprint_after.as_dict() if receipt.fingerprint_after else None
        if before != after:
            raise TransactionConflict(f"source changed during range read: {rel}")
        if expected_fp is not None and before != expected_fp:
            # Do not serve bytes from a world state newer than the Semantic Twin.
            self.refresh_paths([rel], reason="range-read-fingerprint-drift")
            raise TransactionConflict(f"source fingerprint drifted before range read: {rel}; semantic state refreshed")
        raw = receipt.data
        utf8_valid = bool(sio.get("utf8_valid", True))
        text = raw.decode("utf-8", errors="strict" if utf8_valid else "replace")
        return {
            "text": text, "raw": raw, "agent_visible_source_bytes": len(raw),
            "backend_authority_bytes_read": int(receipt.authority_bytes_read),
            "encoding": "utf-8" if utf8_valid else "utf-8-with-replacement",
            "lossy_text": not utf8_valid, "newline": sio.get("newline", "unknown"),
            "checkpoint_line": cp_line, "checkpoint_offset": cp_offset,
        }

    def write_source_bytes(self, rel: str, data: bytes) -> None:
        self.backend.write_bytes(rel, data)

    def source_is_file(self, rel: str) -> bool:
        return self.backend.is_file(rel)

    def delete_source_file(self, rel: str) -> None:
        self.backend.delete_file(rel)

    def move_source_file(self, from_rel: str, to_rel: str) -> None:
        self.backend.move_file(from_rel, to_rel)

    def _backend_reconcile(self, paths: list[str] | None = None) -> dict:
        return self.backend.reconcile(paths).as_dict()

    def _compiled_from_store(self, row) -> CompiledFile:
        f = FileRecord(row["id"], row["path"], row["language"], row["size"], row["digest"], row["mtime_ns"], "",
                       row["indexed_bytes"], bool(row["index_truncated"]), bool(row["parse_complete"]))
        symbols = [SymbolRecord(
            s["id"], s["file_id"], s["path"], s["name"], s["qualified_name"], s["kind"], s["language"],
            s["start_line"], s["end_line"], s["signature"], s["summary"], s["trust"]
        ) for s in self.store.symbols_for_file(row["id"])]
        diags = [DiagnosticRecord(
            d["id"], d["file_id"], d["path"], d["severity"], d["message"], d["line"], d["column"], d["source"], d["trust"]
        ) for d in self.store.diagnostics_for_path(row["path"])]
        cache = self.store.load_compile_cache(row["id"]) or {}
        unresolved = [tuple(x) for x in cache.get("unresolved_relations", [])]
        return CompiledFile(f, symbols, unresolved, diags, cache.get("provider", "legacy-cache"), cache.get("metadata", {}))

    def _compiler_state_fingerprint(self) -> str:
        # Provider/toolchain identity is part of workspace state even when source bytes are unchanged.
        langs = {"python","javascript","typescript","java","html","css","json","markdown","text","binary"}
        payload = {lang: compile_cache_fingerprint(lang) for lang in sorted(langs)}
        return stable_id("compiler-state", json.dumps(payload, sort_keys=True))

    def _cache_valid(self, old, digest: str) -> bool:
        if not old or old["digest"] != digest:
            return False
        cache = self.store.load_compile_cache(old["id"])
        if cache is None:
            return False
        expected = compile_cache_fingerprint(old["language"])
        return bool(cache.get("compiler_cache_version") == COMPILE_CACHE_VERSION and cache.get("fingerprint") == expected)

    def _persist_compiled(self, cf: CompiledFile) -> None:
        self.store.upsert_file(cf.file)
        self.store.replace_file_search(cf.file)
        self.store.replace_symbols_for_file(cf.file.id, cf.symbols)
        self.store.replace_diagnostics_for_file(cf.file.id, cf.diagnostics)
        self.store.save_compile_cache(cf.file.id, {
            "compiler_cache_version": COMPILE_CACHE_VERSION,
            "fingerprint": compile_cache_fingerprint(cf.file.language),
            "provider": cf.provider,
            "unresolved_relations": [list(x) for x in cf.unresolved_relations],
            "metadata": cf.metadata,
        })

    def _delete_indexed_path(self, rel: str, row) -> None:
        for sym in self.store.symbols_for_file(row["id"]):
            self.store.delete_search(sym["id"])
        for diag in self.store.diagnostics_for_path(rel):
            self.store.delete_search(diag["id"])
        self.store.delete_search(row["id"])
        self.store.delete_compile_cache(row["id"])
        self.store.conn.execute("DELETE FROM files WHERE id=?", (row["id"],))

    def _update_source_fingerprints(self, paths: list[str] | None = None) -> None:
        current = dict(self.store.load_project_cache("source-os-fingerprints-v1") or {})
        wanted = paths if paths is not None else [r["path"] for r in self.store.all_files()]
        for rel in wanted:
            fp = self.source_stat_fingerprint(rel)
            if fp is None:
                current.pop(rel, None)
            else:
                current[rel] = fp
        indexed = {r["path"] for r in self.store.all_files()}
        for rel in list(current):
            if rel not in indexed:
                current.pop(rel, None)
        self.store.save_project_cache("source-os-fingerprints-v1", current)

    def _finalize_refresh(self, previous: dict, changed: list[str], reason: str, *, compiled_count: int,
                          reused_count: int, provider_counts: Counter[str], hashed_files: int,
                          refresh_mode: str) -> dict:
        rows = self.store.all_files()
        compiled = [self._compiled_from_store(r) for r in rows]
        entries = [(r["path"], r["digest"]) for r in rows]
        digest = root_digest(entries)
        merkle = build_merkle_snapshot((r["path"], r["digest"], r["size"]) for r in rows)
        semantic = compile_project_semantics(self.source_root, compiled, self.store, digest, bool(changed or compiled_count))
        relation_delta = self.store.sync_relations(semantic.relations)
        occurrence_delta = self.store.sync_occurrences(semantic.occurrences)

        changed_unique = sorted(set(changed))
        head = self.store.head_revision()
        hrow = self.store.revision(head) if head else None
        unchanged_revision = bool(hrow and hrow["root_digest"] == digest)
        now = utc_now()
        rid = head if unchanged_revision else stable_id("rev", digest, now)
        if not unchanged_revision:
            self.store.add_revision(Revision(rid, head, digest, reason, changed_unique, now))
        # Store Merkle state for both new revisions and migrated legacy heads. Objects are content-addressed,
        # so unchanged subtrees are deduplicated across revisions rather than copied N times.
        if self.store.merkle_snapshot_row(rid) is None:
            self.store.save_merkle_snapshot(rid, merkle.as_dict(), now)

        # Effect Twin is revision-bound and refreshed only for changed source paths. Legacy workspaces
        # lazily backfill the table on first `effect_snapshot()` call, keeping warm reconcile cheap.
        effect_report = compile_effects(self.source_root, self.store, rid, changed_unique) if changed_unique else {
            "revision": rid, "paths_considered": 0, "paths_compiled": 0, "facts": 0, "providers": {}, "failures": []
        }
        dataflow_report = compile_dataflow(self.source_root, self.store, rid, changed_unique) if changed_unique else {
            "revision": rid, "paths_considered": 0, "paths_compiled": 0, "facts": 0, "providers": {}, "failures": []
        }

        for rel in changed_unique:
            old = previous.get(rel)
            current = self.store.file_by_path(rel)
            kind = "file-created" if old is None and current is not None else "file-deleted" if current is None else "file-modified"
            self.store.append_event(EventRecord(
                kind=kind, path=rel, observed_at=now, revision_before=head, revision_after=rid,
                old_digest=old["digest"] if old else None, new_digest=current["digest"] if current else None,
                source="source-bridge", details={"reason": reason, "refresh_mode": refresh_mode},
            ))
            self._activity_safe("source."+kind,"source",path=rel,status="changed",summary=f"{kind}: {rel}",data={"reason":reason,"refresh_mode":refresh_mode,"revision_before":head,"revision_after":rid})
        graph_delta = {"relations": relation_delta, "occurrences": occurrence_delta}
        self.store.append_event(EventRecord(
            kind="semantic-refresh", path=None, observed_at=now, revision_before=head, revision_after=rid, source="semantic-twin",
            details={"reason": reason, "refresh_mode": refresh_mode, "unchanged_revision": unchanged_revision,
                     "compiled_files": compiled_count, "reused_files": reused_count, "hashed_files": hashed_files,
                     "project_semantic_cache_hit": semantic.cache_hit, "providers": semantic.providers,
                     "graph_delta": graph_delta},
        ))
        self.store.set_meta("compiler_state_fingerprint", self._compiler_state_fingerprint())
        self._update_source_fingerprints(changed_unique if refresh_mode == "targeted" else None)
        self.store.commit()
        return {
            "revision": rid, "changed_paths": [] if unchanged_revision else changed_unique, "unchanged": unchanged_revision,
            "compiled_files": compiled_count, "reused_files": reused_count, "hashed_files": hashed_files,
            "refresh_mode": refresh_mode, "providers": dict(provider_counts), "project_semantics": semantic.providers,
            "project_semantic_cache_hit": semantic.cache_hit, "occurrence_count": len(semantic.occurrences),
            "graph_delta": graph_delta, "effect_twin": effect_report, "dataflow_twin": dataflow_report,
        }

    @_atomic_workspace_refresh
    def refresh(self, reason: str = "refresh") -> dict:
        """Deep integrity refresh.

        Every project file is content-hashed, but unchanged compatible compiler artifacts are reused.  Consequential
        mutations call this path so metadata-preserving external edits cannot bypass conflict detection.
        """
        backend_sync = self._backend_reconcile()
        previous = {r["path"]: r for r in self.store.all_files()}
        changed: list[str] = []
        seen: set[str] = set()
        compiled_count = reused_count = hashed_files = 0
        hash_bytes_read = compiler_input_bytes = index_bytes_written = 0
        provider_counts: Counter[str] = Counter()

        for path in iter_project_files(self.source_root):
            rel = path.relative_to(self.source_root).as_posix(); seen.add(rel)
            st = path.stat(); digest = sha256_file(path); hashed_files += 1; hash_bytes_read += int(st.st_size)
            old = previous.get(rel)
            if self._cache_valid(old, digest):
                f = FileRecord(old["id"], rel, old["language"], st.st_size, digest, st.st_mtime_ns, "",
                               old["indexed_bytes"], bool(old["index_truncated"]), bool(old["parse_complete"]))
                self.store.upsert_file(f)
                cf = self._compiled_from_store(self.store.file_by_path(rel)); reused_count += 1
            else:
                cf = compile_file(self.source_root, path); compiled_count += 1
                compiler_input_bytes += int(cf.file.size); index_bytes_written += int(cf.file.indexed_bytes)
                if not old or old["digest"] != cf.file.digest:
                    changed.append(rel)
                self._persist_compiled(cf)
            provider_counts[cf.provider] += 1

        for rel in sorted(set(previous) - seen):
            self._delete_indexed_path(rel, previous[rel]); changed.append(rel)

        result = self._finalize_refresh(previous, changed, reason, compiled_count=compiled_count,
                                      reused_count=reused_count, provider_counts=provider_counts,
                                      hashed_files=hashed_files, refresh_mode="deep")
        result["backend_sync"] = backend_sync
        result["workspace_listing_mode"] = "full-enumeration"
        result["paths_considered"] = hashed_files
        result["io_accounting"] = {
            "backend_authority_bytes_read": int(backend_sync.get("authoritative_bytes_read") or 0),
            "hash_bytes_read": hash_bytes_read,
            "compiler_input_bytes_minimum": compiler_input_bytes,
            "index_bytes_written": index_bytes_written,
            "note": "compiler_input_bytes_minimum counts admitted file bytes once; individual providers may internally rescan"
        }
        return result

    @_atomic_workspace_refresh
    def refresh_paths(self, paths: list[str], reason: str = "targeted-refresh") -> dict:
        """Refresh metadata-observed candidate paths while hashing only those candidates.

        This hashes and recompiles only caller/change-feed candidates. Consequential mutations combine
        ordinary `reconcile()` with digest-bound target preflight and targeted post-write refresh; explicit
        `refresh()` remains the independent whole-project deep integrity scrub.
        """
        normalized=[]
        for raw in paths:
            if not isinstance(raw, str) or not raw or raw.startswith("/") or ".." in Path(raw).parts:
                raise ValueError(f"invalid targeted refresh path: {raw!r}")
            normalized.append(Path(raw).as_posix())
        normalized = sorted(set(normalized))
        # Hydrate only caller/change-feed candidates. Do not enumerate the semantic mirror in the
        # targeted path, otherwise a remote backend would still pay an O(project) listing tax.
        backend_sync = self._backend_reconcile(normalized)
        previous = {r["path"]: r for r in self.store.all_files()}
        changed: list[str] = []
        compiled_count = reused_count = hashed_files = 0
        hash_bytes_read = compiler_input_bytes = index_bytes_written = 0
        provider_counts: Counter[str] = Counter()
        for rel in normalized:
            candidate = self.resolve_source_path(rel)
            path = candidate if candidate.is_file() else None
            old = previous.get(rel)
            if path is None:
                if old is not None:
                    self._delete_indexed_path(rel, old); changed.append(rel)
                continue
            st = path.stat(); digest = sha256_file(path); hashed_files += 1; hash_bytes_read += int(st.st_size)
            if self._cache_valid(old, digest):
                f = FileRecord(old["id"], rel, old["language"], st.st_size, digest, st.st_mtime_ns, "",
                               old["indexed_bytes"], bool(old["index_truncated"]), bool(old["parse_complete"]))
                self.store.upsert_file(f)
                cf = self._compiled_from_store(self.store.file_by_path(rel)); reused_count += 1
            else:
                cf = compile_file(self.source_root, path); compiled_count += 1
                compiler_input_bytes += int(cf.file.size); index_bytes_written += int(cf.file.indexed_bytes)
                if not old or old["digest"] != cf.file.digest:
                    changed.append(rel)
                self._persist_compiled(cf)
            provider_counts[cf.provider] += 1
        result = self._finalize_refresh(previous, changed, reason, compiled_count=compiled_count,
                                      reused_count=reused_count, provider_counts=provider_counts,
                                      hashed_files=hashed_files, refresh_mode="targeted")
        self._update_source_fingerprints(normalized)
        self.store.commit()
        result["backend_sync"] = backend_sync
        result["workspace_listing_mode"] = "targeted-no-enumeration"
        result["paths_considered"] = len(normalized)
        result["io_accounting"] = {
            "backend_authority_bytes_read": int(backend_sync.get("authoritative_bytes_read") or 0),
            "hash_bytes_read": hash_bytes_read,
            "compiler_input_bytes_minimum": compiler_input_bytes,
            "index_bytes_written": index_bytes_written,
            "note": "compiler_input_bytes_minimum counts admitted file bytes once; individual providers may internally rescan"
        }
        return result

    def reconcile(self) -> dict:
        """Integrity-assisted ordinary synchronization.

        Size+mtime alone is insufficient: content can change while mtime is restored. Alpha.8 also
        binds ctime/inode fingerprints. Under ordinary filesystem semantics a content write changes
        ctime even if mtime/size are restored, so stale perception is detected without hashing every
        file on every cognitive call. `refresh()` remains the cryptographic/deep integrity boundary.
        """
        backend_sync = self._backend_reconcile()
        stored_fp = self.store.get_meta("compiler_state_fingerprint")
        current_fp = self._compiler_state_fingerprint()
        if stored_fp and stored_fp != current_fp:
            return self.refresh(reason="compiler-provider-fingerprint-change")
        # Windows exposes st_ctime as creation-time semantics rather than POSIX inode-change time.
        # Without a native NTFS change journal, metadata-only fingerprints are not a strong enough
        # perception boundary there. Prefer correctness: perform a deep content verification.
        if os.name == "nt":
            return self.refresh(reason="windows-deep-content-perception-reconcile")
        stored_os = dict(self.store.load_project_cache("source-os-fingerprints-v1") or {})
        current_paths = list(iter_project_files(self.source_root))
        current_os: dict[str, dict] = {}
        for path in current_paths:
            rel = path.relative_to(self.source_root).as_posix()
            fp = self.source_stat_fingerprint(rel)
            if fp is not None:
                current_os[rel] = fp
        candidates = sorted({p for p in set(stored_os) | set(current_os) if stored_os.get(p) != current_os.get(p)})
        if not candidates:
            return {"revision": self.revision, "changed_paths": [], "unchanged": True,
                    "check": "size+mtime+ctime+inode", "hashed_files": 0, "refresh_mode": "integrity-assisted-metadata",
                    "backend_sync": backend_sync, "perception_integrity": "os-change-fingerprint; use refresh() for cryptographic full verification"}
        return self.refresh_paths(candidates, reason="automatic-source-integrity-reconcile")

    def enter(self) -> dict:
        self.reconcile()
        files = self.store.all_files(); symbols = self.store.all_symbols(); diagnostics = self.store.all_diagnostics()
        langs = Counter(r["language"] for r in files)
        total = sum(langs.values()) or 1
        ts_ok, ts_reason = TypeScriptCompilerProvider().available()
        from .semantic.python_jedi import probe as jedi_probe
        jedi_ok,jedi_reason,jedi_version=jedi_probe()
        jedi_summary=(self.store.load_project_cache("semantic-python-jedi-summary-v2") or {}).get("report") or {}
        ts_summary=(self.store.load_project_cache("semantic-typescript-summary-v8") or {}).get("report") or {}
        browser = BrowserRuntime.probe()
        return {
            "workspace": str(self.habitat_dir), "source_root": str(self.source_root), "mode": self.manifest["mode"],
            "revision": self.revision, "file_count": len(files), "symbol_count": len(symbols), "diagnostic_count": len(diagnostics),
            "occurrence_count": self.store.conn.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0],
            "event_cursor": self.store.latest_event_seq(),
            "startup_transaction_recovery": list(self._startup_recovery),
            "languages": {k: round(v / total, 3) for k, v in langs.most_common()},
            "capabilities": self.backend.discover_capabilities(),
            "capability_report": self.capability_report(),
            "backend": self.backend_info(),
            "semantic_providers": {
                "python-ast": {"available": True, "trust_ceiling": "semantic", "project_linking": True},
                "python-jedi": {**{"available":jedi_ok,"reason":jedi_reason,"version":jedi_version,"trust_ceiling":"semantic","project_linking":jedi_ok},**jedi_summary},
                "typescript-compiler-api": {**{"available": ts_ok, "reason": ts_reason, "trust_ceiling": "semantic", "project_linking": ts_ok}, **ts_summary},
                "java": {"available": True, "provider": "regex-fallback", "trust_ceiling": "heuristic"},
                "runtime-browser": browser,
            },
            "index_health": {
                "truncated_text_files": sum(1 for r in files if r["index_truncated"]),
                "incomplete_parse_files": sum(1 for r in files if not r["parse_complete"]),
                "indexed_bytes": sum(r["indexed_bytes"] for r in files), "source_bytes": sum(r["size"] for r in files),
            },
            "live_workspace": {
                "ordinary_sync": "metadata candidates -> targeted content hash -> incremental semantic admission",
                "mutation_integrity": "reconcile + digest-bound target preflight + write-ahead journal + targeted post-write refresh; explicit refresh() is whole-project deep scrub",
                "watcher": self.watch_status(),
                "context_refresh": True,
                "context_materialization": "bounded symbol-body packet; no automatic whole-file dump",
                "context_residency": ContextResidency(self).status(reconcile=False),
                "virtual_context_memory": True,
                "content_addressed_state": "Merkle snapshots derived from already-hashed canonical files; no source copy",
                "active_evidence": self.store.conn.execute("SELECT COUNT(*) FROM evidence WHERE active=1").fetchone()[0],
                "semantic_rename": "Python/Jedi precision lane; fail-closed outside proven provider boundary",
            },
            "principles": {
                "source_authority": "source files", "semantic_twin": "derived and provenance-bound",
                "terminal": "not an agent primitive; raw process output is fallback evidence",
                "ui": "semantic runtime state first; pixels optional secondary oracle",
                "context": "orientation and bounded exact-source packets; retrieved metadata is not authority",
            },
        }

    def orient(self, task: str, budget: int = 18, agent_id: str | None = None):
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        self.reconcile()
        return ContextCompiler(self).compile(task, budget, agent_id=agent_id)

    def explore(self, task: str, line_budget: int = 120, max_regions: int = 12, context_budget: int = 40, agent_id: str | None = None) -> dict:
        """Return ranked semantic code regions under a strict line budget without reading source bytes."""
        if not isinstance(task,str) or not task.strip(): raise ValueError("task must be a non-empty string")
        if line_budget < 1 or line_budget > 10000: raise ValueError("line_budget must be in [1, 10000]")
        if max_regions < 1 or max_regions > 200: raise ValueError("max_regions must be in [1, 200]")
        if context_budget < 1 or context_budget > 200: raise ValueError("context_budget must be in [1, 200]")
        self.reconcile()
        ctx=ContextCompiler(self).compile(task.strip(),context_budget,agent_id=agent_id)
        value=self.store.load_json("context_slices",ctx.handle) or {}
        decision=dict(value.get("decision_packet") or {})
        if decision.get("abstention_recommended") and decision.get("retrieval_confidence")=="low":
            return {"task":task.strip(),"revision":self.revision,"context_handle":ctx.handle,"retrieval_confidence":"low",
                    "abstained":True,"regions":[],"region_count":0,"line_budget":line_budget,"lines_selected":0,"source_bytes_read":0,
                    "reason":"low retrieval confidence; explorer refuses least-bad source regions"}
        regions=[]; lines_used=0; covered: dict[str,list[tuple[int,int]]]={}
        for cand in value.get("ranked",[]):
            if len(regions)>=max_regions or lines_used>=line_budget: break
            oid=cand.get("object_id"); sr=self.store.symbol_by_id(oid); dr=self.store.diagnostic_by_id(oid)
            if sr:
                start=max(1,int(sr["start_line"])); end=max(start,int(sr["end_line"])); kind="symbol"; trust=sr["trust"]
            elif dr and dr["line"]:
                start=max(1,int(dr["line"])-3); end=int(dr["line"])+3; kind="diagnostic-window"; trust=dr["trust"]
            else:
                continue
            existing=covered.setdefault(cand["path"],[])
            if any(a<=start and end<=b for a,b in existing):
                continue
            remaining=line_budget-lines_used
            original_end=end
            end=min(end,start+remaining-1)
            if end<start: break
            count=end-start+1
            region={"object_id":oid,"path":cand["path"],"start_line":start,"end_line":end,"line_count":count,
                    "partial":end<original_end,"kind":kind,"trust":trust,"score":round(float(cand.get("score") or 0),6),
                    "lane":cand.get("lane"),"reason":cand.get("reason"),
                    "virtual_region":f"region://{ctx.handle}/{stable_id('region',oid,str(start),str(end))}"}
            regions.append(region); lines_used += count; existing.append((start,end))
        return {"task":task.strip(),"revision":self.revision,"context_handle":ctx.handle,
                "retrieval_confidence":decision.get("retrieval_confidence"),"concept_coverage":decision.get("concept_coverage"),
                "abstained":False,"regions":regions,"region_count":len(regions),"line_budget":line_budget,"lines_selected":lines_used,
                "source_bytes_read":0,"whole_file_dump":False,"ranking_scope":"semantic symbol/diagnostic regions; exact source remains behind Context VM",
                "truncated_by_line_budget":bool(lines_used>=line_budget)}

    def context_page(self, handle: str, offset: int = 0, limit: int = 20) -> dict:
        self.reconcile()
        if limit < 1 or limit > 200: raise ValueError("limit must be in [1, 200]")
        return ContextCompiler(self).page(handle, offset, limit)

    def context_refresh(self, handle: str, budget: int | None = None) -> dict:
        self.reconcile()
        return ContextCompiler(self).refresh_slice(handle, budget)

    def query(self, query: str, limit: int = 20) -> list[dict]:
        self.reconcile()
        return [dict(r) for r in self.store.search(query, limit)]

    def references(self, object_id: str, limit: int = 200) -> dict:
        self.reconcile()
        return self.references_snapshot(object_id, limit)

    def references_snapshot(self, object_id: str, limit: int = 200) -> dict:
        if limit < 1 or limit > 2000:
            raise ValueError("limit must be in [1, 2000]")
        if not (self.store.symbol_by_id(object_id) or self.store.file_by_id(object_id)):
            raise KeyError(object_id)
        rows = self.store.occurrences_for_target(object_id)[:limit]
        return {
            "object_id": object_id, "revision": self.revision, "count": len(rows),
            "occurrences": [dict(r) for r in rows],
            "truncated": len(self.store.occurrences_for_target(object_id)) > limit,
        }

    def impact(self, changed_paths: list[str] | None = None, object_ids: list[str] | None = None, max_depth: int = 5) -> dict:
        self.reconcile()
        if max_depth < 1 or max_depth > 12:
            raise ValueError("max_depth must be in [1, 12]")
        value = affected_tests(self.store, changed_paths, object_ids, max_depth)
        value["revision"] = self.revision
        return value

    def _inspect_object(self, object_id: str, include_source: str = "none") -> dict:
        s = self.store.symbol_by_id(object_id)
        if s:
            value = dict(s); file_row = self.store.file_by_id(s["file_id"])
            value["source_anchor"] = {"path": s["path"], "start_line": s["start_line"], "end_line": s["end_line"],
                                      "digest": file_row["digest"] if file_row else None, "revision": self.revision}
            value["relations"] = [dict(r) for r in self.store.relations_for(object_id)]
            value["references"] = [dict(o) for o in self.store.occurrences_for_target(object_id)[:200]]
            value["diagnostics"] = [dict(d) for d in self.store.diagnostics_for_path(s["path"])]
            if include_source in {"body", "range"}:
                page = self.read_source_line_range(s["path"], int(s["start_line"]), int(s["end_line"]))
                value["source"] = page["text"].rstrip("\r\n")
                value["source_authority"] = "authoritative source range"
                value["source_accounting"] = {k: page[k] for k in ("agent_visible_source_bytes","backend_authority_bytes_read","encoding","lossy_text","newline")}
            return value
        d = self.store.diagnostic_by_id(object_id)
        if d:
            value = dict(d)
            f = self.store.file_by_id(d["file_id"])
            value["source_anchor"] = {"path": d["path"], "line": d["line"], "column": d["column"],
                                      "digest": f["digest"] if f else None, "revision": self.revision}
            return value
        e = self.store.evidence_by_id(object_id)
        if e:
            value = dict(e)
            try: value["data"] = json.loads(value.pop("data_json"))
            except Exception: value["data"] = {}; value.pop("data_json", None)
            value["active"] = bool(value["active"])
            value["authority"] = "runtime/verification evidence; not source truth"
            if value.get("path"):
                fr = self.store.file_by_path(value["path"]); value["source_digest"] = fr["digest"] if fr else None
            return value
        f = self.store.file_by_id(object_id)
        if f:
            value = dict(f)
            value["symbols"] = [dict(s) for s in self.store.symbols_for_file(f["id"])]
            value["diagnostics"] = [dict(d) for d in self.store.diagnostics_for_path(f["path"])]
            if include_source != "none":
                value["source"] = self.read_source_bytes(f["path"]).decode("utf-8", errors="replace")
                value["source_authority"] = "exact source bytes decoded as UTF-8 with replacement"
            return value
        raise KeyError(object_id)

    def inspect(self, object_id: str, include_source: str = "none", agent_id: str | None = None) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        self.reconcile(); value=self._inspect_object(object_id, include_source)
        if agent_id is not None and value.get("path"):
            fr=self.store.file_by_path(value["path"])
            if fr: self.store.record_agent_observation(agent_id,value["path"],fr["digest"],self.revision,"inspect",object_id,utc_now())
        return value

    def inspect_snapshot(self, object_id: str, include_source: str = "none") -> dict:
        return self._inspect_object(object_id, include_source)

    def inspect_many(self, object_ids: list[str], include_source: str = "none", max_objects: int = 50) -> dict:
        self.reconcile()
        if not isinstance(object_ids, list) or len(object_ids) > max_objects or max_objects < 1 or max_objects > 200:
            raise ValueError("invalid inspect batch bounds")
        return {"revision": self.revision, "objects": [self._inspect_object(oid, include_source) for oid in object_ids]}

    def context_materialize(self, handle: str, max_source_bytes: int = 60_000, max_objects: int = 12) -> dict:
        """Materialize a bounded, revision-bound task packet for an agent decision step.

        Exact source is admitted symbol-by-symbol only while the byte budget permits it.  Files are never
        dumped wholesale by default.  Omissions are explicit so compression cannot masquerade as complete state.
        """
        self.reconcile()
        if max_source_bytes < 0 or max_source_bytes > 2_000_000:
            raise ValueError("max_source_bytes must be in [0, 2000000]")
        if max_objects < 1 or max_objects > 100:
            raise ValueError("max_objects must be in [1, 100]")
        record = self.store.load_json("context_slices", handle)
        if not record:
            raise KeyError(handle)
        if record.get("revision") != self.revision:
            return {"handle": handle, "stale": True, "compiled_revision": record.get("revision"),
                    "current_revision": self.revision, "revision": self.revision, "objects": [], "source_bytes": 0,
                    "omissions": ["Context handle is stale; refresh it before materialization."]}
        selected_ids = list(record.get("selected_ids") or [x.get("object_id") for x in record.get("ranked", []) if x.get("object_id")])[:max_objects]
        objects=[]; source_bytes=0; omissions=[]
        for oid in selected_ids:
            sr=self.store.symbol_by_id(oid); dr=self.store.diagnostic_by_id(oid); er=self.store.evidence_by_id(oid); fr=self.store.file_by_id(oid)
            if sr:
                item={k:sr[k] for k in ("id","path","name","qualified_name","kind","start_line","end_line","trust")}
                item["relations"]=[dict(r) for r in self.store.relations_for(oid)[:20]]
                exact=self._inspect_object(oid,"body").get("source","")
                encoded=exact.encode("utf-8")
                if source_bytes + len(encoded) <= max_source_bytes:
                    item["source"]=exact; item["source_authority"]="exact-source"; source_bytes += len(encoded)
                else:
                    item["source_omitted_reason"]="source-byte-budget"
                    omissions.append(f"Exact source omitted for {oid}: byte budget exhausted.")
                objects.append(item)
            elif dr:
                item={k:dr[k] for k in ("id","path","severity","message","line","column","source","trust")}
                objects.append(item)
            elif er:
                item={k:er[k] for k in ("id","kind","revision","path","severity","summary","trust","source","created_at","active")}
                item["active"] = bool(item["active"]); item["evidence_authority"] = "runtime/verification evidence; not source truth"
                objects.append(item)
            elif fr:
                item={k:fr[k] for k in ("id","path","language","size","digest","parse_complete","index_truncated")}
                item["symbol_ids"]=[x["id"] for x in self.store.symbols_for_file(fr["id"])[:30]]
                item["source_omitted_reason"]="file objects are metadata-only in context materialization; inspect a symbol or page exact source explicitly"
                objects.append(item)
            else:
                omissions.append(f"Selected context object disappeared: {oid}")
        packet={
            "handle":handle,"stale":False,"task":record.get("task"),"revision":self.revision,
            "objects":objects,"source_bytes":source_bytes,"max_source_bytes":max_source_bytes,
            "object_count":len(objects),"max_objects":max_objects,"omissions":omissions,
            "trust_policy":"source text is exact-source; semantic/parser/heuristic metadata retains its own trust grade",
            "source_policy":"symbol bodies only; no automatic whole-file dump",
        }
        packet["packet_bytes"] = len(json.dumps(packet, ensure_ascii=False, default=str).encode("utf-8"))
        return packet

    def context_address_space(self, handle: str, max_pages: int = 100) -> dict:
        self.reconcile(); return ContextVirtualMemory(self).address_space(handle, max_pages)

    def context_fetch_pages(self, handle: str, page_ids: list[str], max_source_bytes: int = 60_000) -> dict:
        self.reconcile(); result=ContextVirtualMemory(self).fetch(handle, page_ids, max_source_bytes)
        record=self.store.load_json("context_slices",handle) or {}; agent_id=record.get("agent_id")
        if agent_id and self.store.agent_session(agent_id):
            for page in result.get("pages") or []:
                fr=self.store.file_by_path(page.get("path"))
                if fr: self.store.record_agent_observation(agent_id,page["path"],fr["digest"],self.revision,"context-page",page.get("object_id") or "",utc_now())
                self._activity_safe("context.page-fault","memory",agent_id=agent_id,ref_id=page.get("object_id") or page.get("page_id"),path=page.get("path"),status="paged",summary=f"paged {page.get('path')}",data={"source_bytes":page.get("source_bytes",0),"start_line":page.get("start_line"),"end_line":page.get("end_line"),"handle":handle})
        return result

    def context_prefetch(self, handle: str, max_source_bytes: int = 20_000, max_pages: int = 8) -> dict:
        self.reconcile(); vm=ContextVirtualMemory(self); plan=vm.plan_next(handle,[],max_pages=max_pages,max_estimated_bytes=max_source_bytes)
        ids=list(plan.get("page_ids") or [])
        if not ids: return {"handle":handle,"stale":bool(plan.get("stale")),"pages":[],"faults":[{"reason":plan.get("reason") or plan.get("action") or "no-fetchable-pages"}],"source_bytes":0,"plan":plan}
        result=self.context_fetch_pages(handle,ids,max_source_bytes); result["plan"]=plan; result["prefetch_policy"]="context plan-next followed by exact digest-bound page faults"; return result

    def context_plan_next(self, handle: str, fetched_page_ids: list[str] | None = None, max_pages: int = 3, max_estimated_bytes: int = 20_000) -> dict:
        self.reconcile(); return ContextVirtualMemory(self).plan_next(handle, fetched_page_ids, max_pages, max_estimated_bytes)

    def context_feedback(self, handle: str, used_object_ids: list[str] | None = None, unhelpful_object_ids: list[str] | None = None, weight: float = 1.0, agent_id: str | None = None) -> dict:
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if used_object_ids is None: used_object_ids = []
        if unhelpful_object_ids is None: unhelpful_object_ids = []
        if not isinstance(used_object_ids, list) or not all(isinstance(x, str) and x for x in used_object_ids):
            raise TypeError("used_object_ids must be a list of non-empty strings")
        if not isinstance(unhelpful_object_ids, list) or not all(isinstance(x, str) and x for x in unhelpful_object_ids):
            raise TypeError("unhelpful_object_ids must be a list of non-empty strings")
        if set(used_object_ids) & set(unhelpful_object_ids):
            raise ValueError("an object cannot be both used and unhelpful in one feedback record")
        if not used_object_ids and not unhelpful_object_ids:
            raise ValueError("context feedback requires at least one used or unhelpful object")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0 or weight > 5:
            raise ValueError("weight must be in (0, 5]")
        self.reconcile()
        value = self.store.load_json("context_slices", handle)
        if not value: raise KeyError(handle)
        if value.get("revision") != self.revision:
            raise ValueError(f"stale context feedback rejected: compiled={value.get('revision')} current={self.revision}")
        allowed = {str(x.get("object_id")) for x in value.get("ranked", []) if x.get("object_id")}
        requested = set(used_object_ids) | set(unhelpful_object_ids)
        outside = sorted(requested - allowed)
        if outside:
            raise ValueError(f"context feedback object was not part of the compiled candidate set: {outside[0]}")
        compiler = ContextCompiler(self)
        task_terms = compiler._content_terms(str(value.get("task") or ""))
        now = utc_now(); records=[]
        for verdict, ids in (("used", used_object_ids), ("unhelpful", unhelpful_object_ids)):
            for oid in ids:
                seq=self.store.record_context_feedback(handle, oid, verdict, float(weight), task_terms, self.revision, now)
                utility=self.store.context_utility_for(oid, task_terms)
                agent_utility=None
                if agent_id is not None:
                    self.store.record_agent_context_feedback(agent_id,oid,verdict,float(weight),task_terms,self.revision,now)
                    agent_utility=self.store.agent_context_utility_for(agent_id,oid,task_terms)
                records.append({"seq":seq,"object_id":oid,"verdict":verdict,"utility":utility,"agent_id":agent_id,"agent_utility":agent_utility})
        self.store.append_event(EventRecord(
            kind="context-feedback", path=None, observed_at=now, revision_before=self.revision, revision_after=self.revision,
            source="agent-context", details={"handle":handle,"compiled_revision":value.get("revision"),"task_terms":task_terms,
                                             "used_object_ids":used_object_ids,"unhelpful_object_ids":unhelpful_object_ids,"weight":float(weight),
                                             "non_authoritative":True,"agent_id":agent_id},
        ))
        self.store.commit()
        return {"handle":handle,"revision":self.revision,"compiled_revision":value.get("revision"),"task_terms":task_terms,
                "agent_id":agent_id,"records":records,"feedback_is_attention_prior_not_source_truth":True}

    def context_efficiency(self, handle: str) -> dict:
        """Report source-context utilization without pretending bytes are model tokens."""
        value = self.store.load_json("context_slices", handle)
        if not value: raise KeyError(handle)
        faults = [dict(r) for r in self.store.context_faults_for_handle(handle)]
        feedback = [dict(r) for r in self.store.context_feedback_for_handle(handle)]
        fetched_objects = []
        seen=set()
        for row in faults:
            if row["object_id"] not in seen:
                seen.add(row["object_id"]); fetched_objects.append(row["object_id"])
        used={r["object_id"] for r in feedback if r["verdict"]=="used"}
        unhelpful={r["object_id"] for r in feedback if r["verdict"]=="unhelpful"}
        fetched_set=set(fetched_objects)
        rated=(used|unhelpful)&fetched_set
        unrated=sorted(fetched_set-rated)
        total_bytes=sum(int(r["source_bytes"]) for r in faults)
        authority_bytes=sum(int(r["authority_bytes_read"] or 0) for r in faults)
        used_fetched=used & fetched_set
        return {
            "handle":handle,"compiled_revision":value.get("revision"),"current_revision":self.revision,
            "fault_count":len(faults),"unique_fetched_objects":len(fetched_set),"unique_page_faults":len({r["page_id"] for r in faults}),
            "duplicate_page_faults":max(0,len(faults)-len({r["page_id"] for r in faults})),
            "refetch_ratio":round(max(0,len(faults)-len({r["page_id"] for r in faults}))/len(faults),6) if faults else 0.0,
            "exact_source_bytes":total_bytes,"agent_visible_source_bytes":total_bytes,"backend_authority_bytes_read":authority_bytes,
            "authority_io_amplification":round(authority_bytes/max(1,total_bytes),4) if total_bytes else None,
            "used_objects":sorted(used_fetched),"unhelpful_objects":sorted(unhelpful & fetched_set),"unrated_objects":unrated,
            "utilization_ratio":round(len(used_fetched)/len(fetched_set),6) if fetched_set else None,
            "rated_ratio":round(len(rated)/len(fetched_set),6) if fetched_set else None,
            "source_bytes_per_used_object":round(total_bytes/len(used_fetched),2) if used_fetched else None,
            "measurement_boundary":"exact source bytes/page faults and explicit feedback; bytes are not tokens and unrated is not equivalent to useless",
        }

    def episode_efficiency(self, episode_id: str) -> dict:
        episode = self.episode_status(episode_id)
        faults=[dict(r) for r in self.store.context_faults_for_episode(episode_id)]
        handles=[]
        if episode.get("context_handle"): handles.append(episode["context_handle"])
        contexts=[self.context_efficiency(h) for h in handles if self.store.load_json("context_slices",h)]
        verifications=[x for x in episode.get("links",[]) if x.get("kind")=="verification-run"]
        statuses=[(x.get("details") or {}).get("status") for x in verifications]
        return {
            "episode_id":episode_id,"status":episode.get("status"),"context_handles":handles,
            "page_fault_count":len(faults),"exact_source_bytes":sum(int(x["source_bytes"]) for x in faults),
            "backend_authority_bytes_read":sum(int(x["authority_bytes_read"] or 0) for x in faults),
            "contexts":contexts,"verification_runs":len(verifications),"verification_statuses":statuses,
            "outcome":episode.get("outcome"),
            "measurement_boundary":"process efficiency/provenance only; verification success does not prove every fetched context object was useful",
        }

    def residency_configure(self, max_objects: int = 32, max_source_bytes: int = 120_000) -> dict:
        self.reconcile(); return ContextResidency(self).configure(max_objects, max_source_bytes)

    def residency_admit(self, handle: str, pin_top: int = 0, max_admit: int | None = None) -> dict:
        if pin_top < 0 or pin_top > 500: raise ValueError("pin_top must be in [0, 500]")
        return ContextResidency(self).admit(handle, pin_top=pin_top, max_admit=max_admit)

    def residency_status(self) -> dict:
        return ContextResidency(self).status()

    def residency_materialize(self, max_source_bytes: int | None = None, max_objects: int | None = None) -> dict:
        return ContextResidency(self).materialize(max_source_bytes, max_objects)

    def residency_touch(self, object_ids: list[str]) -> dict:
        self.reconcile(); return ContextResidency(self).touch(object_ids)

    def residency_pin(self, object_ids: list[str], pinned: bool = True) -> dict:
        self.reconcile(); return ContextResidency(self).pin(object_ids, pinned)

    def residency_evict(self, object_ids: list[str] | None = None, stale_only: bool = False) -> dict:
        if object_ids is not None and not isinstance(object_ids, list):
            raise TypeError("object_ids must be a list when provided")
        if object_ids is not None and not all(isinstance(x, str) and x for x in object_ids):
            raise TypeError("object_ids must contain non-empty strings")
        self.reconcile(); return ContextResidency(self).evict(object_ids, stale_only=stale_only)

    def trace_start(self, label: str = "agent-run") -> dict:
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ValueError("trace label must be 1..200 characters")
        active = self.store.active_trace()
        if active:
            raise RuntimeError(f"trace already active: {active['id']}")
        now = utc_now(); tid = stable_id("trace", label, now)
        self.store.create_trace(tid, label.strip(), now, self.revision)
        return {"trace_id": tid, "label": label.strip(), "started_at": now, "start_revision": self.revision, "active": True}

    def _trace_summary(self, trace_id: str) -> dict:
        session = self.store.trace_by_id(trace_id)
        if not session: raise KeyError(trace_id)
        calls = [dict(r) for r in self.store.trace_calls(trace_id)]
        methods = Counter(r["method"] for r in calls)
        return {
            "trace_id": trace_id, "label": session["label"], "active": bool(session["active"]),
            "started_at": session["started_at"], "stopped_at": session["stopped_at"],
            "start_revision": session["start_revision"], "end_revision": session["end_revision"],
            "call_count": len(calls), "ok_calls": sum(int(r["ok"]) for r in calls),
            "duration_ms": sum(int(r["duration_ms"]) for r in calls),
            "request_bytes": sum(int(r["request_bytes"]) for r in calls),
            "response_bytes": sum(int(r["response_bytes"]) for r in calls),
            "exact_source_bytes": sum(int(r["source_bytes"]) for r in calls),
            "methods": dict(methods), "calls": calls,
        }

    def trace_status(self, trace_id: str | None = None) -> dict:
        if trace_id is not None and (not isinstance(trace_id, str) or not trace_id):
            raise TypeError("trace_id must be a non-empty string when provided")
        if trace_id is None:
            row = self.store.active_trace()
            if not row: return {"active": False, "trace_id": None}
            trace_id = row["id"]
        return self._trace_summary(trace_id)

    def trace_stop(self, trace_id: str | None = None) -> dict:
        if trace_id is not None and (not isinstance(trace_id, str) or not trace_id):
            raise TypeError("trace_id must be a non-empty string when provided")
        if trace_id is None:
            row = self.store.active_trace()
            if not row: raise RuntimeError("no active trace")
            trace_id = row["id"]
        row = self.store.trace_by_id(trace_id)
        if not row: raise KeyError(trace_id)
        if row["active"]:
            self.store.stop_trace(trace_id, utc_now(), self.revision)
        return self._trace_summary(trace_id)

    def record_trace_call(self, method: str, ok: bool, duration_ms: int, request_bytes: int, response_bytes: int, source_bytes: int) -> None:
        active = self.store.active_trace()
        if not active: return
        self.store.append_trace_call(active["id"], method, ok, duration_ms, request_bytes, response_bytes, source_bytes, self.revision, utc_now())

    def read_source(self, path: str, start_line: int = 1, max_lines: int = 200) -> dict:
        if start_line < 1 or max_lines < 1 or max_lines > 2000:
            raise ValueError("invalid source paging bounds")
        row = self.store.file_by_path(path)
        if not row:
            raise FileNotFoundError(path)
        cache = self.store.load_compile_cache(row["id"]) or {}
        source_io = ((cache.get("metadata") or {}).get("source_io") or {})
        total_lines = int(source_io.get("line_count") or 0)
        end_line = start_line + max_lines - 1
        if total_lines:
            end_line = min(end_line, total_lines)
        page = self.read_source_line_range(path, start_line, end_line)
        text = page["text"]
        visible_lines = text.splitlines()
        actual_end = start_line + len(visible_lines) - 1 if visible_lines else start_line - 1
        next_line = actual_end + 1 if total_lines and actual_end < total_lines else None
        return {"path": path, "revision": self.revision, "digest": row["digest"], "start_line": start_line,
                "end_line": actual_end, "total_lines": total_lines or None, "source": text.rstrip("\r\n"),
                "next_line": next_line, "authority": "authoritative-source-range",
                "agent_visible_source_bytes": page["agent_visible_source_bytes"],
                "backend_authority_bytes_read": page["backend_authority_bytes_read"],
                "encoding": page["encoding"], "lossy_text": page["lossy_text"], "newline": page["newline"]}

    def _require_active_episode(self, episode_id: str) -> dict:
        row = self.store.episode(episode_id)
        if not row: raise KeyError(episode_id)
        if row["status"] != "active": raise ValueError(f"work episode is not active: {episode_id}")
        return dict(row)

    def _causal_edge(self, source_kind: str, source_ref: str, relation: str, target_kind: str, target_ref: str, details: dict | None = None) -> int:
        return self.store.append_causal_edge(source_kind, source_ref, relation, target_kind, target_ref, self.revision, details or {}, utc_now())

    def change_plan(self, operations: list[dict]) -> dict:
        if not isinstance(operations,list) or not operations: raise ValueError("operations must be a non-empty list")
        decisions=[]; order={"low":0,"medium":1,"high":2,"critical":3}; max_risk="low"
        structural_ops={"create_file","delete_file","move_file"}
        for idx,op in enumerate(operations):
            if not isinstance(op,dict): raise TypeError("each mutation operation must be an object")
            kind=op.get("op")
            paths=[op.get("from_path"),op.get("to_path")] if kind=="move_file" else [op.get("path")]
            if kind=="replace_symbol_source" and not op.get("path"):
                sym=self.store.symbol_by_id(op.get("symbol_id")) if isinstance(op.get("symbol_id"),str) else None
                paths=[sym["path"]] if sym else []
            for path in [x for x in paths if isinstance(x,str) and x]:
                d=self.policy.evaluate_source("edit",path,structural=kind in structural_ops)
                dd=d.as_dict(); dd.update({"operation_index":idx,"op":kind,"path":path}); decisions.append(dd)
                if order[d.risk]>order[max_risk]: max_risk=d.risk
        return {"revision":self.revision,"operation_count":len(operations),"decisions":decisions,"risk":max_risk,
                "allowed_without_approval":all(x["allowed"] for x in decisions),
                "approval_required":any(x["approval_required"] for x in decisions),
                "denied":any((not x["allowed"] and not x["approval_required"]) for x in decisions),
                "side_effects":False,"claim_boundary":"Policy preflight only; source digests, semantic anchors and transaction preconditions are validated again during staging/commit."}

    def stage_change(self, operations: list[dict], episode_id: str | None = None, agent_id: str | None = None, lease_ttl_s: float = 120.0, approval_id: str | None = None) -> dict:
        episode = self._require_active_episode(episode_id) if episode_id is not None else None
        if agent_id is not None and not self.store.agent_session(agent_id): raise KeyError(agent_id)
        # Policy and lease checks happen before MutationEngine.begin(), which itself may persist a staged transaction.
        paths=[]; approval_needed=False
        structural_ops={"create_file","delete_file","move_file"}
        for op in operations:
            if not isinstance(op,dict): raise TypeError("each mutation operation must be an object")
            kind=op.get("op")
            op_paths=[op.get("from_path"),op.get("to_path")] if kind=="move_file" else [op.get("path")]
            if kind=="replace_symbol_source" and not op.get("path"):
                sym=self.store.symbol_by_id(op.get("symbol_id")) if isinstance(op.get("symbol_id"),str) else None
                op_paths=[sym["path"]] if sym else []
            for path in [x for x in op_paths if isinstance(x,str) and x]:
                decision=self.policy.evaluate_source("edit",path,structural=kind in structural_ops)
                if not decision.allowed:
                    if decision.approval_required:
                        approval_needed=True
                    else:
                        raise PermissionError(decision.reason)
                paths.append(path)
        if approval_needed and not self._consume_approval(approval_id,action="edit",resource=None,agent_id=agent_id):
            raise PermissionError("source mutation requires a valid host approval token")
        acquired=[]
        if agent_id is not None:
            for path in sorted(set(paths)):
                lease=self.lease_acquire(agent_id,"path",path,lease_ttl_s)
                if not lease.get("acquired"):
                    for held in acquired: self.store.release_lease("path",held,agent_id)
                    raise TransactionConflict(f"path is leased by another agent: {path}")
                acquired.append(path)
        try:
            tx_obj=MutationEngine(self).begin(operations)
            tx_obj.owner_agent_id=agent_id; tx_obj.lease_resources=sorted(set(acquired))
            self.store.save_json("transactions",tx_obj.id,tx_obj.__dict__)
            tx = to_dict(tx_obj)
            if agent_id is not None:
                import time
                for path in acquired:
                    self.store.acquire_lease("path",path,agent_id,self.revision,utc_now(),time.time()+float(lease_ttl_s),tx_obj.id)
        except Exception:
            if agent_id is not None:
                for held in acquired: self.store.release_lease("path",held,agent_id)
            raise
        if episode_id is not None:
            self.store.append_episode_link(episode_id, "transaction-staged", tx["id"], self.revision,
                                           {"base_revision":tx["base_revision"],"operation_count":len(tx.get("operations") or []),
                                            "preview_paths":[x.get("path") for x in tx.get("preview",[]) if x.get("path")]}, utc_now())
            self._causal_edge("episode", episode_id, "contains", "transaction", tx["id"], {"phase":"staged"})
            if episode.get("context_handle"):
                self._causal_edge("context", episode["context_handle"], "informed", "transaction", tx["id"], {"episode_id":episode_id})
            self.store.commit()
        self._activity_safe("transaction.staged","mutation",agent_id=agent_id,episode_id=episode_id,ref_id=tx["id"],status="staged",summary=f"staged transaction {tx['id']}",data={"paths":sorted(set(paths)),"operation_count":len(operations)})
        return tx

    def stage_symbol_change(self, symbol_id: str, new_source: str, episode_id: str | None = None, agent_id: str | None = None) -> dict:
        return self.stage_change([{"op": "replace_symbol_source", "symbol_id": symbol_id, "new_source": new_source}], episode_id, agent_id)

    def stage_symbol_rename(self, symbol_id: str, new_name: str, episode_id: str | None = None, agent_id: str | None = None) -> dict:
        """Stage a fail-closed project-wide semantic rename when a precision provider can prove references."""
        self.reconcile()
        symbol=self.store.symbol_by_id(symbol_id)
        if not symbol:
            raise KeyError(symbol_id)
        if symbol["trust"] == "heuristic":
            raise TransactionConflict("semantic rename refuses heuristic symbol anchors")
        proposal=python_rename_sites(self.source_root, symbol, new_name)
        if proposal.get("outside_project_references"):
            raise TransactionConflict("semantic rename found references outside the project root; refusing incomplete mutation")
        operations=[]
        digest_by_path={}
        for site in proposal["sites"]:
            fr=self.store.file_by_path(site["path"])
            if not fr:
                raise TransactionConflict(f"semantic rename reference is not indexed: {site['path']}")
            digest_by_path[site["path"]]=fr["digest"]
            operations.append({"op":"replace_span",**site,"expected_digest":fr["digest"]})
        if not operations:
            raise TransactionConflict("semantic rename produced no exact project references")
        tx=self.stage_change(operations, episode_id, agent_id)
        tx["semantic_rename"]={k:v for k,v in proposal.items() if k!="sites"}
        tx["semantic_rename"]["paths"]=sorted(digest_by_path)
        return tx

    def commit_change(self, txid: str, agent_id: str | None = None) -> dict:
        txmeta=self.store.load_json("transactions",txid)
        if not txmeta: raise KeyError(txid)
        owner=txmeta.get("owner_agent_id")
        if owner is not None and agent_id != owner:
            raise PermissionError("transaction is owned by another agent; commit requires owner agent_id")
        if owner is not None:
            held={(r["resource_kind"],r["resource_id"]):r for r in self.store.lease_rows(owner)}
            for path in txmeta.get("lease_resources") or []:
                if ("path",path) not in held: raise TransactionConflict(f"agent lease expired before commit: {path}")
            pending=[r for r in self.store.agent_notifications(owner,"pending",1000) if r["kind"]=="source-invalidated"]
            if pending:
                ids=",".join(r["id"] for r in pending[:5])
                raise TransactionConflict(f"agent cognition has pending source invalidation; selective revalidation required before commit: {ids}")
        linked_episodes=[r["episode_id"] for r in self.store.episodes_for_ref(txid)]
        for episode_id in linked_episodes:
            self._require_active_episode(episode_id)
        engine = MutationEngine(self); result = to_dict(engine.apply(engine.load(txid)))
        for row in self.store.episodes_for_ref(txid):
            episode_id=row["episode_id"]
            committed = result.get("committed_revision") or self.revision
            self.store.append_episode_link(episode_id, "transaction-committed", committed, self.revision,
                                           {"transaction_id":txid,"changed_paths":result.get("changed_paths") or [],
                                            "semantic_diff":result.get("semantic_diff") or {}}, utc_now())
            self._causal_edge("transaction", txid, "produced", "revision", committed, {"episode_id":episode_id,"changed_paths":result.get("changed_paths") or []})
        self.store.commit()
        notifications=self._notify_observers(result.get("changed_paths") or [],owner_agent_id=owner,transaction_id=txid)
        if notifications: result["coordination_notifications"]=notifications
        if owner is not None:
            for path in txmeta.get("lease_resources") or []: self.store.release_lease("path",path,owner)
        self._activity_safe("transaction.committed","mutation",agent_id=owner,ref_id=txid,status="committed",summary=f"committed {txid}",data={"changed_paths":result.get("changed_paths") or [],"committed_revision":result.get("committed_revision") or self.revision,"rebased_from_revision":result.get("rebased_from_revision")})
        return result

    def rollback_change(self, txid: str, agent_id: str | None = None) -> dict:
        txmeta=self.store.load_json("transactions",txid)
        if not txmeta: raise KeyError(txid)
        owner=txmeta.get("owner_agent_id")
        if owner is not None and agent_id != owner: raise PermissionError("transaction is owned by another agent; rollback requires owner agent_id")
        engine = MutationEngine(self); result = to_dict(engine.rollback_committed(engine.load(txid)))
        for row in self.store.episodes_for_ref(txid):
            self.store.append_episode_link(row["episode_id"], "transaction-rolled-back", result.get("committed_revision"), self.revision,
                                           {"transaction_id":txid,"changed_paths":result.get("changed_paths") or []}, utc_now())
        if owner is not None:
            for path in txmeta.get("lease_resources") or []: self.store.release_lease("path",path,owner)
        self._activity_safe("transaction.rolled-back","mutation",agent_id=owner,ref_id=txid,status="rolled-back",summary=f"rolled back {txid}",data={"changed_paths":result.get("changed_paths") or []})
        return result

    def change(self, operations: list[dict]) -> dict:
        tx = self.stage_change(operations); return self.commit_change(tx["id"])

    def evidence_active(self, kind: str | None = None, limit: int = 100) -> dict:
        self.reconcile()
        if limit < 1 or limit > 2000: raise ValueError("limit must be in [1, 2000]")
        rows=self.store.active_evidence(kind,limit)
        out=[]
        for r in rows:
            d=dict(r); d["active"]=bool(d["active"])
            try: d["data"]=json.loads(d.pop("data_json"))
            except Exception: d["data"]={}; d.pop("data_json",None)
            out.append(d)
        return {"revision":self.revision,"kind":kind,"count":len(out),"evidence":out}

    def _record_verification_evidence(self, receipt, selected: list[str], mode: str) -> dict:
        structured=receipt.structured or {}
        status=structured.get("status")
        created=utc_now(); recorded=[]; resolved=0; resolved_ids=[]
        if status == "passed":
            if mode == "full-suite":
                # A "full suite" is only full for the capability/environment that produced this receipt.
                # Do not resolve failures from other runners (e.g. E2E/mobile/integration) implicitly.
                resolved_ids=self.store.active_evidence_ids(kind="test-failure",source=receipt.capability)
                resolved=self.store.resolve_evidence(kind="test-failure",source=receipt.capability)
            elif selected:
                resolved_ids=self.store.active_evidence_ids(kind="test-failure",paths=selected)
                resolved=self.store.resolve_evidence(kind="test-failure",paths=selected)
        else:
            failed=list(structured.get("failed_tests") or [])
            if not failed and receipt.exit_code not in {0,None}: failed=[f"{receipt.capability} exited {receipt.exit_code}"]
            for name in failed[:100]:
                raw_path=str(name).split("::",1)[0].replace("\\","/")
                path=raw_path if self.store.file_by_path(raw_path) else (selected[0] if len(selected)==1 else None)
                eid=stable_id("evidence","test-failure",receipt.id,str(name))
                value={"id":eid,"kind":"test-failure","revision":self.revision,"path":path,"severity":"error",
                       "summary":f"Test failure: {name}","trust":"exact","source":receipt.capability,"created_at":created,"active":True,
                       "data":{"run_id":receipt.id,"failed_test":name,"exit_code":receipt.exit_code,"selection_mode":mode,"selected_test_files":selected,
                               "environment_fingerprint":receipt.environment_fingerprint}}
                self.store.append_evidence(value); recorded.append(eid)
            failed_total=int(structured.get("failed_tests_total") or len(failed))
            if bool(structured.get("failed_tests_truncated")) or failed_total>len(failed):
                omitted=max(0,failed_total-len(failed))
                eid=stable_id("evidence","test-failure-overflow",receipt.id)
                value={"id":eid,"kind":"test-failure","revision":self.revision,"path":None,"severity":"error",
                       "summary":f"{omitted} additional failing test name(s) omitted from bounded structured receipt",
                       "trust":"exact","source":receipt.capability,"created_at":created,"active":True,
                       "data":{"run_id":receipt.id,"failed_tests_total":failed_total,"named_failures_retained":len(failed),"omitted_failure_names":omitted,
                               "selection_mode":mode,"environment_fingerprint":receipt.environment_fingerprint,"bounded_presentation":True}}
                self.store.append_evidence(value); recorded.append(eid)
        return {"recorded_evidence_ids":recorded,"resolved_prior_failures":resolved,"resolved_evidence_ids":resolved_ids}

    def run(self, capability_id: str, timeout_s: int = 60, approval_id: str | None = None) -> dict:
        self.reconcile()
        caps = {c["id"]: c for c in self.backend.discover_capabilities()}
        if capability_id not in caps: raise KeyError(f"unknown capability: {capability_id}")
        capability = caps[capability_id]
        if not capability.get("available", False):
            raise RuntimeError(f"capability unavailable: {capability_id}: {capability.get('availability_reason')}")
        decision=self.policy.evaluate_execution(capability,sandboxed="full-sandbox" in set(self.backend.execution_provider.info.capabilities))
        if not decision.allowed:
            if not (decision.approval_required and self._consume_approval(approval_id,action="execute",resource=capability_id,agent_id=None)):
                raise PermissionError(decision.reason)
        observed_revision=self.revision
        self._activity_safe("execution.started","execution",ref_id=capability_id,status="running",summary=f"running {capability_id}",data={"timeout_s":timeout_s,"workspace_revision":observed_revision})
        receipt = self.backend.run(capability, timeout_s)
        stored_receipt=to_dict(receipt); stored_receipt["workspace_revision"]=observed_revision
        self.store.save_json("runs", receipt.id, stored_receipt)
        self._activity_safe("execution.completed","execution",ref_id=receipt.id,status=(receipt.structured or {}).get("status") or ("passed" if receipt.exit_code==0 else "failed"),summary=f"{capability_id} completed",data={"capability_id":capability_id,"exit_code":receipt.exit_code,"changed_paths":receipt.changed_paths})
        if receipt.changed_paths: self.refresh(reason=f"execution:{receipt.id}")
        value=dict(stored_receipt); value["policy_decision"]=decision.as_dict(); return value

    def verification_plan(self, changed_paths: list[str] | None = None, object_ids: list[str] | None = None) -> dict:
        self.reconcile()
        impact = affected_tests(self.store, changed_paths, object_ids, max_depth=5)
        test_caps = [c for c in self.backend.discover_capabilities() if c["kind"] == "test" and c["available"]]
        linked = [x["path"] for x in impact["ranked_test_files"]]
        targeted_support = []
        for c in test_caps:
            if c["id"] in {"python.unittest", "python.pytest"}:
                targeted_support.append({"capability": c["id"], "mode": "file-targeted", "trust": "exact"})
            else:
                targeted_support.append({"capability": c["id"], "mode": "full-suite-fallback", "trust": "derived"})
        unknowns = list(impact["unknowns"])
        if not test_caps:
            unknowns.append("No runnable test capability was discovered.")
        return {
            "revision": self.revision, "changed_paths": impact["changed_paths"], "linked_test_files": linked,
            "ranked_test_files": impact["ranked_test_files"], "impact_confidence": impact["confidence"],
            "graph_edges_examined": impact["graph_edges_examined"], "test_capabilities": test_caps,
            "targeted_support": targeted_support,
            "minimality": "ranked tests are graph-derived candidates; targeted execution is used only for supported frameworks",
            "unknowns": unknowns,
        }

    def verify(self, changed_paths: list[str] | None = None, object_ids: list[str] | None = None, timeout_s: int = 60, episode_id: str | None = None) -> dict:
        if episode_id is not None:
            self._require_active_episode(episode_id)
        self.reconcile()
        verified_revision=self.revision
        plan = self.verification_plan(changed_paths, object_ids)
        self._activity_safe("verification.started","verification",episode_id=episode_id,status="running",summary="verification started",data={"changed_paths":changed_paths or [],"object_ids":object_ids or [],"candidate_test_files":plan.get("linked_test_files") or []})
        caps = plan["test_capabilities"]
        if not caps:
            raise RuntimeError("no runnable test capability discovered")
        paths = [x["path"] for x in plan["ranked_test_files"]]
        # Prefer deterministic file-targeted Python runners. Paths come only from the indexed source root.
        cap = next((c for c in caps if c["id"] == "python.pytest"), None) or next((c for c in caps if c["id"] == "python.unittest"), None) or caps[0]
        argv = list(cap["argv"]); mode = "full-suite"
        selected = []
        if paths and cap["id"] == "python.pytest":
            selected = [p for p in paths if p.endswith(".py") and self.source_is_file(p)]
            if selected:
                argv = [argv[0], "-m", "pytest", "-q", *selected]; mode = "targeted-files"
        elif paths and cap["id"] == "python.unittest":
            py_paths = [p for p in paths if p.endswith(".py") and self.source_is_file(p)]
            modules = [Path(p).with_suffix("").as_posix().replace("/", ".") for p in py_paths]
            if modules:
                selected = py_paths; argv = [argv[0], "-m", "unittest", "-v", *modules]; mode = "targeted-modules"
        decision=self.policy.evaluate_execution(cap,sandboxed="full-sandbox" in set(self.backend.execution_provider.info.capabilities))
        if not decision.allowed: raise PermissionError(decision.reason)
        receipt = self.backend.run(cap, timeout_s, argv_override=argv)
        if receipt.structured is None:
            receipt.structured = {}
        receipt.structured["selection"] = {
            "mode": mode, "selected_test_files": selected, "candidate_test_files": paths,
            "impact_confidence": plan["impact_confidence"],
        }
        stored_receipt=to_dict(receipt); stored_receipt["workspace_revision"]=verified_revision
        self.store.save_json("runs", receipt.id, stored_receipt)
        evidence=self._record_verification_evidence(receipt, selected, mode)
        if receipt.changed_paths:
            self.refresh(reason=f"verification:{receipt.id}")
        if episode_id is not None:
            self.store.append_episode_link(episode_id, "verification-run", receipt.id, self.revision,
                                           {"status":(receipt.structured or {}).get("status"),"exit_code":receipt.exit_code,
                                            "selection":(receipt.structured or {}).get("selection"),"evidence":evidence}, utc_now())
            self._causal_edge("episode", episode_id, "verified_with", "run", receipt.id, {"status":(receipt.structured or {}).get("status")})
            self._causal_edge("run", receipt.id, "observed", "revision", self.revision, {"selection_mode":mode,"selected_test_files":selected})
            for eid in evidence.get("recorded_evidence_ids") or []:
                self._causal_edge("run", receipt.id, "generated", "evidence", eid, {"episode_id":episode_id})
            for eid in evidence.get("resolved_evidence_ids") or []:
                self._causal_edge("evidence", eid, "resolved_by", "run", receipt.id, {"episode_id":episode_id})
        self.store.commit()
        vstatus=(receipt.structured or {}).get("status") or ("passed" if receipt.exit_code==0 else "failed")
        self._activity_safe("verification.completed","verification",episode_id=episode_id,ref_id=receipt.id,status=vstatus,summary=f"verification {vstatus}",data={"exit_code":receipt.exit_code,"selection_mode":mode,"selected_test_files":selected,"recorded_evidence_ids":evidence.get("recorded_evidence_ids") or []})
        return {"plan": plan, "receipt": stored_receipt, "evidence": evidence, "episode_id": episode_id, "policy_decision":decision.as_dict()}

    def events_poll(self, since_seq: int = 0, limit: int = 200, reconcile: bool = True) -> dict:
        if since_seq < 0 or limit < 1 or limit > 2000:
            raise ValueError("invalid event bounds")
        if reconcile:
            self.reconcile()
        rows = self.store.events_since(since_seq, limit)
        events=[]
        for r in rows:
            d=dict(r)
            try:
                d["details"] = json.loads(d.pop("details_json"))
            except Exception:
                d["details"] = {}; d.pop("details_json", None)
            events.append(d)
        latest=self.store.latest_event_seq()
        next_seq=events[-1]["seq"] if events else since_seq
        return {"since_seq": since_seq, "next_seq": next_seq, "latest_seq": latest, "events": events, "has_more": next_seq < latest}

    def watch_start(self, interval_s: float = 0.25) -> dict:
        if not self.backend.info.supports_native_watch:
            raise RuntimeError(f"backend {self.backend.info.kind} does not expose a native watch surface; use events.poll/reconcile")
        if self._source_watcher is not None:
            self._source_watcher.close()
        self._source_watcher = PollingSourceWatcher(self.source_root, interval_s=interval_s)
        self._source_watcher.start()
        value = self._source_watcher.status()
        value.update({"revision": self.revision, "event_cursor": self.store.latest_event_seq()})
        return value

    def _admit_watch_observations(self, observations: list[dict], reason: str) -> dict:
        if not observations:
            return {"observations": [], "candidate_paths": [], "refresh": None, "revision": self.revision}
        paths = sorted({p for item in observations for p in item.get("paths", [])})
        refresh = self.refresh_paths(paths, reason=reason) if paths else None
        self.store.append_event(EventRecord(
            kind="watch-observation", path=None, observed_at=utc_now(), revision_before=None,
            revision_after=self.revision, source="source-watcher",
            details={"candidate_paths": paths, "observation_count": len(observations),
                     "metadata_only_detector": True, "refresh_mode": refresh.get("refresh_mode") if refresh else None},
        ))
        self.store.commit()
        return {"observations": observations, "candidate_paths": paths, "refresh": refresh, "revision": self.revision}

    def watch_poll(self, limit: int = 64) -> dict:
        if self._source_watcher is None:
            raise RuntimeError("source watcher is not running")
        return self._admit_watch_observations(self._source_watcher.poll(limit), "watcher-poll")

    def watch_wait(self, timeout_s: float = 5.0, limit: int = 64) -> dict:
        if self._source_watcher is None:
            raise RuntimeError("source watcher is not running")
        return self._admit_watch_observations(self._source_watcher.wait(timeout_s, limit), "watcher-wait")

    def watch_status(self) -> dict:
        if self._source_watcher is None:
            return {"running": False, "revision": self.revision}
        value = self._source_watcher.status(); value["revision"] = self.revision
        return value

    def watch_stop(self) -> dict:
        if self._source_watcher is None:
            return {"running": False, "stopped": False, "revision": self.revision}
        value = self._source_watcher.status()
        self._source_watcher.close(); self._source_watcher = None
        return {"running": False, "stopped": True, "previous": value, "revision": self.revision}

    def state_merkle(self, revision_id: str | None = None, prefix: str = "") -> dict:
        """Return content-addressed state for a project subtree without reading project bytes."""
        self.reconcile()
        revision_id = revision_id or self.revision
        row = self.store.merkle_snapshot_row(revision_id)
        if not row:
            raise KeyError(f"no Merkle snapshot for revision: {revision_id}")
        node = resolve_merkle_path(self.store, row["root_hash"], prefix)
        if node is None:
            raise KeyError(prefix)
        return {"revision": revision_id, "project_root_hash": row["root_hash"], "prefix": prefix, "node": node,
                "snapshot": {"file_count": row["file_count"], "byte_size": row["byte_size"]},
                "storage": self.store.merkle_stats(), "source_bytes_read": 0}

    def state_merkle_diff(self, from_revision: str, to_revision: str | None = None, prefix: str = "") -> dict:
        self.reconcile()
        to_revision = to_revision or self.revision
        old = self.store.merkle_snapshot_row(from_revision); new = self.store.merkle_snapshot_row(to_revision)
        if not old: raise KeyError(f"no Merkle snapshot for revision: {from_revision}")
        if not new: raise KeyError(f"no Merkle snapshot for revision: {to_revision}")
        result = diff_merkle_roots(self.store, old["root_hash"], new["root_hash"], prefix)
        result.update({"from_revision": from_revision, "to_revision": to_revision, "source_bytes_read": 0})
        return result

    def diff_since(self, revision_id: str) -> dict:
        self.reconcile()
        if not self.store.revision(revision_id):
            raise KeyError(revision_id)
        if revision_id == self.revision:
            return {"from_revision": revision_id, "to_revision": self.revision, "changed_paths": [], "revisions": []}
        chain=[]; cur=self.revision; guard=0
        while cur and cur != revision_id and guard < 10000:
            row=self.store.revision(cur)
            if not row: break
            chain.append(dict(row)); cur=row["parent_id"]; guard += 1
        if cur != revision_id:
            return {"from_revision": revision_id, "to_revision": self.revision, "reachable": False, "changed_paths": [], "revisions": chain}
        paths=set()
        for row in chain:
            try: paths.update(json.loads(row["changed_paths"]))
            except Exception: pass
        return {"from_revision": revision_id, "to_revision": self.revision, "reachable": True, "changed_paths": sorted(paths), "revisions": chain}

    def semantic_provider_report(self) -> dict:
        self.reconcile()
        ts_ok, ts_reason = TypeScriptCompilerProvider().available()
        from .semantic.python_jedi import probe as jedi_probe
        jedi_ok, jedi_reason, jedi_version = jedi_probe()
        import shutil
        return {
            "revision": self.revision,
            "providers": {
                "python-ast": {"available": True, "scope": "file syntax + project import/call linkage", "trust_ceiling": "semantic"},
                "python-jedi": {**({"available": jedi_ok, "reason": jedi_reason, "version": jedi_version, "scope": "static cross-file Python goto/call resolution with persistent per-source semantic partitions and a bounded 4-project Jedi LRU", "trust_ceiling": "semantic", "live_session": jedi_project_status(self.source_root)}), **((self.store.load_project_cache("semantic-python-jedi-summary-v2") or {}).get("report") or {})},
                "typescript-program": {**{"available": ts_ok, "reason": ts_reason, "scope": "persistent TypeScript LanguageService/TypeChecker with dirty-source traversal partitions", "trust_ceiling": "semantic", "live_session": typescript_session_status(self.source_root)}, **((self.store.load_project_cache("semantic-typescript-summary-v8") or {}).get("report") or {})},
                "tree-sitter": {"available": False, "reason": "Python tree-sitter bindings are not bundled; optional provider contract reserved", "trust_ceiling": "parser"},
                "scip": {"available": bool(shutil.which("scip")), "reason": "external SCIP indexer/CLI required for precise index ingestion", "trust_ceiling": "semantic"},
                "lsp": {"available": bool(shutil.which("pyright-langserver") or shutil.which("typescript-language-server")), "reason": "external language server required", "trust_ceiling": "semantic"},
                "java": {"available": True, "provider": "regex-fallback", "reason": "javac is intentionally not executed during ingestion", "trust_ceiling": "heuristic"},
            },
            "policy": "missing precise providers are explicit capability gaps; Habitat does not relabel fallback output as precise",
        }


    def observe_ui(self, relpath: str) -> dict:
        self.reconcile(); return observe_html(self.source_root, relpath)

    def _runtime(self) -> BrowserRuntime:
        if self._browser_runtime is None:
            self._browser_runtime = BrowserRuntime(self.source_root, self.habitat_dir / "artifacts" / "ui")
        return self._browser_runtime

    def _enrich_ui_source(self, obs: dict) -> dict:
        rel = obs.get("target_path")
        if not rel: return obs
        css_rules = [s for s in self.store.all_symbols() if s["kind"] == "css-rule"]
        for e in obs.get("elements", []):
            hints = []
            attrs = e.get("attrs", {})
            dom_id = attrs.get("id")
            testid = attrs.get("data-testid")
            name_attr = attrs.get("name")
            semantic_key = dom_id or testid or (f"name:{name_attr}" if name_attr and e.get("tag") in {"input","textarea","select","button","form"} else None)
            if semantic_key:
                oid = stable_id("ui", rel, "element", semantic_key)
                sr = self.store.symbol_by_id(oid)
                if sr:
                    relation = "same-dom-id" if dom_id else "same-data-testid" if testid else "same-name-anchor"
                    hints.append({"object_id": oid, "path": rel, "line": sr["start_line"], "relation": relation, "trust": "parser"})
                # Framework-aware static ownership lane: TSX/JSX parser anchors are correlated by explicit
                # runtime id/data-testid only.  Habitat does not promote this to semantic truth because a
                # build transform could duplicate or rewrite the attribute.  Unique anchors are parser-grade;
                # duplicates remain heuristic candidates.
                candidates = [x for x in self.store.all_symbols() if x["kind"] == "ui-element" and x["name"] == semantic_key
                              and Path(x["path"]).suffix.lower() in {".tsx", ".jsx"}]
                anchor_trust = "parser" if len(candidates) == 1 else "heuristic"
                for candidate in candidates[:6]:
                    hints.append({"object_id": candidate["id"], "path": candidate["path"], "line": candidate["start_line"],
                                  "relation": "framework-jsx-anchor", "trust": anchor_trust})
                    for edge in self.store.incoming_relations(candidate["id"], "renders")[:4]:
                        owner = self.store.symbol_by_id(edge["source_id"])
                        if owner:
                            hints.append({"object_id": owner["id"], "path": owner["path"], "line": owner["start_line"],
                                          "relation": "framework-render-owner",
                                          "trust": "parser" if anchor_trust == "parser" and edge["trust"] != "heuristic" else "heuristic"})
                    for edge in [r for r in self.store.relations_for(candidate["id"]) if r["source_id"] == candidate["id"] and r["kind"] == "handles_event"][:6]:
                        handler = self.store.symbol_by_id(edge["target_id"])
                        if handler:
                            event = "event"
                            m = re.search(r"JSX on([a-zA-Z0-9_-]+) handler", edge["evidence"] or "")
                            if m: event = m.group(1).lower()
                            hints.append({"object_id": handler["id"], "path": handler["path"], "line": handler["start_line"],
                                          "relation": f"framework-event-handler:{event}",
                                          "trust": "parser" if anchor_trust == "parser" and edge["trust"] in {"parser","semantic"} else "heuristic"})
            # Runtime listener registration stacks identify external JS handlers without requiring DevTools UI.
            for listener in e.get("listener_evidence", [])[:20]:
                stack = listener.get("stack") or ""
                for m in re.finditer(r"https?://habitat\.local/([^\s:?#]+):(\d+):(\d+)", stack):
                    js_path = m.group(1)
                    try:
                        js_file = self.resolve_source_path(js_path)
                    except ValueError:
                        continue
                    if js_file.is_file():
                        hints.append({"object_id": self.store.file_by_path(js_path)["id"] if self.store.file_by_path(js_path) else None,
                                      "path": js_path, "line": int(m.group(2)), "column": int(m.group(3)),
                                      "relation": f"runtime-event-listener:{listener.get('type')}", "trust": "semantic"})
            classes = set((attrs.get("class") or "").split())
            for r in css_rules:
                sel = r["qualified_name"]
                if (dom_id and f"#{dom_id}" in sel) or any(f".{c}" in sel for c in classes):
                    hints.append({"object_id": r["id"], "path": r["path"], "line": r["start_line"], "relation": "selector-candidate", "trust": "heuristic"})
                    if len(hints) >= 8: break
            if hints: e["source_hints"] = hints
        return obs

    def open_ui_runtime(self, target: str, screenshot: bool = False, viewport: dict | None = None, allow_external: bool = False) -> dict:
        if allow_external:
            decision=self.policy.evaluate_browser_external()
            if not decision.allowed: raise PermissionError(decision.reason)
        self.reconcile(); value=self._enrich_ui_source(self._runtime().open(target, viewport=viewport, screenshot=screenshot, allow_external=allow_external))
        value["policy_decision"]=self.policy.evaluate_browser_external().as_dict() if allow_external else {"allowed":True,"action":"browser.local","risk":"low","reason":"project-local UI"}
        sid=value.get("session_id") if isinstance(value,dict) else None
        public_target=value.get("target") if isinstance(value,dict) else None
        self._activity_safe("ui.runtime-opened","ui",ref_id=sid,status="observing",summary=f"opened UI runtime: {public_target or '[local UI]'}"[:180],data={
            "session_id":sid,"target":public_target,"url":value.get("url") if isinstance(value,dict) else None,"title":value.get("title") if isinstance(value,dict) else None,
            "viewport":value.get("viewport") if isinstance(value,dict) else None,"operator_frame_seq":value.get("observer_frame_seq") if isinstance(value,dict) else None,
            "operator_stream_seq":((value.get("observer_stream") or {}).get("seq") if isinstance(value,dict) else None),"operator_stream_epoch":((value.get("observer_stream") or {}).get("epoch") if isinstance(value,dict) else None),
            "operator_stream_mode":((value.get("observer_stream") or {}).get("mode") if isinstance(value,dict) else None),"operator_stream_active":bool((value.get("observer_stream") or {}).get("active")) if isinstance(value,dict) else False,
            "allow_external":bool(allow_external),"screenshot":bool(screenshot)})
        return value

    def observe_ui_runtime(self, session_id: str, screenshot: bool = False) -> dict:
        value=self._enrich_ui_source(self._runtime().observe(session_id, screenshot=screenshot))
        self._activity_safe("ui.runtime-observed","ui",ref_id=session_id,status="observed",summary="observed UI runtime",data={
            "session_id":session_id,"url":value.get("url") if isinstance(value,dict) else None,"title":value.get("title") if isinstance(value,dict) else None,
            "viewport":value.get("viewport") if isinstance(value,dict) else None,"operator_frame_seq":value.get("observer_frame_seq") if isinstance(value,dict) else None,
            "operator_stream_seq":((value.get("observer_stream") or {}).get("seq") if isinstance(value,dict) else None),"operator_stream_epoch":((value.get("observer_stream") or {}).get("epoch") if isinstance(value,dict) else None),
            "operator_stream_mode":((value.get("observer_stream") or {}).get("mode") if isinstance(value,dict) else None),"operator_stream_active":bool((value.get("observer_stream") or {}).get("active")) if isinstance(value,dict) else False,
            "screenshot":bool(screenshot),"element_count":len(value.get("elements") or []) if isinstance(value,dict) else None})
        return value

    def act_ui_runtime(self, session_id: str, action: str, handle: str, value: str | None = None, screenshot: bool = False) -> dict:
        preview=None
        try:
            preview=self._runtime().preview_action(session_id, action, handle, value)
        except Exception:
            preview=None
        start_data={"session_id":session_id,"action":action,"handle":handle,"has_value":value is not None}
        if preview: start_data["action_preview"]=preview
        self._activity_safe("ui.action-started","ui",ref_id=handle,status="running",summary=f"UI {action}: {handle}"[:180],data=start_data)
        try:
            result=self._enrich_ui_source(self._runtime().act(session_id, action, handle, value, screenshot=screenshot, preview=preview))
        except Exception as exc:
            self._activity_safe("ui.action-completed","ui",ref_id=handle,status="failed",summary=f"UI {action} failed: {handle}"[:180],data={"session_id":session_id,"action":action,"handle":handle,"error":str(exc)[:400],"action_preview":preview})
            raise
        receipt=result.get("action_receipt") if isinstance(result,dict) else None
        self._activity_safe("ui.action-completed","ui",ref_id=handle,status="passed",summary=f"UI {action}: {handle}"[:180],data={
            "session_id":session_id,"action":action,"handle":handle,"screenshot":bool(screenshot),"action_receipt":receipt,
            "url":result.get("url") if isinstance(result,dict) else None,"title":result.get("title") if isinstance(result,dict) else None,
            "viewport":result.get("viewport") if isinstance(result,dict) else None,"operator_frame_seq":result.get("observer_frame_seq") if isinstance(result,dict) else None,
            "operator_stream_seq":((result.get("observer_stream") or {}).get("seq") if isinstance(result,dict) else None),"operator_stream_epoch":((result.get("observer_stream") or {}).get("epoch") if isinstance(result,dict) else None),
            "operator_stream_mode":((result.get("observer_stream") or {}).get("mode") if isinstance(result,dict) else None),"operator_stream_active":bool((result.get("observer_stream") or {}).get("active")) if isinstance(result,dict) else False})
        return result

    def assert_ui_runtime(self, session_id: str, assertions: list[dict]) -> dict:
        result = self._runtime().assert_semantic(session_id, assertions)
        result["revision"] = self.revision
        passed=bool(result.get("passed")) if isinstance(result,dict) else False
        self._activity_safe("ui.assertion","ui",ref_id=session_id,status="passed" if passed else "failed",summary=f"UI assertion {'passed' if passed else 'failed'}",data={"assertion_count":len(assertions),"passed":passed})
        return result

    def close_ui_runtime(self, session_id: str) -> dict:
        result=self._runtime().close_session(session_id)
        self._activity_safe("ui.runtime-closed","ui",ref_id=session_id,status="closed",summary="closed UI runtime",data={"session_id":session_id,"operator_stream_active":False,"ephemeral_frames_deleted":bool(result.get("ephemeral_frames_deleted"))})
        return result

    def episode_start(self, task: str, context_handle: str | None = None) -> dict:
        if not isinstance(task, str) or not task.strip(): raise ValueError("task must be a non-empty string")
        self.reconcile()
        if context_handle is not None:
            ctx=self.store.load_json("context_slices", context_handle)
            if not ctx: raise KeyError(context_handle)
            if ctx.get("revision") != self.revision:
                raise ValueError(f"stale context cannot ground a new episode: compiled={ctx.get('revision')} current={self.revision}")
        eid=stable_id("episode",self.revision,task.strip(),utc_now())
        value={"id":eid,"task":task.strip(),"context_handle":context_handle,"base_revision":self.revision,
               "backend_binding":self._backend_binding(),"compiler_fingerprint":self._compiler_state_fingerprint(),
               "status":"active","created_at":utc_now(),"outcome":{}}
        self.store.create_episode(value)
        if context_handle:
            self.store.append_episode_link(eid,"context-compiled",context_handle,self.revision,{"task":task.strip()},utc_now())
            self._causal_edge("context", context_handle, "grounds", "episode", eid, {"task":task.strip()})
            self.store.commit()
        self._activity_safe("episode.started","cognition",episode_id=eid,ref_id=eid,status="investigating",summary=task.strip()[:160],data={"task":task.strip(),"context_handle":context_handle})
        return self.episode_status(eid)

    def episode_status(self, episode_id: str) -> dict:
        row=self.store.episode(episode_id)
        if not row: raise KeyError(episode_id)
        links=[]
        for link in self.store.episode_links(episode_id):
            d=dict(link)
            try: d["details"]=json.loads(d.pop("details_json"))
            except Exception: d["details"]={}; d.pop("details_json",None)
            links.append(d)
        try: outcome=json.loads(row["outcome_json"] or "{}")
        except Exception: outcome={}
        return {"id":row["id"],"task":row["task"],"context_handle":row["context_handle"],"base_revision":row["base_revision"],
                "status":row["status"],"created_at":row["created_at"],"closed_at":row["closed_at"],"outcome":outcome,
                "backend_binding":row["backend_binding"],"current_backend_binding":self._backend_binding(),
                "backend_identity_drift":row["backend_binding"]!=self._backend_binding(),
                "compiler_fingerprint":row["compiler_fingerprint"],
                "compiler_identity_drift":row["compiler_fingerprint"]!=self._compiler_state_fingerprint(),
                "links":links,"link_count":len(links),"current_revision":self.revision}

    def episode_finish(self, episode_id: str, status: str = "completed", outcome: dict | None = None) -> dict:
        self._require_active_episode(episode_id)
        if status not in {"completed","failed","abandoned"}: raise ValueError("episode status must be completed, failed, or abandoned")
        if status == "completed":
            staged=[]
            for link in self.store.episode_links(episode_id):
                if link["kind"] != "transaction-staged" or not link["ref_id"]:
                    continue
                tx=self.store.load_json("transactions",link["ref_id"])
                if tx and tx.get("status") == "staged":
                    staged.append(link["ref_id"])
            if staged:
                raise ValueError(f"cannot complete episode with staged transactions: {staged[0]}")
        if outcome is not None and not isinstance(outcome, dict): raise TypeError("outcome must be an object")
        now=utc_now(); self.store.close_episode(episode_id,status,outcome or {},now)
        self.store.append_episode_link(episode_id,"episode-closed",None,self.revision,{"status":status,"outcome":outcome or {}},now)
        self._activity_safe("episode.finished","cognition",episode_id=episode_id,ref_id=episode_id,status=status,summary=f"episode {status}",data={"outcome":outcome or {}})
        return self.episode_status(episode_id)

    def invariant_create(self, statement: str, *, severity: str = "error", metadata: dict | None = None) -> dict:
        if not isinstance(statement,str) or not statement.strip(): raise ValueError("invariant statement must be non-empty")
        if severity not in {"info","warning","error","critical"}: raise ValueError("invalid invariant severity")
        iid=stable_id("invariant",statement.strip(),self.revision,utc_now()); now=utc_now()
        self.store.create_invariant({"id":iid,"statement":statement.strip(),"severity":severity,"status":"unverified","base_revision":self.revision,"created_at":now,"updated_at":now,"metadata":metadata or {}})
        return self.invariant_status(iid)

    def invariant_link(self, invariant_id: str, ref_kind: str, ref_id: str, *, relation: str = "witness", details: dict | None = None) -> dict:
        if ref_kind not in {"symbol","file","test","evidence","requirement","config"}: raise ValueError("unsupported invariant ref_kind")
        if relation not in {"witness","verifier","implements","constrains","contradicts"}: raise ValueError("unsupported invariant relation")
        # Fail closed for semantic object kinds Habitat can validate locally.
        if ref_kind=="symbol" and not self.store.symbol_by_id(ref_id): raise KeyError(ref_id)
        if ref_kind in {"file","test","config"} and not self.store.file_by_path(ref_id): raise KeyError(ref_id)
        if ref_kind=="evidence" and not self.store.evidence_by_id(ref_id): raise KeyError(ref_id)
        self.store.link_invariant(invariant_id,ref_kind,ref_id,relation,self.revision,details or {},utc_now())
        return self.invariant_status(invariant_id)

    def invariant_status(self, invariant_id: str) -> dict:
        row=self.store.invariant(invariant_id)
        if not row: raise KeyError(invariant_id)
        value=dict(row)
        try: value["metadata"]=json.loads(value.pop("metadata_json") or "{}")
        except Exception: value["metadata"]={}; value.pop("metadata_json",None)
        links=[]; active_verifiers=0; contradictions=0
        for r in self.store.invariant_links(invariant_id):
            d=dict(r)
            try: d["details"]=json.loads(d.pop("details_json") or "{}")
            except Exception: d["details"]={}; d.pop("details_json",None)
            if d["relation"]=="verifier": active_verifiers+=1
            if d["relation"]=="contradicts": contradictions+=1
            links.append(d)
        value["links"]=links; value["verifier_count"]=active_verifiers; value["contradiction_count"]=contradictions
        value["assessment"]="contested" if contradictions else "linked-unverified" if links else "unmapped"
        value["claim_boundary"]="Explicit project invariant registry and traceable links; Habitat does not infer invariant truth automatically from code structure."
        return value

    def invariant_update(self, invariant_id: str, status: str) -> dict:
        if status not in {"unverified","verified","violated","contested","retired"}: raise ValueError("invalid invariant status")
        if not self.store.invariant(invariant_id): raise KeyError(invariant_id)
        self.store.update_invariant(invariant_id,status,utc_now()); return self.invariant_status(invariant_id)

    def hypothesis_create(self, statement: str, *, episode_id: str | None = None, task: str | None = None, prior_confidence: float = 0.5) -> dict:
        """Create an explicit, revision-bound hypothesis rather than hiding a guess in narrative context.

        ``prior_confidence`` is an agent belief annotation, not a calibrated probability. Habitat
        never promotes it merely because retrieval found supporting words.
        """
        if not isinstance(statement,str) or not statement.strip(): raise ValueError("statement must be a non-empty string")
        if not isinstance(prior_confidence,(int,float)) or isinstance(prior_confidence,bool) or not 0.0 <= float(prior_confidence) <= 1.0:
            raise ValueError("prior_confidence must be in [0,1]")
        self.reconcile()
        episode=None
        if episode_id is not None:
            episode=self._require_active_episode(episode_id)
            if task is None: task=episode["task"]
        if task is None: task=statement.strip()
        now=utc_now(); hid=stable_id("hypothesis",self.revision,statement.strip(),now)
        value={"id":hid,"episode_id":episode_id,"task":str(task),"statement":statement.strip(),"status":"active",
               "prior_confidence":float(prior_confidence),"current_confidence":float(prior_confidence),
               "base_revision":self.revision,"created_at":now,"updated_at":now}
        self.store.create_hypothesis(value)
        if episode_id:
            self.store.append_episode_link(episode_id,"hypothesis-created",hid,self.revision,{"statement":statement.strip()},now)
            self._causal_edge("episode",episode_id,"proposes","hypothesis",hid,{"prior_confidence":float(prior_confidence)})
            self.store.commit()
        self._activity_safe("hypothesis.created","cognition",episode_id=episode_id,ref_id=hid,status="active",summary=statement.strip()[:160],data={"prior_confidence":float(prior_confidence)})
        return self.hypothesis_status(hid)

    def hypothesis_status(self, hypothesis_id: str) -> dict:
        row=self.store.hypothesis(hypothesis_id)
        if not row: raise KeyError(hypothesis_id)
        evidence=[]; support=oppose=0.0
        for r in self.store.hypothesis_evidence(hypothesis_id):
            d=dict(r); eid=d.get("evidence_id")
            ev=self.store.evidence_by_id(eid) if eid else None
            d["evidence_active"]=bool(ev["active"]) if ev else None
            if d["polarity"]=="for": support+=float(d["weight"])
            elif d["polarity"]=="against": oppose+=float(d["weight"])
            evidence.append(d)
        experiments=[]
        for r in self.store.experiments_for_hypothesis(hypothesis_id):
            d=dict(r)
            for key in ("expected_json","result_json"):
                try: d[key[:-5]]=json.loads(d.pop(key) or "{}")
                except Exception: d[key[:-5]]={}; d.pop(key,None)
            experiments.append(d)
        link_rows=[dict(r) for r in self.store.hypothesis_evidence_rows(hypothesis_id)]
        evidence_ids=[r.get("evidence_id") for r in link_rows if r.get("evidence_id")]
        evidence_map={r["id"]:dict(r) for r in self.store.evidence_by_ids(evidence_ids)}
        assessment=assess_hypothesis(link_rows,evidence_map)
        return {**dict(row),"prior_confidence":float(row["prior_confidence"]),"current_confidence":float(row["current_confidence"]),
                "confidence_semantics":"agent belief annotation; not calibrated probability",
                "evidence":evidence,"evidence_balance":{"for_weight":support,"against_weight":oppose,"net":support-oppose},
                "evidence_assessment":assessment,
                "experiments":experiments,"current_revision":self.revision,"revision_drift":row["base_revision"]!=self.revision}

    def agent_belief_update(self, agent_id: str, hypothesis_id: str, *, stance: str = "uncertain", confidence: float = 0.5, rationale: str | None = None) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if not self.store.hypothesis(hypothesis_id): raise KeyError(hypothesis_id)
        if stance not in {"support","oppose","uncertain"}: raise ValueError("stance must be support, oppose, or uncertain")
        if not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not 0.0 <= float(confidence) <= 1.0: raise ValueError("confidence must be in [0,1]")
        self.store.upsert_agent_hypothesis_belief({"agent_id":agent_id,"hypothesis_id":hypothesis_id,"stance":stance,"confidence":float(confidence),
                                                   "rationale":rationale,"base_revision":self.revision,"updated_at":utc_now()})
        return self.agent_belief_status(agent_id,hypothesis_id)

    def agent_belief_status(self, agent_id: str, hypothesis_id: str) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        h=self.hypothesis_status(hypothesis_id); row=self.store.agent_hypothesis_belief(agent_id,hypothesis_id)
        belief=dict(row) if row else {"agent_id":agent_id,"hypothesis_id":hypothesis_id,"stance":"uncertain","confidence":0.5,"rationale":None,"base_revision":self.revision,"updated_at":None}
        belief["revision_drift"]=belief.get("base_revision")!=self.revision
        belief["shared_hypothesis"]={"statement":h["statement"],"status":h["status"],"shared_confidence_annotation":h["current_confidence"]}
        belief["claim_boundary"]="Agent-specific belief annotation over a shared hypothesis; not verified world state and not a calibrated probability."
        return belief

    def agent_belief_portfolio(self, agent_id: str, limit: int = 200) -> dict:
        if not self.store.agent_session(agent_id): raise KeyError(agent_id)
        if limit<1 or limit>1000: raise ValueError("limit must be in [1,1000]")
        out=[]
        for row in self.store.agent_hypothesis_beliefs(agent_id,limit):
            item=dict(row); h=self.store.hypothesis(item["hypothesis_id"]); item["statement"]=h["statement"] if h else None; item["shared_status"]=h["status"] if h else None
            item["revision_drift"]=item["base_revision"]!=self.revision; out.append(item)
        return {"agent_id":agent_id,"revision":self.revision,"beliefs":out,"count":len(out),
                "claim_boundary":"Private belief portfolio; shared evidence and canonical source remain workspace-level facts."}

    def hypothesis_compare(self, hypothesis_ids: list[str]) -> dict:
        if not isinstance(hypothesis_ids,list) or len(hypothesis_ids)<2 or len(hypothesis_ids)>20 or not all(isinstance(x,str) and x for x in hypothesis_ids):
            raise ValueError("hypothesis_ids must contain 2..20 non-empty IDs")
        rows=[]
        for hid in hypothesis_ids:
            st=self.hypothesis_status(hid); ev=st.get("evidence_assessment") or {}
            annotation=float(st.get("current_confidence") or 0.0); signed=float(ev.get("signed_balance") or 0.0)
            # Belief annotation is only a bounded tie-breaker; evidence balance remains primary.
            score=max(-1.0,min(1.0,signed*0.85+(annotation-0.5)*0.30))
            rows.append({"hypothesis_id":hid,"statement":st.get("statement"),"status":st.get("status"),"belief_annotation":annotation,
                         "evidence_assessment":ev.get("assessment"),"independent_source_groups":ev.get("independent_source_groups",0),"comparison_score":round(score,4)})
        rows.sort(key=lambda x:(-x["comparison_score"],-x["independent_source_groups"],x["hypothesis_id"]))
        margin=rows[0]["comparison_score"]-rows[1]["comparison_score"]
        return {"revision":self.revision,"ranking":rows,"leader":rows[0]["hypothesis_id"],"margin":round(margin,4),
                "needs_discriminating_experiment":abs(margin)<0.25 or rows[0]["independent_source_groups"]<2,
                "claim_boundary":"Ranking combines correlation-aware evidence balance with a bounded agent belief annotation; it is not posterior probability or causal proof."}

    def hypothesis_next_experiment(self, hypothesis_ids: list[str]) -> dict:
        comp=self.hypothesis_compare(hypothesis_ids); top=comp["ranking"][:2]
        return {"revision":self.revision,"hypotheses":[x["hypothesis_id"] for x in top],
                "recommended_strategy":"seek an observation whose expected outcome differs between the leading alternatives",
                "priority":"high" if comp["needs_discriminating_experiment"] else "medium",
                "evidence_gap":{"leader_source_groups":top[0]["independent_source_groups"],"runner_up_source_groups":top[1]["independent_source_groups"],"score_margin":comp["margin"]},
                "claim_boundary":"Habitat identifies a discrimination need; it does not invent a trustworthy experiment without task/domain-specific action semantics."}

    def hypothesis_link_evidence(self, hypothesis_id: str, evidence_id: str | None, polarity: str, weight: float = 1.0, note: str | None = None) -> dict:
        row=self.store.hypothesis(hypothesis_id)
        if not row: raise KeyError(hypothesis_id)
        if row["status"] != "active": raise ValueError("only active hypotheses accept new evidence")
        if polarity not in {"for","against"}: raise ValueError("polarity must be for or against")
        if not isinstance(weight,(int,float)) or isinstance(weight,bool) or not 0 < float(weight) <= 10: raise ValueError("weight must be in (0,10]")
        if evidence_id is not None and not self.store.evidence_by_id(evidence_id): raise KeyError(evidence_id)
        now=utc_now(); self.store.link_hypothesis_evidence(hypothesis_id,evidence_id,polarity,float(weight),note,self.revision,now)
        if evidence_id:
            self._causal_edge("evidence",evidence_id,"supports" if polarity=="for" else "contradicts","hypothesis",hypothesis_id,{"weight":float(weight),"note":note})
            self.store.commit()
        return self.hypothesis_status(hypothesis_id)

    def hypothesis_update(self, hypothesis_id: str, *, status: str | None = None, confidence: float | None = None, reason: str | None = None) -> dict:
        row=self.store.hypothesis(hypothesis_id)
        if not row: raise KeyError(hypothesis_id)
        if status is not None and status not in {"active","supported","rejected","superseded"}: raise ValueError("invalid hypothesis status")
        if confidence is not None and (not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not 0 <= float(confidence) <= 1):
            raise ValueError("confidence must be in [0,1]")
        self.store.update_hypothesis(hypothesis_id,status=status,confidence=confidence,updated_at=utc_now())
        if reason:
            self._causal_edge("hypothesis",hypothesis_id,"belief-updated","revision",self.revision,{"status":status or row["status"],"confidence":confidence,"reason":reason})
            self.store.commit()
        self._activity_safe("hypothesis.updated","cognition",ref_id=hypothesis_id,status=status or row["status"],summary="hypothesis updated",data={"confidence":confidence,"reason":reason})
        return self.hypothesis_status(hypothesis_id)

    def experiment_plan(self, description: str, *, hypothesis_id: str | None = None, episode_id: str | None = None, discriminator: str | None = None, capability: str | None = None, expected: dict | None = None) -> dict:
        if not isinstance(description,str) or not description.strip(): raise ValueError("description must be a non-empty string")
        if hypothesis_id is not None:
            h=self.store.hypothesis(hypothesis_id)
            if not h: raise KeyError(hypothesis_id)
            if h["status"]!="active": raise ValueError("experiment must target an active hypothesis")
            if episode_id is None: episode_id=h["episode_id"]
        if episode_id is not None: self._require_active_episode(episode_id)
        now=utc_now(); eid=stable_id("experiment",self.revision,description.strip(),now)
        value={"id":eid,"hypothesis_id":hypothesis_id,"episode_id":episode_id,"description":description.strip(),
               "discriminator":discriminator,"status":"planned","capability":capability,"expected":expected or {},
               "base_revision":self.revision,"created_at":now}
        self.store.create_experiment(value)
        if hypothesis_id:
            self._causal_edge("hypothesis",hypothesis_id,"tested-by","experiment",eid,{"discriminator":discriminator,"capability":capability})
        if episode_id:
            self.store.append_episode_link(episode_id,"experiment-planned",eid,self.revision,{"hypothesis_id":hypothesis_id,"description":description.strip()},now)
        self.store.commit()
        self._activity_safe("experiment.planned","cognition",episode_id=episode_id,ref_id=eid,status="planned",summary=description.strip()[:160],data={"hypothesis_id":hypothesis_id,"capability":capability})
        return self.experiment_status(eid)

    def experiment_status(self, experiment_id: str) -> dict:
        row=self.store.experiment(experiment_id)
        if not row: raise KeyError(experiment_id)
        d=dict(row)
        for key in ("expected_json","result_json"):
            try: d[key[:-5]]=json.loads(d.pop(key) or "{}")
            except Exception: d[key[:-5]]={}; d.pop(key,None)
        d["current_revision"]=self.revision; d["revision_drift"]=row["base_revision"]!=self.revision
        return d

    def experiment_complete(self, experiment_id: str, result: dict, status: str = "completed") -> dict:
        row=self.store.experiment(experiment_id)
        if not row: raise KeyError(experiment_id)
        if row["status"]!="planned": raise ValueError("experiment is not planned")
        if status not in {"completed","failed","inconclusive","cancelled"}: raise ValueError("invalid experiment completion status")
        if not isinstance(result,dict): raise TypeError("result must be an object")
        if row["episode_id"] is not None: self._require_active_episode(row["episode_id"])
        now=utc_now(); self.store.complete_experiment(experiment_id,status,result,now)
        if row["episode_id"]:
            self.store.append_episode_link(row["episode_id"],"experiment-completed",experiment_id,self.revision,{"status":status,"result":result},now)
        self._causal_edge("experiment",experiment_id,"observed","revision",self.revision,{"status":status,"result":result})
        self.store.commit()
        self._activity_safe("experiment.completed","cognition",episode_id=row["episode_id"],ref_id=experiment_id,status=status,summary=f"experiment {status}",data={"result":result})
        return self.experiment_status(experiment_id)

    def causality_graph(self, ref_id: str, max_depth: int = 4, max_edges: int = 300) -> dict:
        if not isinstance(ref_id,str) or not ref_id: raise ValueError("ref_id must be a non-empty string")
        if max_depth < 1 or max_depth > 12 or max_edges < 1 or max_edges > 5000:
            raise ValueError("invalid causal graph bounds")
        frontier=[ref_id]; seen_refs={ref_id}; edges=[]
        depth=0
        while frontier and depth < max_depth and len(edges) < max_edges:
            next_frontier=[]
            for current in frontier:
                for row in self.store.causal_edges_for_ref(current,limit=max_edges):
                    d=dict(row)
                    try: d["details"]=json.loads(d.pop("details_json"))
                    except Exception: d["details"]={}; d.pop("details_json",None)
                    key=(d["seq"])
                    if any(e["seq"]==key for e in edges): continue
                    edges.append(d)
                    for nxt in (d["source_ref"],d["target_ref"]):
                        if nxt not in seen_refs:
                            seen_refs.add(nxt); next_frontier.append(nxt)
                    if len(edges) >= max_edges: break
                if len(edges) >= max_edges: break
            frontier=next_frontier; depth += 1
        return {"ref_id":ref_id,"max_depth":max_depth,"visited_refs":len(seen_refs),"edge_count":len(edges),"edges":edges,
                "truncated":len(edges)>=max_edges,"causality_scope":"Habitat workflow/provenance graph across context, episode, transaction, revision, run and evidence; not full program causality"}

    def causality_explain(self, ref_id: str) -> dict:
        if not isinstance(ref_id,str) or not ref_id: raise ValueError("ref_id must be a non-empty string")
        episode_ids=[r["episode_id"] for r in self.store.episodes_for_ref(ref_id)]
        episodes=[self.episode_status(eid) for eid in episode_ids]
        graph=self.causality_graph(ref_id,4,300)
        return {"ref_id":ref_id,"episode_count":len(episodes),"episodes":episodes,"graph":graph,
                "causality_scope":"Habitat workflow/provenance links; not a claim of full program causality"}

    def checkpoint(self, task: str, resident_object_ids: list[str] | None = None, notes: str | None = None, next_action: str | None = None, episode_id: str | None = None) -> dict:
        """Create a provenance-bound resumable state, not a narrative-only summary."""
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        if resident_object_ids is not None and not isinstance(resident_object_ids, list):
            raise TypeError("resident_object_ids must be a list when provided")
        if resident_object_ids is not None and not all(isinstance(x, str) and x for x in resident_object_ids):
            raise TypeError("resident_object_ids must contain non-empty strings")
        if notes is not None and not isinstance(notes, str):
            raise TypeError("notes must be a string when provided")
        if next_action is not None and not isinstance(next_action, str):
            raise TypeError("next_action must be a string when provided")
        task = task.strip()
        if episode_id is not None:
            self._require_active_episode(episode_id)
        self.reconcile()
        if resident_object_ids is None:
            resident_object_ids = [r["object_id"] for r in self.store.resident_rows()]
        objects = []
        for oid in resident_object_ids:
            s = self.store.symbol_by_id(oid); f = self.store.file_by_id(oid); d = self.store.diagnostic_by_id(oid)
            row = s or f or d
            if not row: raise KeyError(oid)
            path = row["path"]; fr = self.store.file_by_path(path)
            resident = self.store.resident_by_id(oid)
            objects.append({"object_id": oid, "path": path, "digest": fr["digest"] if fr else None,
                            "kind": "symbol" if s else "file" if f else "diagnostic",
                            "pinned": bool(resident["pinned"]) if resident else False,
                            "relevance": float(resident["relevance"]) if resident else None})
        rev = self.store.revision(self.revision)
        sid = stable_id("session", self.revision, task, utc_now())
        merkle_row = self.store.merkle_snapshot_row(self.revision)
        backend_identity = self.backend_info()
        backend_binding = self._backend_binding()
        value = {
            "id": sid, "task": task, "revision": self.revision, "root_digest": rev["root_digest"] if rev else None,
            "merkle_root": merkle_row["root_hash"] if merkle_row else None,
            "compiler_state_fingerprint": self._compiler_state_fingerprint(), "event_cursor": self.store.latest_event_seq(),
            "backend_identity": backend_identity, "backend_binding": backend_binding,
            "source_authority_binding": self._source_authority_binding(),
            "execution_provider_binding": self._execution_provider_binding(),
            "episode_id": episode_id,
            "resident_objects": objects, "residency_config": ContextResidency(self)._config(),
            "next_action": next_action, "notes": notes, "created_at": utc_now(),
            "invalidation_conditions": ["resident source digest changes", "resident object disappears", "compiler/provider identity changes", "source authority identity changes", "execution provider identity changes"],
        }
        self.store.save_json("sessions", sid, value)
        if episode_id is not None:
            self.store.append_episode_link(episode_id, "checkpoint-created", sid, self.revision,
                                           {"task": task, "next_action": next_action}, utc_now())
            self.store.commit()
        return value

    def resume(self, session_id: str) -> dict:
        self.reconcile()
        value = self.store.load_json("sessions", session_id)
        if not value: raise KeyError(session_id)
        fresh, stale, missing = [], [], []
        for obj in value.get("resident_objects", []):
            oid = obj["object_id"]
            exists = self.store.symbol_by_id(oid) or self.store.file_by_id(oid) or self.store.diagnostic_by_id(oid)
            if not exists:
                missing.append(obj); continue
            fr = self.store.file_by_path(obj["path"])
            (fresh if fr and fr["digest"] == obj.get("digest") else stale).append(obj)
        provider_drift = bool(value.get("compiler_state_fingerprint") and value.get("compiler_state_fingerprint") != self._compiler_state_fingerprint())
        current_backend = self.backend_info()
        current_backend_binding = self._backend_binding()
        backend_drift = bool(value.get("backend_binding") and value.get("backend_binding") != current_backend_binding)
        source_authority_drift = bool(value.get("source_authority_binding") and value.get("source_authority_binding") != self._source_authority_binding())
        execution_provider_drift = bool(value.get("execution_provider_binding") and value.get("execution_provider_binding") != self._execution_provider_binding())
        revision_changed = value.get("revision") != self.revision
        current_merkle = self.store.merkle_snapshot_row(self.revision)
        merkle_drift = bool(value.get("merkle_root") and current_merkle and value.get("merkle_root") != current_merkle["root_hash"])
        diff = self.diff_since(value["revision"]) if revision_changed and self.store.revision(value["revision"]) else {
            "from_revision": value.get("revision"), "to_revision": self.revision, "reachable": value.get("revision") == self.revision,
            "changed_paths": [], "revisions": []
        }
        if provider_drift or source_authority_drift or stale or missing or (backend_drift and not execution_provider_drift):
            mode = "reorient"
        elif revision_changed or execution_provider_drift:
            mode = "selective-revalidate"
        else:
            mode = "direct"
        episode_id = value.get("episode_id")
        episode = self.episode_status(episode_id) if episode_id and self.store.episode(episode_id) else None
        return {
            "session_id": session_id, "task": value["task"], "checkpoint_revision": value["revision"],
            "episode_id": episode_id, "episode": episode,
            "current_revision": self.revision, "revision_changed": revision_changed, "changed_paths_since_checkpoint": diff.get("changed_paths", []),
            "fresh_objects": fresh, "stale_objects": stale, "missing_objects": missing, "provider_identity_drift": provider_drift,
            "backend_identity_drift": backend_drift, "source_authority_identity_drift": source_authority_drift,
            "execution_provider_identity_drift": execution_provider_drift,
            "checkpoint_backend": value.get("backend_identity"), "current_backend": current_backend,
            "checkpoint_merkle_root": value.get("merkle_root"), "current_merkle_root": current_merkle["root_hash"] if current_merkle else None, "merkle_drift": merkle_drift,
            "resume_mode": mode, "continuation_allowed_without_reorientation": mode == "direct",
            "reorient_recommended": mode == "reorient", "selective_revalidation_required": mode == "selective-revalidate",
            "checkpoint_event_cursor": value.get("event_cursor"), "current_event_cursor": self.store.latest_event_seq(),
            "next_action": value.get("next_action"), "notes": value.get("notes"), "invalidation_conditions": value.get("invalidation_conditions", []),
        }

