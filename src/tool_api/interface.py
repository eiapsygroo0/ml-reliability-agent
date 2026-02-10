from __future__ import annotations
from typing import Any, Callable, Dict, Protocol

class ToolClient(Protocol):
    """Backend-agnostic interface for tool execution. Implemented by StdioJsonRpcClient (stdio)
    or by an MCP client adapter when the agent is driven via MCP (e.g. from Cursor)."""
    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        ...


class CallableToolClient:
    """Wraps a callable (e.g. MCP host tool invoker) to implement ToolClient."""
    def __init__(self, invoke: Callable[[str, Dict[str, Any]], Dict[str, Any]]):
        self._invoke = invoke

    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._invoke(tool_name, args)