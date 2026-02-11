"""Unit tests for SREAgent rule-based helpers."""
from __future__ import annotations

from typing import Any, Dict
import pytest
from src.agent.agent import SREAgent
from src.agent.memory import IncidentMemory
from src.agent.models import Diagnosis, Incident, PlanStep, RootCause
from src.agent.policy import PolicyConfig, PolicyEngine
from src.tool_api.interface import ToolClient


class _MockToolClient(ToolClient):
    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {}


def _make_agent() -> SREAgent:
    from src.tool_api.helpers import ToolHelpers
    client = _MockToolClient()
    tools = ToolHelpers(client)
    policy = PolicyEngine(PolicyConfig())
    return SREAgent(tools=tools, policy=policy, memory=IncidentMemory())


def _incident(run_id: str = "run-1") -> Incident:
    return Incident(
        incident_id="inc-1",
        pipeline="p1",
        stage="transform",
        symptom="task_failed",
        evidence=[],
        run_id=run_id,
    )


def test_diagnose_from_rules_oom() -> None:
    agent = _make_agent()
    incident = _incident()
    diag = agent._diagnose_from_rules(incident, "ERROR: OOMKill / out of memory.")
    assert diag.root_cause.subtype == "oom"
    assert diag.root_cause.category == "infra"


def test_diagnose_from_rules_missing_partition() -> None:
    agent = _make_agent()
    incident = _incident()
    diag = agent._diagnose_from_rules(incident, "partition 2026-01-05 not found in warehouse")
    assert diag.root_cause.subtype == "missing_partition"
    assert diag.root_cause.category == "data"


def test_diagnose_from_rules_schema_mismatch() -> None:
    agent = _make_agent()
    incident = _incident()
    diag = agent._diagnose_from_rules(incident, "schema mismatch; column rename detected.")
    assert diag.root_cause.subtype == "schema_mismatch"
    assert diag.root_cause.category == "code"


def test_build_plan_from_rules_oom() -> None:
    agent = _make_agent()
    incident = _incident()
    diag = Diagnosis(
        root_cause=RootCause(category="infra", subtype="oom", confidence=0.85, evidence=[]),
        notes="",
    )
    plan = agent._build_plan_from_rules(incident, diag)
    assert len(plan.steps) >= 1
    actions = [s.action for s in plan.steps]
    assert "scale_memory" in actions
    assert "rerun" in actions
    assert plan.risk_overall in ("low", "medium", "high")


def test_build_plan_from_rules_schema_mismatch() -> None:
    agent = _make_agent()
    incident = _incident()
    diag = Diagnosis(
        root_cause=RootCause(category="code", subtype="schema_mismatch", confidence=0.8, evidence=[]),
        notes="",
    )
    plan = agent._build_plan_from_rules(incident, diag)
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "open_ticket"
    assert plan.risk_overall == "high"
