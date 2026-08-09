from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import jsonschema
from habitat.workspace import HabitatWorkspace

class Alpha6SchemaContracts(unittest.TestCase):
    def schema(self,name): return json.loads((Path(__file__).parents[1]/'schemas'/name).read_text())
    def test_backend_feedback_plan_episode_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); p=r/'p'; p.mkdir(); (p/'auth.py').write_text('def validate_credentials(x):\n    return bool(x)\n')
            with HabitatWorkspace.create(p,r/'h') as ws:
                jsonschema.validate(ws.backend_info(),self.schema('backend-info.schema.json'))
                ctx=ws.orient('credential validation',8)
                plan=ws.context_plan_next(ctx.handle,max_pages=1,max_estimated_bytes=4000)
                jsonschema.validate(plan,self.schema('context-page-plan.schema.json'))
                ranked=ws.store.load_json('context_slices',ctx.handle)['ranked']
                fb=ws.context_feedback(ctx.handle,[ranked[0]['object_id']],[],1.0)
                jsonschema.validate(fb,self.schema('context-feedback.schema.json'))
                ep=ws.episode_start('credential validation',ctx.handle)
                jsonschema.validate(ep,self.schema('work-episode.schema.json'))

if __name__=='__main__': unittest.main()
