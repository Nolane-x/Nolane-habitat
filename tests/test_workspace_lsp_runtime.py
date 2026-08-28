from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from habitat.semantic.lsp_transport import LspServerSpec
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


def fake_spec(startup_marker: Path, *, event_log: Path | None = None) -> LspServerSpec:
    argv = [
        sys.executable,
        str(Path(__file__).with_name("fake_lsp_server.py")),
        "--mode",
        "normal",
        "--startup-marker",
        str(startup_marker),
    ]
    if event_log is not None:
        argv.extend(("--event-log", str(event_log)))
    return LspServerSpec(
        provider_id="lsp.fake",
        languages=frozenset({"python"}),
        argv=tuple(argv),
        required_capabilities=frozenset({"definition"}),
    )


def events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class WorkspaceLspRuntimeTests(unittest.TestCase):
    def make_workspace(self, temp: WorkspaceTemporaryDirectory) -> tuple[HabitatWorkspace, Path]:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        target = source / "sample.py"
        target.write_text("value = 1\n", encoding="utf-8")
        workspace = HabitatWorkspace.create(source, root / "habitat")
        return workspace, target

    def test_lsp_status_is_lazy_and_does_not_spawn_a_server(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, _ = self.make_workspace(temp)
            marker = Path(temp) / "server-started"
            spec = fake_spec(marker)

            self.assertEqual(ws.lsp_status()["providers"], [])
            self.assertFalse(marker.exists())

            activated = ws.lsp_activate(spec)
            self.assertEqual(activated["provider_id"], "lsp.fake")
            self.assertTrue(marker.exists())

    def test_workspace_query_uses_workspace_revision_and_fabric_uses_runtime_admission_truth(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, target = self.make_workspace(temp)
            marker = Path(temp) / "server-started"
            ws.lsp_activate(fake_spec(marker))

            result = ws.lsp_query(
                "lsp.fake",
                "definition",
                target,
                position={"line": 0, "character": 1},
            )
            self.assertEqual(result["revision"], ws.revision)

            report = ws.semantic_fabric()
            runtime = [provider for provider in report["providers"] if provider["id"] == "lsp.fake"]
            self.assertEqual(len(runtime), 1)
            provider = runtime[0]
            self.assertTrue(provider["detected"])
            self.assertTrue(provider["admitted"])
            self.assertEqual(provider["lifecycle"], "workspace-scoped")
            self.assertEqual(
                set(provider["capabilities"]),
                {"definition", "references", "hover", "document-symbols"},
            )
            self.assertNotIn("rename", provider["capabilities"])
            self.assertNotIn("code-action", provider["capabilities"])

    def test_workspace_close_closes_lsp_documents_before_core_storage(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, target = self.make_workspace(temp)
            marker = Path(temp) / "server-started"
            event_log = Path(temp) / "events.jsonl"
            ws.lsp_activate(fake_spec(marker, event_log=event_log))
            ws.lsp_query(
                "lsp.fake",
                "definition",
                target,
                position={"line": 0, "character": 1},
            )

            ws.close()

            closes = [event for event in events(event_log) if event["method"] == "textDocument/didClose"]
            self.assertEqual(len(closes), 1)
            self.assertEqual(closes[0]["params"]["textDocument"]["uri"], target.resolve().as_uri())


if __name__ == "__main__":
    unittest.main()
