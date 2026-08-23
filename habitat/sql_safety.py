from __future__ import annotations

import re


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(value: str, allowed: frozenset[str]) -> str:
    if value not in allowed or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"unsupported SQLite identifier: {value!r}")
    return f'"{value}"'


def placeholder_group(count: int) -> str:
    if count < 1:
        raise ValueError("placeholder count must be positive")
    return ",".join("?" for _ in range(count))


def savepoint_identifier(depth: int) -> str:
    """Return a quoted savepoint name derived from a validated internal depth."""

    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
        raise ValueError("savepoint depth must be a non-negative integer")
    return f'"habitat_atomic_{depth}"'


def user_version_pragma(version: int) -> str:
    """Return a pragma statement derived from a validated schema version."""

    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise ValueError("schema version must be a non-negative integer")
    return f"PRAGMA user_version = {version}"
