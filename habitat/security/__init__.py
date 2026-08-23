"""Security primitives for truthful Habitat authority and execution boundaries."""

from .capabilities import CapabilityReport, ExecutionCapability, require_capability

__all__ = ["CapabilityReport", "ExecutionCapability", "require_capability"]
