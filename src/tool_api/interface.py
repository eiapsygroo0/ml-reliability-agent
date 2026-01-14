from __future__ import annotations
from typing import Protocol, Dict, Any

class ToolClient(Protocol):
    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        ...