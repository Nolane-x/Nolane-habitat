from __future__ import annotations

import importlib
import importlib.util
import unittest
from pathlib import Path

from habitat.semantic.base import SemanticParseResult, SemanticProvider


class _DetectedProvider(SemanticProvider):
    id = "detected-runtime-provider"
    languages = frozenset({"typescript"})
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities = frozenset({"parse"})
    lifecycle = "stateless"

    def available(self) -> tuple[bool, str]:
        return True, "runtime adapter probe passed"

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        return SemanticParseResult(self.id, True, reason="selected")


class _MissingProvider(_DetectedProvider):
    id = "missing-runtime-provider"

    def available(self) -> tuple[bool, str]:
        return False, "runtime adapter missing"


class SemanticRuntimeRegistryTests(unittest.TestCase):
    def runtime_api(self):
        spec = importlib.util.find_spec("habitat.semantic.runtime")
        self.assertIsNotNone(spec, "Semantic runtime module must own default provider admission")
        return importlib.import_module("habitat.semantic.runtime")

    def test_detected_packaged_provider_is_admitted_with_runtime_evidence(self):
        api = self.runtime_api()
        registry = api.build_default_semantic_registry(providers=(_DetectedProvider(),))

        selected = registry.providers_for("parse", language="typescript")
        self.assertEqual(("detected-runtime-provider",), tuple(p.id for p in selected))

    def test_missing_packaged_provider_remains_unadmitted(self):
        api = self.runtime_api()
        registry = api.build_default_semantic_registry(providers=(_MissingProvider(),))

        self.assertEqual((), registry.providers_for("parse", language="typescript"))


if __name__ == "__main__":
    unittest.main()
