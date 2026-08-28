from __future__ import annotations


def varint(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("fixture varint requires a non-negative integer")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field_varint(number: int, value: int) -> bytes:
    return varint((number << 3) | 0) + varint(value)


def field_bytes(number: int, value: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(value)) + value


def field_text(number: int, value: str) -> bytes:
    return field_bytes(number, value.encode("utf-8"))


def packed_int32(values: tuple[int, ...]) -> bytes:
    return b"".join(varint(value) for value in values)


def tool_info(name: str = "scip-python", version: str = "0.6.0", arguments: tuple[str, ...] = ("index",)) -> bytes:
    payload = field_text(1, name) + field_text(2, version)
    for argument in arguments:
        payload += field_text(3, argument)
    return payload


def metadata(
    *,
    project_root: str = "file:///workspace",
    tool_name: str = "scip-python",
    tool_version: str = "0.6.0",
    arguments: tuple[str, ...] = ("index",),
    protocol_version: int = 0,
    text_document_encoding: int = 1,
) -> bytes:
    return (
        field_varint(1, protocol_version)
        + field_bytes(2, tool_info(tool_name, tool_version, arguments))
        + field_text(3, project_root)
        + field_varint(4, text_document_encoding)
    )


def single_line_range(line: int, start: int, end: int) -> bytes:
    return field_varint(1, line) + field_varint(2, start) + field_varint(3, end)


def multi_line_range(start_line: int, start: int, end_line: int, end: int) -> bytes:
    return (
        field_varint(1, start_line)
        + field_varint(2, start)
        + field_varint(3, end_line)
        + field_varint(4, end)
    )


def diagnostic(
    message: str,
    *,
    severity: int = 2,
    code: str = "W1",
    source: str = "fixture",
) -> bytes:
    return (
        field_varint(1, severity)
        + field_text(2, code)
        + field_text(3, message)
        + field_text(4, source)
    )


def occurrence(
    symbol: str,
    *,
    roles: int = 0,
    legacy_range: tuple[int, ...] | None = None,
    typed_single: tuple[int, int, int] | None = None,
    typed_multi: tuple[int, int, int, int] | None = None,
    diagnostics: tuple[bytes, ...] = (),
) -> bytes:
    payload = b""
    if legacy_range is not None:
        payload += field_bytes(1, packed_int32(legacy_range))
    payload += field_text(2, symbol)
    payload += field_varint(3, roles)
    for item in diagnostics:
        payload += field_bytes(6, item)
    if typed_single is not None:
        payload += field_bytes(8, single_line_range(*typed_single))
    if typed_multi is not None:
        payload += field_bytes(9, multi_line_range(*typed_multi))
    return payload


def symbol_information(
    symbol: str,
    *,
    display_name: str = "",
    kind: int = 17,
    documentation: tuple[str, ...] = (),
    enclosing_symbol: str = "",
) -> bytes:
    payload = field_text(1, symbol)
    for item in documentation:
        payload += field_text(3, item)
    payload += field_varint(5, kind)
    if display_name:
        payload += field_text(6, display_name)
    if enclosing_symbol:
        payload += field_text(8, enclosing_symbol)
    return payload


def document(
    relative_path: str,
    *,
    language: str = "python",
    position_encoding: int = 3,
    occurrences: tuple[bytes, ...] = (),
    symbols: tuple[bytes, ...] = (),
    text: str = "",
) -> bytes:
    payload = field_text(1, relative_path)
    for item in occurrences:
        payload += field_bytes(2, item)
    for item in symbols:
        payload += field_bytes(3, item)
    payload += field_text(4, language)
    if text:
        payload += field_text(5, text)
    payload += field_varint(6, position_encoding)
    return payload


def index_payload(*, metadata_payload: bytes | None = None, documents: tuple[bytes, ...] = ()) -> bytes:
    payload = b""
    if metadata_payload is not None:
        payload += field_bytes(1, metadata_payload)
    for item in documents:
        payload += field_bytes(2, item)
    return payload


def sample_index() -> tuple[bytes, str]:
    symbol = "scip-python python demo 1.0 foo()."
    definition = occurrence(
        symbol,
        roles=0x1,
        legacy_range=(0, 4, 7),
        typed_single=(0, 4, 7),
    )
    reference = occurrence(
        symbol,
        typed_single=(2, 8, 11),
        diagnostics=(diagnostic("fixture warning"),),
    )
    first = document(
        "src/a.py",
        occurrences=(definition,),
        symbols=(symbol_information(symbol, display_name="foo", documentation=("Demo function",)),),
    )
    second = document("src/b.py", occurrences=(reference,))
    return index_payload(metadata_payload=metadata(), documents=(first, second)), symbol
