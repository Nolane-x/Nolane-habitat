import tempfile, unittest
from pathlib import Path
from habitat.workspace import HabitatWorkspace
from habitat.protocol import HabitatProtocol, PROTOCOL_VERSION

class Alpha1ProtocolTests(unittest.TestCase):
    def test_capability_negotiation_and_source_read(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); p=r/'p'; p.mkdir(); (p/'a.py').write_text('def f():\n    return 1\n')
            proto=HabitatProtocol(HabitatWorkspace.create(p,r/'h'))
            caps=proto.handle({'id':1,'method':'protocol.capabilities','params':{}})
            self.assertTrue(caps['ok']); self.assertEqual(caps['protocol'],PROTOCOL_VERSION); self.assertFalse(caps['result']['generic_shell'])
            self.assertIn('ui.runtime.open',caps['result']['methods'])
            source=proto.handle({'id':2,'method':'workspace.source.read','params':{'path':'a.py','max_lines':1}})
            self.assertTrue(source['ok']); self.assertIn('def f',source['result']['source'])

if __name__=='__main__': unittest.main()
