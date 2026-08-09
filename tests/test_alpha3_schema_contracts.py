import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from habitat.model import to_dict
from habitat.workspace import HabitatWorkspace


class Alpha3SchemaContracts(unittest.TestCase):
    def schema(self,name):
        return json.loads((Path(__file__).parents[1]/'schemas'/name).read_text())

    def norm(self,value):
        return json.loads(json.dumps(to_dict(value)))

    def test_context_materialize_refresh_and_watch_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'p'; p.mkdir(); f=p/'a.py'
            f.write_text('def work(value):\n    return value\n')
            ws=HabitatWorkspace.create(p,root/'h')
            ctx=ws.orient('fix work function',budget=5)
            packet=self.norm(ws.context_materialize(ctx.handle,10_000,5))
            jsonschema.validate(packet,self.schema('context-materialization.schema.json'))
            f.write_text('def work(value):\n    return value or 0\n')
            refreshed=self.norm(ws.context_refresh(ctx.handle))
            jsonschema.validate(refreshed,self.schema('context-refresh.schema.json'))
            ws.watch_start(0.05)
            f.write_text('def work(value):\n    return value or 1\n')
            receipt=self.norm(ws.watch_wait(2.0))
            jsonschema.validate(receipt,self.schema('watch-receipt.schema.json'))
            ws.watch_stop(); ws.close()


if __name__=='__main__':
    unittest.main()
