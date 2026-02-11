from __future__ import annotations
from rich.console import Console

from src.agent.models import Incident, RootCause, Diagnosis, Plan, PlanStep, VerificationResult
from src.agent.policy import PolicyEngine
from src.agent.memory import IncidentMemory
from src.tool_api.helpers import ToolHelpers

from src.rag import SimpleRunbookRAG
from src.agent.llm.gemini_client import GeminiClient
from src.agent.llm.prompts import DIAGNOSE_SYSTEM, PLAN_SYSTEM

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

console = Console()

class SREAgent:
    def __init__(self,
                 tools: ToolHelpers,
                 policy: PolicyEngine,
                 rag: Optional[SimpleRunbookRAG] = None,
                 llm: Optional[GeminiClient] = None,
                 memory: Optional[IncidentMemory] = None,
                 use_llm: bool = False,
                 ):
        self.tools = tools
        self.rag = rag
        self.policy = policy
        self.memory = memory or IncidentMemory()
        self.llm = llm
        self.use_llm = use_llm and bool(os.getenv("GEMINI_API_KEY"))

    def _diagnose_from_rules(self, incident: Incident, logs: str) -> Diagnosis:
        evidence = incident.evidence + [logs]
        if "partition" in logs or "not found" in logs:
            rc = RootCause(category="data", subtype="missing_partition", confidence=0.85, evidence=evidence)
            return Diagnosis(root_cause=rc, notes="missing partition detected from logs.")
        if "OOM" in logs or "out of memory" in logs:
            rc = RootCause(category="infra", subtype="oom", confidence=0.85, evidence=evidence)
            return Diagnosis(root_cause=rc, notes="OOM detected from logs.")
        if "schema mismatch" in logs or "column" in logs:
            rc = RootCause(category="code", subtype="schema_mismatch", confidence=0.80, evidence=evidence)
            return Diagnosis(root_cause=rc, notes="Schema mismatch usually needs code/config update.")
        if "dependency" in logs or "timeout" in logs or "5xx" in logs:
            rc = RootCause(category="dependency", subtype="dependency_outage", confidence=0.80, evidence=evidence)
            return Diagnosis(root_cause=rc, notes="Dependency outage suspected from logs.")
        if "SLA" in logs or "backlog" in logs or "slow" in logs:
            rc = RootCause(category="performance", subtype="sla_miss", confidence=0.75, evidence=evidence)
            return Diagnosis(root_cause=rc, notes="Performance/SLA issue suspected.")
        if "DQ_FAIL" in logs or "null_rate" in logs:
            rc = RootCause(category="data", subtype="null_spike", confidence=0.80, evidence=evidence)
            return Diagnosis(root_cause=rc, notes="Data quality failure suspected (null spike).")
        rc = RootCause(category="unknown", subtype="unknown", confidence=0.40, evidence=evidence)
        return Diagnosis(root_cause=rc, notes="Unable to classify root cause confidently.")

    def diagnose(self, incident: Incident) -> Diagnosis:
        logs = self.tools.get_logs(incident.run_id)

        if self.llm is not None:
            health = self.tools.verify_health(pipeline=incident.pipeline)["checks"]
            dq = self.tools.dq_check(pipeline=incident.pipeline)["dq"]
            user = {
                "incident": incident.model_dump(),
                "logs": logs,
                "health": health,
                "dq": dq,
            }
            try:
                return self.llm.generate_json(
                    system=DIAGNOSE_SYSTEM,
                    user=json.dumps(user, indent=2),
                    schema=Diagnosis,
                )
            except Exception:
                return self._diagnose_from_rules(incident, logs)

        return self._diagnose_from_rules(incident, logs)

    def _build_plan_from_rules(self, incident: Incident, diagnosis: Diagnosis) -> Plan:
        docs = []
        if self.rag is not None:
            query = f"{incident.pipeline} {incident.stage}{incident.symptom}{diagnosis.root_cause}"
            docs = self.rag.retrieve(query, k=2)
        runbook_context = "\n\n".join([f"## {d.title}\n{d.content}" for d in docs if d.score > 0]) if docs else ""
        root = diagnosis.root_cause.subtype
        steps: list[PlanStep] = []
        if root == "missing_partition":
            steps.append(PlanStep(tool="pipeline", action="backfill", args={"partition": "2026-01-01"}, risk="low", estimated_cost_units=1.5))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
        elif root == "oom":
            prior = self.memory.success_rate(incident.pipeline, root, "scale_memory")
            mem_target = 2048 if prior >= 0.5 else 1536
            steps.append(PlanStep(tool="k8s", action="scale_memory", args={"run_id": incident.run_id, "memory_mb": mem_target}, risk="medium", estimated_cost_units=0.5))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
        elif root == "dependency_outage":
            steps.append(PlanStep(tool="pipeline", action="use_cache", args={"run_id": incident.run_id, "enabled": True}, risk="low", estimated_cost_units=0.2))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
        elif root == "sla_miss":
            steps.append(PlanStep(tool="platform", action="increase_concurrency", args={"run_id": incident.run_id, "concurrency": 4}, risk="medium", estimated_cost_units=0.4))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
        elif root == "null_spike":
            steps.append(PlanStep(tool="pipeline", action="use_cache", args={"run_id": incident.run_id, "enabled": True}, risk="medium", estimated_cost_units=0.2))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
        elif root == "schema_mismatch":
            steps.append(PlanStep(tool="itsm", action="open_ticket", args={"title": "Schema mismatch: requires code/config update", "run_id": incident.run_id}, risk="high", estimated_cost_units=0.1))
        else:
            steps.append(PlanStep(tool="human", action="noop", args={"reason": "unknown root cause; escalate"}, risk="high", estimated_cost_units=0.0))
        summary = f"Diagnosis: {diagnosis.root_cause} (conf={diagnosis.root_cause.confidence:.2f}). Runbook hits: {[d.title for d in docs]}."
        if runbook_context:
            summary += " Using runbook guidance."
        risk = "high" if any(s.risk == "high" for s in steps) else ("medium" if any(s.risk == "medium" for s in steps) else "low")
        total_cost = sum(s.estimated_cost_units for s in steps)
        return Plan(
            summary=summary,
            steps=steps,
            expected_outcome="Restore pipeline health and pass DQ + consecutive checks",
            risk_overall=risk,
            total_cost_units=total_cost,
        )

    def plan(self, incident: Incident, diagnosis: Diagnosis) -> Plan:
        if self.llm is not None:
            payload = {
                "incident": incident.model_dump(),
                "diagnosis": diagnosis.model_dump(),
                "constraints": {
                    "available_actions": [
                    "rerun", "backfill", "scale_memory", "use_cache",
                    "increase_concurrency", "open_ticket", "noop" 
                    ],
                    "notes": "Do not propose code changes: open_ticket instead."
                },
            }
            try:
                plan = self.llm.generate_json(
                    system=PLAN_SYSTEM,
                    user=json.dumps(payload, indent=2),
                    schema=Plan,
                )
                return self.policy.apply(plan, diagnosis)
            except Exception:
                return self.policy.apply(self._build_plan_from_rules(incident, diagnosis), diagnosis)

        return self.policy.apply(self._build_plan_from_rules(incident, diagnosis), diagnosis)

    def _execute_step(self, step: PlanStep) -> Any:
        """Execute a single plan step; returns outcome for audit."""

        def open_ticket(s: PlanStep) -> Any:
            console.print(f"[cyan]Opened ticket:[/cyan] {s.args}")
            return {"opened": s.args}

        def noop(s: PlanStep) -> Any:
            console.print(f"[yellow]No-op:[/yellow] {s.args.get('reason', '')}")
            return {"reason": s.args.get("reason", "")}

        handlers: Dict[str, Callable[[PlanStep], Any]] = {
            "backfill": lambda s: self.tools.backfill(partition=s.args["partition"]),
            "scale_memory": lambda s: self.tools.scale_memory(
                run_id=s.args["run_id"], memory_mb=int(s.args["memory_mb"])
            ),
            "use_cache": lambda s: self.tools.use_cache(
                run_id=s.args["run_id"], enabled=bool(s.args.get("enabled", True))
            ),
            "increase_concurrency": lambda s: self.tools.increase_concurrency(
                run_id=s.args["run_id"], concurrency=int(s.args["concurrency"])
            ),
            "rerun": lambda s: self.tools.rerun_pipeline(run_id=s.args["run_id"]),
            "open_ticket": open_ticket,
            "noop": noop,
        }

        if step.action in handlers:
            return handlers[step.action](step)
        console.print(f"[red]Unknown action[/red]: {step.action}")
        return {"error": "unknown_action"}

    def act(
        self,
        plan: Plan,
        auto_approve: bool = False,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute plan steps. Returns list of step results for audit (step_index, approved, outcome)."""
        step_results: List[Dict[str, Any]] = []
        approve_all_remaining = auto_approve

        for i, step in enumerate(plan.steps, start=1):
            console.print(
                f"[bold] Step {i}[/bold]: {step.tool}.{step.action}, args={step.args} "
                f"risk={step.risk} cost={step.estimated_cost_units:.2f} "
                f"approval_required={step.approval_required}"
            )

            if dry_run:
                step_results.append({"step_index": i, "approved": True, "outcome": "dry_run_skipped"})
                continue

            approved = True
            if step.approval_required and not approve_all_remaining:
                ans = input("Approve this step? [y/n/a=approve all remaining]: ").strip().lower()
                if ans == "a":
                    approve_all_remaining = True
                    approved = True
                elif ans != "y":
                    approved = False
                    console.print("[yellow]Rejected by human. Stopping execution[/yellow]")
                    step_results.append({"step_index": i, "approved": False, "outcome": "rejected"})
                    return step_results

            step_results.append({"step_index": i, "approved": approved, "outcome": None})
            step_results[-1]["outcome"] = self._execute_step(step)

        return step_results  
    
    def verify(self, pipeline: str, required_consecutive: int = 2) -> VerificationResult:
        health = self.tools.verify_health(pipeline=pipeline)["checks"]
        dq = self.tools.dq_check(pipeline=pipeline)["dq"]
        consec = self.tools.consecutive_successes(pipeline=pipeline, n=required_consecutive)["count"]

        checks = {
            "schema_ok": bool(health.get("schema_ok", False)),
            "dq_ok": bool(all(dq.values())),
            "consecutive_ok": consec >= required_consecutive,
        }
        healthy = all(checks.values())
        notes = f"consecutive={consec}, dq={dq}, health={health}"
        return VerificationResult(healthy=healthy, checks=checks, consecutive_successes=consec, notes=notes)

    def verify_until_healthy(
        self,
        pipeline: str,
        required_consecutive: int = 2,
        max_attempts: int = 5,
        backoff_seconds: float = 1.0,
    ) -> VerificationResult:
        """Run verify() in a loop with backoff until healthy or max_attempts."""
        last = self.verify(pipeline, required_consecutive=required_consecutive)
        for _ in range(max_attempts - 1):
            if last.healthy:
                return last
            time.sleep(backoff_seconds)
            last = self.verify(pipeline, required_consecutive=required_consecutive)
        return last

    def finalize(self, pipeline: str, diagnosis: Diagnosis, plan: Plan, verify: VerificationResult) -> None:
        self.memory.record(pipeline, diagnosis, plan, verify)