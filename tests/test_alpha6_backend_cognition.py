from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


class Alpha6BackendCognitionTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        p=root/'project'; (p/'tests').mkdir(parents=True)
        (p/'auth.py').write_text(
            'def validate_credentials(user, password):\n'
            '    return user == "admin" and password == "secret"\n\n'
            'def login(user, password):\n'
            '    return validate_credentials(user, password)\n', encoding='utf-8')
        (p/'legacy.py').write_text(
            'def validate_credentials_legacy(user, password):\n'
            '    return False\n', encoding='utf-8')
        (p/'tests'/'test_auth.py').write_text(
            'import unittest\nfrom auth import validate_credentials\n\n'
            'class T(unittest.TestCase):\n'
            '    def test_valid(self):\n'
            '        self.assertTrue(validate_credentials("admin", "secret"))\n', encoding='utf-8')
        return p

    def test_directory_mirror_separates_authority_from_semantic_materialization(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root); habitat=root/'habitat'
            with HabitatWorkspace.create(project, habitat, backend='mirror') as ws:
                info=ws.backend_info()
                self.assertEqual(info['kind'],'directory-mirror')
                self.assertNotEqual(info['authoritative_root'],info['materialized_root'])
                self.assertFalse(info['semantic_twin_authority'])
                ctx=ws.orient('fix credential validation login',8)
                self.assertEqual(ctx.decision_packet['retrieval_confidence'],'high')
                sym=next(s for s in ws.store.all_symbols() if s['qualified_name']=='validate_credentials')
                body=ws.inspect(sym['id'],'body')['source']
                staged=ws.stage_symbol_change(sym['id'],body.replace('password == "secret"','password == "better"'))
                committed=ws.commit_change(staged['id'])
                self.assertIn('auth.py',committed['changed_paths'])
                self.assertIn('"better"',(project/'auth.py').read_text())
                self.assertIn('"better"',(Path(info['materialized_root'])/'auth.py').read_text())
                with self.assertRaises(RuntimeError):
                    ws.watch_start()

    def test_mirror_page_fault_detects_authority_drift_before_reconcile(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project, root/'habitat', backend='mirror') as ws:
                ctx=ws.orient('credential validation login',8)
                plan=ws.context_plan_next(ctx.handle,max_pages=1,max_estimated_bytes=5000)
                self.assertEqual(plan['action'],'fault-pages')
                page_id=plan['page_ids'][0]
                # Change authority without reconciling the semantic mirror. Exact page fault must reject it.
                auth=(project/'auth.py')
                auth.write_text(auth.read_text().replace('"secret"','"drifted"'),encoding='utf-8')
                result=ws.context_fetch_pages(ctx.handle,[page_id],5000)
                self.assertEqual(result['pages'],[])
                self.assertEqual(result['faults'][0]['reason'],'context-revision-stale')

    def test_mirror_targeted_refresh_does_not_require_full_backend_enumeration(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h',backend='mirror') as ws:
                auth=project/'auth.py'
                auth.write_text(auth.read_text().replace('password == "secret"','password == "rotated"'),encoding='utf-8')
                result=ws.refresh_paths(['auth.py'],'targeted-backend-probe')
                sync=result['backend_sync']
                self.assertEqual(sync['listing_mode'],'targeted-no-enumeration')
                self.assertEqual(sync['paths_considered'],1)
                self.assertEqual(sync['hydrated_paths'],['auth.py'])
                self.assertEqual(result['hashed_files'],1)
                self.assertIn('"rotated"',ws.inspect(next(s['id'] for s in ws.store.all_symbols() if s['path']=='auth.py' and s['name']=='validate_credentials'),'body')['source'])

    def test_context_feedback_is_bounded_prior_and_cannot_invent_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                first=ws.orient('credential validation login',10)
                ranked=ws.store.load_json('context_slices',first.handle)['ranked']
                auth=next(x for x in ranked if x['path']=='auth.py' and x['kind']=='symbol')
                legacy=next(x for x in ranked if x['path']=='legacy.py' and x['kind']=='symbol')
                fb=ws.context_feedback(first.handle,[auth['object_id']],[legacy['object_id']],1.0)
                self.assertTrue(fb['feedback_is_attention_prior_not_source_truth'])
                second=ws.orient('credential validation login',10)
                second_ranked=ws.store.load_json('context_slices',second.handle)['ranked']
                a2=next(x for x in second_ranked if x['object_id']==auth['object_id'])
                l2=next(x for x in second_ranked if x['object_id']==legacy['object_id'])
                self.assertIn('utility',a2['lane'])
                self.assertGreater(a2['score'],l2['score'])
                with self.assertRaises(ValueError):
                    ws.context_feedback(first.handle,['symbol:not-a-candidate'],[],1.0)

    def test_page_planner_abstains_on_no_gold_without_source_read(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                ctx=ws.orient('quantum banana teleportation matrix',8)
                plan=ws.context_plan_next(ctx.handle,max_pages=4,max_estimated_bytes=5000)
                self.assertEqual(plan['action'],'abstain-or-broaden-query')
                self.assertEqual(plan['planned_pages'],[])
                self.assertEqual(plan['source_bytes_read'],0)

    def test_work_episode_links_context_transaction_revision_verification(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                ctx=ws.orient('change credential validation and verify',10)
                ep=ws.episode_start('change credential validation and verify',ctx.handle)
                sym=next(s for s in ws.store.all_symbols() if s['qualified_name']=='validate_credentials')
                body=ws.inspect(sym['id'],'body')['source']
                staged=ws.stage_symbol_change(sym['id'],body.replace('password == "secret"','password in {"secret", "backup"}'),ep['id'])
                committed=ws.commit_change(staged['id'])
                verification=ws.verify(changed_paths=committed['changed_paths'],episode_id=ep['id'])
                self.assertEqual(verification['receipt']['exit_code'],0)
                final=ws.episode_finish(ep['id'],'completed',{'verification':'passed'})
                kinds=[x['kind'] for x in final['links']]
                self.assertIn('context-compiled',kinds)
                self.assertIn('transaction-staged',kinds)
                self.assertIn('transaction-committed',kinds)
                self.assertIn('verification-run',kinds)
                self.assertIn('episode-closed',kinds)
                explained=ws.causality_explain(staged['id'])
                self.assertEqual(explained['episode_count'],1)
                self.assertEqual(explained['episodes'][0]['id'],ep['id'])

    def test_mirror_verification_receipt_binds_execution_backend(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h',backend='mirror') as ws:
                result=ws.verify(changed_paths=['auth.py'],timeout_s=30)
                receipt=result['receipt']
                info=ws.backend_info()
                self.assertEqual(receipt['exit_code'],0)
                self.assertEqual(receipt['backend_id'],info['backend_id'])
                self.assertEqual(receipt['execution_backend'],info['execution_kind'])
                self.assertEqual(info['kind'],'directory-mirror')

    def test_checkpoint_can_bind_active_work_episode(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                ctx=ws.orient('credential validation login',8)
                ep=ws.episode_start('credential validation login',ctx.handle)
                cp=ws.checkpoint('credential validation login',next_action='verify auth',episode_id=ep['id'])
                self.assertEqual(cp['episode_id'],ep['id'])
                resumed=ws.resume(cp['id'])
                self.assertEqual(resumed['episode_id'],ep['id'])
                self.assertEqual(resumed['episode']['status'],'active')
                self.assertIn('checkpoint-created',[x['kind'] for x in resumed['episode']['links']])

    def test_checkpoint_binds_backend_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root); h=root/'h'
            with HabitatWorkspace.create(project,h) as ws:
                cp=ws.checkpoint('continue auth work')
                self.assertIn('backend_binding',cp)
            manifest=json.loads((h/'workspace.json').read_text())
            manifest['backend']['id']='backend:changed-for-probe'
            (h/'workspace.json').write_text(json.dumps(manifest),encoding='utf-8')
            with HabitatWorkspace(h) as ws2:
                resumed=ws2.resume(cp['id'])
                self.assertTrue(resumed['backend_identity_drift'])
                self.assertEqual(resumed['resume_mode'],'reorient')

    def test_protocol_exposes_backend_feedback_planner_and_episode(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                proto=HabitatProtocol(ws)
                caps=proto.handle({'id':'c','method':'protocol.capabilities','params':{}})
                methods=set(caps['result']['methods'])
                for name in ('workspace.backend.info','workspace.context.plan_next','workspace.context.feedback','workspace.episode.start','workspace.causality.explain'):
                    self.assertIn(name,methods)
                b=proto.handle({'id':'b','method':'workspace.backend.info','params':{}})
                self.assertTrue(b['ok']); self.assertEqual(b['result']['kind'],'local-filesystem')


if __name__ == '__main__':
    unittest.main()
