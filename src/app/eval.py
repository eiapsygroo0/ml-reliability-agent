from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from src.tool_api.stdio_client import StdioJsonRpcClient
from src.tool_api.helpers import ToolHelpers
from src.agent.policy import PolicyEngine, PolicyConfig
from src.agent.memory import IncidentMemory
from src.agent.agent import SREAgent
from src.agent.models import Diagnosis, Incident

@dataclass
class EvalResult:
    scenario: str
    success: bool
    steps: int
    risk_overall: str
    cost: float
    seconds: float
    diagnosis_ok: bool = True
    expected_category: str = ""
    expected_subtype: str = ""

def load_scenario_matrix(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("scenarios") or {}
    except Exception:
        return {}

def init_run(rpc: StdioJsonRpcClient, pipeline: str, stage: str, scenario: str) -> str:
    res = rpc._rpc("sim.init_run", {"pipeline": pipeline, "stage": stage, "scenario": scenario})
    return res["run_id"]

def run_one(
    rpc: StdioJsonRpcClient,
    scenario: str,
    memory: IncidentMemory,
    expected: Dict[str, Any] | None = None,
) -> EvalResult:
    tools = ToolHelpers(rpc)
    agent = SREAgent(
        tools=tools,
        policy=PolicyEngine(PolicyConfig(auto_approval_min_confidence=0.75)),
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
    verify = agent.verify(pipeline=pipeline, required_consecutive=1)
    agent.finalize(pipeline, diagnosis, plan, verify)
    dt = time.time() - t0

    diagnosis_ok = True
    exp_cat = ""
    exp_sub = ""
    if expected and "diagnosis" in expected:
        exp = expected["diagnosis"]
        exp_cat = exp.get("category", "")
        exp_sub = exp.get("subtype", "")
        diagnosis_ok = (
            diagnosis.root_cause.category == exp_cat
            and diagnosis.root_cause.subtype == exp_sub
        )

    return EvalResult(
        scenario=scenario,
        success=verify.healthy,
        steps=len(plan.steps),
        risk_overall=plan.risk_overall,
        cost=plan.total_cost_units,
        seconds=dt,
        diagnosis_ok=diagnosis_ok,
        expected_category=exp_cat,
        expected_subtype=exp_sub,
    )

def run_eval(
    scenarios: List[str],
    scenario_matrix_path: str | Path | None = None,
    report_path: str | Path | None = None,
    assert_diagnosis: bool = False,
) -> List[EvalResult]:
    scenario_matrix_path = scenario_matrix_path or Path(__file__).parent / "scenarios.yaml"
    matrix = load_scenario_matrix(scenario_matrix_path)

    rpc = StdioJsonRpcClient(server_module="src.tool_server_stdio.server")
    try:
        memory = IncidentMemory()
        results = [
            run_one(rpc, s, memory, expected=matrix.get(s))
            for s in scenarios
        ]
        success_rate = sum(1 for r in results if r.success) / len(results) if results else 0.0
        diagnosis_ok_rate = sum(1 for r in results if r.diagnosis_ok) / len(results) if results else 0.0
        avg_steps = sum(r.steps for r in results) / len(results) if results else 0.0
        avg_cost = sum(r.cost for r in results) / len(results) if results else 0.0
        avg_time = sum(r.seconds for r in results) / len(results) if results else 0.0

        print("\n=== Evaluation Results ===")
        for r in results:
            diag = "ok" if r.diagnosis_ok else "FAIL"
            print(
                f"{r.scenario:18} success={r.success} diagnosis={diag} steps={r.steps} "
                f"risk={r.risk_overall:6} cost={r.cost:.2f} time={r.seconds:.3f}s"
            )

        print("\n=== Summary ===")
        print(f"success_rate={success_rate:.2%}")
        print(f"diagnosis_match_rate={diagnosis_ok_rate:.2%}")
        print(f"avg_steps={avg_steps:.2f}")
        print(f"avg_cost_units={avg_cost:.2f}")
        print(f"avg_seconds={avg_time:.3f}")

        if assert_diagnosis and any(not r.diagnosis_ok for r in results):
            failed = [r.scenario for r in results if not r.diagnosis_ok]
            raise AssertionError(f"Diagnosis regression: {failed}")

        report = {
            "success_rate": success_rate,
            "diagnosis_match_rate": diagnosis_ok_rate,
            "avg_steps": avg_steps,
            "avg_cost_units": avg_cost,
            "avg_seconds": avg_time,
            "results": [
                {
                    "scenario": r.scenario,
                    "success": r.success,
                    "diagnosis_ok": r.diagnosis_ok,
                    "steps": r.steps,
                    "risk_overall": r.risk_overall,
                    "cost": r.cost,
                    "seconds": r.seconds,
                }
                for r in results
            ],
        }
        if report_path is not None:
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"\nReport written to {report_path}")

        return results
    finally:
        rpc.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str, default=None, help="Write JSON report to this path")
    parser.add_argument("--assert_diagnosis", action="store_true", help="Exit non-zero if any diagnosis does not match matrix")
    args = parser.parse_args()
    run_eval(
        ["oom", "missing_partition", "schema_mismatch", "null_spike", "dependency_outage", "sla_miss"],
        report_path=args.report,
        assert_diagnosis=args.assert_diagnosis,
    )

        
        
        
    