from __future__ import annotations
from rich.console import Console

from src.agent.models import Incident, RootCause, Diagnosis, Plan, PlanStep, VerificationResult
from src.agent.policy import PolicyEngine
from src.agent.memory import IncidentMemory
from src.tool_api.helpers import ToolHelpers

from src.rag import SimpleRunbookRAG
from src.agent.llm.gemini_client import GeminiClient
from src.agent.llm.prompts import DIAGNOSE_SYSTEM, PLAN_SYSTEM

import os
import json

console = Console()

class SREAgent:
    def __init__(self, 
                 tools: ToolHelpers,
                 rag: SimpleRunbookRAG, 
                 policy: PolicyEngine,
                 llm: GeminiClient | None = None,
                 memory: IncidentMemory|None = None,
                 use_llm: bool = False,
                 ):
        self.tools = tools
        self.rag = rag
        self.policy = policy
        self.memory = memory or IncidentMemory()
        self.llm = llm
        self.use_llm = use_llm and bool(os.getenv("GEMINI_API_KEY"))
        
    # def diagnose(self, incident: Incident) -> Diagnosis:
    #     logs = self.tools.get_logs(incident.run_id)
       
    def diagnose(self, incident:Incident) -> Diagnosis:
        logs = self.tools.get_logs(incident.run_id)
        health = self.tools.verify_health(pipeline=incident.pipeline)["checks"]
        dq = self.tools.dq_check(pipeline=incident.pipeline)["dq"]
        
        # LLM-first(if configured), fallback to rules
        if self.llm is not None:
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
                evidence = incident.evidence + [logs]
        
                # # Rule-based diagnosis (robust for MVP)
                # if "column" in logs or "schema" in logs:
                #     return Diagnosis(root_cause="schema_mismatch", confidence=0.89, evidence=evidence)
                # if "column" in logs or "schema" in logs:
                #     return Diagnosis(root_cause="missing_partition", confidence=0.85, evidence=evidence)
                # if "out of memory" in logs or "OOM" in logs:
                #     return Diagnosis(root_cause="oom", confidence=0.85, evidence=evidence)
                if "partition" in logs or "not found" in logs:
                    rc = RootCause(category="data", subtype="missing_partition", confident=0.85, evidence=evidence)
                    return Diagnosis(root_cause=rc, notes="missing partition detected from logs.")
                
                if "OOM" in logs or "out of memory" in logs:
                    rc = RootCause(category="infra",subtype="oom", confidence=0.85, evidence=evidence)
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
        
                        
    def plan(self, incident: Incident, diagnosis: Diagnosis) -> Plan:
        if self.llm is not None:
            # provide tool list as constraints 
            tool_caps = self.tools.c.call("get_log", {"run_id": incident.run_id})
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
                
                # Retrieve runbook context
                query = f"{incident.pipeline} {incident.stage}{incident.symptom}{diagnosis.root_cause}"
                docs = self.rag.retrieve(query, k=2)
                
                runbook_context = "\n\n".join([f"## {d.title}\n{d.content}" for d in docs if d.score > 0])
                
                root = diagnosis.root_cause.subtype
                # Minimal planning logic grounded by diagnosis
                steps:list[PlanStep] = []
                
                if root == "missing_partition":
                    steps.append(PlanStep(tool="pipeline", action="backfill", args={"partition": "2026-01-01"}, risk="low", estimated_cost_units=1.5))
                    steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_unit=1.0))
                elif root == "oom":
                    # steps.append(PlanStep(tool="k8s", action="scale_memory", args={"run_id": run_id, "memory_mb":2048}, risk="medium")) 
                    # steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": run_id}, risk="low"))
                    prior = self.memory.success_rate(incident.pipeline, root, "scale_memory")
                    mem_target = 2048 if prior >= 0.5 else 1536
                    steps.append(PlanStep(tool="k8s", action="scale_memory",args={"run_id": incident.run_id, "memory_mb":mem_target}, risk="medium", estimated_cost_units=0.5))
                    steps.append(PlanStep(tool="pipeline", action="rerun", args={"run_id": incident.run_id}, risk="low", estimated_cost_unit=1.0))
                elif root == "dependency_outage":
                    #  Prefer caache fallback (safe+cheap), then rerun
                    steps.append(PlanStep(tool="pipeline", action="use_cache", 
                                        args={"run_id": incident.run_id, "enabled":True},
                                        risk="low", estimated_cost_unit=0.2))
                    steps.append(PlanStep(tool="pipeline", action="rerun",
                                        args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
                elif root == "sla_miss":
                    # Performance optimization: increase concurrency
                    steps.append(PlanStep(tool="platform", action="increase_concurrency", 
                                        args={"run_id": incident.run_id, "concurrency": 4},
                                        risk="medium", estimated_cost_units=0.4))  
                    steps.append(PlanStep(tool="pipeline", action="rerun",
                                        args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0)) 
                elif root == "null_spike":
                    # data quality issues: rerun likely won't help. Use cache or escalate
                    steps.append(PlanStep(tool="pipeline", action="use_cache",
                                        args={"run_id": incident.run_id, "enabled": True},
                                        risk="medium", estimated_cost_units=0.2))
                    steps.append(PlanStep(tool="pipeline", action="rerun",
                                        args={"run_id": incident.run_id}, risk="low", estimated_cost_units=1.0))
                    
                elif root == "schema_mismatch":
                    steps.append(PlanStep(tool="itsm", action="open_ticket",
                                        args={"title": "Schema mismatch: requires code/config update",
                                        "run_id": incident.run_id},
                                        risk="high", estimated_cost_units=0.1))
                
                else:
                    steps.append(PlanStep(tool="human", action="noop",
                                        args={"reason":"unknown root cause; escalte"},
                                        risk="high", estimated_cost_units=0.0))
                summary = f"Diagnosis: {diagnosis.root_cause} (conf={diagnosis.confidence:.2f}). Runbook hits: {[d.title for d in docs]}."
                if runbook_context:
                    summary += " Using runbook guidance."
                    
                risk = "low"
                if any(s.risk == "high" for s in steps):
                    risk = "high"
                elif any(s.risk == "medium" for s in steps):
                    risk = "medium"
                    
                total_cost = sum(s.estimated_cost_unit for s in steps)    
                plan = Plan(
                    summary=summary,
                    steps=steps,
                    expected_outcome="Restore pipeline health and pass DQ + consecutive checks",
                    risk_overall=risk,
                    total_cost_unit=total_cost,
                )
                return self.policy.apply(plan, diagnosis)
        
    def act(self, plan: Plan, auto_approve:bool = False) -> None:
        for i, step in enumerate(plan.steps, start=1):
            console.print(f"[bold] Step {i}[/bold]: {step.tool}.{step.action}, args={step.args}"
                          f"risk={step.risk} cost={step.estimated_cost_units:.2f}"
                          f"approval_required={step.approval_required}")
            
            if step.approval_required and not auto_approve:
                ans = input("Approve this step?[y/n]").stripe().lower()
                if ans != "y":
                    console.print("[yellow]Rejected by human. Stopping execution[\yellow]")
                    return
                
            if step.action == "backfill":
                self.tools.backfill(partition=step.args["partition"])
            elif step.action == "scale_memory":
                self.tools.scale_memory(run_id=step.args["run_id"], memory_mb=int(step.args["memory_mb"]))
            elif step.action == "use_cache":
                self.tools.use_cache(run_id=step.args["run_id"], enabled=bool(step.args.get("enabled", True)))
            elif step.action == "increase_concurrency":
                self.tools.increase_concurrency(run_id=step.args["run_id"], concurrency=int(step.args["concurrency"]))
            elif step.action == "rerun":
                self.tools.rerun_pipeline(run_id=step.args["run_id"])
            elif step.action == "open_ticket":
                console.print(f"[cyan]Opened ticket:[/cyan] {step.args}")
            elif step.action == "noop":
                console.print(f"[yellow]No-op:[/yellow] {step.args.get('reason', '')}") 
            else:
                console.print(f"[red]Unknown action[/red]: {step.action}")  
    
    def verify(self, pipeline: str, required_consecutive:int = 2) -> VerificationResult:
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
    
    def finalize(self, pipeline: str, diagnosis: Diagnosis, plan: Plan, verify: VerificationResult)-> None:
        self.memory.record(pipeline, diagnosis, plan, verify)