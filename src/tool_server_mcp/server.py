"""MCP server with same tools as stdio server for parity (get_logs, rerun, backfill, etc.)."""
from __future__ import annotations

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from src.simulator.simulator import LocalPipelineSimulator
from src.tool_registry import schemas as S
from src.tool_server_stdio.impl_simulator import SimulatorToolImpl

mcp = FastMCP(name="ml-sre-tools")
sim = LocalPipelineSimulator()
impl = SimulatorToolImpl(sim)


def _get_logs(run_id: str) -> Dict[str, Any]:
    return impl.get_logs(S.GetLogsIn(run_id=run_id)).model_dump()


def _rerun_pipeline(run_id: str) -> Dict[str, Any]:
    return impl.rerun_pipeline(S.RerunIn(run_id=run_id)).model_dump()


def _backfill(partition: str) -> Dict[str, Any]:
    impl.backfill(S.BackfillIn(partition=partition))
    return {"partition": partition, "backfilled": True}


def _scale_memory(run_id: str, memory_mb: int) -> Dict[str, Any]:
    return impl.scale_memory(S.ScaleMemoryIn(run_id=run_id, memory_mb=memory_mb)).model_dump()


def _use_cache(run_id: str, enabled: bool = True) -> Dict[str, Any]:
    return impl.use_cache(S.UseCacheIn(run_id=run_id, enabled=enabled)).model_dump()


def _increase_concurrency(run_id: str, concurrency: int = 4) -> Dict[str, Any]:
    return impl.increase_concurrency(S.IncreaseConcurrencyIn(run_id=run_id, concurrency=concurrency)).model_dump()


def _verify_health(pipeline: str) -> Dict[str, Any]:
    return impl.verify_health(S.VerifyHealthIn(pipeline=pipeline)).model_dump()


def _dq_check(pipeline: str) -> Dict[str, Any]:
    return impl.dq_check(S.DqCheckIn(pipeline=pipeline)).model_dump()


def _consecutive_successes(pipeline: str, n: int = 2) -> Dict[str, Any]:
    return impl.consecutive_successes(S.ConsecutiveIn(pipeline=pipeline, n=n)).model_dump()


@mcp.tool()
def init_run(pipeline: str, stage: str, scenario: str) -> str:
    run = sim.create_run(pipeline, stage)
    sim.set_scenario(run.run_id, scenario)
    return run.run_id


@mcp.tool()
def get_logs(run_id: str) -> Dict[str, Any]:
    """Fetch logs for a pipeline run."""
    return _get_logs(run_id)


@mcp.tool()
def rerun_pipeline(run_id: str) -> Dict[str, Any]:
    """Rerun a pipeline run id and return status."""
    return _rerun_pipeline(run_id)


@mcp.tool()
def backfill(partition: str) -> Dict[str, Any]:
    """Backfill a missing partition date."""
    return _backfill(partition)


@mcp.tool()
def scale_memory(run_id: str, memory_mb: int) -> Dict[str, Any]:
    """Increase memory for a run id."""
    return _scale_memory(run_id, memory_mb)


@mcp.tool()
def use_cache(run_id: str, enabled: bool = True) -> Dict[str, Any]:
    """Enable cached fallback data for a run id."""
    return _use_cache(run_id, enabled)


@mcp.tool()
def increase_concurrency(run_id: str, concurrency: int = 4) -> Dict[str, Any]:
    """Increase concurrency for a run id to address performance/SLA."""
    return _increase_concurrency(run_id, concurrency)


@mcp.tool()
def verify_health(pipeline: str) -> Dict[str, Any]:
    """Return basic health checks."""
    return _verify_health(pipeline)


@mcp.tool()
def dq_check(pipeline: str) -> Dict[str, Any]:
    """Return data quality checks."""
    return _dq_check(pipeline)


@mcp.tool()
def consecutive_successes(pipeline: str, n: int = 2) -> Dict[str, Any]:
    """Return consecutive successes count for a pipeline."""
    return _consecutive_successes(pipeline, n)
