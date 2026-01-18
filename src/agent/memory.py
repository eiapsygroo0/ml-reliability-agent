from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
from src.agent.models import Diagnosis, Plan, VerificationResult

@dataclass
class IncidentMemory:
    # key: (pipeline, root_subtype, action) -> (successes, attemps)
    stats: Dict[Tuple[str, str, str], Tuple[int, int]] = field(default_factory=dict)
    
    def record(self, pipeline: str, diagnosis: Diagnosis, plan: Plan, verify: VerificationResult) -> None:
        root = diagnosis.root_cause.subtype
        success = 1 if verify.healthy else 0
        for step in plan.steps:
            key = (pipeline, root, step.action)
            succ, attempt = self.stats.get(key, (0, 0))
            self.stats[key] = (succ + success, attempt+ 1)
            
    def success_rate(self, pipeline: str, root_subtype: str, action: str) -> float:
        succ, att = self.stats.get((pipeline, root_subtype, action), (0, 0))
        return (succ/att) if att > 0 else 0.0