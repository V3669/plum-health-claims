from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class AgentError(Exception):
    pass


class IllegalStateTransition(Exception):
    pass


class UnknownCategoryError(AgentError):
    pass


@runtime_checkable
class SyncAgent(Protocol):
    name: str

    def execute(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class AsyncAgent(Protocol):
    name: str

    async def execute(self, *args: Any, **kwargs: Any) -> Any: ...
