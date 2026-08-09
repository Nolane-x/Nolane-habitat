from __future__ import annotations
import json, tempfile
from pathlib import Path
from habitat.workspace import HabitatWorkspace
from habitat.model import to_dict


def main(output: str = "reports/DEMO-EVIDENCE-alpha1.json"):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); src=root/"project"; src.mkdir(); (src/"tests").mkdir()
        (src/"auth.py").write_text('def validate_credentials(email, password):\n    return password == "secret"\n',encoding="utf-8")
        (src/"tests"/"test_auth.py").write_text('import unittest\nimport auth\nclass T(unittest.TestCase):\n    def test_valid(self): self.assertTrue(auth.validate_credentials("a","secret"))\n',encoding="utf-8")
        (src/"index.html").write_text('<label for="name">Name</label><input id="name"><button id="go">Go</button><div id="out" role="status"></div><script src="app.js"></script><link rel="stylesheet" href="style.css">',encoding="utf-8")
        (src/"app.js").write_text("document.getElementById('go').addEventListener('click',()=>document.getElementById('out').textContent='Hello '+document.getElementById('name').value)",encoding="utf-8")
        (src/"style.css").write_text('#go { padding: 4px; } .wide { width: 120%; }',encoding="utf-8")
        ws=HabitatWorkspace.create(src,root/"hab")
        entered=ws.enter()
        ctx=ws.orient("fix credential validation implementation and verify tests",budget=8)
        target=next(o for o in ctx.objects if ws.store.symbol_by_id(o.object_id) and ws.store.symbol_by_id(o.object_id)["name"]=="validate_credentials")
        inspected=ws.inspect(target.object_id,"body")
        staged=ws.stage_symbol_change(target.object_id,'def validate_credentials(email, password):\n    """Validate the demo credential."""\n    return password == "secret"')
        committed=ws.commit_change(staged["id"])
        verification=ws.verification_plan(changed_paths=["auth.py"])
        test_run=ws.run("python.unittest",timeout_s=20)
        ui_open=ws.open_ui_runtime("index.html")
        sid=ui_open["session_id"]
        ws.act_ui_runtime(sid,"fill","ui:id:name","Nolane")
        ui_after=ws.act_ui_runtime(sid,"click","ui:id:go")
        ws.close_ui_runtime(sid)
        checkpoint=ws.checkpoint("continue demo task",[target.object_id])
        resume=ws.resume(checkpoint["id"])
        warm=ws.refresh("demo-warm")
        evidence={
            "entered":entered,
            "context":to_dict(ctx),
            "inspected":inspected,
            "staged":{"id":staged["id"],"preview":staged["preview"]},
            "committed":committed,
            "verification":verification,
            "test_run":test_run,
            "ui_open":{"session_id":ui_open["session_id"],"mode":ui_open["mode"],"aria_snapshot":ui_open["aria_snapshot"],"events":ui_open["events"],"element_count":len(ui_open["elements"])},
            "ui_after":{"delta":ui_after["delta"],"out":next(e for e in ui_after["elements"] if e["handle"]=="ui:id:out")},
            "checkpoint":checkpoint,
            "resume":resume,
            "warm_refresh":warm,
            "claim_boundary":"Executable vertical-slice evidence only; no LLM token/task-success claim."
        }
        Path(output).write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({"ok":True,"test_status":test_run.get("structured",{}).get("status"),"ui_text":evidence["ui_after"]["out"]["text"],"warm":warm},indent=2))
        ws.close()

if __name__=="__main__": main()
