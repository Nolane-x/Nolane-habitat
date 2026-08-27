from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SemanticProviderCapability:
    id: str
    layer: str
    available: bool
    precision: str
    capabilities: tuple[str, ...]
    reason: str
    command: str | None = None
    version: str | None = None
    admitted: bool = False
    trust_ceiling: str = "parser"
    lifecycle: str = "stateless"

    def as_dict(self) -> dict:
        value = asdict(self)
        value["detected"] = self.available
        return value


def _command_version(command: str | None) -> str | None:
    if not command:
        return None
    import subprocess
    try:
        proc = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=2, shell=False)
        text = (proc.stdout or proc.stderr or "").strip().splitlines()
        return text[0][:200] if text else None
    except Exception:
        return None


def _find_first(commands: Iterable[str]) -> str | None:
    for name in commands:
        value = shutil.which(name)
        if value:
            return value
    return None


def semantic_fabric_report(root: Path) -> dict:
    """Report host detection separately from Habitat provider admission.

    Detection says only that a runtime, executable, or index is present on the host. Admission is
    a later Habitat decision that requires a concrete provider contract and evidence. Keeping the
    two states separate prevents capability discovery from overstating active semantic precision.
    """
    root = Path(root).resolve()
    tree_sitter_py = importlib.util.find_spec("tree_sitter") is not None
    tree_cli = shutil.which("tree-sitter")
    tree_available = bool(tree_sitter_py or tree_cli)
    lsp_candidates = {
        "python": ("pyright-langserver", "basedpyright-langserver", "pylsp"),
        "typescript": ("typescript-language-server",),
        "rust": ("rust-analyzer",),
        "go": ("gopls",),
        "c-cpp": ("clangd",),
        "java": ("jdtls",),
        "csharp": ("csharp-ls", "omnisharp"),
        "kotlin": ("kotlin-language-server",),
        "swift": ("sourcekit-lsp",),
    }
    lsp = {}
    for lang, commands in lsp_candidates.items():
        cmd = _find_first(commands)
        lsp[lang] = {"available": bool(cmd), "command": cmd, "version": _command_version(cmd)}
    scip_cmd = _find_first(("scip", "scip-python", "scip-typescript", "scip-clang"))
    scip_indexes = sorted(str(p.relative_to(root)) for p in root.rglob("*.scip") if p.is_file())[:20]
    capabilities = [
        SemanticProviderCapability(
            "syntax.tree-sitter", "syntax", tree_available, "parser",
            ("incremental-parse", "syntax-tree", "error-tolerant-parse"),
            "tree_sitter Python binding or tree-sitter CLI detected" if tree_available else "Tree-sitter runtime not installed on this host",
            tree_cli, _command_version(tree_cli), False, "parser", "workspace-scoped",
        ),
        SemanticProviderCapability(
            "index.scip", "precomputed-semantic-index", bool(scip_cmd or scip_indexes), "semantic",
            ("occurrences", "symbols", "definitions", "references"),
            "SCIP command or index detected" if (scip_cmd or scip_indexes) else "No SCIP command/index detected",
            scip_cmd, _command_version(scip_cmd), False, "semantic", "stateless",
        ),
    ]
    for lang, value in lsp.items():
        capabilities.append(SemanticProviderCapability(
            f"lsp.{lang}", "language-semantic-service", bool(value["available"]), "semantic",
            ("definition", "references", "diagnostics", "hover", "capability-negotiation"),
            "language server detected" if value["available"] else "language server not detected",
            value["command"], value["version"], False, "semantic", "workspace-scoped",
        ))
    providers = [c.as_dict() for c in capabilities]
    detected_count = sum(1 for c in capabilities if c.available)
    admitted_count = sum(1 for c in capabilities if c.admitted)
    return {
        "fabric_version": 2,
        "root": str(root),
        "providers": providers,
        "available_count": detected_count,
        "detected_count": detected_count,
        "admitted_count": admitted_count,
        "scip_indexes": scip_indexes,
        "agent_abstraction": {
            "provider_independent_objects": ["symbol", "type", "call", "implements", "reads", "writes", "throws", "dataflow"],
            "rule": "Agents consume Habitat semantic objects and trust/provenance; concrete parser/LSP/SCIP names are diagnostics, not required reasoning vocabulary.",
        },
        "claim_boundary": "Host detection does not mean admitted. Tree-sitter/LSP/SCIP become active semantic providers only after Habitat admission evidence exists.",
    }
