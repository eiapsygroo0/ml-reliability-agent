"""MCP server with same tools as stdio server for parity (get_logs, rerun, backfill, etc.)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from src.simulator.simulator import LocalPipelineSimulator
from src.tool_registry.registry import build_registry, make_mcp_callable
from src.tool_server_stdio.impl_simulator import SimulatorToolImpl

mcp = FastMCP(name="ml-sre-tools")
sim = LocalPipelineSimulator()
impl = SimulatorToolImpl(sim)
reg = build_registry(impl)

for spec in reg.list_specs():
    mcp.tool()(make_mcp_callable(spec, reg))


@mcp.tool()
def init_run(pipeline: str, stage: str, scenario: str) -> str:
    """Create a run and set its scenario (for eval/setup)."""
    run = sim.create_run(pipeline, stage)
    sim.set_scenario(run.run_id, scenario)
    return run.run_id
