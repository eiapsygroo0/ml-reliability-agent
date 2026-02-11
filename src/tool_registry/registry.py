from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, Type
from pydantic import BaseModel

from src.tool_registry import schemas as S

try:
    from pydantic_core import PydanticUndefined
except ImportError:
    PydanticUndefined = object()  # sentinel when pydantic_core not available


def get_tool_definitions() -> List[Tuple[str, str, Type[BaseModel], Type[BaseModel]]]:
    """Single source of truth: (name, description, input_model, output_model)."""
    return [
        ("get_logs", "Fetch logs for a pipeline run", S.GetLogsIn, S.GetLogsOut),
        ("rerun_pipeline", "Rerun a pipeline run id and return status", S.RerunIn, S.RerunOut),
        ("backfill", "Backfill a missing partition date", S.BackfillIn, S.BackfillOut),
        ("scale_memory", "Increase memory for a run id", S.ScaleMemoryIn, S.ScaleMemoryOut),
        ("use_cache", "Enable cached fallback data for a run id", S.UseCacheIn, S.UseCacheOut),
        (
            "increase_concurrency",
            "Increase concurrency for a run id to address performance/SLA",
            S.IncreaseConcurrencyIn,
            S.IncreaseConcurrencyOut,
        ),
        ("verify_health", "Return basic health checks", S.VerifyHealthIn, S.VerifyHealthOut),
        ("dq_check", "Return data quality checks", S.DqCheckIn, S.DqCheckOut),
        (
            "consecutive_successes",
            "Return consecutive successes count for a pipeline",
            S.ConsecutiveIn,
            S.ConsecutiveOut,
        ),
    ]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def list_specs(self) -> List[ToolSpec]:
        """Return all registered tool specs (e.g. for MCP registration)."""
        return list(self._tools.values())

    def list_tools(self) -> Dict[str, Any]:
        tools = []
        for t in self._tools.values():
            tools.append({
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_model.model_json_schema(),
                "output_schema": t.output_model.model_json_schema(),
            })
        return {"tools": tools}

    def call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        spec = self._tools[name]
        parsed = spec.input_model(**args)
        out = spec.handler(parsed)
        if not isinstance(out, spec.output_model):
            raise TypeError(f"Handler returned {type(out)}, expected {spec.output_model}")
        return out.model_dump()


def build_registry(impl: Any) -> ToolRegistry:
    """Build a ToolRegistry from the shared tool definitions and an implementation object."""
    reg = ToolRegistry()
    for name, description, input_model, output_model in get_tool_definitions():
        handler = getattr(impl, name)
        reg.register(
            ToolSpec(
                name=name,
                description=description,
                input_model=input_model,
                output_model=output_model,
                handler=handler,
            )
        )
    return reg


def make_mcp_callable(spec: ToolSpec, registry: ToolRegistry):  # noqa: ANN201
    """Return a callable suitable for FastMCP registration: correct name, doc, and signature from spec."""
    def fn(**kwargs: Any) -> Dict[str, Any]:
        return registry.call(spec.name, kwargs)

    fn.__name__ = spec.name
    fn.__doc__ = spec.description
    fn.__annotations__ = {k: v.annotation for k, v in spec.input_model.model_fields.items()}

    params = []
    for name, field in spec.input_model.model_fields.items():
        default = inspect.Parameter.empty
        if not field.is_required():
            if getattr(field, "default", None) is not PydanticUndefined:
                default = field.default
            elif getattr(field, "default_factory", None) is not None:
                default = field.default_factory()
        params.append(
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=field.annotation)
        )
    fn.__signature__ = inspect.Signature(params)
    return fn