import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from habitat.context.compiler import ContextCompiler
from habitat.execution import run_action
from habitat.mcp_adapter import compose_change_symbol
from habitat.mutation import MutationEngine
from habitat.protocol import HabitatProtocol
from habitat.ui import BrowserRuntime
from habitat.workspace import HabitatWorkspace


class Alpha8PerceptionAndIOTests(unittest.TestCase):
    def test_reconcile_detects_same_size_restored_mtime_edit(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); f=root/'auth.py'
            f.write_text('value = "secret"\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                old=ws.revision; st=f.stat()
                f.write_text('value = "public"\n')
                os.utime(f,ns=(st.st_atime_ns,st.st_mtime_ns))
                out=ws.reconcile()
                self.assertIn('auth.py',out['changed_paths'])
                self.assertNotEqual(ws.revision,old)
            finally: ws.close()

    def test_virtual_page_fault_uses_sparse_authority_range_io(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); f=root/'big.py'
            filler=''.join(f'x_{i} = "'+('a'*90)+'"\n' for i in range(12000))
            f.write_text(filler+'\ndef needle_target(value):\n    return value + 1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                ctx=ws.orient('needle target implementation',12)
                address=ws.context_address_space(ctx.handle,100)
                page=next(p for p in address['pages'] if p.get('fetchable') and p['path']=='big.py' and p.get('source_range'))
                got=ws.context_fetch_pages(ctx.handle,[page['page_id']],10000)
                self.assertIn('needle_target',got['pages'][0]['source'])
                self.assertLess(got['backend_authority_bytes_read'], f.stat().st_size//5)
                self.assertEqual(got['agent_visible_source_bytes'], got['source_bytes'])
            finally: ws.close()

    def test_unicode_task_terms_retrieve_unicode_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir()
            (root/'auth.py').write_text('def xác_thực_người_dùng(quyền_truy_cập):\n    return quyền_truy_cập\n',encoding='utf-8')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                ctx=ws.orient('sửa xác thực người dùng và quyền truy cập',12)
                self.assertTrue(any(o.path=='auth.py' for o in ctx.objects),[(o.path,o.reason) for o in ctx.objects])
            finally: ws.close()

    def test_zero_budget_rejected_consistently(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'a.py').write_text('x=1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                with self.assertRaises(ValueError): ws.orient('x',0)
                with self.assertRaises(ValueError): ws.context_refresh(ws.orient('x',1).handle,0)
            finally: ws.close()

    def test_long_task_coverage_uses_evaluated_denominator(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir()
            names=[f'concept{i}' for i in range(30)]
            (root/'concepts.py').write_text('\n'.join(f'def {n}(): return {i}' for i,n in enumerate(names))+'\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                ctx=ws.orient(' '.join(names),60)
                d=ctx.decision_packet
                self.assertEqual(d['coverage_evaluated_concepts'],30)
                self.assertGreater(d['concept_coverage'],0.8)
            finally: ws.close()


class Alpha8StateMachineAndMutationTests(unittest.TestCase):
    def test_stale_feedback_and_stale_episode_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); f=root/'a.py'; f.write_text('def alpha():\n    return 1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                ctx=ws.orient('alpha implementation',8); oid=ctx.objects[0].object_id
                f.write_text('def alpha():\n    return 2\n'); ws.refresh('external')
                with self.assertRaises(ValueError): ws.context_feedback(ctx.handle,[oid],[])
                with self.assertRaises(ValueError): ws.episode_start('alpha task',ctx.handle)
            finally: ws.close()

    def test_invalid_episode_has_no_transaction_or_run_side_effect(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'a.py').write_text('def a():\n    return 1\n'); (root/'tests').mkdir(); (root/'tests'/'test_a.py').write_text('from a import a\n\ndef test_a(): assert a()==1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                before_tx=ws.store.conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
                with self.assertRaises(KeyError): ws.stage_change([{'op':'replace_text','path':'a.py','old':'return 1','new':'return 2'}],episode_id='missing')
                self.assertEqual(before_tx,ws.store.conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0])
                before_runs=ws.store.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
                with self.assertRaises(KeyError): ws.verify(changed_paths=['a.py'],episode_id='missing')
                self.assertEqual(before_runs,ws.store.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0])
            finally: ws.close()

    def test_completed_episode_cannot_leave_staged_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'a.py').write_text('x=1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                ep=ws.episode_start('change x')
                tx=ws.stage_change([{'op':'replace_text','path':'a.py','old':'x=1','new':'x=2'}],ep['id'])
                with self.assertRaises(ValueError): ws.episode_finish(ep['id'],'completed')
                ws.rollback_change(tx['id'])
                self.assertEqual(ws.episode_finish(ep['id'],'completed')['status'],'completed')
            finally: ws.close()

    def test_crlf_and_executable_mode_survive_text_mutation(self):
        if os.name == 'nt': self.skipTest('POSIX mode semantics')
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); f=root/'script.py'
            f.write_bytes(b'#!/usr/bin/env python3\r\ndef f():\r\n    return 1\r\n'); os.chmod(f,0o755)
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                tx=ws.stage_change([{'op':'replace_text','path':'script.py','old':'return 1','new':'return 2'}])
                ws.commit_change(tx['id'])
                raw=f.read_bytes(); self.assertIn(b'\r\n',raw); self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
                self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o755)
            finally: ws.close()

    def test_write_ahead_recovery_rolls_back_interrupted_apply(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); f=root/'a.py'; f.write_text('x=1\n')
            h=base/'h'; ws=HabitatWorkspace.create(root,h)
            eng=MutationEngine(ws); tx=eng.begin([{'op':'replace_text','path':'a.py','old':'x=1','new':'x=2'}])
            originals,outputs,_=eng._prepare(tx.operations); meta=eng._backup(tx,originals)
            journal={'version':1,'transaction_id':tx.id,'base_revision':tx.base_revision,'state':'applying','backup_meta':meta,'applied':[{'op':'write','path':'a.py'}],'created_at':'probe'}
            eng._write_journal(tx.id,journal); ws.write_source_bytes('a.py',outputs['a.py']); ws.close()
            reopened=HabitatWorkspace(h)
            try:
                self.assertEqual(f.read_text(),'x=1\n')
                self.assertTrue(any(x['transaction_id']==tx.id and x['action']=='rolled-back-incomplete-transaction' for x in reopened.enter()['startup_transaction_recovery']))
            finally: reopened.close()


class Alpha8PolicyAndSafetyTests(unittest.TestCase):
    def test_gitignore_and_habitatignore_exclude_sensitive_and_generated_files(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'custom_generated').mkdir()
            (root/'.gitignore').write_text('secret.yaml\ncustom_generated/\n')
            (root/'secret.yaml').write_text('SUPERSECRET=1\n'); (root/'custom_generated'/'gen.py').write_text('GENERATED=1\n'); (root/'keep.py').write_text('KEEP=1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                paths={r['path'] for r in ws.store.all_files()}
                self.assertIn('keep.py',paths); self.assertNotIn('secret.yaml',paths); self.assertNotIn('custom_generated/gen.py',paths)
                self.assertFalse(any(r['path']=='secret.yaml' for r in ws.query('SUPERSECRET')))
            finally: ws.close()

    def test_workspace_state_cannot_live_inside_source_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); (root/'a.py').write_text('x=1\n')
            with self.assertRaises(ValueError): HabitatWorkspace.create(root,root/'.habitat')

    def test_workspace_identity_reuse_requires_explicit_reset_and_single_file_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); one=base/'one.py'; two=base/'two.py'; one.write_text('ONE=1\n'); two.write_text('TWO=2\n'); h=base/'h'
            HabitatWorkspace.create(one,h).close()
            with self.assertRaises(FileExistsError): HabitatWorkspace.create(two,h)
            ws=HabitatWorkspace.create(two,h,reset=True)
            try: self.assertEqual({r['path'] for r in ws.store.all_files()},{'two.py'})
            finally: ws.close()

    def test_protocol_rejects_truthy_string_boolean(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'a.py').write_text('x=1\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                r=HabitatProtocol(ws).handle({'id':1,'method':'workspace.events.poll','params':{'reconcile':'false'}})
                self.assertFalse(r['ok']); self.assertEqual(r['error']['code'],'INVALID_PARAMS')
            finally: ws.close()

    def test_unbound_unique_python_name_does_not_create_cross_file_call_edge(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir()
            (root/'a.py').write_text('def helper():\n    return 1\n'); (root/'b.py').write_text('def run():\n    return helper()\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                helper=next(s for s in ws.store.all_symbols() if s['path']=='a.py' and s['name']=='helper')
                run=next(s for s in ws.store.all_symbols() if s['path']=='b.py' and s['name']=='run')
                rels=ws.store.relations_for(run['id'])
                self.assertFalse(any(r['kind']=='calls' and r['target_id']==helper['id'] for r in rels),[dict(r) for r in rels])
            finally: ws.close()

    def test_execution_capture_is_disk_bounded_and_redacts_common_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); code='print("API_KEY=supersecret")\nprint("x"*200000)\n'
            receipt=run_action(root,'probe',[os.environ.get('PYTHON',os.sys.executable),'-c',code],20,'script')
            self.assertGreater(receipt.stdout_total_bytes,64000)
            self.assertLessEqual(len(receipt.stdout.encode()),64000)
            self.assertNotIn('supersecret',receipt.stdout)
            self.assertGreaterEqual(receipt.redaction['stdout_matches'],1)
            self.assertFalse(receipt.environment_fingerprint['sandboxed'])

    def test_non_utf8_source_is_marked_lossy_not_claimed_exact_text(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'legacy.txt').write_bytes(b'alpha\xffbeta\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                page=ws.read_source('legacy.txt',1,10)
                self.assertTrue(page['lossy_text']); self.assertIn('\ufffd',page['source']); self.assertEqual(page['encoding'],'utf-8-with-replacement')
            finally: ws.close()

    @unittest.skipUnless(BrowserRuntime.probe().get('available'), 'browser unavailable')
    def test_browser_external_navigation_is_denied_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'index.html').write_text('<h1>ok</h1>')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                with self.assertRaises(PermissionError): ws.open_ui_runtime('https://example.com')
                obs=ws.open_ui_runtime('index.html'); self.assertFalse(obs['security']['external_network_allowed'])
                ws.close_ui_runtime(obs['session_id'])
            finally: ws.close()

    def test_structural_create_move_delete_are_first_class_transaction_ops(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'a.py').write_text('x = 1\n',encoding='utf-8')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                tx=ws.stage_change([{'op':'create_file','path':'new.py','content':'value = 2\n','mode':0o640}])
                out=ws.commit_change(tx['id']); self.assertIn('new.py',out['changed_paths']); self.assertTrue((root/'new.py').is_file())
                tx=ws.stage_change([{'op':'move_file','from_path':'new.py','to_path':'moved.py'}])
                ws.commit_change(tx['id']); self.assertFalse((root/'new.py').exists()); self.assertTrue((root/'moved.py').is_file())
                tx=ws.stage_change([{'op':'delete_file','path':'moved.py'}])
                ws.commit_change(tx['id']); self.assertFalse((root/'moved.py').exists())
            finally: ws.close()

    def test_mcp_change_symbol_reports_commit_even_if_verification_errors(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'a.py').write_text('def f():\n    return 1\n',encoding='utf-8')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                sym=next(s for s in ws.store.all_symbols() if s['name']=='f')
                original_verify=ws.verify
                def boom(*args,**kwargs): raise RuntimeError('verification probe failed')
                ws.verify=boom
                out=compose_change_symbol(ws,sym['id'],'def f():\n    return 2\n',verify=True)
                self.assertTrue(out['committed']); self.assertEqual(out['status'],'COMMITTED_VERIFICATION_ERROR')
                self.assertIn('return 2',(root/'a.py').read_text())
                self.assertEqual(out['verification_error']['type'],'RuntimeError')
                ws.verify=original_verify
            finally: ws.close()


class Alpha8HypothesisTests(unittest.TestCase):
    def test_explicit_hypothesis_experiment_loop_is_revision_bound(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'p'; root.mkdir(); (root/'auth.py').write_text('def validate(x):\n    return bool(x)\n')
            ws=HabitatWorkspace.create(root,base/'h')
            try:
                ctx=ws.orient('validate authentication',8); ep=ws.episode_start('debug auth',ctx.handle)
                h=ws.hypothesis_create('stale entitlement causes authorization failure',episode_id=ep['id'],prior_confidence=0.35)
                self.assertEqual(h['confidence_semantics'],'agent belief annotation; not calibrated probability')
                h=ws.hypothesis_link_evidence(h['id'],None,'for',1.5,'observed failure only under expired entitlement')
                self.assertEqual(h['evidence_balance']['for_weight'],1.5)
                ex=ws.experiment_plan('compare refresh behavior before and after entitlement expiry',hypothesis_id=h['id'],discriminator='failure only after expiry')
                self.assertEqual(ex['status'],'planned')
                done=ws.experiment_complete(ex['id'],{'observed':'failure after expiry only'},'completed')
                self.assertEqual(done['status'],'completed')
                updated=ws.hypothesis_update(h['id'],status='supported',confidence=0.72,reason='discriminating experiment matched prediction')
                self.assertEqual(updated['status'],'supported'); self.assertAlmostEqual(updated['current_confidence'],0.72)
                graph=ws.causality_graph(h['id'])
                self.assertTrue(any(e['relation']=='tested-by' for e in graph['edges']))
            finally: ws.close()


    def test_hypothesis_and_experiment_schema_contracts(self):
        import json
        import jsonschema
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=root/'project'; project.mkdir(); (project/'a.py').write_text('def f():\n    return 1\n',encoding='utf-8')
            with HabitatWorkspace.create(project,root/'h') as ws:
                ctx=ws.orient('inspect f',4); ep=ws.episode_start('inspect f',ctx.handle)
                hyp=ws.hypothesis_create('f may be wrong',episode_id=ep['id'],prior_confidence=0.4)
                exp=ws.experiment_plan('run discriminating check',hypothesis_id=hyp['id'],discriminator='f returns 1',expected={'return':1})
                base=Path(__file__).resolve().parents[1]/'schemas'
                jsonschema.validate(hyp,json.loads((base/'hypothesis.schema.json').read_text()))
                jsonschema.validate(exp,json.loads((base/'experiment.schema.json').read_text()))


if __name__ == '__main__':
    unittest.main()

