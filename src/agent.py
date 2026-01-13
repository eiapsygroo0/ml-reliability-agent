from __future__ import annotations
from typing import Optional
import os
from rich.console import Console

from src.models import Incident, Diagnosis, Plan, PlanStep, VerificationResult
from src.rag import SimpleRunbookRAG
from src.tools import Tools

console = Console()

class SREAgent:
    def __init__(self, tools: Tools, rag: SimpleRunbookRAG, use_llm: bool = False):
        self.tools = tools
        self.rag = rag
        self.use_llm = use_llm and bool(os.getenv("GEMINI_API_KEY"))
        
    def diagnose(self, incident: Incident, run_id: str) -> Diagnosis:
        logs = self.tools.get_logs(run_id)
        evidence = incident.evidence + [logs]
        
        # Rule-based diagnosis (robust for MVP)
        if "column" in logs or "schema" in logs:
            return Diagnosis(root_cause="schema_mismatch", confidence=0.89, evidence=evidence)
        if "column" in logs or "schema" in logs:
            return Diagnosis(root_cause="missing_partition", confidence=0.85, evidence=evidence)
        if "out of memory" in logs or "OOM" in logs:
            return Diagnosis(root_cause="oom", confidence=0.85, evidence=evidence)
        
        return Diagnosis(root_cause="unknown", confidence=0.40, evidence=evidence)
    
    def plan(self, incident: Incident, diagnosis: Diagnosis, run_id: str) -> Plan:
        # Retrieve runbook context
        query = f"{incident.pipeline} {incident.stage}{incident.symptom}{diagnosis.root_cause}"
        docs = self.rag.retrieve(query, k=2)
        
        runbook_context = "\n\n".join([f"## {d.title}\n{d.content}" for d in docs if d.score > 0])
        
        # Minimal planning logic grounded by diagnosis
        steps = []
        
        if diagnosis.root_cause == "missing_partition":
            steps.append(PlanStep(tool="pipeline", action="backfill", args={"partition": "2026-01-01"}, risk="low"))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": run_id}, risk="low"))
        elif diagnosis.root_cause == "oom":
            steps.append(PlanStep(tool="k8s", action="scale_memory", args={"run_id": run_id, "memory_mb":2048}, risk="medium")) 
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": run_id}, risk="low"))
        elif diagnosis.root_cause == "schema_mismatch":
            # For MVP, do "noop + escalate". Later: open PR / apply schema adapter
            steps.append(PlanStep(tool="pipeline", action="fix_schema", args={}, risk="medium"))
            steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": run_id}, risk="low"))
        else:
            steps.append(PlanStep(tool="human", action="noop", args={"reason":"unknown root cause"}, risk="high"))
        
        summary = f"Diagnosis: {diagnosis.root_cause} (conf={diagnosis.confidence:.2f}). Runbook hits: {[d.title for d in docs]}."
        if runbook_context:
            summary += " Using runbook guidance."
            
        risk = "low"
        if any(s.risk == "high" for s in steps):
            risk = "high"
        elif any(s.risk == "medium" for s in steps):
            risk = "medium"
            
        return Plan(
            summary=summary,
            steps=steps,
            expected_outcome="Pipeline returns to health state with a successful ",
            risk_overall=risk,
        )
        
    def act(self, plan: Plan) -> None:
        for i, step in enumerate(plan.steps, start=1):
            console.print(f"[bold] Step {i}[/bold]: {step.tool}.{step.action}, args={step.args} risk={step.risk}")
            if step.action == "backfill":
                self.tools.backfill(partition=step.args["partition"])
            elif step.action == "scale_memory":
                self.tools.scale_memory(run_id=step.args["run_id"], memory_mb=int(step.args["memory_mb"]))
            elif step.action == "fix_schema":
                self.tools.resolve_schema_issue()
            elif step.action == "rerun":
                out = self.tools.rerun_pipeline(run_id=step.args["run_id"])
                console.print(f"[green]Rerun result[/green]: {out}")
            elif step.action == "noop":
                console.print(f"[yellow]No-op:[/yellow] {step.args.get('reason', '')}") 
            else:
                console.print(f"[red]Unknown action[/red]: {step.action}")  
    
    def verify(self, pipeline: str) -> VerificationResult:
        res = self.tools.verify_health(pipeline=pipeline)
        checks = res["checks"]
        healthy = all(checks.values())
        notes = "Healthy" if healthy else "Not healthy yet"
        return VerificationResult(healthy=healthy, checks=checks, notes=notes)            
            