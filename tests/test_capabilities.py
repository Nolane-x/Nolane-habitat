import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from habitat.execution import _python_has_module, discover_capabilities
from habitat.cli import main
from habitat.security.capabilities import (
    CapabilityReport,
    ExecutionCapability,
    build_capability_report,
    require_capability,
)
from habitat.workspace import HabitatWorkspace


class CapabilityTests(unittest.TestCase):
    def test_capabilities_expose_availability_instead_of_pretending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "tests").mkdir()
            caps = discover_capabilities(root)
            self.assertTrue(caps)
            for cap in caps:
                self.assertIn("available", cap)
                self.assertIn("availability_reason", cap)
            unittest_cap = next(c for c in caps if c["id"] == "python.unittest")
            self.assertTrue(unittest_cap["available"])

    def test_malformed_package_manifest_is_reported_as_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text("{not json", encoding="utf-8")

            manifests = [
                capability
                for capability in discover_capabilities(root)
                if capability["id"] == "npm.manifest"
            ]

            self.assertEqual(1, len(manifests))
            self.assertFalse(manifests[0]["available"])
            self.assertIn("invalid", manifests[0]["availability_reason"])

    def test_module_presence_probe_does_not_import_slow_module(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "slow_capability_probe.py").write_text(
                "import time\ntime.sleep(6)\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"PYTHONPATH": str(root)}):
                available = _python_has_module(sys.executable, "slow_capability_probe")

        self.assertTrue(available)

    def test_enter_reports_trusted_local_execution_without_sandbox_claims(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "source"
            root.mkdir()
            workspace = HabitatWorkspace.create(root, Path(td) / "workspace")
            self.addCleanup(workspace.close)

            report = workspace.enter()["capability_report"]

            self.assertEqual("trusted-local-process", report["execution"]["profile"])
            self.assertFalse(report["execution"]["sandboxed"])
            self.assertFalse(report["execution"]["network_restricted"])
            self.assertFalse(report["execution"]["filesystem_restricted"])
            self.assertEqual(workspace.revision, report["generated_at_revision"])

    def test_unverified_execution_capability_fails_closed(self):
        report = CapabilityReport(
            source_authority={},
            execution=ExecutionCapability(
                profile="trusted-local-process",
                sandboxed=False,
                network_restricted=False,
                filesystem_restricted=False,
                process_isolated=False,
                verified_by=(),
            ),
            mutation={},
            observatory={},
            generated_at_revision="revision",
        )

        with self.assertRaisesRegex(PermissionError, "not verified"):
            require_capability(report, "sandboxed")

    def test_verified_sandbox_is_reported_only_with_all_containment_evidence(self):
        report = build_capability_report(
            source_authority={"authority_id": "source:1", "capabilities": []},
            execution_provider={
                "provider_id": "executor:1",
                "capabilities": [
                    "full-sandbox",
                    "filesystem-confinement",
                    "network-confinement",
                    "pid-namespace",
                ],
            },
            generated_at_revision="revision",
        )

        self.assertTrue(report.execution.sandboxed)
        self.assertEqual(("executor:1",), report.execution.verified_by)
        require_capability(report, "sandboxed")

    def test_capabilities_cli_emits_the_truthful_workspace_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "source"
            root.mkdir()
            workspace_root = Path(td) / "workspace"
            workspace = HabitatWorkspace.create(root, workspace_root)
            self.addCleanup(workspace.close)
            output = io.StringIO()
            try:
                with redirect_stdout(output):
                    exit_code = main(["capabilities", str(workspace_root)])
            except SystemExit as exc:
                exit_code = exc.code

            self.assertEqual(0, exit_code)
            self.assertEqual(
                "trusted-local-process",
                json.loads(output.getvalue())["execution"]["profile"],
            )

if __name__ == "__main__": unittest.main()
