from __future__ import annotations
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.tool_api.stdio_client import StdioJsonRpcClient
from src.tool_api.helpers import ToolHelpers
from src.agent.policy import PolicyEngine, PolicyConfig
from src.agent.memory import IncidentMemory
from src.agent.agent import SREAgent
from src.agent.models import Incident
from src.agent.run_log import build_run_log, write_run_log
from src.app.config import load_config

console = Console()

def init_run(rpc: StdioJsonRpcClient, pipeline: str, stage: str, scenario: str) -> str:
    res = rpc._rpc("sim.init_run", {"pipeline": pipeline, "stage": stage, "scenario": scenario})
    return res["run_id"]

def run_scenario(
    scenario: str,
    auto_approve: bool = True,
    dry_run: bool = False,
    audit_log_path: str | Path | None = None,
    config_path: str | Path | None = None,
    verify_until_healthy: bool = False,
):
    cfg = load_config(config_path)
    policy = PolicyEngine(cfg["policy"])
    memory = IncidentMemory.from_path(cfg["memory_path"]) if cfg.get("memory_path") else IncidentMemory()

    rpc = StdioJsonRpcClient(server_module="src.tool_server_stdio.server")
    try:
        tools = ToolHelpers(rpc)
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

        t0 = time.time()
        diagnosis = agent.diagnose(incident)
        console.print(Panel.fit(diagnosis.model_dump_json(indent=2), title="Diagnosis"))

        plan = agent.plan(incident, diagnosis)
        console.print(Panel.fit(plan.model_dump_json(indent=2), title="Plan"))

        step_results = agent.act(plan, auto_approve=auto_approve, dry_run=dry_run)
        if not dry_run:
            tools.rerun_pipeline(run_id)

        if verify_until_healthy and not dry_run:
            verify = agent.verify_until_healthy(pipeline=pipeline, required_consecutive=2, max_attempts=5, backoff_seconds=1.0)
        else:
            verify = agent.verify(pipeline=pipeline, required_consecutive=2)
        console.print(Panel.fit(verify.model_dump_json(indent=2), title="Verification"))

        agent.finalize(pipeline, diagnosis, plan, verify)
        dt = time.time() - t0

        if audit_log_path is not None:
            log = build_run_log(incident, diagnosis, plan, step_results, verify, dt)
            write_run_log(log, audit_log_path)
    finally:
        rpc.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default="oom",
                        choices=["oom", "missing_partition", "schema_mismatch",
                                 "null_spike", "dependency_outage", "sla_miss"])
    parser.add_argument("--auto_approve", action="store_true")
    parser.add_argument("--dry_run", action="store_true", help="Print plan steps only, do not execute")
    parser.add_argument("--audit_log", type=str, default=None, help="Append run log to this file (NDJSON)")
    parser.add_argument("--config", type=str, default=None, help="Config file (YAML/JSON) for policy and memory path")
    parser.add_argument("--verify_until_healthy", action="store_true", help="Loop verify with backoff until healthy or max attempts")
    args = parser.parse_args()
    run_scenario(
        args.scenario,
        auto_approve=args.auto_approve,
        dry_run=args.dry_run,
        audit_log_path=args.audit_log,
        config_path=args.config,
        verify_until_healthy=args.verify_until_healthy,
    )
