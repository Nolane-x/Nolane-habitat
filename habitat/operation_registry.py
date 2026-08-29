from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .protocol import HabitatProtocol


OperationHandler = Callable[["HabitatProtocol", dict[str, Any]], Any]


@dataclass(frozen=True)
class OperationDescriptor:
    name: str
    handler: OperationHandler
    read_only: bool = False


class OperationRegistry:
    def __init__(self, descriptors: tuple[OperationDescriptor, ...]):
        by_name: dict[str, OperationDescriptor] = {}
        names: list[str] = []
        read_only_names: set[str] = set()

        for descriptor in descriptors:
            if descriptor.name in by_name:
                raise ValueError(f"duplicate operation: {descriptor.name}")
            by_name[descriptor.name] = descriptor
            names.append(descriptor.name)
            if descriptor.read_only:
                read_only_names.add(descriptor.name)

        self._by_name = MappingProxyType(by_name)
        self.names = tuple(names)
        self.read_only_names = frozenset(read_only_names)

    def get(self, name: str) -> OperationDescriptor | None:
        return self._by_name.get(name)
