from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class ObservatoryFrontendSplitTests(unittest.TestCase):
    def test_frontend_module_owns_server_and_legacy_facade_reexports_contracts(self):
        from habitat.observability import ObservatoryReadModel as CoreReadModel
        from habitat.observatory import ObservatoryReadModel as LegacyReadModel
        from habitat.observatory import ObservatoryServer as LegacyServer
        from habitat.observatory_frontend import ObservatoryServer as FrontendServer

        self.assertIs(LegacyReadModel, CoreReadModel)
        self.assertIs(LegacyServer, FrontendServer)

    def test_clean_core_import_does_not_load_frontend_transport_or_browser_modules(self):
        repo_root = Path(__file__).parents[1]
        code = """
import json
import sys
before = set(sys.modules)
from habitat.observability import ObservatoryReadModel
added = set(sys.modules) - before
print(json.dumps({
    'frontend_loaded': 'habitat.observatory_frontend' in sys.modules,
    'legacy_loaded': 'habitat.observatory' in sys.modules,
    'http_server_added': 'http.server' in added,
    'webbrowser_added': 'webbrowser' in added,
}))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["frontend_loaded"])
        self.assertFalse(report["legacy_loaded"])
        self.assertFalse(report["http_server_added"])
        self.assertFalse(report["webbrowser_added"])


if __name__ == "__main__":
    unittest.main()
