import json, tempfile, unittest
from pathlib import Path
import jsonschema

from habitat.toml_compat import tomllib
from habitat.workspace import HabitatWorkspace
import habitat

class Alpha9SchemaContracts(unittest.TestCase):
    def schema(self,name): return json.loads((Path(__file__).parents[1]/'schemas'/name).read_text())
    def test_manifest_policy_agent_and_uncertainty_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'p'; root.mkdir(); (root/'a.py').write_text('def f(): return 1\n')
            ws=HabitatWorkspace.create(root,Path(td)/'h')
            try:
                manifest=json.loads((Path(td)/'h'/'workspace.json').read_text()); self.assertGreaterEqual(manifest['schema'],6)
                jsonschema.validate(manifest,self.schema('workspace-manifest.schema.json'))
                jsonschema.validate(ws.policy_status()['policy'],self.schema('policy.schema.json'))
                agent=ws.agent_open('schema-agent'); jsonschema.validate(agent,self.schema('agent-session.schema.json'))
                h=ws.hypothesis_create('f may fail'); jsonschema.validate(h['evidence_assessment'],self.schema('uncertainty-assessment.schema.json'))
            finally: ws.close()

    def test_release_identity_consistent(self):
        root = Path(__file__).parents[1]
        version=(root / "VERSION").read_text().strip()
        self.assertEqual(habitat.__version__, version)
        metadata = tomllib.loads((root / "pyproject.toml").read_text())
        expected_pep=version.replace("-alpha.","a")
        self.assertEqual(metadata["project"]["version"], expected_pep)
