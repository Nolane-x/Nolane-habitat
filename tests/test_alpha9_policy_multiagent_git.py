from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from habitat.execution import containment_probe, run_action
from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace
from habitat.mutation import TransactionConflict


class Alpha9PolicyContainmentTests(unittest.TestCase):
    def test_policy_denies_configured_source_and_untrusted_unsandboxed_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"p"; root.mkdir(); (root/"a.py").write_text("def f():\n    return 1\n")
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                ws.policy_update({"source":{"deny":["a.py"]}})
                with self.assertRaises(PermissionError):
                    ws.stage_change([{"op":"replace_text","path":"a.py","old":"return 1","new":"return 2"}])
                ws.policy_update({"source":{"deny":[".git/**",".habitat/**"]},"mode":"untrusted"})
                caps=[c for c in ws.enter()["capabilities"] if c.get("kind")=="test" and c.get("available")]
                if caps:
                    with self.assertRaises(PermissionError): ws.run(caps[0]["id"])
            finally: ws.close()

    def test_network_containment_is_honest_and_blocks_external_network_when_available(self):
        probe=containment_probe()
        if not probe.get("network_namespace_available"):
            self.skipTest(probe.get("reason"))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            code="""import socket\ns=socket.socket(); s.settimeout(.5)\ntry:\n s.connect(('1.1.1.1',53)); print('NETWORK_OPEN'); raise SystemExit(7)\nexcept OSError:\n print('NETWORK_BLOCKED')\n"""
            receipt=run_action(root,"probe",[sys.executable,"-c",code],10,None,"network-contained")
            self.assertEqual(receipt.exit_code,0)
            self.assertIn("NETWORK_BLOCKED",receipt.stdout)
            self.assertTrue(receipt.environment_fingerprint["network_restricted"])
            self.assertFalse(receipt.environment_fingerprint["filesystem_restricted"])
            self.assertFalse(receipt.environment_fingerprint["sandboxed"])


class Alpha9MultiAgentTests(unittest.TestCase):
    def test_agent_path_lease_blocks_second_agent_and_owner_is_required_to_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"p"; root.mkdir(); (root/"a.py").write_text("value = 1\n")
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                a=ws.agent_open("A")["id"]; b=ws.agent_open("B")["id"]
                tx=ws.stage_change([{"op":"replace_text","path":"a.py","old":"1","new":"2"}],agent_id=a)
                with self.assertRaises(TransactionConflict):
                    ws.stage_change([{"op":"replace_text","path":"a.py","old":"1","new":"3"}],agent_id=b)
                with self.assertRaises(PermissionError): ws.commit_change(tx["id"],agent_id=b)
                out=ws.commit_change(tx["id"],agent_id=a)
                self.assertEqual(out["status"],"committed")
                self.assertEqual((root/"a.py").read_text(),"value = 2\n")
                self.assertEqual(ws.lease_status(a)["leases"],[])
            finally: ws.close()

    def test_agent_utility_is_namespaced_and_only_boosts_same_agent_context(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"p"; root.mkdir()
            (root/"auth.py").write_text("def validate_credentials(user):\n    return bool(user)\n")
            (root/"other.py").write_text("def validate_profile(user):\n    return bool(user)\n")
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                a=ws.agent_open("A")["id"]; b=ws.agent_open("B")["id"]
                c1=ws.orient("validate credential",agent_id=a)
                oid=c1.objects[0].object_id
                ws.context_feedback(c1.handle,[oid],[],2.0,agent_id=a)
                a2=ws.orient("validate credential",agent_id=a)
                b2=ws.orient("validate credential",agent_id=b)
                ra=ws.store.load_json("context_slices",a2.handle)["ranked"]
                rb=ws.store.load_json("context_slices",b2.handle)["ranked"]
                ca=next(x for x in ra if x["object_id"]==oid)
                cb=next(x for x in rb if x["object_id"]==oid)
                self.assertEqual(ca.get("agent_utility_prior"),a)
                self.assertIsNone(cb.get("agent_utility_prior"))
            finally: ws.close()


class Alpha9GitCognitionTests(unittest.TestCase):
    def test_git_status_history_blame_and_explain_line(self):
        if not shutil_which("git"): self.skipTest("git unavailable")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"repo"; root.mkdir()
            subprocess.run(["git","init","-q",str(root)],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.com"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","Habitat Test"],check=True)
            (root/"a.py").write_text("x = 1\n")
            subprocess.run(["git","-C",str(root),"add","a.py"],check=True)
            subprocess.run(["git","-C",str(root),"commit","-q","-m","add initial value"],check=True)
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                st=ws.git_status(); self.assertTrue(st["available"]); self.assertFalse(st["dirty"])
                hist=ws.git_history("a.py",10); self.assertEqual(hist["count"],1); self.assertIn("initial",hist["commits"][0]["subject"])
                blame=ws.git_blame("a.py",1,1); self.assertEqual(blame["lines"][0]["text"],"x = 1")
                exp=ws.git_explain_line("a.py",1); self.assertIn("initial",exp["commit"]["message"])
                (root/"a.py").write_text("x = 2\n")
                self.assertTrue(ws.git_status()["dirty"])
            finally: ws.close()


def shutil_which(name):
    import shutil
    return shutil.which(name)


class Alpha9UncertaintyTests(unittest.TestCase):
    def test_correlated_evidence_is_not_counted_as_independent_votes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"p"; root.mkdir(); (root/"a.py").write_text("def f(): return 1\n")
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                h=ws.hypothesis_create("f is broken",prior_confidence=.4)
                now="2026-01-01T00:00:00Z"
                for i in range(2):
                    eid=f"evidence:test:{i}"
                    ws.store.append_evidence({"id":eid,"kind":"test-failure","revision":ws.revision,"path":"a.py","severity":"error","summary":"f failed","trust":"exact","source":"python.pytest","created_at":now,"active":True,"data":{}})
                    ws.hypothesis_link_evidence(h["id"],eid,"for",1.0)
                h2=ws.hypothesis_status(h["id"])
                a=h2["evidence_assessment"]
                self.assertEqual(a["independent_source_groups"],1)
                self.assertEqual(a["support_strength"],1.0)
                self.assertFalse(a["calibrated_probability"])
            finally: ws.close()


class Alpha9DependencyCognitionTests(unittest.TestCase):
    def test_direct_dependency_snapshot_and_query_are_manifest_grounded(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"p"; root.mkdir()
            (root/"pyproject.toml").write_text('[project]\nname="demo"\nversion="0"\ndependencies=["requests>=2", "pydantic==2.8"]\n')
            (root/"package.json").write_text(json.dumps({"dependencies":{"react":"^19.0.0"},"devDependencies":{"vitest":"^2"}}))
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                snap=ws.dependencies_snapshot(); self.assertEqual(snap["count"],4)
                self.assertIn("pyproject.toml",snap["manifests"]); self.assertIn("package.json",snap["manifests"])
                q=ws.dependencies_query("react"); self.assertEqual(q["count"],1); self.assertEqual(q["matches"][0]["ecosystem"],"npm")
                self.assertIn("Transitive",snap["claim_boundary"])
            finally: ws.close()


class Alpha9ProtocolTests(unittest.TestCase):
    def test_protocol_exposes_policy_git_agent_and_lease_methods(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"p"; root.mkdir(); (root/"a.py").write_text("x=1\n")
            ws=HabitatWorkspace.create(root,Path(td)/"h")
            try:
                methods=set(HabitatProtocol(ws).handle({"id":1,"method":"protocol.capabilities","params":{}})["result"]["methods"])
                for m in {"workspace.policy.status","workspace.execution.security","workspace.git.status","workspace.dependencies.snapshot","workspace.agent.open","workspace.lease.acquire"}:
                    self.assertIn(m,methods)
            finally: ws.close()

if __name__ == "__main__": unittest.main()
