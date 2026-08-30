from __future__ import annotations

from contextlib import closing
import json
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .workspace import HabitatWorkspace

from .project_world import build_project_world
from .runtime_twin import build_runtime_topology
from .runtime_correlation import correlate_runtime_fact
from .cognitive_resilience import analyze_cognitive_loop, epistemic_pressure


class ObservatoryReadModel:
    """Thread-safe observer projection using short-lived SQLite read-only connections.

    The control-plane Workspace keeps its own authoritative connection. Projection readers never
    share that handle and never write to the Habitat database.
    """
    def __init__(self, workspace: HabitatWorkspace):
        self.db_path=(workspace.habitat_dir/"habitat.sqlite3").resolve()
        self.backend=workspace.backend_info()
        self.execution_security=workspace.execution_security()
        self.authority_root=Path(workspace.backend.source_authority.info.authoritative_root).resolve()

    def _connect(self):
        # pathlib emits a correct file:// URI on POSIX and Windows (including drive letters and
        # spaces). Hand-building file: URIs from quoted native paths is subtly non-portable.
        uri=self.db_path.as_uri()+"?mode=ro"
        conn=sqlite3.connect(uri,uri=True,timeout=2.0)
        conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def _json_field(d: dict, source: str, target: str, default):
        raw=d.pop(source,None)
        try: d[target]=json.loads(raw) if raw else default
        except Exception: d[target]=default
        return d

    def revision(self) -> str:
        with closing(self._connect()) as c:
            r=c.execute("SELECT value FROM meta WHERE key='head_revision'").fetchone()
            return r[0] if r else "none"

    def latest_activity_seq(self) -> int:
        with closing(self._connect()) as c:
            r=c.execute("SELECT COALESCE(MAX(seq),0) FROM activity_events").fetchone(); return int(r[0] or 0)

    def activity_since(self, since_seq: int=0, limit: int=500) -> dict:
        with closing(self._connect()) as c:
            c.execute("BEGIN")
            bounds=c.execute("SELECT COALESCE(MIN(seq),0),COALESCE(MAX(seq),0) FROM activity_events").fetchone()
            oldest,latest=int(bounds[0] or 0),int(bounds[1] or 0)
            rows=c.execute("SELECT * FROM activity_events WHERE seq>? ORDER BY seq ASC LIMIT ?",(int(since_seq),int(limit))).fetchall()
            rev=c.execute("SELECT value FROM meta WHERE key='head_revision'").fetchone()
        out=[]
        for row in rows:
            d=dict(row); self._json_field(d,"data_json","data",{}); out.append(d)
        last=int(out[-1]["seq"]) if out else int(since_seq)
        return {"revision":rev[0] if rev else "none","since_seq":int(since_seq),"oldest_seq":oldest,"latest_seq":latest,"last_returned_seq":last,
                "gap_detected":bool(oldest and since_seq and int(since_seq)<oldest-1),"has_more":bool(last<latest),"events":out}

    def snapshot(self) -> dict:
        with closing(self._connect()) as c:
            # One SQLite read transaction gives the Observatory a coherent machine-world frame.
            c.execute("BEGIN")
            revrow=c.execute("SELECT value FROM meta WHERE key='head_revision'").fetchone(); revision=revrow[0] if revrow else "none"
            files=[dict(r) for r in c.execute("SELECT * FROM files ORDER BY path LIMIT 180").fetchall()]
            file_count=int(c.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            relation_count=int(c.execute("SELECT COUNT(*) FROM relations").fetchone()[0])
            symbols=[dict(r) for r in c.execute("SELECT * FROM symbols ORDER BY path,start_line LIMIT 120").fetchall()]
            symbol_count=int(c.execute("SELECT COUNT(*) FROM symbols").fetchone()[0])
            runtime_count_total=int(c.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0])
            effect_count_total=int(c.execute("SELECT COUNT(*) FROM effect_facts").fetchone()[0])
            dataflow_count_total=int(c.execute("SELECT COUNT(*) FROM dataflow_facts").fetchone()[0])
            agents=[]
            for r in c.execute("SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT 50").fetchall():
                d=dict(r); self._json_field(d,"metadata_json","metadata",{}); d["task"]=(d.get("metadata") or {}).get("task"); agents.append(d)
            episodes=[]
            for r in c.execute("SELECT * FROM work_episodes ORDER BY created_at DESC LIMIT 20").fetchall():
                d=dict(r); self._json_field(d,"outcome_json","outcome",{}); episodes.append(d)
            hypotheses=[dict(r) for r in c.execute("SELECT * FROM hypotheses WHERE status='active' ORDER BY updated_at DESC LIMIT 30").fetchall()]
            epistemic=[]
            for r in c.execute("SELECT * FROM epistemic_items WHERE status='open' ORDER BY updated_at DESC LIMIT 40").fetchall():
                d=dict(r); self._json_field(d,"provenance_json","provenance",{}); self._json_field(d,"invalidation_json","invalidation_conditions",[]); epistemic.append(d)
            memories=[]
            for r in c.execute("SELECT * FROM project_memories ORDER BY updated_at DESC LIMIT 40").fetchall():
                d=dict(r); self._json_field(d,"provenance_json","provenance",{}); self._json_field(d,"evidence_json","evidence_ids",[]); d["confidence_annotation"]=d.pop("confidence",None); d["revision_drift"]=d.get("base_revision")!=revision; memories.append(d)
            evidence=[]
            for r in c.execute("SELECT * FROM evidence WHERE active=1 ORDER BY created_at DESC LIMIT 50").fetchall():
                d=dict(r); self._json_field(d,"data_json","data",{}); evidence.append(d)
            runtime=[]
            for r in c.execute("SELECT * FROM runtime_events ORDER BY started_at DESC LIMIT 40").fetchall():
                d=dict(r); self._json_field(d,"attributes_json","attributes",{}); runtime.append(d)
            global_res=[dict(r) for r in c.execute("SELECT * FROM resident_objects ORDER BY pinned DESC,last_access_seq DESC LIMIT 60").fetchall()]
            private=[]
            for r in c.execute("SELECT * FROM agent_resident_objects ORDER BY last_access_seq DESC LIMIT 80").fetchall():
                private.append(dict(r))
            faults=c.execute("SELECT COUNT(*),COUNT(DISTINCT handle||':'||page_id),COALESCE(SUM(source_bytes),0),COALESCE(SUM(authority_bytes_read),0) FROM context_faults").fetchone()
            latest=int(c.execute("SELECT COALESCE(MAX(seq),0) FROM activity_events").fetchone()[0] or 0)
            activities=[]
            for r in reversed(c.execute("SELECT * FROM activity_events ORDER BY seq DESC LIMIT 80").fetchall()):
                d=dict(r); self._json_field(d,"data_json","data",{}); activities.append(d)

            # Operator reconstruction has its own UI-event budget. Mixing it with the generic
            # 80-event visual timeline made a busy non-UI workspace forget a still-live browser
            # session even though the durable UI receipts remained in SQLite.
            ui_activities=[]
            for r in reversed(c.execute("SELECT * FROM activity_events WHERE kind LIKE 'ui.%' ORDER BY seq DESC LIMIT 240").fetchall()):
                d=dict(r); self._json_field(d,"data_json","data",{}); ui_activities.append(d)
            operator={"status":"idle","session_id":None,"target":None,"url":None,"title":None,"viewport":None,"frame_seq":0,"stream_seq":0,"stream_epoch":None,"stream_mode":None,"stream_active":False,"last_action":None,"last_event_seq":0}
            latest_ui=ui_activities[-1] if ui_activities else None
            latest_data=(latest_ui or {}).get("data") or {}
            latest_kind=str((latest_ui or {}).get("kind") or "")
            active_sid=latest_data.get("session_id") or ((latest_ui or {}).get("ref_id") if latest_kind in {"ui.runtime-opened","ui.runtime-observed","ui.runtime-closed","ui.assertion"} else None)

            open_seq=0
            if active_sid:
                open_row=c.execute("SELECT * FROM activity_events WHERE kind='ui.runtime-opened' AND ref_id=? ORDER BY seq DESC LIMIT 1",(active_sid,)).fetchone()
                if open_row:
                    opened=dict(open_row); self._json_field(opened,"data_json","data",{}); data=opened.get("data") or {}; open_seq=int(opened.get("seq") or 0)
                    operator.update({"status":"live","session_id":active_sid,"target":data.get("target"),"url":data.get("url") or data.get("target"),"title":data.get("title"),"viewport":data.get("viewport"),"frame_seq":int(data.get("operator_frame_seq") or 0),"stream_seq":int(data.get("operator_stream_seq") or 0),"stream_epoch":data.get("operator_stream_epoch"),"stream_mode":data.get("operator_stream_mode"),"stream_active":bool(data.get("operator_stream_active")),"last_event_seq":open_seq})
                else:
                    operator["session_id"]=active_sid

            for e in ui_activities:
                if int(e.get("seq") or 0) < open_seq: continue
                data=e.get("data") or {}; kind=str(e.get("kind") or ""); sid=data.get("session_id") or (e.get("ref_id") if kind in {"ui.runtime-opened","ui.runtime-observed","ui.runtime-closed","ui.assertion"} else None)
                if not sid or (operator.get("session_id") is not None and sid != operator.get("session_id")): continue
                operator["session_id"]=sid
                if kind=="ui.runtime-opened": operator["status"]="live"
                elif kind=="ui.runtime-closed": operator["status"]="closed"; operator["stream_active"]=False
                elif kind=="ui.action-started":
                    operator["status"]="acting"; operator["last_action"]=data.get("action_preview") or {"action":data.get("action"),"handle":data.get("handle")}
                elif kind=="ui.action-completed":
                    operator["status"]="live" if str(e.get("status") or "").lower() not in {"failed","error"} else "error"; operator["last_action"]=data.get("action_receipt") or data.get("action_preview") or {"action":data.get("action"),"handle":data.get("handle")}
                elif kind=="ui.runtime-observed": operator["status"]="live"
                operator["target"]=data.get("target") or operator.get("target"); operator["url"]=data.get("url") or operator.get("url"); operator["title"]=data.get("title") or operator.get("title"); operator["viewport"]=data.get("viewport") or operator.get("viewport")
                epoch=data.get("operator_stream_epoch")
                if epoch and epoch != operator.get("stream_epoch"):
                    # A new stream generation resets monotonic counters; do not max() it against
                    # a previous generation and accidentally pin the UI to an old frame number.
                    operator["stream_epoch"]=epoch; operator["frame_seq"]=int(data.get("operator_frame_seq") or 0); operator["stream_seq"]=int(data.get("operator_stream_seq") or 0)
                else:
                    operator["frame_seq"]=max(int(operator.get("frame_seq") or 0),int(data.get("operator_frame_seq") or 0)); operator["stream_seq"]=max(int(operator.get("stream_seq") or 0),int(data.get("operator_stream_seq") or 0))
                    operator["stream_epoch"]=epoch or operator.get("stream_epoch")
                operator["stream_mode"]=data.get("operator_stream_mode") or operator.get("stream_mode"); operator["stream_active"]=bool(data.get("operator_stream_active",operator.get("stream_active"))); operator["last_event_seq"]=int(e.get("seq") or operator.get("last_event_seq") or 0)
            rels=[dict(r) for r in c.execute("SELECT source_id,target_id,kind,trust FROM relations LIMIT 800").fetchall()]
            hlinks=[dict(r) for r in c.execute("SELECT hypothesis_id,evidence_id,polarity FROM hypothesis_evidence WHERE evidence_id IS NOT NULL ORDER BY seq DESC LIMIT 200").fetchall()]
            effects=[]
            for r in c.execute("SELECT * FROM effect_facts ORDER BY created_at DESC LIMIT 160").fetchall():
                d=dict(r); self._json_field(d,"metadata_json","metadata",{}); effects.append(d)
            dataflows=[]
            for r in c.execute("SELECT * FROM dataflow_facts ORDER BY created_at DESC LIMIT 180").fetchall():
                d=dict(r); self._json_field(d,"metadata_json","metadata",{}); dataflows.append(d)
            worlds=[]
            for r in c.execute("SELECT w.*, (SELECT COUNT(*) FROM counterfactual_changes ch WHERE ch.world_id=w.id) AS change_count FROM counterfactual_worlds w ORDER BY updated_at DESC LIMIT 30").fetchall():
                d=dict(r); self._json_field(d,"metadata_json","metadata",{}); m=d.get("metadata") or {}; gen=int(m.get("overlay_generation") or 0); verified=m.get("verified_generation")
                d["overlay_generation"]=gen; d["verification_status"]=m.get("verification_status") or "never"; d["verification_fresh"]=bool(d["verification_status"] in {"passed","failed"} and verified is not None and int(verified)==gen and d.get("base_revision")==revision)
                worlds.append(d)
            invariants=[]
            for r in c.execute("SELECT i.*, (SELECT COUNT(*) FROM invariant_links l WHERE l.invariant_id=i.id AND l.relation='verifier') AS verifier_count FROM project_invariants i WHERE i.status!='retired' ORDER BY updated_at DESC LIMIT 30").fetchall():
                d=dict(r); self._json_field(d,"metadata_json","metadata",{}); invariants.append(d)
            trajectories=[]
            for r in c.execute("SELECT * FROM executive_trajectories ORDER BY updated_at DESC LIMIT 20").fetchall():
                d=dict(r); self._json_field(d,"budget_json","budget",{}); self._json_field(d,"metrics_json","metrics",{}); self._json_field(d,"outcome_json","outcome",{}); trajectories.append(d)
            milestones=[]
            for r in c.execute("SELECT * FROM executive_milestones ORDER BY updated_at DESC LIMIT 80").fetchall():
                d=dict(r); self._json_field(d,"dependencies_json","dependencies",[]); self._json_field(d,"result_json","result",{}); milestones.append(d)
            notifications=[dict(r) for r in c.execute("SELECT * FROM agent_notifications WHERE status='pending' ORDER BY created_at DESC LIMIT 50").fetchall()]
            leases=[dict(r) for r in c.execute("SELECT * FROM resource_leases ORDER BY expires_at DESC LIMIT 60").fetchall()]
            # Per-agent health is derived entirely inside the same SQLite read transaction so one rendered
            # frame does not mix an agent's activity/read-set status from different database moments.
            agent_health={}
            for a in agents:
                aid=a["id"]
                arows=[]
                for rr in reversed(c.execute("SELECT * FROM activity_events WHERE agent_id=? ORDER BY seq DESC LIMIT 40",(aid,)).fetchall()):
                    dd=dict(rr); self._json_field(dd,"data_json","data",{}); arows.append(dd)
                aloop=analyze_cognitive_loop(arows)
                pending_count=sum(1 for n in notifications if n.get("agent_id")==aid)
                lease_count=sum(1 for l in leases if l.get("agent_id")==aid)
                resident_count=int(c.execute("SELECT COUNT(*) FROM agent_resident_objects WHERE agent_id=?",(aid,)).fetchone()[0] or 0)
                health_status="stale" if pending_count else ("loop-risk" if aloop.get("risk") in {"medium","high"} else "active")
                agent_health[aid]={"status":health_status,"pending_invalidations":pending_count,"leases":lease_count,"private_residents":resident_count,"loop":aloop}
                a["health"]=agent_health[aid]
        project_world=build_project_world(self.authority_root,files,max_files=600)
        runtime_topology=build_runtime_topology(runtime,max_events=300)
        for ef in effects: ef["runtime_support"]=correlate_runtime_fact(ef,runtime,revision)
        for df in dataflows: df["runtime_support"]=correlate_runtime_fact(df,runtime,revision)
        # Bounded human-facing epistemic scheduler summary. The observer does not invoke control APIs.
        contradictions=[x for x in epistemic if x.get("kind")=="contradiction"]
        unknowns=[x for x in epistemic if x.get("kind")=="unknown"]
        assumptions=[x for x in epistemic if x.get("kind")=="assumption"]
        if notifications:
            director={"operation":"selective-revalidate","reason":"agent cognition invalidated by a changed observed resource","information_gain":"high","cost":"low"}
        elif contradictions:
            director={"operation":"discriminate-contradiction","reason":contradictions[0].get("statement"),"information_gain":"high","cost":"medium"}
        elif len(hypotheses)>=2:
            director={"operation":"plan-discriminating-experiment","reason":"multiple active hypotheses remain","information_gain":"high","cost":"medium"}
        elif unknowns:
            director={"operation":"probe-unknown","reason":unknowns[0].get("statement"),"information_gain":"medium","cost":"medium"}
        else:
            director={"operation":"bounded-explore-or-act","reason":"no explicit high-severity epistemic blocker","information_gain":"low","cost":"low"}
        for x in epistemic: x["stale"]=x.get("base_revision")!=revision
        loop_health=analyze_cognitive_loop(activities)
        pressure=epistemic_pressure(epistemic,notifications,invariants)
        epistemic_debt=len(contradictions)*3+len(unknowns)*2+len(assumptions)+len(notifications)*3
        nodes=[]; node_ids=set()
        for fr in files[:90]: nodes.append({"id":fr["id"],"type":"file","label":fr["path"],"path":fr["path"]}); node_ids.add(fr["id"])
        for sr in symbols[:120]: nodes.append({"id":sr["id"],"type":"symbol","label":sr["qualified_name"],"path":sr["path"]}); node_ids.add(sr["id"])
        for a in agents: nodes.append({"id":a["id"],"type":"agent","label":a["name"],"agent_id":a["id"]}); node_ids.add(a["id"])
        for ep in episodes[:16]: nodes.append({"id":ep["id"],"type":"episode","label":ep["task"][:80]}); node_ids.add(ep["id"])
        for h in hypotheses[:20]: nodes.append({"id":h["id"],"type":"hypothesis","label":h["statement"][:80]}); node_ids.add(h["id"])
        for x in epistemic[:18]: nodes.append({"id":x["id"],"type":"epistemic","label":x["statement"][:80],"agent_id":x.get("agent_id")}); node_ids.add(x["id"])
        for m in memories[:18]: nodes.append({"id":m["id"],"type":"memory","label":m["statement"][:80],"agent_id":m.get("agent_id")}); node_ids.add(m["id"])
        for e in evidence[:20]: nodes.append({"id":e["id"],"type":"evidence","label":e["summary"][:80],"path":e.get("path")}); node_ids.add(e["id"])
        for rt in runtime[:20]: nodes.append({"id":rt["id"],"type":"runtime","label":rt["name"][:80],"path":rt.get("path")}); node_ids.add(rt["id"])
        for ef in effects[:36]:
            eid="effect:"+ef["id"]; nodes.append({"id":eid,"type":"effect","label":f"{ef['kind']} → {ef['target']}"[:90],"path":ef.get("path"),"effect_kind":ef.get("kind")}); node_ids.add(eid)
        for df in dataflows[:42]:
            did="flow:"+df["id"]; nodes.append({"id":did,"type":"dataflow","label":f"{df['source']} → {df['target']}"[:90],"path":df.get("path"),"flow_kind":df.get("kind")}); node_ids.add(did)
        for cw in worlds[:12]: nodes.append({"id":cw["id"],"type":"counterfactual","label":cw["label"][:80],"agent_id":cw.get("owner_agent_id"),"status":cw.get("status")}); node_ids.add(cw["id"])
        for inv in invariants[:16]: nodes.append({"id":inv["id"],"type":"invariant","label":inv["statement"][:80],"status":inv.get("status")}); node_ids.add(inv["id"])
        for tr in trajectories[:12]: nodes.append({"id":tr["id"],"type":"trajectory","label":tr["goal"][:80],"agent_id":tr.get("agent_id"),"status":tr.get("status"),"strategy":tr.get("current_strategy")}); node_ids.add(tr["id"])
        for ms in milestones[:24]:
            if ms.get("trajectory_id") in node_ids:
                nodes.append({"id":ms["id"],"type":"milestone","label":ms["title"][:80],"status":ms.get("status"),"priority":ms.get("priority")}); node_ids.add(ms["id"])
        for n in project_world.get("nodes",[])[:80]:
            if n["id"] not in node_ids: nodes.append(n); node_ids.add(n["id"])
        for n in runtime_topology.get("nodes",[])[:80]:
            if n["id"] not in node_ids: nodes.append(n); node_ids.add(n["id"])
        edges=[{"source":r["source_id"],"target":r["target_id"],"kind":r["kind"],"trust":r["trust"]} for r in rels if r["source_id"] in node_ids and r["target_id"] in node_ids]
        edges += [{"source":r["hypothesis_id"],"target":r["evidence_id"],"kind":"evidence-"+r["polarity"],"trust":"derived"} for r in hlinks if r["hypothesis_id"] in node_ids and r["evidence_id"] in node_ids]
        edges += [{"source":h["episode_id"],"target":h["id"],"kind":"hypothesis","trust":"derived"} for h in hypotheses if h.get("episode_id") in node_ids and h["id"] in node_ids]
        edges += [{"source":x["episode_id"],"target":x["id"],"kind":"epistemic","trust":"derived"} for x in epistemic if x.get("episode_id") in node_ids and x["id"] in node_ids]
        edges += [{"source":x["agent_id"],"target":x["id"],"kind":"agent-cognition","trust":"derived"} for x in epistemic if x.get("agent_id") in node_ids and x["id"] in node_ids]
        edges += [{"source":m["episode_id"],"target":m["id"],"kind":"remembered-in","trust":"derived"} for m in memories if m.get("episode_id") in node_ids and m["id"] in node_ids]
        edges += [{"source":m["agent_id"],"target":m["id"],"kind":"private-memory","trust":"derived"} for m in memories if m.get("agent_id") in node_ids and m["id"] in node_ids]
        edges += [{"source":tr["agent_id"],"target":tr["id"],"kind":"executive-trajectory","trust":"exact"} for tr in trajectories if tr.get("agent_id") in node_ids and tr["id"] in node_ids]
        edges += [{"source":tr["episode_id"],"target":tr["id"],"kind":"executive-governance","trust":"exact"} for tr in trajectories if tr.get("episode_id") in node_ids and tr["id"] in node_ids]
        edges += [{"source":ms["trajectory_id"],"target":ms["id"],"kind":"milestone","trust":"exact"} for ms in milestones if ms.get("trajectory_id") in node_ids and ms["id"] in node_ids]
        for ms in milestones:
            if ms["id"] not in node_ids: continue
            for dep in ms.get("dependencies") or []:
                if dep in node_ids: edges.append({"source":dep,"target":ms["id"],"kind":"milestone-dependency","trust":"exact"})
        edges += [{"source":rt["id"],"target":rt["symbol_id"],"kind":"runtime-observed","trust":"semantic"} for rt in runtime if rt.get("symbol_id") in node_ids and rt["id"] in node_ids]
        edges += [{"source":rt["episode_id"],"target":rt["id"],"kind":"runtime-evidence","trust":"derived"} for rt in runtime if rt.get("episode_id") in node_ids and rt["id"] in node_ids]
        for m in memories:
            if m["id"] not in node_ids: continue
            for eid in m.get("evidence_ids") or []:
                if eid in node_ids: edges.append({"source":m["id"],"target":eid,"kind":"memory-evidence","trust":"derived"})
        for ef in effects[:36]:
            eid="effect:"+ef["id"]
            src=ef.get("symbol_id")
            if src in node_ids and eid in node_ids: edges.append({"source":src,"target":eid,"kind":"effect-"+ef["kind"],"trust":ef.get("trust","parser")})
            else:
                fr=next((f for f in files if f.get("path")==ef.get("path")),None)
                if fr and fr["id"] in node_ids and eid in node_ids: edges.append({"source":fr["id"],"target":eid,"kind":"effect-"+ef["kind"],"trust":ef.get("trust","parser")})
        for df in dataflows[:42]:
            did="flow:"+df["id"]; src=df.get("symbol_id")
            if src in node_ids and did in node_ids: edges.append({"source":src,"target":did,"kind":"dataflow-"+df["kind"],"trust":df.get("trust","parser")})
            elif did in node_ids:
                fr=next((f for f in files if f.get("path")==df.get("path")),None)
                if fr and fr["id"] in node_ids: edges.append({"source":fr["id"],"target":did,"kind":"dataflow-"+df["kind"],"trust":df.get("trust","parser")})
        for cw in worlds[:12]:
            if cw.get("owner_agent_id") in node_ids and cw["id"] in node_ids: edges.append({"source":cw["owner_agent_id"],"target":cw["id"],"kind":"world-fork","trust":"exact"})
        for e in project_world.get("edges",[]):
            if e["source"] in node_ids and e["target"] in node_ids: edges.append(e)
        for e in runtime_topology.get("edges",[]):
            if e["source"] in node_ids and e["target"] in node_ids: edges.append(e)
        return {"revision":revision,"generated_at":time.time(),"read_only":True,"backend":self.backend,"execution_security":self.execution_security,
                "project":{"files":file_count,"symbols":symbol_count,"files_view":[{"path":f["path"],"language":f["language"],"size":f["size"]} for f in files]},
                "agents":agents,"episodes":episodes,"hypotheses":hypotheses,"epistemic":epistemic,"evidence":evidence,"runtime":runtime,"project_memory":memories,
                "effects":effects,"dataflows":dataflows,"counterfactual_worlds":worlds,"invariants":invariants,"executive":{"trajectories":trajectories,"milestones":milestones},"coordination":{"pending":notifications,"leases":leases},
                "project_world":project_world,"runtime_topology":runtime_topology,
                "cognitive_director":{"next":director,"epistemic_debt":epistemic_debt,"contradictions":len(contradictions),"unknowns":len(unknowns),"assumptions":len(assumptions),"loop":loop_health,"pressure":pressure},
                "context_memory":{"residents":(private+global_res)[:60],"fault_count":int(faults[0] or 0),"unique_page_faults":int(faults[1] or 0),
                                  "duplicate_page_faults":max(0,int(faults[0] or 0)-int(faults[1] or 0)),"refetch_ratio":round(max(0,int(faults[0] or 0)-int(faults[1] or 0))/max(1,int(faults[0] or 0)),4),
                                  "agent_visible_source_bytes":int(faults[2] or 0),"authority_bytes_read":int(faults[3] or 0),
                                  "io_amplification":round(int(faults[3] or 0)/max(1,int(faults[2] or 0)),4) if int(faults[2] or 0) else None},
                "observer_health":{"snapshot_consistency":"sqlite-read-transaction","external_projection_consistency":"revision-bound-best-effort","activity_loop":loop_health,"epistemic_pressure":pressure,"activity_seq":latest,"agents":agent_health},
                "graph":{"nodes":nodes,"edges":edges},
                "graph_sampling":{"bounded":bool(file_count>90 or symbol_count>120 or relation_count>800 or effect_count_total>160 or dataflow_count_total>180 or runtime_count_total>40),
                                  "source_totals":{"files":file_count,"symbols":symbol_count,"relations":relation_count,"effects":effect_count_total,"dataflows":dataflow_count_total,"runtime_events":runtime_count_total},
                                  "read_model_limits":{"files":90,"symbols":120,"relations":800,"effects":160,"dataflows":180,"runtime_events":40},
                                  "graph_candidates":len(nodes),"graph_edges":len(edges),
                                  "claim_boundary":"Observer graph is a bounded focus+context projection; omitted project state is disclosed rather than treated as absent."},
                "activity_seq":latest,"activity":activities,"operator":operator,
                "visual_metrics":{"graph_nodes":len(nodes),"graph_edges":len(edges),"effects":len(effects),"dataflows":len(dataflows),"runtime_topology_nodes":len(runtime_topology.get("nodes",[])),"world_entities":len(project_world.get("nodes",[])),"counterfactual_worlds":len(worlds),"executive_trajectories":len(trajectories),"executive_milestones":len(milestones)},
                "claim_boundary":"Human visual observatory only. SQLite-backed frame state is read in one transaction; Project World filesystem projections are revision-bound best-effort unless the backend supplies a snapshot token. The read model is query-only and never exposes raw private model chain-of-thought."}
