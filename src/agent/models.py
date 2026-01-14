from __future__ import annotations
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]
ActionType = Literal["rerun", 
                     "backfill",
                     "scale_memory",
                     "use_cache",
                     "increase_concurrency",
                     "open_ticket",
                     "noop",
                     "fix_schema"]
RootCategory = Literal["data", "infra", "code", "dependency", "performance", "unknown"]
class Incident(BaseModel):
    incident_id: str
    pipeline: str
    stage: str
    symptom: str
    evidence: List[str] = Field(default_factory=list)
    run_id: str

class RootCause(BaseModel):
    category: RootCategory
    subtype: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
        
class Diagnosis(BaseModel):
    root_cause: RootCause
    notes: str = ""
    
class PlanStep(BaseModel):
    tool: str
    action: ActionType
    args: Dict[str, Any] = Field(default_factory=dict)
    
    risk: Severity = "low"
    estimated_cost_units: float = 0.0
    approval_required: bool = False
    rollback: Optional[Dict[str, Any]] = None
    
class Plan(BaseModel):
    summary: str
    steps: List[PlanStep]
    expected_outcome: str
    risk_overall: Severity = "low"
    total_cost_unit: float = 0.0
    
class VerificationResult(BaseModel):
    healthy: bool
    checks: Dict[str, bool] = Field(default_factory=dict)
    consecutive_successes: int = 0
    notes: str = ""
    
    