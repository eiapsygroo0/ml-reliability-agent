from __future__ import annotations
import time
from dataclasses import dataclass
from typing import List

from src.tool_api.stdio_client import StdioJsonRpcClient
from src.tool_api.helpers import ToolHelpers
from src.agent.policy import PolicyEngine, PolicyConfig
from src.agent.memory import IncidentMemory
from src.agent.agent import SREAgent
from src.agent.models import Incident

@dataclass
class EvalResult:
    scenario: str
    success: bool
    steps: int
    risk_overall: str
    cost: float
    seconds: float
    
def init_run(rpc: StdioJsonRpcClient, pipeline: str, stage: str, scenario: str) -> str:
    res = rpc._rpc("sim.init_run", {"pipeline": pipeline, "stage": stage, "scenario": scenario})
    return res["run_id"]

def run_one(rpc: StdioJsonRpcClient, scenario: str, memory: IncidentMemory) -> EvalResult:
    tools = ToolHelpers(rpc)
    agent = SREAgent(
        tools=tools,
        policy=PolicyEngine(PolicyConfig(auto_fix_min_confidence=0.75)),
        memory=memory,
    )
    
    pipeline = "feature_daily"
    stage = "transform"
    run_id = init_run(rpc, pipeline, stage, scenario)
    incident = Incident(
        incident_id=f"inc-{run_id}",
        pipeline=pipeline,
        stage=stage,
        symptom="task_failed",
        evidence=[f"scenario={scenario}", f"run_id={run_id}"],
        run_id=run_id,
    )
    t0 = time.time()
    diagnosis = agent.diagnose(incident)
    plan = agent.plan(incident, diagnosis)
    agent.act(plan, auto_approve=True)
    
    tools.rerun_pipeline(run_id)
    verify = agent.verify(pipeline=pipeline, require_consecutive=2)
    agent.finalize(pipeline, diagnosis, plan, verify)
    dt = time.time() - t0
    
    return EvalResult(
        scenario=scenario,
        success=verify.healthy,
        steps=len(plan.steps),
        risk_overall=plan.risk_overall,
        cost=plan.total_cost_units,
        seconds=dt,
    )

def run_eval(scenarios: List[str]) -> None:
    rpc = StdioJsonRpcClient(server_module="src.tool_server_stdio.server")
    try:
        memory = IncidentMemory()
        results = [run_one(rpc, s, memory) for s in scenarios]
        success_rate = sum(1 for r in results if r.success) / len(results)
        avg_steps = sum(r.steps for r in results) / len(results)
        avg_cost = sum(r.cost for r in results) / len(results)
        avg_time = sum(r.seconds for r in results) / len(results)
        
        print("\n=== Evaluation Results ===")
        for r in results:
            print(f"{r.scenario:18} success={r.success} steps={r.steps} risk={r.risk_overall:6} "
                  f"cost={r.cost:.2f} time={r.seconds:.3f}s")

        print("\n=== Summary ===")
        print(f"success_rate={success_rate:.2%}")
        print(f"avg_steps={avg_steps:.2f}")
        print(f"avg_cost_units={avg_cost:.2f}")
        print(f"avg_seconds={avg_time:.3f}")
        
    finally:
        rpc.close()
        
if __name__ == "__main__":
    run_eval(["oom", "missing_partition", "schema_mismatch",
            "null_spike", "dependency_outage", "sla_miss"])

        
        
        
    