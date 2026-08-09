from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import jsonschema
from habitat.workspace import HabitatWorkspace

class Alpha7SchemaContracts(unittest.TestCase):
    def schema(self,name):
        return json.loads((Path(__file__).parents[1]/'schemas'/name).read_text())

    def test_alpha7_public_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); p=r/'p'; p.mkdir(); (p/'tests').mkdir()
            (p/'auth.py').write_text('def validate_credentials(x):\n    return bool(x)\n',encoding='utf-8')
            (p/'tests'/'test_auth.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n',encoding='utf-8')
            with HabitatWorkspace.create(p,r/'h') as ws:
                jsonschema.validate(ws.manifest,self.schema('workspace-manifest.schema.json'))
                jsonschema.validate(ws.backend_info(),self.schema('backend-info.schema.json'))
                explored=ws.explore('credential validation',line_budget=8,max_regions=3)
                jsonschema.validate(explored,self.schema('exploration-regions.schema.json'))
                ctx=ws.orient('credential validation',8)
                plan=ws.context_plan_next(ctx.handle,max_pages=1,max_estimated_bytes=4000)
                ws.context_fetch_pages(ctx.handle,plan['page_ids'],4000)
                ranked=ws.store.load_json('context_slices',ctx.handle)['ranked']
                if ranked:
                    ws.context_feedback(ctx.handle,[ranked[0]['object_id']],[],1.0)
                jsonschema.validate(ws.context_efficiency(ctx.handle),self.schema('context-efficiency.schema.json'))
                ep=ws.episode_start('credential validation',ctx.handle)
                jsonschema.validate(ws.causality_graph(ep['id']),self.schema('causal-graph.schema.json'))

if __name__=='__main__': unittest.main()
