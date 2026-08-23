"""Verify the public Habitat protocol and MCP catalog against a versioned fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_CONTRACT_FIELDS = (
    "schema",
    "protocol_version",
    "mcp_spec_target",
    "protocol_method_count",
    "protocol_methods_sha256",
    "mcp_tools",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def collect_contract() -> dict[str, Any]:
    from habitat.mcp_adapter import MCP_SPEC_TARGET, tool_catalog
    from habitat.protocol import HabitatProtocol, PROTOCOL_VERSION

    methods = sorted(HabitatProtocol.METHODS)
    tools = sorted(
        (
            {"name": str(tool["name"]), "purpose": str(tool["purpose"])}
            for tool in tool_catalog()
        ),
        key=lambda tool: tool["name"],
    )
    return {
        "schema": 1,
        "protocol_version": PROTOCOL_VERSION,
        "mcp_spec_target": MCP_SPEC_TARGET,
        "protocol_method_count": len(methods),
        "protocol_methods_sha256": hashlib.sha256(
            json.dumps(methods, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "mcp_tools": tools,
    }


def verify_contract(fixture: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    breaking = [
        field
        for field in _CONTRACT_FIELDS
        if fixture.get(field) != actual.get(field)
    ]
    return {
        "compatible": not breaking,
        "breaking": breaking,
        "fixture_sha256": _canonical_digest(fixture),
        "contract_sha256": _canonical_digest(actual),
    }


def _write_json_atomically(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not _COMMIT_SHA.fullmatch(args.source_commit):
        raise ValueError("source commit must be a 40-character lowercase SHA")

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict):
        raise ValueError("contract fixture must be a JSON object")
    report = {
        "schema": 1,
        "suite": "public-contract",
        "source_commit": args.source_commit,
        **verify_contract(fixture, collect_contract()),
    }
    report["report_sha256"] = _canonical_digest(report)
    _write_json_atomically(args.out, report)
    return 0 if report["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
