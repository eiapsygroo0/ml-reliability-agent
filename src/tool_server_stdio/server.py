from __future__ import annotations
import json
import sys
from typing import Any, Dict

from src.simulator.simulator import LocalPipelineSimulator
from src.tool_registry.registry import ToolRegistry, ToolSpec
from src.tool_registry import schemas as S
from src.tool_server_stdio.impl_simulator import SimulatorToolImpl

def _send(obj: Dict[str, Any]) -> None:
    # Protocol messages must go to stdout
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()
    
def _log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
    
def build_registry(sim: LocalPipelineSimulator) -> ToolRegistry:
    impl = SimulatorToolImpl(sim)
    reg = ToolRegistry()
    
    reg.register(ToolSpec(
        name="get_logs",
        description="Fetch logs for a pipeline run",
        input_model=S.GetLogsIn,
        output_model=S.GetLogsOut,
        handler=impl.get_logs,
    ))
    reg.register(ToolSpec(
        name="rerun_pipeline",
        description="Rerun a pipeline run id and return status",
        input_model=S.RerunIn,
        output_model=S.RerunOut,
        handler=impl.rerun_pipeline,
    ))
    reg.register(ToolSpec(
        name="backfill",
        description="Backfill a missing partition date",
        input_model=S.BackfillIn,
        output_model=S.BackfillOut,
        handler=impl.backfill,
    ))
    reg.register(ToolSpec(
        name="scale_memory",
        description="Increase memory for a run id",
        input_model=S.ScaleMemoryIn,
        output_model=S.ScaleMemoryOut,
        handler=impl.scale_memory,
    ))
    reg.register(ToolSpec(
        name="use_cache",
        description="Enable cached fallback data for a run id",
        input_model=S.UseCacheIn,
        output_model=S.UseCacheOut,
        handler=impl.use_cache,
    ))
    reg.register(ToolSpec(
        name="increase_concurrency",
        description="Increase concurrency for a run id to address performance/SLA",
        input_model=S.IncreaseConcurrencyIn,
        output_model=S.IncreaseConcurrencyOut,
        handler=impl.increase_concurrency,
    ))
    reg.register(ToolSpec(
        name="verify_health",
        description="Return basic health checks",
        input_model=S.VerifyHealthIn,
        output_model=S.VerifyHealthOut,
        handler=impl.verify_health,
    ))
    reg.register(ToolSpec(
        name="dq_check",
        description="Return data quality checks",
        input_model=S.DqCheckIn,
        output_model=S.DqCheckOut,
        handler=impl.dq_check,
    ))
    reg.register(ToolSpec(
        name="consecutive_successes",
        description="Return consecutive successes count for a pipeline",
        input_model=S.ConsecutiveIn,
        output_model=S.ConsecutiveOut,
        handler=impl.consecutive_successes,
    ))

    return reg

def main() -> None:
    sim = LocalPipelineSimulator()
    reg = build_registry(sim)
    _log("stdio tool server started")
    
    def init_run(pipeline: str, stage: str, scenario: str) -> Dict[str, Any]:
        run = sim.create_run(pipeline, stage)
        sim.set_scenario(run.run_id, scenario)
        return {"run_id": run.run_Id}
    
    while True:
        line = sys.stdin.readline()
        if not line:
            _log("stdin closed; exiting tool server")
            break
        
        try:
            req = json.loads(line)
            method = req.get("method")
            rid = req.get("id")
            params = req.get("param") or {}
            if req.get("jsonrpc") != "2.0":
                raise ValueError("Invalid jsonrpc version")
            
            if method == "tools.list":
                result = reg.list_tools()
                _send({"jsonrpc": "2.0", "id":rid, "result": result})
                
            elif method == "tools.call":
                name = params["name"]
                args = params.get("args", {})
                result = reg.call(name, args)
                _send({"jsonrpc": "2.0", "id": rid, "result":result})
                
            elif method == "sim.init_run":
                result = init_run(params["pipeline"], params["stage"], params["scenario"])
                _send({"jsonrpc": "2.0", "id": rid, "result": result})
                
            else:
                _send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}})

        except Exception as e:
            _send({"jsonrpc": "2.0", "id": req.get("id", None), "error": {"code": -32000, "message": str(e)}})

    