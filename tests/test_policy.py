"""Unit tests for PolicyEngine."""
from __future__ import annotations

import pytest
from src.agent.models import Diagnosis, Plan, PlanStep, RootCause
from src.agent.policy import PolicyConfig, PolicyEngine


def _diagnosis(confidence: float = 0.85, category: str = "infra", subtype: str = "oom") -> Diagnosis:
    return Diagnosis(
        root_cause=RootCause(category=category, subtype=subtype, confidence=confidence, evidence=[]),
        notes="",
    )


def _plan(steps: list[PlanStep]) -> Plan:
    return Plan(
        summary="test",
        steps=steps,
        expected_outcome="ok",
        risk_overall="low",
        total_cost_units=1.0,
    )


def test_step_require_approval_high_risk() -> None:
    cfg = PolicyConfig(auto_approval_min_confidence=0.75)
    engine = PolicyEngine(cfg)
    step = PlanStep(tool="itsm", action="open_ticket", args={}, risk="high")
    diag = _diagnosis(confidence=0.9, category="code", subtype="schema_mismatch")
    assert engine.step_require_approval(step, diag) is True


def test_step_require_approval_low_risk_high_confidence() -> None:
    cfg = PolicyConfig(auto_approval_min_confidence=0.75)
    engine = PolicyEngine(cfg)
    step = PlanStep(tool="pipeline", action="rerun", args={}, risk="low")
    diag = _diagnosis(confidence=0.9, category="infra", subtype="oom")
    assert engine.step_require_approval(step, diag) is False


def test_step_require_approval_low_confidence() -> None:
    cfg = PolicyConfig(auto_approval_min_confidence=0.75)
    engine = PolicyEngine(cfg)
    step = PlanStep(tool="pipeline", action="rerun", args={}, risk="low")
    diag = _diagnosis(confidence=0.5, category="unknown", subtype="unknown")
    assert engine.step_require_approval(step, diag) is True


def test_step_require_approval_code_category() -> None:
    cfg = PolicyConfig(auto_approval_min_confidence=0.9)
    engine = PolicyEngine(cfg)
    step = PlanStep(tool="pipeline", action="rerun", args={}, risk="low")
    diag = _diagnosis(confidence=0.95, category="code", subtype="schema_mismatch")
    assert engine.step_require_approval(step, diag) is True


def test_apply_returns_new_plan() -> None:
    cfg = PolicyConfig(auto_approval_min_confidence=0.75)
    engine = PolicyEngine(cfg)
    step = PlanStep(tool="pipeline", action="rerun", args={}, risk="low")
    plan = _plan([step])
    diag = _diagnosis(confidence=0.9)
    out = engine.apply(plan, diag)
    assert out is not plan
    assert out.steps[0] is not step
    assert out.steps[0].approval_required is False
