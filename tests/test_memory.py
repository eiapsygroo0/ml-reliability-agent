"""Unit tests for IncidentMemory."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from src.agent.memory import IncidentMemory
from src.agent.models import Diagnosis, Plan, PlanStep, RootCause, VerificationResult


def _diagnosis(subtype: str = "oom") -> Diagnosis:
    return Diagnosis(
        root_cause=RootCause(category="infra", subtype=subtype, confidence=0.85, evidence=[]),
        notes="",
    )


def _plan(actions: list[str]) -> Plan:
    steps = [PlanStep(tool="pipeline", action=a, args={}) for a in actions]
    return Plan(summary="", steps=steps, expected_outcome="", risk_overall="low", total_cost_units=0.0)


def test_record_and_success_rate_healthy() -> None:
    memory = IncidentMemory()
    diag = _diagnosis(subtype="oom")
    plan = _plan(["scale_memory", "rerun"])
    verify = VerificationResult(healthy=True, checks={"schema_ok": True, "dq_ok": True, "consecutive_ok": True})
    memory.record("p1", diag, plan, verify)
    assert memory.success_rate("p1", "oom", "scale_memory") == 1.0
    assert memory.success_rate("p1", "oom", "rerun") == 1.0


def test_record_and_success_rate_unhealthy() -> None:
    memory = IncidentMemory()
    diag = _diagnosis(subtype="oom")
    plan = _plan(["scale_memory", "rerun"])
    verify = VerificationResult(healthy=False, checks={"schema_ok": True, "dq_ok": False})
    memory.record("p1", diag, plan, verify)
    assert memory.success_rate("p1", "oom", "scale_memory") == 0.0
    assert memory.success_rate("p1", "oom", "rerun") == 0.0


def test_success_rate_unknown_key() -> None:
    memory = IncidentMemory()
    assert memory.success_rate("p1", "oom", "rerun") == 0.0


def test_save_and_load_roundtrip() -> None:
    memory = IncidentMemory()
    diag = _diagnosis(subtype="missing_partition")
    plan = _plan(["backfill", "rerun"])
    verify = VerificationResult(healthy=True, checks={"schema_ok": True, "dq_ok": True, "consecutive_ok": True})
    memory.record("p1", diag, plan, verify)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    try:
        memory.save(path)
        loaded = IncidentMemory()
        loaded.load(path)
        assert loaded.success_rate("p1", "missing_partition", "backfill") == 1.0
        assert loaded.success_rate("p1", "missing_partition", "rerun") == 1.0
    finally:
        path.unlink(missing_ok=True)
