from abc import ABC, abstractmethod
from typing import Any, Dict


class CommandQuery(ABC):
    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Any:
        pass


class CommandMutation(ABC):
    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Any:
        pass

