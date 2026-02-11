"""Unit tests for tool_registry."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from src.tool_registry import schemas as S
from src.tool_registry.registry import build_registry, get_tool_definitions


def test_get_tool_definitions_returns_nine() -> None:
    defs = get_tool_definitions()
    assert len(defs) == 9
    names = [d[0] for d in defs]
    assert "get_logs" in names
    assert "rerun_pipeline" in names
    assert "consecutive_successes" in names


def test_build_registry_list_tools() -> None:
    mock = MagicMock()
    mock.get_logs = lambda req: S.GetLogsOut(logs="mock logs")
    mock.rerun_pipeline = lambda req: S.RerunOut(run_id=req.run_id, status="success", failure_reason=None)
    mock.backfill = lambda req: S.BackfillOut(partition=req.partition, backfilled=True)
    mock.scale_memory = lambda req: S.ScaleMemoryOut(run_id=req.run_id, memory_mb=req.memory_mb)
    mock.use_cache = lambda req: S.UseCacheOut(run_id=req.run_id, use_cache=req.enabled)
    mock.increase_concurrency = lambda req: S.IncreaseConcurrencyOut(run_id=req.run_id, concurrency=req.concurrency)
    mock.verify_health = lambda req: S.VerifyHealthOut(pipeline=req.pipeline, checks={"schema_ok": True, "dq_ok": True})
    mock.dq_check = lambda req: S.DqCheckOut(pipeline=req.pipeline, dq={"row_count_ok": True, "null_rate_ok": True})
    mock.consecutive_successes = lambda req: S.ConsecutiveOut(pipeline=req.pipeline, count=2)

    reg = build_registry(mock)
    listed = reg.list_tools()
    assert "tools" in listed
    assert len(listed["tools"]) == 9


def test_build_registry_call_get_logs() -> None:
    mock = MagicMock()
    mock.get_logs = lambda req: S.GetLogsOut(logs="test log output")
    mock.rerun_pipeline = lambda req: S.RerunOut(run_id=req.run_id, status="success", failure_reason=None)
    mock.backfill = lambda req: S.BackfillOut(partition=req.partition, backfilled=True)
    mock.scale_memory = lambda req: S.ScaleMemoryOut(run_id=req.run_id, memory_mb=req.memory_mb)
    mock.use_cache = lambda req: S.UseCacheOut(run_id=req.run_id, use_cache=req.enabled)
    mock.increase_concurrency = lambda req: S.IncreaseConcurrencyOut(run_id=req.run_id, concurrency=req.concurrency)
    mock.verify_health = lambda req: S.VerifyHealthOut(pipeline=req.pipeline, checks={})
    mock.dq_check = lambda req: S.DqCheckOut(pipeline=req.pipeline, dq={})
    mock.consecutive_successes = lambda req: S.ConsecutiveOut(pipeline=req.pipeline, count=0)

    reg = build_registry(mock)
    out = reg.call("get_logs", {"run_id": "x"})
    assert out["logs"] == "test log output"
