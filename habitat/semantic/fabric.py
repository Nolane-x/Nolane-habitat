from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from .admission import SemanticAdmissionRegistry


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


def _admitted_runtime_identities(registry: SemanticAdmissionRegistry) -> list[dict]:
    """Return one deterministic identity per admitted semantic provider.

    Registry selection is capability-scoped by design, so the diagnostic fabric queries the
    fixed read-only semantic lanes it knows how to describe and de-duplicates by provider id.
    Host detection is intentionally absent from this path: a binary on PATH can never create an
    admitted identity.
    """
    by_id: dict[str, dict] = {}
    for capability in (
        "parse",
        "definition",
        "references",
        "hover",
        "document-symbols",
        "diagnostics",
    ):
        for identity in registry.cache_identity(capability):
            by_id[identity["provider_id"]] = identity
    return [by_id[provider_id] for provider_id in sorted(by_id)]


def semantic_fabric_report(
    root: Path,
    *,
    semantic_registry: SemanticAdmissionRegistry | None = None,
) -> dict:
    """Report host detection separately from Habitat provider admission.

    ``fabric_version`` remains the alpha.19 wire/report version. ``contract_version``
    versions the provider-admission semantics independently so a stronger internal contract
    does not silently break existing consumers of the diagnostic surface.

    When a workspace registry is supplied, its admitted provider set is merged into this
    diagnostic view so reporting and compilation share the same admission truth. Host discovery
    alone still never implies admission.
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

    if semantic_registry is not None:
        provider_by_id = {provider["id"]: provider for provider in providers}
        for identity in _admitted_runtime_identities(semantic_registry):
            runtime_provider = {
                "id": identity["provider_id"],
                "layer": identity["layer"],
                "available": True,
                "detected": True,
                "precision": identity["trust_ceiling"],
                "capabilities": tuple(identity["capabilities"]),
                "reason": identity["probe_reason"] or "provider admitted by Habitat semantic runtime",
                "command": None,
                "version": None,
                "admitted": True,
                "trust_ceiling": identity["trust_ceiling"],
                "lifecycle": identity["lifecycle"],
                "languages": tuple(identity["languages"]),
                "incremental": bool(identity["incremental"]),
                "admission_evidence": tuple(identity["admission_evidence"]),
            }
            current = provider_by_id.get(runtime_provider["id"])
            if current is None:
                providers.append(runtime_provider)
                provider_by_id[runtime_provider["id"]] = runtime_provider
            else:
                current.update(runtime_provider)

    detected_count = sum(1 for provider in providers if provider["detected"])
    admitted_count = sum(1 for provider in providers if provider["admitted"])
    return {
        "fabric_version": 1,
        "contract_version": 2,
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
        "claim_boundary": "Host detection does not mean admitted. Detected Tree-sitter/LSP/SCIP capabilities are not claimed active until Habitat admission evidence exists.",
    }
