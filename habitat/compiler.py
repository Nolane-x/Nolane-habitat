from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from .model import DiagnosticRecord, FileRecord, RelationRecord, SymbolRecord
from .semantic.typescript import TypeScriptCompilerProvider, provider_version as typescript_provider_version
from .util import detect_language, sha256_file, stable_id

MAX_INDEX_BYTES = 200_000
MAX_PARSE_BYTES = 5_000_000
COMPILE_CACHE_VERSION = 3




def compile_cache_fingerprint(language: str) -> dict:
    """Environment-sensitive identity for cached per-file semantic artifacts.

    A source digest alone is insufficient: a compiler/parser upgrade can change symbols,
    diagnostics, or unresolved relations without changing source bytes.
    """
    fp = {"compiler_cache_version": COMPILE_CACHE_VERSION}
    if language in {"javascript", "typescript"}:
        version = typescript_provider_version()
        fp["typescript_available"] = version is not None
        fp["typescript_version"] = version
    return fp


@dataclass
class CompiledFile:
    file: FileRecord
    symbols: list[SymbolRecord]
    unresolved_relations: list[tuple[str, str, str, str, str | None]]
    diagnostics: list[DiagnosticRecord] = field(default_factory=list)
    provider: str = "builtin"
    metadata: dict = field(default_factory=dict)


def python_module_name(relpath: str) -> str:
    p = Path(relpath)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class PythonExtractor(ast.NodeVisitor):
    def __init__(self, relpath: str, file_id: str, text: str):
        self.relpath = relpath
        self.file_id = file_id
        self.text = text
        self.module = python_module_name(relpath)
        self.symbols: list[SymbolRecord] = []
        self.unresolved: list[tuple[str, str, str, str, str | None]] = []
        self.stack: list[str] = []
        self.symbol_stack: list[str] = []
        self.import_bindings: dict[str, str] = {}

    @staticmethod
    def _dotted(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            left = PythonExtractor._dotted(node.value)
            return f"{left}.{node.attr}" if left else node.attr
        return None

    def _resolve_bound_name(self, dotted: str) -> str | None:
        parts = dotted.split(".")
        if not parts:
            return None
        bound = self.import_bindings.get(parts[0])
        if bound:
            return bound + (("." + ".".join(parts[1:])) if len(parts) > 1 else "")
        if parts[0] == "self" and self.stack:
            # self.method inside a class/method. Use nearest class component when available.
            cls = self.stack[0] if self.stack else None
            if cls and len(parts) > 1:
                return f"{self.module}::{cls}.{'.'.join(parts[1:])}"
        return None

    def _add(self, node: ast.AST, name: str, kind: str, signature: str | None = None) -> str:
        qname = ".".join([*self.stack, name]) if self.stack else name
        sid = stable_id("sym", self.relpath, kind, qname)
        end = getattr(node, "end_lineno", getattr(node, "lineno", 1))
        summary = ast.get_docstring(node, clean=True) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
        self.symbols.append(SymbolRecord(
            id=sid, file_id=self.file_id, path=self.relpath, name=name, qualified_name=qname,
            kind=kind, language="python", start_line=getattr(node, "lineno", 1), end_line=end,
            signature=signature, summary=summary, trust="exact",
        ))
        return sid

    def visit_ClassDef(self, node: ast.ClassDef):
        sid = self._add(node, node.name, "class", f"class {node.name}")
        parent = self.symbol_stack[-1] if self.symbol_stack else None
        if parent:
            self.unresolved.append((parent, sid, "contains", "exact", None))
        self.stack.append(node.name); self.symbol_stack.append(sid)
        self.generic_visit(node)
        self.symbol_stack.pop(); self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        sig = self._signature(node)
        sid = self._add(node, node.name, "function" if not self.stack else "method", sig)
        parent = self.symbol_stack[-1] if self.symbol_stack else None
        if parent:
            self.unresolved.append((parent, sid, "contains", "exact", None))
        self.stack.append(node.name); self.symbol_stack.append(sid)
        self.generic_visit(node)
        self.symbol_stack.pop(); self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call):
        if self.symbol_stack:
            dotted = self._dotted(node.func)
            if dotted:
                qualified = self._resolve_bound_name(dotted)
                if qualified:
                    if "::" not in qualified:
                        # imported module/symbol represented as a dotted Python module path
                        pieces = qualified.split(".")
                        # resolution later finds the longest module prefix.
                        qualified = qualified
                    self.unresolved.append((self.symbol_stack[-1], qualified, "calls_qualified", "semantic", f"line {getattr(node,'lineno',0)}"))
                else:
                    # Unqualified local names are resolved only if unique in an appropriate scope.
                    self.unresolved.append((self.symbol_stack[-1], dotted.split(".")[-1], "calls_name", "parser", f"line {getattr(node,'lineno',0)}"))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.import_bindings[local] = alias.name
            self.unresolved.append((self.file_id, alias.name, "imports_module", "exact", f"line {node.lineno}"))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        trust = "semantic"
        if node.level:
            # Resolve ordinary package-relative imports from the current module identity without importing/executing code.
            package = self.module.split(".")[:-1]
            ascend = max(0, node.level - 1)
            if ascend <= len(package):
                base = package[: len(package) - ascend] if ascend else package
                mod = ".".join([*base, *([node.module] if node.module else [])])
            else:
                mod = "." * node.level + mod
                trust = "parser"
        if mod:
            self.unresolved.append((self.file_id, mod, "imports_module", trust, f"line {node.lineno}"))
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            # `from . import auth` binds a module; `from .auth import validate` binds a symbol.
            target = f"{mod}.{alias.name}" if mod else alias.name
            self.import_bindings[local] = target
            self.unresolved.append((self.file_id, target, "imports_symbol", trust, f"line {node.lineno}"))

    @staticmethod
    def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        parts = []
        for arg in [*node.args.posonlyargs, *node.args.args]:
            parts.append(arg.arg)
        if node.args.vararg:
            parts.append("*" + node.args.vararg.arg)
        for arg in node.args.kwonlyargs:
            parts.append(arg.arg)
        if node.args.kwarg:
            parts.append("**" + node.args.kwarg.arg)
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(parts)})"


JS_FN = re.compile(r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)")
JS_CLASS = re.compile(r"(?m)^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")
JS_ARROW = re.compile(r"(?m)^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
JAVA_CLASS = re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+)*class\s+([A-Za-z_$][\w$]*)")
JAVA_METHOD = re.compile(r"(?m)^\s*(?:public|private|protected)\s+(?:static\s+)?(?:[\w<>\[\], ?]+)\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?:throws[^\{]+)?\{")
HTML_ID = re.compile(r"\bid=[\"']([^\"']+)[\"']", re.I)
CSS_RULE = re.compile(r"(?s)([^{}]+)\{[^{}]*\}")


class _HTMLSemanticParser(HTMLParser):
    def __init__(self, rel: str, file_id: str):
        super().__init__(convert_charrefs=True)
        self.rel = rel
        self.file_id = file_id
        self.symbols: list[SymbolRecord] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs):
        values = {k.lower(): v for k, v in attrs if k and v is not None}
        key = None
        selector = None
        if values.get("id"):
            key = values["id"]; selector = f"#{key}"
        elif values.get("data-testid"):
            key = values["data-testid"]; selector = f'[data-testid="{key}"]'
        elif values.get("name") and tag.lower() in {"input","textarea","select","button","form"}:
            key = f"name:{values['name']}"; selector = f'{tag}[name="{values["name"]}"]'
        if not key or key in self._seen:
            return
        self._seen.add(key)
        line, _ = self.getpos()
        sid = stable_id("ui", self.rel, "element", key)
        self.symbols.append(SymbolRecord(
            sid, self.file_id, self.rel, key, key, "ui-element", "html", line, line,
            f"{tag.lower()} {selector}", None, "parser"
        ))



def _source_io_metadata(path: Path, stride: int = 128) -> dict:
    """Build a sparse line→byte index once during compilation."""
    import codecs
    checkpoints = [[1, 0]]
    line = 1
    absolute = 0
    crlf = lf = 0
    utf8_valid = True
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    prev_last = b""
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            try:
                decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                utf8_valid = False
                decoder = codecs.getincrementaldecoder("utf-8")("replace")
            # Count only bytes in this chunk. ``prev_last`` is consulted solely
            # for a CRLF pair split across chunk boundaries; prepending it would
            # double-count a trailing newline from the previous chunk.
            i = 0
            while True:
                pos = chunk.find(b"\n", i)
                if pos < 0:
                    break
                abs_pos = absolute + pos
                previous_is_cr = (pos > 0 and chunk[pos - 1:pos] == b"\r") or (pos == 0 and prev_last == b"\r")
                if previous_is_cr:
                    crlf += 1
                else:
                    lf += 1
                line += 1
                if (line - 1) % stride == 0:
                    checkpoints.append([line, abs_pos + 1])
                i = pos + 1
            prev_last = chunk[-1:]
            absolute += len(chunk)
    if utf8_valid:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            utf8_valid = False
    newline = "mixed" if crlf and lf else "crlf" if crlf else "lf" if lf else "none"
    return {"line_stride": stride, "checkpoints": checkpoints, "line_count": line, "newline": newline, "utf8_valid": utf8_valid}


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _fallback_js_ts(rel: str, file_id: str, language: str, text: str):
    symbols: list[SymbolRecord] = []
    unresolved: list[tuple[str, str, str, str, str | None]] = []
    for regex, kind in [(JS_FN, "function"), (JS_CLASS, "class"), (JS_ARROW, "function")]:
        for m in regex.finditer(text):
            name = m.group(1); line = _line_of(text, m.start())
            symbols.append(SymbolRecord(stable_id("sym", rel, kind, name), file_id, rel, name, name, kind,
                                        language, line, line, m.group(0).strip(), None, "heuristic"))
    for m in re.finditer(r"(?:import .*? from\s+|require\()?[\"']([^\"']+)[\"']", text):
        unresolved.append((file_id, m.group(1), "imports_module", "heuristic", f"line {_line_of(text,m.start())}"))
    return symbols, unresolved


def compile_file(root: Path, path: Path) -> CompiledFile:
    rel = path.relative_to(root).as_posix()
    language = detect_language(path)
    st = path.stat()
    digest = sha256_file(path)
    file_id = stable_id("file", rel)
    indexed_text = ""
    parse_text = ""
    index_truncated = False
    parse_complete = True
    indexed_bytes = 0
    if language != "binary":
        with path.open("rb") as fh:
            index_raw = fh.read(MAX_INDEX_BYTES)
        indexed_bytes = len(index_raw)
        indexed_text = index_raw.decode("utf-8", errors="replace")
        index_truncated = st.st_size > indexed_bytes
        if language in {"python", "javascript", "typescript", "java", "html", "css", "json"}:
            if st.st_size <= MAX_PARSE_BYTES:
                parse_text = path.read_bytes().decode("utf-8", errors="replace")
            else:
                parse_text = indexed_text
                parse_complete = False
        else:
            parse_text = indexed_text
    text = parse_text
    file_rec = FileRecord(file_id, rel, language, st.st_size, digest, st.st_mtime_ns, indexed_text, indexed_bytes, index_truncated, parse_complete)
    symbols: list[SymbolRecord] = []
    unresolved: list[tuple[str, str, str, str, str | None]] = []
    diagnostics: list[DiagnosticRecord] = []
    provider = "builtin"
    semantic_metadata: dict = {}

    if language == "python" and parse_complete:
        try:
            tree = ast.parse(text, filename=rel)
            ex = PythonExtractor(rel, file_id, text)
            ex.visit(tree)
            symbols, unresolved = ex.symbols, ex.unresolved
            provider = "python-ast"
            semantic_metadata = {"module": ex.module, "import_bindings": ex.import_bindings}
        except SyntaxError as exc:
            msg = exc.msg or "Python syntax error"
            diagnostics.append(DiagnosticRecord(
                stable_id("diag", rel, str(exc.lineno), str(exc.offset), msg), file_id, rel,
                "error", msg, exc.lineno, exc.offset, "python-ast", "exact"
            ))
    elif language in {"javascript", "typescript"} and parse_complete:
        result = TypeScriptCompilerProvider().parse(root, path, text, file_id)
        if result.available:
            symbols, unresolved, diagnostics = result.symbols, result.unresolved_relations, result.diagnostics
            provider = result.provider
        else:
            symbols, unresolved = _fallback_js_ts(rel, file_id, language, text)
            provider = "regex-fallback"
    elif language == "java" and parse_complete:
        for regex, kind in [(JAVA_CLASS, "class"), (JAVA_METHOD, "method")]:
            for m in regex.finditer(text):
                name = m.group(1); line = _line_of(text, m.start())
                symbols.append(SymbolRecord(stable_id("sym", rel, kind, name), file_id, rel, name, name, kind,
                                            language, line, line, m.group(0).strip(), None, "heuristic"))
        provider = "java-regex-fallback"
    elif language == "html" and parse_complete:
        parser = _HTMLSemanticParser(rel, file_id)
        try:
            parser.feed(text)
            symbols = parser.symbols
            provider = "html-semantic-parser"
        except Exception:
            # HTMLParser is forgiving, but keep a conservative fallback if malformed input triggers host edge cases.
            for m in HTML_ID.finditer(text):
                name = m.group(1); line = _line_of(text, m.start())
                symbols.append(SymbolRecord(stable_id("ui", rel, "element", name), file_id, rel, name, name, "ui-element",
                                            language, line, line, f"id={name}", None, "parser"))
            provider = "html-id-fallback"
    elif language == "css" and parse_complete:
        for m in CSS_RULE.finditer(text):
            selector = " ".join(m.group(1).split())[:300]
            if not selector or selector.startswith("@"):
                continue
            selector_start = m.start(1)
            while selector_start < m.end(1) and text[selector_start].isspace():
                selector_start += 1
            line = _line_of(text, selector_start)
            symbols.append(SymbolRecord(stable_id("css", rel, "rule", selector, str(line)), file_id, rel, selector, selector,
                                        "css-rule", language, line, _line_of(text, m.end()), selector, None, "heuristic"))
        provider = "css-rule-heuristic"
    semantic_metadata = dict(semantic_metadata or {})
    if language != "binary":
        semantic_metadata["source_io"] = _source_io_metadata(path)
    return CompiledFile(file_rec, symbols, unresolved, diagnostics, provider, semantic_metadata)


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    name = Path(p).name
    return "/tests/" in f"/{p}" or name.startswith("test_") or name.endswith("_test.py") or any(x in name for x in (".test.", ".spec."))


def build_relation_resolver_index(compiled: list[CompiledFile]) -> dict:
    """Build the immutable lookup state used by per-file relation partitions.

    Alpha.4 intentionally separates *resolver state* from *relation emission*.  A project edit may
    change only one source partition while leaving the lookup state for unrelated names/modules
    semantically identical.  Partition fingerprints below encode exactly the resolver candidates a
    source file can observe, rather than hashing the entire project graph.
    """
    by_name: dict[str, list[str]] = {}
    by_path_stem: dict[str, list[str]] = {}
    file_path_by_id: dict[str, str] = {}
    symbol_file: dict[str, str] = {}
    module_to_file: dict[str, str] = {}
    module_symbols: dict[tuple[str, str], list[str]] = {}
    symbol_identity: dict[str, tuple[str, str, str, int, int]] = {}

    for cf in compiled:
        file_path_by_id[cf.file.id] = cf.file.path
        by_path_stem.setdefault(Path(cf.file.path).stem, []).append(cf.file.id)
        module = cf.metadata.get("module") if isinstance(cf.metadata, dict) else None
        if module:
            module_to_file[module] = cf.file.id
        for sym in cf.symbols:
            symbol_file[sym.id] = cf.file.id
            symbol_identity[sym.id] = (sym.path, sym.name, sym.qualified_name, sym.start_line, sym.end_line)
            by_name.setdefault(sym.name, []).append(sym.id)
            if module:
                for key in {(module, sym.qualified_name), (module, sym.name)}:
                    bucket = module_symbols.setdefault(key, [])
                    if sym.id not in bucket:
                        bucket.append(sym.id)

    for mapping in (by_name, by_path_stem, module_symbols):
        for key in mapping:
            mapping[key] = sorted(mapping[key])
    return {
        "by_name": by_name,
        "by_path_stem": by_path_stem,
        "file_path_by_id": file_path_by_id,
        "symbol_file": symbol_file,
        "module_to_file": module_to_file,
        "module_symbols": module_symbols,
        "symbol_identity": symbol_identity,
    }


def _resolve_qualified_from_index(index: dict, spec: str) -> tuple[list[str], str | None, str]:
    module_symbols = index["module_symbols"]
    module_to_file = index["module_to_file"]
    if "::" in spec:
        mod, qname = spec.split("::", 1)
        ids = module_symbols.get((mod.lstrip("."), qname), [])
        return list(ids), module_to_file.get(mod.lstrip(".")), "semantic"
    clean = spec.lstrip(".")
    parts = clean.split(".") if clean else []
    for n in range(len(parts), 0, -1):
        mod = ".".join(parts[:n])
        if mod in module_to_file:
            qname = ".".join(parts[n:])
            ids = module_symbols.get((mod, qname), []) if qname else []
            return list(ids), module_to_file[mod], "semantic"
    matches = [m for m in module_to_file if clean and (m.endswith("." + clean) or m == clean)]
    if len(matches) == 1:
        mod = matches[0]
        return [], module_to_file[mod], "derived"
    return [], None, "heuristic"


def relation_partition_fingerprint(cf: CompiledFile, index: dict) -> str:
    """Hash only resolution facts visible to one source partition.

    Body-only edits of an unrelated module therefore do not invalidate callers.  Renaming/adding a
    symbol *does* invalidate partitions that resolve that name because their candidate set changes.
    This is a dependency-closure cache key, not merely a source-file cache key.
    """
    import hashlib, json
    observed = []
    by_name = index["by_name"]
    symbol_file = index["symbol_file"]
    by_path_stem = index["by_path_stem"]
    module_to_file = index["module_to_file"]
    for source, target, kind, trust, evidence in cf.unresolved_relations:
        dep = None
        if kind == "calls_name":
            ids = list(by_name.get(target, []))
            local = [sid for sid in ids if symbol_file.get(sid) == symbol_file.get(source)]
            dep = {"ids": ids, "local": local}
        elif kind in {"calls_qualified", "imports_symbol"}:
            ids, target_file, resolved_trust = _resolve_qualified_from_index(index, target)
            dep = {"ids": ids, "file": target_file, "resolution": resolved_trust}
        elif kind == "imports_module":
            clean = target.lstrip(".")
            tid = module_to_file.get(clean)
            stems = [] if tid else list(by_path_stem.get(clean.split(".")[-1], []))
            dep = {"file": tid, "stems": stems}
        elif kind in {"contains", "renders", "ui_handler_name"}:
            if kind == "ui_handler_name":
                dep = {"ids": list(by_name.get(target, [])), "source_file": symbol_file.get(source)}
            else:
                dep = {"target": target}
        observed.append([source, target, kind, trust, evidence, dep])
    payload = {
        "source_path": cf.file.path,
        "provider": cf.provider,
        "facts": observed,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def resolve_relations_for_file(cf: CompiledFile, index: dict) -> list[RelationRecord]:
    """Resolve only one source file's parser facts against a shared resolver index."""
    by_name = index["by_name"]
    by_path_stem = index["by_path_stem"]
    file_path_by_id = index["file_path_by_id"]
    symbol_file = index["symbol_file"]
    module_to_file = index["module_to_file"]
    out: list[RelationRecord] = []
    seen: set[tuple[str, str, str]] = set()

    def add(source: str, target: str, kind: str, trust: str, evidence: str | None):
        key = (source, target, kind)
        if not source or not target or key in seen:
            return
        seen.add(key)
        out.append(RelationRecord(source, target, kind, trust, evidence))

    for source, target, kind, trust, evidence in cf.unresolved_relations:
        if kind == "calls_qualified":
            ids, _, resolved_trust = _resolve_qualified_from_index(index, target)
            if len(ids) == 1:
                add(source, ids[0], "calls", "semantic" if resolved_trust == "semantic" else "derived", evidence)
            elif len(ids) > 1:
                for tid in ids[:8]:
                    add(source, tid, "calls", "heuristic", f"ambiguous qualified call; {evidence or ''}".strip())
        elif kind == "calls_name":
            ids = by_name.get(target, [])
            source_file = symbol_file.get(source)
            local_ids = [sid for sid in ids if symbol_file.get(sid) == source_file]
            if len(local_ids) == 1:
                add(source, local_ids[0], "calls", "parser", evidence)
            elif len(ids) > 1:
                # A bare name without an import/binding is not evidence of a cross-file call.
                # Preserve ambiguity only as weak hypotheses; a unique project-wide name is
                # deliberately *not* linked, because Python would raise NameError without a
                # runtime binding and such false edges contaminate impact/context expansion.
                for tid in ids[:8]:
                    add(source, tid, "calls", "heuristic", f"ambiguous unbound name-only call; {evidence or ''}".strip())
        elif kind == "imports_symbol":
            ids, target_file, resolved_trust = _resolve_qualified_from_index(index, target)
            for tid in ids[:8]:
                add(source, tid, "imports_symbol", "semantic" if len(ids) == 1 and resolved_trust == "semantic" else "heuristic", evidence)
            if target_file:
                add(source, target_file, "imports", "semantic" if resolved_trust == "semantic" else "derived", evidence)
                source_path = file_path_by_id.get(source, cf.file.path)
                if _is_test_path(source_path) or _is_test_path(cf.file.path):
                    add(source, target_file, "tests", "derived", f"test-like file imports target symbol; {evidence or ''}".strip())
        elif kind == "imports_module":
            clean = target.lstrip(".")
            tid = module_to_file.get(clean)
            resolved_trust = trust
            if tid is None:
                stems = by_path_stem.get(clean.split(".")[-1], [])
                if len(stems) == 1:
                    tid = stems[0]; resolved_trust = "derived"
            if tid:
                add(source, tid, "imports", resolved_trust, evidence)
                source_path = file_path_by_id.get(source, cf.file.path)
                if _is_test_path(source_path) or _is_test_path(cf.file.path):
                    add(source, tid, "tests", "derived", f"test-like file imports target; {evidence or ''}".strip())
        elif kind in {"contains", "renders"}:
            add(source, target, kind, trust, evidence)
        elif kind == "ui_handler_name":
            ids = by_name.get(target, [])
            source_file = symbol_file.get(source)
            local_ids = [sid for sid in ids if symbol_file.get(sid) == source_file]
            candidates = local_ids if local_ids else ids
            if len(candidates) == 1:
                add(source, candidates[0], "handles_event", "parser" if local_ids else "derived", evidence)
            elif len(candidates) > 1:
                for tid in candidates[:8]:
                    add(source, tid, "handles_event", "heuristic", f"ambiguous JSX event handler; {evidence or ''}".strip())
    return out


def resolve_relations(compiled: list[CompiledFile], source_file_ids: set[str] | None = None) -> list[RelationRecord]:
    """Resolve parser facts into project relations, optionally for selected source partitions."""
    index = build_relation_resolver_index(compiled)
    out: list[RelationRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for cf in compiled:
        if source_file_ids is not None and cf.file.id not in source_file_ids:
            continue
        for r in resolve_relations_for_file(cf, index):
            key = (r.source_id, r.target_id, r.kind)
            if key in seen:
                continue
            seen.add(key); out.append(r)
    return out
