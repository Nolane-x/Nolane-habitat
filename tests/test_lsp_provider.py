from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


FAKE_SERVER = Path(__file__).with_name("fake_lsp_server.py")


def make_session(root: Path, mode: str = "normal"):
    from habitat.semantic.lsp_transport import LspProcessSession, LspServerSpec

    spec = LspServerSpec(
        provider_id="lsp.fake",
        languages=frozenset({"python"}),
        argv=(sys.executable, str(FAKE_SERVER), "--mode", mode),
        required_capabilities=frozenset({"definition"}),
    )
    session = LspProcessSession(spec, root)
    session.start()
    return session


class LspSemanticProviderTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="habitat-lsp-provider-")
        self.root = Path(self._td.name)
        self.session = make_session(self.root)

    def tearDown(self):
        self.session.close()
        self._td.cleanup()

    def test_descriptor_is_read_only_semantic_workspace_provider(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        provider = LspSemanticProvider(self.session)
        descriptor = provider.descriptor()
        self.assertEqual(descriptor.id, "lsp.fake")
        self.assertEqual(descriptor.languages, frozenset({"python"}))
        self.assertEqual(descriptor.layer, "language-semantic-service")
        self.assertEqual(descriptor.trust_ceiling, "semantic")
        self.assertEqual(descriptor.lifecycle, "workspace-scoped")
        self.assertTrue(descriptor.incremental)
        self.assertFalse(descriptor.source_authority)
        self.assertFalse(descriptor.mutation_authority)
        self.assertEqual(
            descriptor.capabilities,
            frozenset({"definition", "references", "hover", "document-symbols", "diagnostics"}),
        )
        forbidden = {"rename", "code-action", "format", "workspace-edit", "execute-command"}
        self.assertFalse(descriptor.capabilities & forbidden)

    def test_provider_fingerprint_is_deterministic_and_runtime_bound(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        provider = LspSemanticProvider(self.session)
        first = provider.provider_fingerprint()
        second = provider.provider_fingerprint()
        self.assertIsInstance(first, str)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        int(first, 16)

    def test_definition_returns_habitat_owned_provenance_envelope(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        provider = LspSemanticProvider(self.session)
        uri = (self.root / "sample.py").resolve().as_uri()
        value = provider.definition(
            uri,
            {"line": 0, "character": 1},
            revision="rev-7",
            source_digest="d" * 64,
            document_version=3,
        )
        self.assertEqual(value["provider_id"], "lsp.fake")
        self.assertEqual(value["method"], "textDocument/definition")
        self.assertEqual(value["trust"], "semantic")
        self.assertEqual(value["revision"], "rev-7")
        self.assertEqual(value["source_digest"], "d" * 64)
        self.assertEqual(value["document_version"], 3)
        self.assertEqual(value["provider_fingerprint"], provider.provider_fingerprint())
        self.assertEqual(value["result"]["uri"], uri)
        observed = datetime.fromisoformat(value["observed_at"])
        self.assertIsNotNone(observed.tzinfo)
        self.assertIsNotNone(observed.utcoffset())

    def test_definition_rejects_invalid_result_shape(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        invalid = make_session(self.root, "invalid-result-shape")
        try:
            provider = LspSemanticProvider(invalid)
            with self.assertRaises(ValueError):
                provider.definition(
                    (self.root / "sample.py").resolve().as_uri(),
                    {"line": 0, "character": 0},
                    revision="rev-1",
                    source_digest="a" * 64,
                    document_version=1,
                )
        finally:
            invalid.close()

    def test_references_reject_invalid_result_shape(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        invalid = make_session(self.root, "invalid-result-shape")
        try:
            provider = LspSemanticProvider(invalid)
            with self.assertRaises(ValueError):
                provider.references(
                    (self.root / "sample.py").resolve().as_uri(),
                    {"line": 0, "character": 0},
                    revision="rev-1",
                    source_digest="b" * 64,
                    document_version=1,
                )
        finally:
            invalid.close()

    def test_hover_rejects_invalid_result_shape(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        invalid = make_session(self.root, "invalid-result-shape")
        try:
            provider = LspSemanticProvider(invalid)
            with self.assertRaises(ValueError):
                provider.hover(
                    (self.root / "sample.py").resolve().as_uri(),
                    {"line": 0, "character": 0},
                    revision="rev-1",
                    source_digest="c" * 64,
                    document_version=1,
                )
        finally:
            invalid.close()

    def test_document_symbols_reject_invalid_result_shape(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        invalid = make_session(self.root, "invalid-result-shape")
        try:
            provider = LspSemanticProvider(invalid)
            with self.assertRaises(ValueError):
                provider.document_symbols(
                    (self.root / "sample.py").resolve().as_uri(),
                    revision="rev-1",
                    source_digest="d" * 64,
                    document_version=1,
                )
        finally:
            invalid.close()

    def test_query_methods_are_fixed_allowlist_not_arbitrary_passthrough(self):
        from habitat.semantic.lsp_provider import LspSemanticProvider

        provider = LspSemanticProvider(self.session)
        self.assertFalse(hasattr(provider, "rename"))
        self.assertFalse(hasattr(provider, "code_action"))
        self.assertFalse(hasattr(provider, "execute_command"))
        self.assertFalse(hasattr(provider, "request"))


if __name__ == "__main__":
    unittest.main()
