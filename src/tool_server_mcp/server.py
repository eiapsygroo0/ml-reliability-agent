from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from src.simulator.simulator import LocalPipelineSimulator

mcp = FastMCP(name="ml-sre-tools")
sim = LocalPipelineSimulator()

@mcp.tool()
def init_run(pipeline: str, stage: str, scenario: str) -> str:
    run = sim.create_run(pipeline, stage)
    sim.set_scenario(run.run_id, scenario)
    return run.run_id

