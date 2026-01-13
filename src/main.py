from __future__ import annotations
from rich.console import Console
from rich.panel import Panel

from src.simulator import LocalPipelineSimulator
from src.tools import Tools
from src.rag import SimpleRunbookRAG
from src.agent import SREAgent
from src.models import Incident

console = Console()

def run_scenario(kind: str):
    sim = LocalPipelineSimulator()
    tools = Tools(sim)
    rag = SimpleRunbookRAG(runbook_path="src/runbooks/pipeline_runbook.md")
    agent = SREAgent(tools=tools, rag=rag, use_llm=False)
    
    pipeline = "feature_daily"
    stage = "transform"
    
    #create a failing run
    if kind == "missing_partition":
        failed = sim.create_failed_run(pipeline, stage, "missing_partition")
    elif kind == "oom":
        failed = sim.create_failed_run(pipeline, stage, "oom")
        sim.runs[failed.run_id].memory_mb = 256
    elif kind == "schema_mismatch":
        sim.schema_version = 2
        failed = sim.create_failed_run(pipeline, stage, "schema_mismatch")
    else:
        raise ValueError("Unknown scenario kind")
    
    incident = Incident(
        incident_id = f"inc-{failed.run_id}",
        pipeline=pipeline,
        stage=stage,
        symptom="task_failed",
        evidence=[f"run_id={failed.run_id}", f"failure_reason={failed.failure_reason}"],   
    )
    
    console.print(Panel.fit(f"Scenario: {kind}\nRun ID: {failed.run_id}", title="ML Pipeline Incident"))
    
    diagnosis = agent.diagnose(incident, run_id=failed.run_id)
    console.print(Panel.fit(diagnosis.model_dump_json(indent=2), title="Diagnosis"))
    
    plan = agent.plan(incident, diagnosis, run_id=failed.run_id)
    console.print(Panel.fit(plan.model_dump_json(indent=2), title="Plan"))
    
    agent.act(plan)

    verify = agent.verify(pipeline=pipeline)

    console.print(Panel.fit(verify.model_dump_json(indent=2), title="Verification"))
    
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default="missing_partition",
                        choices=["missing_partition", "oom", "schema_mismatch"])
    args = parser.parse_args()

    run_scenario(args.scenario)    