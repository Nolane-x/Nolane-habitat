import json,tempfile,unittest
from pathlib import Path
from habitat.workspace import HabitatWorkspace

class Alpha5SchemaContracts(unittest.TestCase):
    def schema(self,name): return json.loads((Path(__file__).resolve().parents[1]/'schemas'/name).read_text())
    def test_alpha5_schemas_have_required_contracts(self):
        for name,required in {
            'context-address-space.schema.json':{'handle','pages','page_count','whole_file_dump_default'},
            'context-page-fault.schema.json':{'handle','pages','faults','source_bytes'},
            'merkle-state.schema.json':{'revision','project_root_hash','node','source_bytes_read'},
            'runtime-ui-assertion.schema.json':{'passed','results','screenshot_used'},
            'evidence.schema.json':{'id','kind','revision','active'},
            'semantic-rename.schema.json':{'provider','symbol_id','site_count','paths'},
        }.items(): self.assertTrue(required <= set(self.schema(name)['required']))
    def test_live_virtual_memory_and_merkle_match_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p';root.mkdir();(root/'a.py').write_text('def alpha():\n    return 1\n')
            ws=HabitatWorkspace.create(root,Path(td)/'h'); ctx=ws.orient('alpha implementation',4)
            addr=ws.context_address_space(ctx.handle); merkle=ws.state_merkle()
            self.assertTrue(set(self.schema('context-address-space.schema.json')['required']) <= set(addr))
            self.assertTrue(set(self.schema('merkle-state.schema.json')['required']) <= set(merkle))
            self.assertIn(ctx.decision_packet['retrieval_confidence'],{'low','medium','high'})

if __name__=='__main__': unittest.main()
