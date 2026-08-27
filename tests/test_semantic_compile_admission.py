from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from habitat.compiler import compile_file
from habitat.semantic.admission import SemanticAdmissionRegistry
from habitat.semantic.base import SemanticParseResult, SemanticProvider


class _FakeTypeScriptProvider(SemanticProvider):
    id = "fake-typescript-provider"
    languages = frozenset({"javascript", "typescript"})
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities = frozenset({"parse"})
    lifecycle = "stateless"

    def __init__(self) -> None:
        self.parse_calls = 0

    def available(self) -> tuple[bool, str]:
        return True, "test probe succeeded"

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        self.parse_calls += 1
        return SemanticParseResult(self.id, True, reason="test provider selected")


class SemanticCompileAdmissionTests(unittest.TestCase):
    def _typescript_file(self, root: Path) -> Path:
        path = root / "app.ts"
        path.write_text("export function admitted() { return 1; }\n", encoding="utf-8")
        return path

    def test_unadmitted_provider_cannot_enter_compile_data_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = self._typescript_file(root)
            provider = _FakeTypeScriptProvider()
            registry = SemanticAdmissionRegistry()
            registry.register(provider)
            registry.probe(provider.id)

            compiled = compile_file(root, path, semantic_registry=registry)

            self.assertEqual("regex-fallback", compiled.provider)
            self.assertEqual(0, provider.parse_calls)

    def test_admitted_provider_is_selected_by_compile_data_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = self._typescript_file(root)
            provider = _FakeTypeScriptProvider()
            registry = SemanticAdmissionRegistry()
            registry.register(provider)
            registry.probe(provider.id)
            registry.admit(provider.id, evidence=("probe:test", "contract:test-semantic-compile-admission"))

            compiled = compile_file(root, path, semantic_registry=registry)

            self.assertEqual(provider.id, compiled.provider)
            self.assertEqual(1, provider.parse_calls)


if __name__ == "__main__":
    unittest.main()
