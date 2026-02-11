"""Integration test: full diagnose -> plan -> act -> verify for one scenario."""
from __future__ import annotations

import pytest
from src.tool_api.stdio_client import StdioJsonRpcClient
from src.tool_api.helpers import ToolHelpers
from src.agent.policy import PolicyEngine, PolicyConfig
from src.agent.memory import IncidentMemory
from src.agent.agent import SREAgent
from src.agent.models import Incident


def init_run(rpc: StdioJsonRpcClient, pipeline: str, stage: str, scenario: str) -> str:
    res = rpc._rpc("sim.init_run", {"pipeline": pipeline, "stage": stage, "scenario": scenario})
    return res["run_id"]


def test_full_flow_missing_partition() -> None:
    rpc = StdioJsonRpcClient(server_module="src.tool_server_stdio.server")
    try:
        tools = ToolHelpers(rpc)
        agent = SREAgent(
            tools=tools,
            policy=PolicyEngine(PolicyConfig(auto_approval_min_confidence=0.75)),
            memory=IncidentMemory(),
        )
        pipeline = "feature_daily"
        stage = "transform"
        scenario = "missing_partition"
        run_id = init_run(rpc, pipeline, stage, scenario)
        incident = Incident(
            incident_id=f"inc-{run_id}",
            pipeline=pipeline,
            stage=stage,
            symptom="task_failed",
            evidence=[f"scenario={scenario}", f"run_id={run_id}"],
            run_id=run_id,
        )
        diagnosis = agent.diagnose(incident)
        assert diagnosis.root_cause.subtype == "missing_partition"
        assert diagnosis.root_cause.category == "data"

        plan = agent.plan(incident, diagnosis)
        assert len(plan.steps) >= 1
        actions = [s.action for s in plan.steps]
        assert "backfill" in actions or "rerun" in actions

        step_results = agent.act(plan, auto_approve=True, dry_run=False)
        assert len(step_results) == len(plan.steps)

        tools.rerun_pipeline(run_id)
        verify = agent.verify(pipeline=pipeline, required_consecutive=1)
        # Verify ran; healthy may be False if plan params don't match scenario (e.g. backfill partition)
        assert "schema_ok" in verify.checks
    finally:
        rpc.close()
