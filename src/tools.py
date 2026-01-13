from __future__ import annotations
from typing import Dict, Any
from src.simulator import LocalPipelineSimulator

class Tools:
    def __init__(self, sim: LocalPipelineSimulator):
        self.sim = sim
    
    def get_logs(self, run_id: str) -> str:
        run = self.sim.runs[run_id]
        
        # fake logs
        if run.failure_reason == "oom":
            return "ERROR: CUDA out of memory / container killed (OOMKill)."
        if run.failure_reason == "missing_partition":
            return f"ERROR: partition {run.partition} not found in warehouse."
        if run.failure_reason == "schema_mismatch":
            return "ERROR: column <attr1> not found, but found <attr2>"
        
        return "INFO: run completed successfully"
    
    def rerun_pipeline(self, run_id: str) -> Dict[str, Any]:
        run = self.sim.rerun(run_id)
        return {"run_id": run_id, "status": run.status, "failure_reason": run.failure_reason}
    
    def backfill(self, partition: str) -> Dict[str, Any]:
        self.sim.backfill_partition(partition)
        return {"partition": partition, "backfilled": True}
    
    # def scale_memory(self, run_id: str, memory_mb: int) -> Dict[str, Any]:
    #     run = self.sim.scale_memory(run_id, memory_mb)
    #     return {"run_id": run.run_id, "memory_mb": run.memory_mb}
    def scale_memory(self, run_id: str, memory_mb: int) -> Dict[str, Any]:
        before = self.sim.runs[run_id].memory_mb
        run = self.sim.scale_memory(run_id, memory_mb)
        after = self.sim.runs[run_id].memory_mb
        print(f"[DEBUG] scale_memory: run_id={run_id} before={before} after={after}")
        return {"run_id": run.run_id, "memory_mb": run.memory_mb}
    
    def resolve_schema_issue(self) -> Dict[str, Any]:
        self.sim.fix_schema()
        return {"status": "schema_restored", "version":1}
        
    def verify_health(self, pipeline:str) -> Dict[str, Any]:
        checks = self.sim.health_check(pipeline)
        return {"pipeline": pipeline, "checks": checks}
        
        