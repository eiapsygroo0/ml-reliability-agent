"""Structured run log for audit trail: one JSON-per-run with diagnosis, plan, approvals, outcomes, verification, timing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agent.models import Diagnosis, Incident, Plan, VerificationResult


def build_run_log(
    incident: Incident,
    diagnosis: Diagnosis,
    plan: Plan,
    step_results: List[Dict[str, Any]],
    verify: VerificationResult,
    timing_seconds: float,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single JSON-serializable run log for one incident."""
    return {
        "incident_id": incident.incident_id,
        "run_id": run_id or incident.run_id,
        "pipeline": incident.pipeline,
        "diagnosis": diagnosis.model_dump(),
        "plan": plan.model_dump(),
        "step_results": step_results,
        "verification": verify.model_dump(),
        "timing_seconds": timing_seconds,
    }


def write_run_log(log: Dict[str, Any], path: str | Path) -> None:
    """Append one run log line (JSON) to a file, or write a single file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")
