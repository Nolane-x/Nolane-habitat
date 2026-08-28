from __future__ import annotations

from pathlib import Path

from .base import SemanticParseResult, SemanticProvider
from ..util import detect_language


class TreeSitterProvider(SemanticProvider):
    """Optional broad syntax provider backed by tree-sitter-language-pack.

    Runtime imports are deliberately lazy so a core Habitat installation remains usable without
    the optional Tree-sitter extra. A grammar is advertised only after this process has obtained a
    parser and successfully parsed a tiny smoke sample for that grammar.
    """

    id = "tree-sitter"
    layer = "syntax"
    trust_ceiling = "parser"
    capabilities = frozenset({"parse", "error-tolerant-parse"})
    lifecycle = "workspace-scoped"
    incremental = False
    source_authority = False
    mutation_authority = False
    provenance_required = True

    _CANDIDATES = ("python", "javascript", "typescript", "java")
    _SMOKE_SOURCE = {
        "python": b"def habitat_probe():\n    return 1\n",
        "javascript": b"function habitatProbe() { return 1; }\n",
        "typescript": b"function habitatProbe(): number { return 1; }\n",
        "java": b"class HabitatProbe { int value() { return 1; } }\n",
    }

    def __init__(self) -> None:
        self.languages = frozenset()
        self._parsers: dict[str, object] = {}
        self._probe_reason = "Tree-sitter runtime not probed"

    def available(self) -> tuple[bool, str]:
        try:
            from tree_sitter_language_pack import get_parser, has_language
        except Exception as exc:
            self.languages = frozenset()
            self._parsers.clear()
            self._probe_reason = f"Tree-sitter optional runtime unavailable: {exc}"
            return False, self._probe_reason

        loaded: dict[str, object] = {}
        failures: list[str] = []
        for language in self._CANDIDATES:
            try:
                if not has_language(language):
                    failures.append(f"{language}:not-in-registry")
                    continue
                parser = get_parser(language)
                tree = parser.parse(self._SMOKE_SOURCE[language])
                root = getattr(tree, "root_node", None)
                if root is None or not getattr(root, "type", None):
                    failures.append(f"{language}:unusable-tree")
                    continue
                loaded[language] = parser
            except Exception as exc:
                failures.append(f"{language}:{type(exc).__name__}")

        self._parsers = loaded
        self.languages = frozenset(sorted(loaded))
        if not loaded:
            suffix = ", ".join(failures) if failures else "no candidate grammars"
            self._probe_reason = f"Tree-sitter runtime detected but no grammar admitted by probe ({suffix})"
            return False, self._probe_reason

        detail = ",".join(sorted(loaded))
        self._probe_reason = f"Tree-sitter parsers smoke-tested for: {detail}"
        return True, self._probe_reason

    def parse(self, root: Path, path: Path, text: str, file_id: str) -> SemanticParseResult:
        language = detect_language(path)
        if language not in self._parsers:
            detected, reason = self.available()
            if not detected or language not in self._parsers:
                return SemanticParseResult(self.id, False, reason=reason)
        parser = self._parsers[language]
        try:
            tree = parser.parse(text.encode("utf-8", errors="replace"))
            root_node = getattr(tree, "root_node", None)
            if root_node is None:
                return SemanticParseResult(self.id, False, reason="Tree-sitter returned no root node")
        except Exception as exc:
            return SemanticParseResult(self.id, False, reason=f"Tree-sitter parse failed: {exc}")
        return SemanticParseResult(self.id, True, reason=self._probe_reason)
