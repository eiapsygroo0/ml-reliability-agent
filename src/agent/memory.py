from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple
from src.agent.models import Diagnosis, Plan, VerificationResult


@dataclass
class IncidentMemory:
    """Tracks success rates per (pipeline, root_subtype, action). Optional persistence to JSON."""
    stats: Dict[Tuple[str, str, str], Tuple[int, int]] = field(default_factory=dict)
    _path: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._path is not None:
            self.load(self._path)

    @classmethod
    def from_path(cls, path: str | Path) -> "IncidentMemory":
        p = Path(path)
        return cls(_path=p)

    def load(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("stats", []):
                key = (item["pipeline"], item["root_subtype"], item["action"])
                self.stats[key] = (item["successes"], item["attempts"])
        except (json.JSONDecodeError, KeyError):
            pass

    def save(self, path: str | Path | None = None) -> None:
        p = path or self._path
        if p is None:
            return
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "stats": [
                {
                    "pipeline": k[0],
                    "root_subtype": k[1],
                    "action": k[2],
                    "successes": v[0],
                    "attempts": v[1],
                }
                for k, v in self.stats.items()
            ]
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record(self, pipeline: str, diagnosis: Diagnosis, plan: Plan, verify: VerificationResult) -> None:
        root = diagnosis.root_cause.subtype
        success = 1 if verify.healthy else 0
        for step in plan.steps:
            key = (pipeline, root, step.action)
            succ, attempt = self.stats.get(key, (0, 0))
            self.stats[key] = (succ + success, attempt + 1)
        if self._path is not None:
            self.save()

    def success_rate(self, pipeline: str, root_subtype: str, action: str) -> float:
        succ, att = self.stats.get((pipeline, root_subtype, action), (0, 0))
        return (succ / att) if att > 0 else 0.0