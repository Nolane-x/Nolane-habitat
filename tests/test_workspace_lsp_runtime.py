from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from habitat.semantic.lsp_transport import LspServerSpec
from habitat.workspace import HabitatWorkspace
from tests.support import WorkspaceTemporaryDirectory


def fake_spec(
    startup_marker: Path,
    *,
    event_log: Path | None = None,
    publish_diagnostics: bool = False,
    stale_diagnostics_on_change: bool = False,
) -> LspServerSpec:
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
    if publish_diagnostics:
        argv.append("--publish-diagnostics")
    if stale_diagnostics_on_change:
        argv.append("--stale-diagnostics-on-change")
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
                {"definition", "references", "hover", "document-symbols", "diagnostics"},
            )
            self.assertNotIn("rename", provider["capabilities"])
            self.assertNotIn("code-action", provider["capabilities"])

    def test_passive_diagnostics_are_version_bound_and_stale_notifications_are_dropped(self):
        with WorkspaceTemporaryDirectory() as temp:
            ws, target = self.make_workspace(temp)
            marker = Path(temp) / "server-started"
            ws.lsp_activate(
                fake_spec(
                    marker,
                    publish_diagnostics=True,
                    stale_diagnostics_on_change=True,
                )
            )

            ws.lsp_query(
                "lsp.fake",
                "definition",
                target,
                position={"line": 0, "character": 1},
            )
            first = ws.lsp_diagnostics("lsp.fake", target)
            self.assertIsNotNone(first)
            self.assertEqual(first["method"], "textDocument/publishDiagnostics")
            self.assertEqual(first["trust"], "semantic")
            self.assertEqual(first["revision"], ws.revision)
            self.assertEqual(first["document_version"], 1)
            self.assertEqual(first["result"][0]["code"], "fake-diagnostic")

            target.write_text("value = 2\n", encoding="utf-8")
            ws.refresh("diagnostic-source-change")
            ws.lsp_query(
                "lsp.fake",
                "definition",
                target,
                position={"line": 0, "character": 1},
            )

            # The fake server deliberately publishes the previous LSP document version after the
            # change. Habitat must invalidate the old current diagnostic and refuse to promote the
            # stale notification as current semantic truth.
            self.assertIsNone(ws.lsp_diagnostics("lsp.fake", target))

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
