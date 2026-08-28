from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.lsp_transport import LspServerSpec


def fake_spec(mode: str = "normal", *extra: str) -> LspServerSpec:
    return LspServerSpec(
        provider_id="lsp.fake",
        languages=frozenset({"python"}),
        argv=(
            sys.executable,
            str(Path(__file__).with_name("fake_lsp_server.py")),
            "--mode",
            mode,
            *extra,
        ),
        required_capabilities=frozenset({"definition"}),
    )


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wait_for_path(path: Path, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not path.exists():
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out waiting for marker: {path}")
        time.sleep(0.01)


class LspRuntimeManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "sample.py"
        self.source.write_text("value = 1\n", encoding="utf-8")
        self.revision = ["r1"]
        self.registry = SemanticAdmissionRegistry()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def manager(self):
        from habitat.semantic.lsp_runtime import LspRuntimeManager

        return LspRuntimeManager(
            self.root,
            semantic_registry=self.registry,
            revision_getter=lambda: self.revision[0],
        )

    def test_manager_does_not_activate_or_admit_before_explicit_activate(self):
        manager = self.manager()
        try:
            self.assertEqual(manager.status()["providers"], [])
            self.assertFalse(self.registry.is_admitted("lsp.fake"))
        finally:
            manager.close()

    def test_activate_handshakes_then_admits_read_only_provider(self):
        manager = self.manager()
        try:
            result = manager.activate(fake_spec())
            self.assertEqual(result["provider_id"], "lsp.fake")
            self.assertEqual(result["state"], "READY")
            self.assertTrue(self.registry.is_admitted("lsp.fake"))
            selected = self.registry.providers_for("definition", language="python")
            self.assertEqual([provider.descriptor().id for provider in selected], ["lsp.fake"])
            descriptor = selected[0].descriptor()
            self.assertFalse(descriptor.source_authority)
            self.assertFalse(descriptor.mutation_authority)
        finally:
            manager.close()

    def test_failed_initialize_never_becomes_admitted(self):
        manager = self.manager()
        try:
            with self.assertRaises(Exception):
                manager.activate(fake_spec("initialize-error"))
            self.assertFalse(self.registry.is_admitted("lsp.fake"))
            self.assertEqual(manager.status()["providers"], [])
        finally:
            manager.close()

    def test_query_emits_did_open_then_full_text_did_change_with_monotonic_versions(self):
        event_log = self.root / "events.jsonl"
        manager = self.manager()
        try:
            manager.activate(fake_spec("normal", "--event-log", str(event_log)))
            first = manager.query(
                "lsp.fake",
                "definition",
                self.source,
                position={"line": 0, "character": 1},
            )
            self.assertEqual(first["document_version"], 1)

            self.source.write_text("value = 2\n", encoding="utf-8")
            self.revision[0] = "r2"
            second = manager.query(
                "lsp.fake",
                "definition",
                self.source,
                position={"line": 0, "character": 1},
            )
            self.assertEqual(second["document_version"], 2)

            events = read_events(event_log)
            opens = [event for event in events if event["method"] == "textDocument/didOpen"]
            changes = [event for event in events if event["method"] == "textDocument/didChange"]
            self.assertEqual(len(opens), 1)
            self.assertEqual(opens[0]["params"]["textDocument"]["version"], 1)
            self.assertEqual(opens[0]["params"]["textDocument"]["languageId"], "python")
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["params"]["textDocument"]["version"], 2)
            self.assertEqual(changes[0]["params"]["contentChanges"], [{"text": "value = 2\n"}])
        finally:
            manager.close()

    def test_query_rejects_result_if_source_or_revision_changes_while_request_is_in_flight(self):
        delay_marker = self.root / "request-started"
        release_marker = self.root / "release-request"
        manager = self.manager()
        try:
            manager.activate(
                fake_spec(
                    "controlled-delay",
                    "--delay-marker",
                    str(delay_marker),
                    "--release-marker",
                    str(release_marker),
                )
            )
            captured: list[BaseException] = []

            def run_query() -> None:
                try:
                    manager.query(
                        "lsp.fake",
                        "definition",
                        self.source,
                        position={"line": 0, "character": 1},
                    )
                except BaseException as exc:  # captured for assertion in the test thread
                    captured.append(exc)

            thread = threading.Thread(target=run_query)
            thread.start()
            wait_for_path(delay_marker)
            self.source.write_text("value = 999\n", encoding="utf-8")
            self.revision[0] = "r2"
            release_marker.write_text("go", encoding="utf-8")
            thread.join(timeout=3.0)
            self.assertFalse(thread.is_alive())

            from habitat.semantic.lsp_runtime import LspStaleResultError

            self.assertEqual(len(captured), 1)
            self.assertIsInstance(captured[0], LspStaleResultError)
        finally:
            manager.close()

    def test_close_provider_sends_did_close_and_revokes_admission(self):
        event_log = self.root / "events.jsonl"
        manager = self.manager()
        try:
            manager.activate(fake_spec("normal", "--event-log", str(event_log)))
            manager.query(
                "lsp.fake",
                "definition",
                self.source,
                position={"line": 0, "character": 1},
            )
            manager.close_provider("lsp.fake")
            self.assertFalse(self.registry.is_admitted("lsp.fake"))
            self.assertEqual(manager.status()["providers"], [])
            closes = [event for event in read_events(event_log) if event["method"] == "textDocument/didClose"]
            self.assertEqual(len(closes), 1)
            self.assertEqual(closes[0]["params"]["textDocument"]["uri"], self.source.resolve().as_uri())
        finally:
            manager.close()

    def test_closed_provider_can_be_explicitly_reactivated_with_same_identity(self):
        manager = self.manager()
        try:
            first = manager.activate(fake_spec())
            first_fingerprint = first["provider_fingerprint"]
            manager.close_provider("lsp.fake")
            self.assertFalse(self.registry.is_admitted("lsp.fake"))

            second = manager.activate(fake_spec())
            self.assertEqual(second["provider_id"], "lsp.fake")
            self.assertEqual(second["state"], "READY")
            self.assertTrue(second["admitted"])
            self.assertTrue(self.registry.is_admitted("lsp.fake"))
            self.assertEqual(second["provider_fingerprint"], first_fingerprint)
            selected = self.registry.providers_for("definition", language="python")
            self.assertEqual([provider.descriptor().id for provider in selected], ["lsp.fake"])
        finally:
            manager.close()


if __name__ == "__main__":
    unittest.main()
