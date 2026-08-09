from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from habitat.protocol import HabitatProtocol
from habitat.workspace import HabitatWorkspace


class Alpha12ObservatoryCinematicTests(unittest.TestCase):
    def make_ws(self):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); root=base/'project'; root.mkdir(); hab=base/'habitat'
        (root/'app.py').write_text('''import os\n\ndef load_user(user_id):\n    if not user_id:\n        raise ValueError("missing user")\n    token=os.getenv("TOKEN")\n    return db.query(user_id)\n''',encoding='utf-8')
        (root/'package.json').write_text(json.dumps({'name':'cinematic-demo','scripts':{'test':'pytest'}}),encoding='utf-8')
        (root/'docker-compose.yml').write_text('services:\n  api:\n    image: demo/api\n  db:\n    image: postgres\n',encoding='utf-8')
        ws=HabitatWorkspace.create(root,hab); self.addCleanup(ws.close); self.addCleanup(td.cleanup)
        return ws,root

    def test_observatory_snapshot_contains_effect_world_runtime_counterfactual_and_director(self):
        ws,root=self.make_ws(); a=ws.agent_open('Codex')['id']; ep=ws.episode_start('debug load user')
        ws.epistemic_create('contradiction','static validation exists but runtime still errors',agent_id=a,episode_id=ep['id'])
        ws.effect_refresh(['app.py'])
        ws.runtime_ingest('opentelemetry',[{
            'trace_id':'t','span_id':'s','name':'GET /users/:id','duration_ms':4.2,
            'attributes':{'service.name':'api','http.route':'/users/:id','db.system':'postgresql','code.file.path':str(root/'app.py'),'code.line.number':3}
        }],agent_id=a,episode_id=ep['id'])
        world=ws.counterfactual_fork('guard missing user',agent_id=a)
        ws.counterfactual_apply(world['id'],[{'op':'replace_text','path':'app.py','old':'raise ValueError("missing user")','new':'return None'}])
        obs=ws.observatory_start(open_browser=False); self.addCleanup(ws.observatory_stop)
        snap=json.loads(urllib.request.urlopen(obs['url']+'api/snapshot',timeout=5).read())
        self.assertTrue(snap['read_only'])
        self.assertGreater(len(snap['effects']),0)
        self.assertGreater(len(snap['project_world']['nodes']),0)
        self.assertGreater(len(snap['runtime_topology']['nodes']),0)
        self.assertEqual(snap['counterfactual_worlds'][0]['status'],'open')
        self.assertEqual(snap['cognitive_director']['next']['operation'],'discriminate-contradiction')
        self.assertGreaterEqual(snap['visual_metrics']['graph_nodes'],1)

    def test_observatory_assets_are_spectator_only_and_cinematic_runtime_has_no_controls(self):
        base=Path(__file__).parents[1]/'habitat'/'observatory_assets'
        html=(base/'index.html').read_text(encoding='utf-8').lower()
        js=(base/'app.js').read_text(encoding='utf-8')
        css=(base/'style.css').read_text(encoding='utf-8')
        self.assertNotIn('<button',html); self.assertNotIn('<form',html); self.assertNotIn('<input',html)
        self.assertIn('observer only',html); self.assertIn('auto-camera',html)
        self.assertIn('spawnEvent',js); self.assertIn('camera',js.lower()); self.assertIn('requestAnimationFrame',js)
        self.assertIn('shock',css.lower()); self.assertIn('scanline',css.lower())

    def test_protocol_declares_new_world_and_counterfactual_surfaces(self):
        ws,_=self.make_ws(); methods=set(HabitatProtocol(ws).METHODS)
        expected={
            'workspace.cognition.plan','workspace.project.world','workspace.effect.refresh','workspace.effect.snapshot',
            'workspace.runtime.topology','workspace.counterfactual.fork','workspace.counterfactual.status','workspace.counterfactual.apply',
            'workspace.counterfactual.evaluate','workspace.counterfactual.compare','workspace.counterfactual.promote','workspace.counterfactual.discard'
        }
        self.assertTrue(expected.issubset(methods))

    def test_ui_runtime_domain_actions_emit_observable_activity(self):
        # This regression verifies the domain event surface without requiring Chromium by stubbing the runtime.
        ws,_=self.make_ws()
        class Stub:
            def open(self,*a,**k): return {'session_id':'ui:s1','elements':[]}
            def observe(self,*a,**k): return {'session_id':'ui:s1','elements':[{'handle':'ui:id:x'}]}
            def act(self,*a,**k): return {'session_id':'ui:s1','elements':[]}
            def assert_semantic(self,*a,**k): return {'passed':True,'assertions':[]}
            def close_session(self,*a,**k): return {'closed':True}
            def close(self): return None
        ws._browser_runtime=Stub()
        ws.open_ui_runtime('index.html'); ws.observe_ui_runtime('ui:s1'); ws.act_ui_runtime('ui:s1','click','ui:id:x'); ws.assert_ui_runtime('ui:s1',[{'handle':'ui:id:x','exists':True}]); ws.close_ui_runtime('ui:s1')
        kinds={x['kind'] for x in ws.activity_since(0,500)['events']}
        for k in {'ui.runtime-opened','ui.runtime-observed','ui.action-started','ui.action-completed','ui.assertion','ui.runtime-closed'}:
            self.assertIn(k,kinds)


if __name__=='__main__': unittest.main()
