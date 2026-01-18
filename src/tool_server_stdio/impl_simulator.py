from __future__ import annotations
from src.simulator.simulator import LocalPipelineSimulator
from src.tool_registry import schema as S

class SimulatorToolImpl:
    def __init__(self, sim: LocalPipelineSimulator):
        self.sim = sim
        
    def get_logs(self, req: S.GetLogsIn) -> S.GetLogsOut:
        run = self.sim.runs[req.run_id]
        fr = run.failure_reason
        
        if fr == "oom":
            return S.GetLogsOut(logs="ERROR: OOMKill / out of memory.")
        if fr == "missing_partition":
            return S.GetLogsOut(logs=f"ERROR: partition {run.partition} not found.")
        if fr == "schema_mismatch":
            return S.GetLogsOut(logs="ERROR: schema mismatch; column rename detected.")
        if fr == "dependency_outage":
            return S.GetLogsOut(logs="ERROR: dependency timeout / 5xx responses (dependency_down).")
        if fr == "null_spike":
            return S.GetLogsOut(logs=f"ERROR: DQ_FAIL null_rate={self.sim.null_rate:.2f}")
        if fr == "sla_miss":
            return S.GetLogsOut(logs=f"ERROR: SLA breach runtime={self.sim.last_runtime_seconds}s backlog={self.sim.backlog}")
        if run.status == "success":
            return S.GetLogsOut(logs="INFO: run completed successfully.")
        return S.GetLogsOut(logs="ERROR: unknown failure.")
    
    def rerun_pipeline(self, req: S.RerunIn) -> S.RerunOut:
        r = self.sim.rerun(req.run_id)
        return S.RerunOut(run_id=r.run_id, status=r.status, failure_reason=r.failure_reason)
    
    def backfill(self, req: S.BackfillIn) -> S.BackfillOut:
        r = self.sim.backfill_partition(req.partition)
        return S.BackfillOut(partition=req.partition, backfilled=True)
    
    def scale_memory(self, req: S.ScaleMemoryIn) -> S.ScaleMemoryOut:
        self.sim.scale_memory(req.run_id, req.memory_mb)
        return S.ScaleMemoryOut(run_id=req.run_id, memory_mb=req.memory_mb)
    
    def use_cache(self, req: S.UseCacheIn) -> S.UseCacheOut:
        self.sim.set_use_cache(req.run_id, req.enabled)
        run = self.sim.runs[req.run_id]
        return S.UseCacheOut(run_id=req.run_id, use_cache=run.use_cache)
    
    def increase_concurrency(self, req: S.IncreaseConcurrencyIn) -> S.IncreaseConcurrencyOut:
        self.sim.set_concurrency(req.run_id, req.concurrency)
        run = self.sim.runs[req.run_id]
        return S.IncreaseConcurrencyOut(run_id=req.run_id, concurrency=run.concurrency)

    def verify_health(self, req: S.VerifyHealthIn) -> S.VerifyHealthOut:
        checks = self.sim.health_check()
        return S.VerifyHealthOut(pipeline=req.pipeline, checks=checks)

    def dq_check(self, req: S.DqCheckIn) -> S.DqCheckOut:
        return S.DqCheckOut(pipeline=req.pipeline, dq=self.sim.dq_check())

    def consecutive_successes(self, req: S.ConsecutiveIn) -> S.ConsecutiveOut:
        count = self.sim.consecutive_successes(req.pipeline, n=req.n)
        return S.ConsecutiveOut(pipeline=req.pipeline, count=count)       