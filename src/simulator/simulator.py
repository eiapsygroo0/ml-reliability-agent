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
    use_cache: bool = False
    concurrency: int = 1
    
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
    
    # DQ knobs
    null_rate: float = 0.01
    row_count: int = 1_000_000
    # Dependency knob
    dependency_up: bool = True
    #performance knobs
    sla_seconds: int = 300
    last_runtime_seconds: int = 200
    backlog: int = 0
    
    def create_run(self, pipeline: str, stage: str) -> PipelineRun:
        run_id = str(uuid.uuid4())[:8]
        run = PipelineRun(run_id=run_id, pipeline=pipeline, stage=stage, status="failed")
        self.runs[run_id] = run
        return run
    
    def set_scenario(self, run_id: str, scenario: str) -> None:
        """
        Configure simulator state such that rerun(run_id) will exhibit the scenario.
        """
        run = self.runs[run_id]

        if scenario == "missing_partition":
            run.failure_reason = "missing_partition"
            run.partition = "2026-01-05"  # not present by default
        elif scenario == "oom":
            run.failure_reason = "oom"
            run.memory_mb = 512
        elif scenario == "schema_mismatch":
            run.failure_reason = "schema_mismatch"
            self.schema_version = 2
        elif scenario == "null_spike":
            run.failure_reason = "null_spike"
            self.null_rate = 0.65  # DQ fail
        elif scenario == "dependency_outage":
            run.failure_reason = "dependency_outage"
            self.dependency_up = False
        elif scenario == "sla_miss":
            run.failure_reason = "sla_miss"
            self.last_runtime_seconds = 800
            self.backlog = 50
            run.concurrency = 1
        else:
            run.failure_reason = scenario

        self.runs[run_id] = run  

    def backfill_partition(self, partition: str) -> None:
        self.available_partitions.add(partition)
        
        self.row_count = max(self.row_count, 900_000)
        self.null_rate = min(self.null_rate, 0.15)
        
    def scale_memory(self, run_id: str, memory_mb: int) -> None:
        self.runs[run_id].memory_mb = memory_mb
    
    def set_use_cache(self, run_id: str, enabled: bool) -> None:
        self.runs[run_id].use_cache = enabled
        if enabled:
            self.dependency_up = True
            self.null_rate = min(self.null_rate, 0.20)
            
    def set_concurrency(self, run_id: str, concurrency: int) -> None:
        self.runs[run_id].concurrency = concurrency
        # increase concurrency helps performance / backlog
        self.last_runtime_seconds = max(150, self.last_runtime_seconds // max(1, concurrency))
        self.backlog = max(0, self.backlog - 20*max(1, concurrency))
            
    def dq_check(self) -> Dict[str, bool]:
        return {
            "row_count_ok": self.row_count >= 100_000,
            "null_rate_ok": self.null_rate <= 0.20,
        }
    
    def consecutive_successes(self, pipeline: str, n: int = 2) -> int:
        run_list = [r for r in self.runs.values() if r.pipeline == pipeline]
        if not run_list:
            return 0
        consecutive = 0
        for r in reversed(run_list):
            if r.status == "success":
                consecutive += 1
                if consecutive >= n:
                    return consecutive
            else:
                break
        return consecutive
    
    def health_check(self) -> Dict[str, bool]:
        dq = self.dq_check()
        return {
            "schema_ok": (self.schema_version == 1),
            "dq_ok": all(dq.values())
        }
    
    def rerun(self, run_id: str) -> PipelineRun:
        prev = self.runs[run_id]
        run = PipelineRun(
            run_id=prev.run_id,
            pipeline=prev.pipeline,
            stage=prev.stage,
            status="success",
            failure_reason=None,
            memory_mb=prev.memory_mb,
            partition=prev.partition,
            use_cache=prev.use_cache,
            concurrency=prev.concurrency,
        )
        # schema failure
        if self.schema_version != 1:
            run.status = "failed"
            run.failure_reason = "schema_mismatch"

        # Data partition missing
        elif run.partition not in self.available_partitions:
            run.status = "failed"
            run.failure_reason = "missing_partition"

        # Infra OOM
        elif run.memory_mb < 1024 and run.stage in {"transform", "train"}:
            run.status = "failed"
            run.failure_reason = "oom"

        # Dependency outage (unless cache fallback enabled)
        elif (not self.dependency_up) and (not run.use_cache):
            run.status = "failed"
            run.failure_reason = "dependency_outage"

        # Data quality failure
        elif not all(self.dq_check().values()):
            run.status = "failed"
            run.failure_reason = "null_spike"

        # Performance/SLA (treat as "failed" if SLA breach is severe, else "degraded")
        elif self.last_runtime_seconds > self.sla_seconds and self.backlog > 10:
            # If concurrency is still 1, treat as failure; otherwise, consider recovered
            if run.concurrency <= 1:
                run.status = "failed"
                run.failure_reason = "sla_miss"
            else:
                # improved by concurrency
                run.status = "success"
                run.failure_reason = None
            
        self.runs[run_id] = run
        return run
        
