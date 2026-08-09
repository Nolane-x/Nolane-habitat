import json, tempfile, unittest
from pathlib import Path
import jsonschema
from habitat.workspace import HabitatWorkspace
from habitat.model import to_dict
from habitat.ui import BrowserRuntime

class Alpha1SchemaContracts(unittest.TestCase):
    def schema(self,name): return json.loads((Path(__file__).parents[1]/'schemas'/name).read_text())
    def normalize(self,v): return json.loads(json.dumps(to_dict(v)))
    def test_manifest_context_transaction_execution_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); p=r/'p'; p.mkdir(); (p/'tests').mkdir()
            (p/'a.py').write_text('def f():\n    return 1\n')
            (p/'tests'/'test_a.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_x(self): self.assertTrue(True)\n')
            ws=HabitatWorkspace.create(p,r/'h')
            jsonschema.validate(ws.manifest,self.schema('workspace-manifest.schema.json'))
            ctx=ws.orient('fix f implementation',5); jsonschema.validate(self.normalize(ctx),self.schema('context-slice.schema.json'))
            sym=next(s for s in ws.store.all_symbols() if s['name']=='f')
            tx=ws.stage_symbol_change(sym['id'],'def f():\n    return 2'); jsonschema.validate(tx,self.schema('transaction.schema.json'))
            run=ws.run('python.unittest',20); jsonschema.validate(run,self.schema('execution-receipt.schema.json'))
            ws.close()
    @unittest.skipUnless(BrowserRuntime.probe()['available'],'runtime browser unavailable')
    def test_runtime_ui_contract(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); p=r/'p'; p.mkdir(); (p/'index.html').write_text('<button id="b">B</button>')
            ws=HabitatWorkspace.create(p,r/'h'); obs=ws.open_ui_runtime('index.html')
            jsonschema.validate(obs,self.schema('runtime-ui-surface.schema.json')); ws.close()

if __name__=='__main__': unittest.main()
