import json
import tempfile
import unittest
from pathlib import Path

from tools.check_release_identity import check_identity, main


class ReleaseIdentityTests(unittest.TestCase):
    def _write_identity_fixture(self, root: Path, version: str = "0.1.0-alpha.19") -> None:
        (root / "habitat").mkdir()
        (root / "docs").mkdir()
        (root / "VERSION").write_text(version + "\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            'version = "0.1.0a19"\n', encoding="utf-8"
        )
        (root / "habitat" / "__init__.py").write_text(
            f'__version__ = "{version}"\n', encoding="utf-8"
        )
        (root / "CHANGELOG.md").write_text(
            f"## {version} — 2026-08-23\n", encoding="utf-8"
        )
        (root / "README.md").write_text(version + "\n", encoding="utf-8")
        (root / "docs" / "CODEX-INTEGRATION.md").write_text(
            f"--ref v{version}\n", encoding="utf-8"
        )

    def test_consistent_release_identity_has_no_errors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_identity_fixture(root)

            report = check_identity(root)

        self.assertTrue(report["ok"])
        self.assertEqual([], report["errors"])

    def test_stale_current_document_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_identity_fixture(root)
            (root / "README.md").write_text("0.1.0-alpha.18\n", encoding="utf-8")

            report = check_identity(root)

        self.assertFalse(report["ok"])
        self.assertIn("README.md", report["errors"][0])

    def test_candidate_documentation_need_not_claim_an_unpublished_tag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_identity_fixture(root)
            (root / "docs" / "CODEX-INTEGRATION.md").write_text(
                "Install the plugin from the checkout being verified.\n",
                encoding="utf-8",
            )

            report = check_identity(root)

        self.assertTrue(report["ok"])

    def test_identity_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_identity_fixture(root)
            output = root / "artifacts" / "identity.json"

            exit_code = main(["--root", str(root), "--out", str(output)])

            self.assertEqual(0, exit_code)
            self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["ok"])
