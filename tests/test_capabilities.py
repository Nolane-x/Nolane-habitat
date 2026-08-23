import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from habitat.execution import discover_capabilities
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
