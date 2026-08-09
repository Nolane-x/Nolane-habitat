import json
import unittest
from pathlib import Path

from habitat.protocol import HabitatProtocol
if __package__:
    from .support import WorkspaceTemporaryDirectory
else:
    from support import WorkspaceTemporaryDirectory


class Alpha4SchemaContracts(unittest.TestCase):
    def _schema(self,name):
        return json.loads((Path(__file__).resolve().parents[1]/'schemas'/name).read_text())

    def test_alpha4_schemas_declare_required_contract_fields(self):
        residence=self._schema('context-residency.schema.json')
        trace=self._schema('agent-trace.schema.json')
        self.assertTrue({'revision','config','count','state_counts','objects'} <= set(residence['required']))
        self.assertTrue({'trace_id','call_count','response_bytes','exact_source_bytes'} <= set(trace['required']))

    def test_live_outputs_satisfy_core_required_fields(self):
        with WorkspaceTemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); (p/'a.py').write_text('def alpha():\n    return 1\n')
            ws=td.create_workspace(p,root/'h')
            ctx=ws.orient('alpha implementation',budget=4); ws.residency_admit(ctx.handle)
            status=ws.residency_status()
            self.assertTrue(set(self._schema('context-residency.schema.json')['required']) <= set(status))
            proto=HabitatProtocol(ws); tid=proto.handle({'id':'s','method':'workspace.trace.start','params':{}})['result']['trace_id']
            proto.handle({'id':'q','method':'workspace.query','params':{'query':'alpha'}})
            trace=proto.handle({'id':'x','method':'workspace.trace.stop','params':{'trace_id':tid}})['result']
            self.assertTrue(set(self._schema('agent-trace.schema.json')['required']) <= set(trace))


if __name__ == '__main__': unittest.main()
