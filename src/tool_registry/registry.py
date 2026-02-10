from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, Any, Type
from pydantic import BaseModel

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