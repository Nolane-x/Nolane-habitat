import json, tempfile, unittest
from pathlib import Path
import jsonschema
from habitat.model import to_dict
from habitat.workspace import HabitatWorkspace

class Alpha2SchemaContracts(unittest.TestCase):
    def schema(self,n): return json.loads((Path(__file__).parents[1]/'schemas'/n).read_text())
    def norm(self,v): return json.loads(json.dumps(to_dict(v)))
    def test_context_occurrence_event_impact_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); p=r/'p'; p.mkdir(); (p/'tests').mkdir()
            (p/'a.py').write_text('def f(x):\n    return x\n')
            (p/'tests'/'test_a.py').write_text('import unittest\nimport a\nclass T(unittest.TestCase):\n    def test_f(self): self.assertTrue(a.f(True))\n')
            ws=HabitatWorkspace.create(p,r/'h')
            ctx=self.norm(ws.orient('fix f and verify',5)); jsonschema.validate(ctx,self.schema('context-slice.schema.json'))
            sym=next(s for s in ws.store.all_symbols() if s['path']=='a.py' and s['name']=='f')
            refs=ws.references(sym['id'])['occurrences']; self.assertTrue(refs)
            for o in refs: jsonschema.validate(o,self.schema('occurrence.schema.json'))
            impact=ws.impact(object_ids=[sym['id']]); jsonschema.validate(impact,self.schema('impact-plan.schema.json'))
            events=ws.events_poll(0,reconcile=False)['events']; self.assertTrue(events)
            for e in events: jsonschema.validate(e,self.schema('workspace-event.schema.json'))

if __name__=='__main__': unittest.main()
