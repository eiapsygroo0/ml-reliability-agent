from __future__ import annotations
from rich.console import Console
from rich.panel import Panel

from src.tool_api.stdio_client import StdioJsonRpcClient
from src.tool_api.helpers import ToolHelpers
from src.agent.policy import PolicyEngine, PolicyConfig
from src.agent.memory import IncidentMemory
from src.agent.agent import SREAgent
from src.agent.models import Incident

console = Console()

def init_run(rpc: StdioJsonRpcClient, pipeline: str, stage: str, scenario: str) -> str:
    res = rpc._rpc("sim.init_run", {"pipeline":pipeline, "stage": stage, "scenario": scenario})
    return res["run_id"]

def run_scenario(scenario: str, auto_approve: bool = True):
    rpc = StdioJsonRpcClient(server_module="src.tool_server_stdio.server")
    try:
        tools = ToolHelpers(rpc)
        policy = PolicyEngine(PolicyConfig(auto_fix_min_confidence=0.75))
        memory = IncidentMemory()
        agent = SREAgent(tools=tools, policy=policy, memory=memory)
        
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
        
        console.print(Panel.fit(f"Scenario: {scenario} \n Run ID: {run_id}", title="ML Pipeline Incident"))
        
        diagnosis = agent.diagnose(incident)
        console.print(Panel.fit(diagnosis.model_dump_json(indent=2), title="Diagnosis"))
        
        plan = agent.plan(incident, diagnosis)
        console.print(Panel.fit(plan.model_dump_json(indent=2), title="Plan"))
        
        agent.act(plan, auto_approve=auto_approve)
        tools.rerun_pipeline(run_id)
        
        verify = agent.verify(pipeline=pipeline, require_consecutive=2)
        console.print(Panel.fit(verify.model_dump_json(indent=2), title="Verification"))
        
        agent.finalize(pipeline, diagnosis, plan, verify)
        
    finally:
        rpc.close()
        
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default="oom", 
                        choices=["oom", "missing_partition", "schema_mismatch",
                                 "null_spike", "dependency_outage", "sla_miss"])
    parser.add_argument("--auto_approve", action="store_true")
    args = parser.parse_args()
    run_scenario(args.scenario, auto_approve=args.auto_approve)
        
        
        
        

































# def run_scenario(kind: str):
#     sim = LocalPipelineSimulator()
#     tools = Tools(sim)
#     rag = SimpleRunbookRAG(runbook_path="src/runbooks/pipeline_runbook.md")
#     agent = SREAgent(tools=tools, rag=rag, use_llm=False)
    
#     pipeline = "feature_daily"
#     stage = "transform"
    
#     #create a failing run
#     if kind == "missing_partition":
#         failed = sim.create_failed_run(pipeline, stage, "missing_partition")
#     elif kind == "oom":
#         failed = sim.create_failed_run(pipeline, stage, "oom")
#         sim.runs[failed.run_id].memory_mb = 256
#     elif kind == "schema_mismatch":
#         sim.schema_version = 2
#         failed = sim.create_failed_run(pipeline, stage, "schema_mismatch")
#     else:
#         raise ValueError("Unknown scenario kind")
    
#     incident = Incident(
#         incident_id = f"inc-{failed.run_id}",
#         pipeline=pipeline,
#         stage=stage,
#         symptom="task_failed",
#         evidence=[f"run_id={failed.run_id}", f"failure_reason={failed.failure_reason}"],   
#     )
    
#     console.print(Panel.fit(f"Scenario: {kind}\nRun ID: {failed.run_id}", title="ML Pipeline Incident"))
    
#     diagnosis = agent.diagnose(incident, run_id=failed.run_id)
#     console.print(Panel.fit(diagnosis.model_dump_json(indent=2), title="Diagnosis"))
    
#     plan = agent.plan(incident, diagnosis, run_id=failed.run_id)
#     console.print(Panel.fit(plan.model_dump_json(indent=2), title="Plan"))
    
#     agent.act(plan)

#     verify = agent.verify(pipeline=pipeline)

#     console.print(Panel.fit(verify.model_dump_json(indent=2), title="Verification"))
    
# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser()
#     parser.add_argument("--scenario", type=str, default="missing_partition",
#                         choices=["missing_partition", "oom", "schema_mismatch"])
#     args = parser.parse_args()

#     run_scenario(args.scenario)    