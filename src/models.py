from __future__ import annotations
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]
ActionType = Literal["rerun", "backfill", "scale_memory", "noop", "fix_schema"]

class Incident(BaseModel):
    incident_id: str
    pipeline: str
    stage: str
    symptom: str
    evidence: List[str] = Field(default_factory=list)
    
class Diagnosis(BaseModel):
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    
class PlanStep(BaseModel):
    tool: str
    action: ActionType
    args: Dict[str, Any] = Field(default_factory=dict)
    risk: Severity = "low"
    rollback: Optional[Dict[str, Any]] = None
    
class Plan(BaseModel):
    summary: str
    steps: List[PlanStep]
    expected_outcome: str
    risk_overall: Severity = "low"
    
class VerificationResult(BaseModel):
    healthy: bool
    checks: Dict[str, bool] = Field(default_factory=dict)
    notes: str = ""
    
    