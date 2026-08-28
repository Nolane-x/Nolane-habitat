from __future__ import annotations

from pathlib import Path

from .base import SemanticParseResult, SemanticProvider
from ..model import DiagnosticRecord, SymbolRecord
from ..util import detect_language, stable_id


_DECLARATIONS: dict[str, dict[str, str]] = {
    "python": {
        "class_definition": "class",
        "function_definition": "function",
    },
    "javascript": {
        "class_declaration": "class",
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
    },
    "typescript": {
        "class_declaration": "class",
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "method_signature": "method",
        "abstract_method_signature": "method",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
    },
}

_SCOPE_KINDS = {"class", "interface", "enum", "function", "method", "constructor"}


def _row(point: object) -> int:
    value = getattr(point, "row", None)
    if isinstance(value, int):
        return value
    try:
        return int(point[0])  # type: ignore[index]
    except Exception:
        return 0


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


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
        source = text.encode("utf-8", errors="replace")
        try:
            tree = parser.parse(source)
            root_node = getattr(tree, "root_node", None)
            if root_node is None:
                return SemanticParseResult(self.id, False, reason="Tree-sitter returned no root node")
        except Exception as exc:
            return SemanticParseResult(self.id, False, reason=f"Tree-sitter parse failed: {exc}")

        rel_path = _relative_path(root, path)
        declaration_map = _DECLARATIONS.get(language, {})
        symbols: list[SymbolRecord] = []

        def walk(node: object, scope: tuple[str, ...]) -> None:
            node_type = str(getattr(node, "type", ""))
            symbol_scope = scope
            kind = declaration_map.get(node_type)
            if kind is not None:
                try:
                    name_node = node.child_by_field_name("name")  # type: ignore[attr-defined]
                except Exception:
                    name_node = None
                if name_node is not None:
                    try:
                        raw_name = source[int(name_node.start_byte):int(name_node.end_byte)]
                        name = raw_name.decode("utf-8", errors="replace").strip()
                    except Exception:
                        name = ""
                    if name:
                        qualified_name = ".".join((*scope, name)) if scope else name
                        start_line = _row(getattr(node, "start_point", (0, 0))) + 1
                        end_line = _row(getattr(node, "end_point", (start_line - 1, 0))) + 1
                        try:
                            node_bytes = source[int(node.start_byte):int(node.end_byte)]  # type: ignore[attr-defined]
                            signature = node_bytes.splitlines()[0].decode("utf-8", errors="replace").strip()[:240]
                        except Exception:
                            signature = None
                        symbols.append(SymbolRecord(
                            id=stable_id("symbol", file_id, self.id, node_type, qualified_name, str(start_line)),
                            file_id=file_id,
                            path=rel_path,
                            name=name,
                            qualified_name=qualified_name,
                            kind=kind,
                            language=language,
                            start_line=start_line,
                            end_line=max(start_line, end_line),
                            signature=signature or None,
                            trust="parser",
                        ))
                        if kind in _SCOPE_KINDS:
                            symbol_scope = (*scope, name)
            try:
                children = tuple(node.children)  # type: ignore[attr-defined]
            except Exception:
                children = ()
            for child in children:
                walk(child, symbol_scope)

        walk(root_node, ())

        diagnostics: list[DiagnosticRecord] = []
        if bool(getattr(root_node, "has_error", False)):
            error_node = None
            stack = [root_node]
            while stack:
                candidate = stack.pop()
                if str(getattr(candidate, "type", "")) == "ERROR" or bool(getattr(candidate, "is_missing", False)):
                    error_node = candidate
                    break
                try:
                    stack.extend(reversed(tuple(candidate.children)))  # type: ignore[attr-defined]
                except Exception:
                    pass
            diagnostic_node = error_node or root_node
            line = _row(getattr(diagnostic_node, "start_point", (0, 0))) + 1
            diagnostics.append(DiagnosticRecord(
                id=stable_id("diag", file_id, self.id, "syntax-error", str(line)),
                file_id=file_id,
                path=rel_path,
                severity="error",
                message="Tree-sitter recovered a syntax tree containing parse errors",
                line=line,
                column=None,
                source=self.id,
                trust="parser",
            ))

        return SemanticParseResult(
            self.id,
            True,
            symbols=tuple(symbols),
            diagnostics=tuple(diagnostics),
            reason=self._probe_reason,
        )
