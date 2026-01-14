from __future__ import annotations
from typing import Dict, Any
from src.tool_api.interface import ToolClient


class ToolHelpers:
    """
    Transport-agnostic typed helpers.
    Agent should use this instead of caring about stdio/http/etc.
    """
    def __init__(self, client: ToolClient):
        self.c = client

    def get_logs(self, run_id: str) -> str:
        return self.c.call("get_logs", {"run_id": run_id})["logs"]

    def rerun_pipeline(self, run_id: str) -> Dict[str, Any]:
        return self.c.call("rerun_pipeline", {"run_id": run_id})

    def backfill(self, partition: str) -> Dict[str, Any]:
        return self.c.call("backfill", {"partition": partition})

    def scale_memory(self, run_id: str, memory_mb: int) -> Dict[str, Any]:
        return self.c.call("scale_memory", {"run_id": run_id, "memory_mb": memory_mb})

    def use_cache(self, run_id: str, enabled: bool = True) -> Dict[str, Any]:
        return self.c.call("use_cache", {"run_id": run_id, "enabled": enabled})

    def increase_concurrency(self, run_id: str, concurrency: int) -> Dict[str, Any]:
        return self.c.call("increase_concurrency", {"run_id": run_id, "concurrency": concurrency})

    def verify_health(self, pipeline: str) -> Dict[str, Any]:
        return self.c.call("verify_health", {"pipeline": pipeline})

    def dq_check(self, pipeline: str) -> Dict[str, Any]:
        return self.c.call("dq_check", {"pipeline": pipeline})

    def consecutive_successes(self, pipeline: str, n: int = 2) -> Dict[str, Any]:
        return self.c.call("consecutive_successes", {"pipeline": pipeline, "n": n})
