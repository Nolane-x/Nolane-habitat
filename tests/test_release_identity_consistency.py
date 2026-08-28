from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.check_release_identity import check_identity


class ReleaseIdentityConsistencyTests(unittest.TestCase):
    def _root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "habitat").mkdir()
        (root / "plugins/nolane-habitat/.codex-plugin").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "VERSION").write_text("0.1.0-alpha.19\n", encoding="utf-8")
        (root / "pyproject.toml").write_text('version = "0.1.0a19"\n', encoding="utf-8")
        (root / "habitat/__init__.py").write_text('__version__ = "0.1.0-alpha.19"\n', encoding="utf-8")
        (root / "CHANGELOG.md").write_text("## 0.1.0-alpha.19\n", encoding="utf-8")
        (root / "plugins/nolane-habitat/.codex-plugin/plugin.json").write_text(
            json.dumps({"version": "0.1.0-alpha.19"}), encoding="utf-8"
        )
        (root / "README.md").write_text(
            "Nolane Habitat 0.1.0-alpha.19\n[Design](docs/design/FOUNDATION-CONVERGENCE.md)\n",
            encoding="utf-8",
        )
        (root / "docs/IMPLEMENTATION-STATUS.md").write_text(
            "# Implementation Status — 0.1.0-alpha.19\n", encoding="utf-8"
        )
        (root / "docs/LIMITATIONS.md").write_text(
            "# Habitat 0.1.0-alpha.19 Limitations and Claim Boundary\n", encoding="utf-8"
        )
        (root / "docs/design").mkdir()
        (root / "docs/design/FOUNDATION-CONVERGENCE.md").write_text("# Design\n", encoding="utf-8")
        return td, root

    def test_current_documents_must_match_version(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        (root / "docs/LIMITATIONS.md").write_text(
            "# Habitat 0.1.0-alpha.17 Limitations and Claim Boundary\n", encoding="utf-8"
        )
        report = check_identity(root)
        self.assertFalse(report["ok"])
        self.assertTrue(any("docs/LIMITATIONS.md" in error for error in report["errors"]))

    def test_current_local_markdown_link_must_exist(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        (root / "README.md").write_text(
            "Nolane Habitat 0.1.0-alpha.19\n[Design](docs/design/MISSING.md)\n",
            encoding="utf-8",
        )
        report = check_identity(root)
        self.assertFalse(report["ok"])
        self.assertIn("docs/design/MISSING.md", report["broken_links"])


if __name__ == "__main__":
    unittest.main()
