from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace
from habitat.backends.local import DirectoryMirrorSourceAuthority, LocalExecutionProvider, CompositeProjectBackend


class Alpha7DeepSubstrateTests(unittest.TestCase):
    def _python_project(self, root: Path) -> Path:
        p=root/'project'; (p/'tests').mkdir(parents=True)
        (p/'auth.py').write_text(
            'def validate_credentials(user, password):\n'
            '    return user == "admin" and password == "secret"\n\n'
            'def login(user, password):\n'
            '    return validate_credentials(user, password)\n', encoding='utf-8')
        (p/'billing.py').write_text('def calculate_tax(total):\n    return total * 0.1\n',encoding='utf-8')
        for i in range(12):
            (p/f'noise_{i:02d}.py').write_text(f'def helper_{i}(value):\n    return value\n',encoding='utf-8')
        (p/'tests'/'test_auth.py').write_text(
            'import unittest\nfrom auth import validate_credentials\n\n'
            'class T(unittest.TestCase):\n'
            '    def test_valid(self):\n'
            '        self.assertTrue(validate_credentials("admin", "secret"))\n',encoding='utf-8')
        return p

    def _ts_project(self, root: Path) -> Path:
        p=root/'ts'; p.mkdir()
        (p/'a.ts').write_text('export function target(x:number){ return x + 1; }\n',encoding='utf-8')
        (p/'b.ts').write_text('import { target } from "./a";\nexport function run(){ return target(1); }\n',encoding='utf-8')
        (p/'c.ts').write_text('export function other(){ return 3; }\n',encoding='utf-8')
        return p

    def test_manifest_binds_source_authority_and_execution_provider_separately(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._python_project(root); h=root/'h'
            with HabitatWorkspace.create(project,h,backend='mirror') as ws:
                info=ws.backend_info()
                self.assertTrue(info['substrate_composable'])
                self.assertNotEqual(info['source_authority_id'],info['execution_provider_id'])
                self.assertEqual(info['source_authority']['kind'],'directory-mirror')
                self.assertEqual(info['execution_provider']['kind'],'authority-local-process')
            manifest=json.loads((h/'workspace.json').read_text())
            self.assertGreaterEqual(manifest['schema'],4)
            self.assertEqual(manifest['source_authority'],'external-directory')
            self.assertIn('source_authority_provider',manifest)
            self.assertIn('execution_provider',manifest)

    def test_execution_provider_identity_drift_invalidates_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._python_project(root); h=root/'h'
            with HabitatWorkspace.create(project,h) as ws:
                cp=ws.checkpoint('continue auth work')
            manifest=json.loads((h/'workspace.json').read_text())
            manifest['execution_provider']['id']='executor:drift-probe'
            (h/'workspace.json').write_text(json.dumps(manifest),encoding='utf-8')
            with HabitatWorkspace(h) as ws:
                resumed=ws.resume(cp['id'])
                self.assertTrue(resumed['backend_identity_drift'])
                self.assertEqual(resumed['resume_mode'],'selective-revalidate')

    def test_context_fault_ledger_reports_explicit_utilization(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._python_project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                ctx=ws.orient('credential validation login',12)
                ep=ws.episode_start('credential validation login',ctx.handle)
                plan=ws.context_plan_next(ctx.handle,max_pages=2,max_estimated_bytes=5000)
                fetched=ws.context_fetch_pages(ctx.handle,plan['page_ids'],5000)
                self.assertGreater(fetched['source_bytes'],0)
                used=fetched['pages'][0]['object_id']
                ws.context_feedback(ctx.handle,[used],[],1.0)
                report=ws.context_efficiency(ctx.handle)
                self.assertGreaterEqual(report['fault_count'],1)
                self.assertGreater(report['exact_source_bytes'],0)
                self.assertIn(used,report['used_objects'])
                self.assertIn('bytes are not tokens',report['measurement_boundary'])
                ep_report=ws.episode_efficiency(ep['id'])
                self.assertGreater(ep_report['exact_source_bytes'],0)

    def test_causal_graph_crosses_context_transaction_revision_run(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._python_project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                ctx=ws.orient('change credential validation and verify',12)
                ep=ws.episode_start('change credential validation and verify',ctx.handle)
                sym=next(s for s in ws.store.all_symbols() if s['qualified_name']=='validate_credentials')
                body=ws.inspect(sym['id'],'body')['source']
                tx=ws.stage_symbol_change(sym['id'],body.replace('password == "secret"','password in {"secret", "backup"}'),ep['id'])
                committed=ws.commit_change(tx['id'])
                verification=ws.verify(changed_paths=committed['changed_paths'],episode_id=ep['id'])
                graph=ws.causality_graph(ctx.handle,max_depth=6,max_edges=100)
                relations={e['relation'] for e in graph['edges']}
                self.assertIn('grounds',relations)
                self.assertIn('informed',relations)
                self.assertIn('produced',relations)
                self.assertIn('verified_with',relations)
                refs={e['source_ref'] for e in graph['edges']}|{e['target_ref'] for e in graph['edges']}
                self.assertIn(tx['id'],refs)
                self.assertIn(verification['receipt']['id'],refs)

    def test_line_budget_explorer_is_region_precise_and_no_gold_abstains(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._python_project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                result=ws.explore('fix credential validation login',line_budget=8,max_regions=4)
                self.assertFalse(result['abstained'])
                self.assertLessEqual(result['lines_selected'],8)
                self.assertEqual(result['source_bytes_read'],0)
                self.assertTrue(result['regions'])
                self.assertEqual(result['regions'][0]['path'],'auth.py')
                self.assertFalse(any(r['path'].startswith('noise_') for r in result['regions']))
                no_gold=ws.explore('quantum banana teleportation matrix',line_budget=20,max_regions=4)
                self.assertTrue(no_gold['abstained'])
                self.assertEqual(no_gold['regions'],[])
                self.assertEqual(no_gold['source_bytes_read'],0)

    def test_typescript_language_service_session_reuses_process_for_dirty_partition(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._ts_project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                first=(ws.store.load_project_cache('semantic-typescript-summary-v8') or {}).get('report') or {}
                if not first.get('available'):
                    self.skipTest(first.get('reason','TypeScript unavailable'))
                (project/'a.ts').write_text('export function target(x:number){ return x + 2; }\n',encoding='utf-8')
                ws.refresh(reason='alpha7-ts-body-1')
                second=(ws.store.load_project_cache('semantic-typescript-summary-v8') or {}).get('report') or {}
                self.assertTrue(second.get('persistent_session'))
                self.assertTrue(second.get('session_reused'))
                self.assertEqual(second.get('partitions_recomputed'),1)
                self.assertEqual(second.get('scanned_files'),1)
                self.assertEqual(second.get('hydrated_files'),1)

    def test_decoupled_executor_source_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); authority=root/'authority'; mirror=root/'mirror'; execution=root/'execution'
            authority.mkdir(); execution.mkdir()
            (authority/'x.py').write_text('value = 1\n',encoding='utf-8')
            (execution/'x.py').write_text('value = 1\n',encoding='utf-8')
            source=DirectoryMirrorSourceAuthority(authority,mirror)
            executor=LocalExecutionProvider(execution,kind='sandbox-local')
            backend=CompositeProjectBackend(source,executor)
            capability={
                'id':'probe.mutate','kind':'script',
                'argv':[sys.executable,'-c','from pathlib import Path; Path("x.py").write_text("value = 2\\n")'],
            }
            with self.assertRaisesRegex(RuntimeError,'non-authoritative checkout'):
                backend.run(capability,20)
            self.assertEqual((authority/'x.py').read_text(encoding='utf-8'),'value = 1\n')
            self.assertEqual((mirror/'x.py').read_text(encoding='utf-8'),'value = 1\n')

    def test_host_runtime_shutdown_is_idempotent_and_drains_global_services(self):
        from habitat import runtime_service_status, shutdown_runtime_services
        before=runtime_service_status()
        first=shutdown_runtime_services(); second=shutdown_runtime_services()
        after=runtime_service_status()
        self.assertFalse(first['errors'],first)
        self.assertFalse(second['errors'],second)
        self.assertEqual(after['typescript'].get('session_count'),0)
        self.assertEqual(after['jedi'].get('project_count'),0)
        self.assertFalse(after['browser'].get('browser_started'))
        self.assertTrue(second['idempotent'])

    def test_protocol_exposes_alpha7_high_level_methods(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=self._python_project(root)
            with HabitatWorkspace.create(project,root/'h') as ws:
                methods=set(HabitatProtocol(ws).METHODS)
                for name in ('workspace.explore','workspace.context.efficiency','workspace.episode.efficiency','workspace.causality.graph'):
                    self.assertIn(name,methods)


if __name__ == '__main__':
    unittest.main()
