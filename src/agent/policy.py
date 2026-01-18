from __future__ import annotations
from dataclasses import dataclass
from src.agent.models import Diagnosis, Plan, PlanStep


@dataclass
class PolicyConfig:
    auto_fix_min_confidence: float = 0.75
    require_approval_for_risk: set[str] | None = None
    env: str = "local"  # "staging" | "prod" later

    def __post_init__(self):
        if self.require_approval_for_risk is None:
            self.require_approval_for_risk = {"high"}


class PolicyEngine:
    def __init__(self, cfg: PolicyConfig):
        self.cfg = cfg

    def step_requires_approval(self, step: PlanStep, diagnosis: Diagnosis) -> bool:
        # Risk gate
        if step.risk in self.cfg.require_approval_for_risk:
            return True
        # Low confidence gate
        if diagnosis.root_cause.confidence < self.cfg.auto_fix_min_confidence:
            return True
        # Code changes gate
        if diagnosis.root_cause.category == "code":
            return True
        return False

    def apply(self, plan: Plan, diagnosis: Diagnosis) -> Plan:
        for s in plan.steps:
            s.approval_required = self.step_requires_approval(s, diagnosis)
        return plan
