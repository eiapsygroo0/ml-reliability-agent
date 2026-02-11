from __future__ import annotations
import json
import sys
from typing import Any, Dict

from src.simulator.simulator import LocalPipelineSimulator
from src.tool_registry.registry import build_registry
from src.tool_server_stdio.impl_simulator import SimulatorToolImpl


def _send(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def main() -> None:
    sim = LocalPipelineSimulator()
    impl = SimulatorToolImpl(sim)
    reg = build_registry(impl)
    _log("stdio tool server started")
    
    def init_run(pipeline: str, stage: str, scenario: str) -> Dict[str, Any]:
        run = sim.create_run(pipeline, stage)
        sim.set_scenario(run.run_id, scenario)
        return {"run_id": run.run_id}
    
    while True:
        line = sys.stdin.readline()
        if not line:
            _log("stdin closed; exiting tool server")
            break
        
        try:
            req = json.loads(line)
            method = req.get("method")
            rid = req.get("id")
            params = req.get("params") or req.get("param") or {}
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


if __name__ == "__main__":
    main()
