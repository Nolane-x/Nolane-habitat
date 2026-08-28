from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .scip_wire import ScipWireError, decode_packed_int32, iter_fields


DEFAULT_MAX_INDEX_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_DOCUMENTS = 250_000
DEFAULT_MAX_OCCURRENCES = 5_000_000


class ScipParseError(ValueError):
    """Raised when a SCIP index cannot be admitted as bounded semantic evidence."""


@dataclass(frozen=True)
class ScipToolInfo:
    name: str
    version: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class ScipLocation:
    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    symbol: str
    roles: int


@dataclass(frozen=True)
class ScipDiagnostic:
    severity: str
    code: str
    message: str
    source: str
    location: ScipLocation | None


@dataclass(frozen=True)
class ScipSymbolInformation:
    symbol: str
    documentation: tuple[str, ...]
    kind: int
    display_name: str
    enclosing_symbol: str


@dataclass(frozen=True)
class ScipOccurrence:
    symbol: str
    roles: int
    location: ScipLocation | None
    diagnostics: tuple[ScipDiagnostic, ...]


@dataclass(frozen=True)
class ScipDocument:
    path: str
    language: str
    position_encoding: int
    occurrences: tuple[ScipOccurrence, ...]
    symbols: tuple[ScipSymbolInformation, ...]
    diagnostics: tuple[ScipDiagnostic, ...]


@dataclass(frozen=True)
class ScipIndexSnapshot:
    index_digest: str
    project_root: str
    protocol_version: int
    text_document_encoding: int
    tool: ScipToolInfo
    documents: tuple[ScipDocument, ...]
    definitions_by_symbol: dict[str, tuple[ScipLocation, ...]]
    references_by_symbol: dict[str, tuple[ScipLocation, ...]]


def _checked_limit(value: int, name: str, *, allow_zero: bool = True) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _fields(payload: bytes):
    try:
        return tuple(iter_fields(payload))
    except ScipWireError as exc:
        raise ScipParseError(str(exc)) from exc


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, bytes):
        raise ScipParseError(f"{field_name} must be length-delimited")
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScipParseError(f"{field_name} must be UTF-8") from exc


def _message(value: object, field_name: str) -> bytes:
    if not isinstance(value, bytes):
        raise ScipParseError(f"{field_name} must be length-delimited")
    return value


def _varint(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise ScipParseError(f"{field_name} must be a varint")
    return value


def _canonical_document_path(value: str) -> str:
    if not value or "\x00" in value or "\\" in value or value.startswith("/") or "//" in value:
        raise ScipParseError(f"invalid SCIP document relative_path: {value!r}")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ScipParseError(f"non-canonical SCIP document relative_path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ScipParseError(f"non-canonical SCIP document relative_path: {value!r}")
    return value


def _parse_tool(payload: bytes) -> ScipToolInfo:
    name = ""
    version = ""
    arguments: list[str] = []
    seen_name = seen_version = False
    for number, wire, value in _fields(payload):
        if number == 1:
            if wire != 2 or seen_name:
                raise ScipParseError("invalid or duplicate ToolInfo.name")
            name = _text(value, "ToolInfo.name")
            seen_name = True
        elif number == 2:
            if wire != 2 or seen_version:
                raise ScipParseError("invalid or duplicate ToolInfo.version")
            version = _text(value, "ToolInfo.version")
            seen_version = True
        elif number == 3:
            if wire != 2:
                raise ScipParseError("ToolInfo.arguments must be strings")
            arguments.append(_text(value, "ToolInfo.arguments"))
    return ScipToolInfo(name=name, version=version, arguments=tuple(arguments))


def _parse_metadata(payload: bytes) -> tuple[int, ScipToolInfo, str, int]:
    protocol_version = 0
    tool = ScipToolInfo("", "", ())
    project_root = ""
    text_document_encoding = 0
    seen: set[int] = set()
    for number, wire, value in _fields(payload):
        if number not in {1, 2, 3, 4}:
            continue
        if number in seen:
            raise ScipParseError(f"duplicate SCIP Metadata field {number}")
        seen.add(number)
        if number == 1:
            if wire != 0:
                raise ScipParseError("Metadata.version must be a varint")
            protocol_version = _varint(value, "Metadata.version")
        elif number == 2:
            if wire != 2:
                raise ScipParseError("Metadata.tool_info must be a message")
            tool = _parse_tool(_message(value, "Metadata.tool_info"))
        elif number == 3:
            if wire != 2:
                raise ScipParseError("Metadata.project_root must be a string")
            project_root = _text(value, "Metadata.project_root")
        elif number == 4:
            if wire != 0:
                raise ScipParseError("Metadata.text_document_encoding must be a varint")
            text_document_encoding = _varint(value, "Metadata.text_document_encoding")
    return protocol_version, tool, project_root, text_document_encoding


def _parse_single_range(payload: bytes) -> tuple[int, int, int, int]:
    values: dict[int, int] = {}
    for number, wire, value in _fields(payload):
        if number not in {1, 2, 3}:
            continue
        if wire != 0 or number in values:
            raise ScipParseError("invalid single-line SCIP range")
        values[number] = _varint(value, "SingleLineRange")
    if set(values) != {1, 2, 3}:
        raise ScipParseError("incomplete single-line SCIP range")
    line, start, end = values[1], values[2], values[3]
    if end < start:
        raise ScipParseError("SCIP range end precedes start")
    return line, start, line, end


def _parse_multi_range(payload: bytes) -> tuple[int, int, int, int]:
    values: dict[int, int] = {}
    for number, wire, value in _fields(payload):
        if number not in {1, 2, 3, 4}:
            continue
        if wire != 0 or number in values:
            raise ScipParseError("invalid multi-line SCIP range")
        values[number] = _varint(value, "MultiLineRange")
    if set(values) != {1, 2, 3, 4}:
        raise ScipParseError("incomplete multi-line SCIP range")
    start_line, start, end_line, end = values[1], values[2], values[3], values[4]
    if end_line < start_line or (end_line == start_line and end < start):
        raise ScipParseError("SCIP range end precedes start")
    return start_line, start, end_line, end


def _parse_legacy_range(payload: bytes) -> tuple[int, int, int, int]:
    try:
        values = decode_packed_int32(payload)
    except ScipWireError as exc:
        raise ScipParseError(str(exc)) from exc
    if len(values) == 3:
        start_line, start, end = values
        if end < start:
            raise ScipParseError("SCIP legacy range end precedes start")
        return start_line, start, start_line, end
    if len(values) == 4:
        start_line, start, end_line, end = values
        if end_line < start_line or (end_line == start_line and end < start):
            raise ScipParseError("SCIP legacy range end precedes start")
        return start_line, start, end_line, end
    raise ScipParseError("SCIP legacy range must contain three or four int32 values")


def _severity(value: int) -> str:
    return {1: "error", 2: "warning", 3: "information", 4: "hint"}.get(value, "unspecified")


def _parse_diagnostic(payload: bytes, location: ScipLocation | None) -> ScipDiagnostic:
    severity = 0
    code = ""
    message = ""
    source = ""
    seen: set[int] = set()
    for number, wire, value in _fields(payload):
        if number not in {1, 2, 3, 4}:
            continue
        if number in seen:
            raise ScipParseError(f"duplicate SCIP Diagnostic field {number}")
        seen.add(number)
        if number == 1:
            if wire != 0:
                raise ScipParseError("Diagnostic.severity must be a varint")
            severity = _varint(value, "Diagnostic.severity")
        elif number in {2, 3, 4}:
            if wire != 2:
                raise ScipParseError("diagnostic text fields must be strings")
            parsed = _text(value, "Diagnostic text")
            if number == 2:
                code = parsed
            elif number == 3:
                message = parsed
            else:
                source = parsed
    return ScipDiagnostic(_severity(severity), code, message, source, location)


def _parse_occurrence(payload: bytes, path: str) -> ScipOccurrence:
    symbol = ""
    roles = 0
    legacy: bytes | None = None
    typed: tuple[int, int, int, int] | None = None
    diagnostics_payloads: list[bytes] = []
    seen_symbol = seen_roles = False
    typed_kind: int | None = None
    for number, wire, value in _fields(payload):
        if number == 1:
            if wire != 2 or legacy is not None:
                raise ScipParseError("invalid or duplicate Occurrence.range")
            legacy = _message(value, "Occurrence.range")
        elif number == 2:
            if wire != 2 or seen_symbol:
                raise ScipParseError("invalid or duplicate Occurrence.symbol")
            symbol = _text(value, "Occurrence.symbol")
            seen_symbol = True
        elif number == 3:
            if wire != 0 or seen_roles:
                raise ScipParseError("invalid or duplicate Occurrence.symbol_roles")
            roles = _varint(value, "Occurrence.symbol_roles")
            seen_roles = True
        elif number == 6:
            if wire != 2:
                raise ScipParseError("Occurrence.diagnostics must be messages")
            diagnostics_payloads.append(_message(value, "Occurrence.diagnostic"))
        elif number in {8, 9}:
            if wire != 2 or typed_kind is not None:
                raise ScipParseError("invalid SCIP typed_range oneof")
            typed_kind = number
            typed_payload = _message(value, "Occurrence.typed_range")
            typed = _parse_single_range(typed_payload) if number == 8 else _parse_multi_range(typed_payload)

    raw_range = typed
    if raw_range is None and legacy is not None:
        raw_range = _parse_legacy_range(legacy)
    location = None
    if raw_range is not None:
        start_line, start_column, end_line, end_column = raw_range
        location = ScipLocation(
            path=path,
            start_line=start_line + 1,
            start_column=start_column + 1,
            end_line=end_line + 1,
            end_column=end_column + 1,
            symbol=symbol,
            roles=roles,
        )
    diagnostics = tuple(_parse_diagnostic(item, location) for item in diagnostics_payloads)
    return ScipOccurrence(symbol=symbol, roles=roles, location=location, diagnostics=diagnostics)


def _parse_symbol_information(payload: bytes) -> ScipSymbolInformation:
    symbol = ""
    documentation: list[str] = []
    kind = 0
    display_name = ""
    enclosing_symbol = ""
    seen: set[int] = set()
    for number, wire, value in _fields(payload):
        if number == 3:
            if wire != 2:
                raise ScipParseError("SymbolInformation.documentation must be strings")
            documentation.append(_text(value, "SymbolInformation.documentation"))
            continue
        if number not in {1, 5, 6, 8}:
            continue
        if number in seen:
            raise ScipParseError(f"duplicate SCIP SymbolInformation field {number}")
        seen.add(number)
        if number == 1:
            if wire != 2:
                raise ScipParseError("SymbolInformation.symbol must be a string")
            symbol = _text(value, "SymbolInformation.symbol")
        elif number == 5:
            if wire != 0:
                raise ScipParseError("SymbolInformation.kind must be a varint")
            kind = _varint(value, "SymbolInformation.kind")
        elif number == 6:
            if wire != 2:
                raise ScipParseError("SymbolInformation.display_name must be a string")
            display_name = _text(value, "SymbolInformation.display_name")
        elif number == 8:
            if wire != 2:
                raise ScipParseError("SymbolInformation.enclosing_symbol must be a string")
            enclosing_symbol = _text(value, "SymbolInformation.enclosing_symbol")
    return ScipSymbolInformation(symbol, tuple(documentation), kind, display_name, enclosing_symbol)


def _parse_document(payload: bytes) -> ScipDocument:
    path: str | None = None
    language = ""
    position_encoding = 0
    occurrence_payloads: list[bytes] = []
    symbols: list[ScipSymbolInformation] = []
    seen_language = seen_position_encoding = False
    for number, wire, value in _fields(payload):
        if number == 1:
            if wire != 2 or path is not None:
                raise ScipParseError("invalid or duplicate Document.relative_path")
            path = _canonical_document_path(_text(value, "Document.relative_path"))
        elif number == 2:
            if wire != 2:
                raise ScipParseError("Document.occurrences must be messages")
            occurrence_payloads.append(_message(value, "Document.occurrence"))
        elif number == 3:
            if wire != 2:
                raise ScipParseError("Document.symbols must be messages")
            symbols.append(_parse_symbol_information(_message(value, "Document.symbol")))
        elif number == 4:
            if wire != 2 or seen_language:
                raise ScipParseError("invalid or duplicate Document.language")
            language = _text(value, "Document.language")
            seen_language = True
        elif number == 6:
            if wire != 0 or seen_position_encoding:
                raise ScipParseError("invalid or duplicate Document.position_encoding")
            position_encoding = _varint(value, "Document.position_encoding")
            seen_position_encoding = True
    if path is None:
        raise ScipParseError("SCIP Document.relative_path is required")
    occurrences = tuple(_parse_occurrence(item, path) for item in occurrence_payloads)
    diagnostics = tuple(diagnostic for item in occurrences for diagnostic in item.diagnostics)
    return ScipDocument(path, language, position_encoding, occurrences, tuple(symbols), diagnostics)


def parse_scip_index(
    path: Path,
    *,
    max_index_bytes: int = DEFAULT_MAX_INDEX_BYTES,
    max_documents: int = DEFAULT_MAX_DOCUMENTS,
    max_occurrences: int = DEFAULT_MAX_OCCURRENCES,
) -> ScipIndexSnapshot:
    max_index_bytes = _checked_limit(max_index_bytes, "max_index_bytes")
    max_documents = _checked_limit(max_documents, "max_documents")
    max_occurrences = _checked_limit(max_occurrences, "max_occurrences")
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise ScipParseError(f"cannot stat SCIP index: {source}") from exc
    if size > max_index_bytes:
        raise ScipParseError("SCIP index exceeds configured byte limit")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ScipParseError(f"cannot read SCIP index: {source}") from exc
    if len(raw) > max_index_bytes:
        raise ScipParseError("SCIP index exceeds configured byte limit")

    metadata_payload: bytes | None = None
    document_payloads: list[bytes] = []
    for number, wire, value in _fields(raw):
        if number == 1:
            if wire != 2 or metadata_payload is not None:
                raise ScipParseError("SCIP Index must contain metadata exactly once")
            metadata_payload = _message(value, "Index.metadata")
        elif number == 2:
            if wire != 2:
                raise ScipParseError("Index.documents must be messages")
            document_payloads.append(_message(value, "Index.document"))
            if len(document_payloads) > max_documents:
                raise ScipParseError("SCIP index exceeds configured document limit")
    if metadata_payload is None:
        raise ScipParseError("SCIP Index.metadata is required")

    protocol_version, tool, project_root, text_document_encoding = _parse_metadata(metadata_payload)
    documents: list[ScipDocument] = []
    occurrence_count = 0
    seen_paths: set[str] = set()
    for payload in document_payloads:
        document = _parse_document(payload)
        if document.path in seen_paths:
            raise ScipParseError(f"duplicate SCIP document path: {document.path}")
        seen_paths.add(document.path)
        occurrence_count += len(document.occurrences)
        if occurrence_count > max_occurrences:
            raise ScipParseError("SCIP index exceeds configured occurrence limit")
        documents.append(document)

    definitions: dict[str, list[ScipLocation]] = {}
    references: dict[str, list[ScipLocation]] = {}
    for document in documents:
        for occurrence in document.occurrences:
            if not occurrence.symbol or occurrence.location is None:
                continue
            target = definitions if occurrence.roles & 0x1 else references
            target.setdefault(occurrence.symbol, []).append(occurrence.location)

    return ScipIndexSnapshot(
        index_digest=hashlib.sha256(raw).hexdigest(),
        project_root=project_root,
        protocol_version=protocol_version,
        text_document_encoding=text_document_encoding,
        tool=tool,
        documents=tuple(documents),
        definitions_by_symbol={key: tuple(value) for key, value in definitions.items()},
        references_by_symbol={key: tuple(value) for key, value in references.items()},
    )


__all__ = [
    "DEFAULT_MAX_DOCUMENTS",
    "DEFAULT_MAX_INDEX_BYTES",
    "DEFAULT_MAX_OCCURRENCES",
    "ScipDiagnostic",
    "ScipDocument",
    "ScipIndexSnapshot",
    "ScipLocation",
    "ScipOccurrence",
    "ScipParseError",
    "ScipSymbolInformation",
    "ScipToolInfo",
    "parse_scip_index",
]
