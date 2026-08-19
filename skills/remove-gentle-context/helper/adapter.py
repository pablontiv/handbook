from __future__ import annotations

from collections import OrderedDict
from typing import Protocol

from helper.models import Candidate, Check, Operation, Receipt, RuntimeContext


class Adapter(Protocol):
    client: str

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]: ...
    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]: ...
    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]: ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: OrderedDict[str, Adapter] = OrderedDict()

    def register(self, adapter: Adapter) -> None:
        client = adapter.client
        if client in self._adapters:
            raise ValueError("adapter_duplicate_client")
        self._adapters[client] = adapter

    def for_client(self, client: str) -> Adapter:
        try:
            return self._adapters[client]
        except KeyError as exc:
            raise ValueError("adapter_unknown_client") from exc
