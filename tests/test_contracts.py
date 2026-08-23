import json
import tempfile
import unittest
from pathlib import Path

from tools.verify_contracts import collect_contract, main, verify_contract


class ContractCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture_path = Path(__file__).parent / "fixtures" / "contracts" / "agent-v1alpha2.json"
        self.fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def test_current_public_surface_matches_the_versioned_fixture(self):
        verdict = verify_contract(self.fixture, collect_contract())

        self.assertTrue(verdict["compatible"], verdict)
        self.assertEqual([], verdict["breaking"])

    def test_catalog_removal_is_reported_as_a_breaking_change(self):
        actual = collect_contract()
        actual["mcp_tools"] = actual["mcp_tools"][1:]

        verdict = verify_contract(self.fixture, actual)

        self.assertFalse(verdict["compatible"])
        self.assertIn("mcp_tools", verdict["breaking"])

    def test_cli_writes_a_commit_bound_compatibility_report(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "contract.json"

            exit_code = main(
                [
                    "--source-commit",
                    "a" * 40,
                    "--fixture",
                    str(self.fixture_path),
                    "--out",
                    str(output),
                ]
            )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, exit_code)
            self.assertTrue(report["compatible"])
            self.assertEqual("a" * 40, report["source_commit"])
            self.assertEqual("passed", report["status"])
            self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")
