from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import uuid

@dataclass
class PipelineRun:
    run_id: str
    pipeline: str
    stage: str
    status: str
    failure_reason: Optional[str] = None
    memory_mb: int = 1024
    partition: str = "2026-01-01"
    
@dataclass
class LocalPipelineSimulator:
    """
    a fake pipeline system that can fail for kwown reasons.
    Tools will operate on this state(rerun, backfill, scale).
    """
    runs: Dict[str, PipelineRun] = field(default_factory=dict)
    
    # knobs to simulate environment
    available_partitions: set[str] = field(default_factory=lambda: {"2026-01-01"})
    schema_version: int = 1 # 1 = expected, 2 = breaking change
    
    def create_failed_run(self, pipeline: str, stage: str, failure_reason: str) -> PipelineRun:
        run_id = str(uuid.uuid4())[:8]
        run = PipelineRun(run_id=run_id, pipeline=pipeline, stage=stage, status="failed", failure_reason=failure_reason)
        self.runs[run_id] = run
        return run
        
    def rerun(self, run_id: str) -> PipelineRun:
        run = self.runs[run_id]

        # Reset status only, keep resources & config
        run.status = "success"
        run.failure_reason = None

        # Re-evaluate failure modes using CURRENT state
        if self.schema_version != 1:
            run.status = "failed"
            run.failure_reason = "schema_mismatch"
        elif run.partition not in self.available_partitions:
            run.status = "failed"
            run.failure_reason = "missing_partition"
        elif run.memory_mb < 1024:
            if run.stage in {"transform", "train"}:
                run.status = "failed"
                run.failure_reason = "oom"

        self.runs[run_id] = run
        return run

    def backfill_partition(self, partition: str) -> None:
        self.available_partitions.add(partition)
        
    def scale_memory(self, run_id: str, memory_mb: int) -> PipelineRun:
        run = self.runs[run_id]
        run.memory_mb = memory_mb
        self.runs[run_id] = run
        return run
    
    def fix_schema(self) -> None:
        self.schema_version = 1
        
    def health_check(self, pipeline:str) -> Dict[str, bool]:
        recent = [r for r in self.runs.values() if r.pipeline==pipeline]
        ok_runs = any(r.status == "success" for r in recent)
        no_schema_break = (self.schema_version == 1)    
        return {"recent_success": ok_runs, "schema_ok": no_schema_break}