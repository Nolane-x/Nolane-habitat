from __future__ import annotations

from collections.abc import Iterator


class ScipWireError(ValueError):
    """Raised when a bounded SCIP Protobuf wire payload is malformed."""


def _read_varint(data: memoryview, offset: int) -> tuple[int, int]:
    value = 0
    for index in range(10):
        if offset >= len(data):
            raise ScipWireError("truncated protobuf varint")
        byte = int(data[offset])
        offset += 1
        if index == 9 and (byte & 0xFE):
            raise ScipWireError("protobuf varint exceeds uint64 range")
        value |= (byte & 0x7F) << (index * 7)
        if not (byte & 0x80):
            return value, offset
    raise ScipWireError("protobuf varint exceeds 10 bytes")


def iter_fields(payload: bytes | bytearray | memoryview) -> Iterator[tuple[int, int, object]]:
    """Yield validated Protobuf fields without recursively decoding messages.

    Habitat only needs wire types used by current SCIP messages: varint (0), fixed64 (1),
    length-delimited (2), and fixed32 (5). Deprecated Protobuf groups are deliberately rejected.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("protobuf payload must be bytes-like")
    data = memoryview(payload).cast("B")
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number == 0:
            raise ScipWireError("protobuf field number zero is invalid")

        if wire_type == 0:
            value, offset = _read_varint(data, offset)
            yield field_number, wire_type, value
            continue

        if wire_type == 1:
            end = offset + 8
            if end > len(data):
                raise ScipWireError("truncated fixed64 protobuf field")
            value = int.from_bytes(data[offset:end], "little", signed=False)
            offset = end
            yield field_number, wire_type, value
            continue

        if wire_type == 2:
            length, offset = _read_varint(data, offset)
            remaining = len(data) - offset
            if length > remaining:
                raise ScipWireError("truncated length-delimited protobuf field")
            end = offset + length
            value = bytes(data[offset:end])
            offset = end
            yield field_number, wire_type, value
            continue

        if wire_type in {3, 4}:
            raise ScipWireError("protobuf groups are not supported for SCIP")

        if wire_type == 5:
            end = offset + 4
            if end > len(data):
                raise ScipWireError("truncated fixed32 protobuf field")
            value = int.from_bytes(data[offset:end], "little", signed=False)
            offset = end
            yield field_number, wire_type, value
            continue

        raise ScipWireError(f"unsupported protobuf wire type: {wire_type}")


def decode_packed_int32(payload: bytes | bytearray | memoryview) -> tuple[int, ...]:
    """Decode a packed non-negative int32 sequence such as SCIP's legacy range field."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("packed int32 payload must be bytes-like")
    data = memoryview(payload).cast("B")
    offset = 0
    values: list[int] = []
    while offset < len(data):
        value, offset = _read_varint(data, offset)
        if value > 0x7FFFFFFF:
            raise ScipWireError("packed SCIP int32 exceeds non-negative int32 range")
        values.append(value)
    return tuple(values)


__all__ = ["ScipWireError", "decode_packed_int32", "iter_fields"]
