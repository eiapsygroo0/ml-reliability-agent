from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class GetLogsIn(BaseModel):
    run_id: str
    
class GetLogsOut(BaseModel):
    logs: str
    
class RerunIn(BaseModel):
    run_id: str
    
class RerunOut(BaseModel):
    run_id: str
    status: str
    failure_reason: Optional[str] = None
    
class BackfillIn(BaseModel):
    partition: str
    
class BackfillOut(BaseModel):
    partition: str
    backfilled: bool = True
    
class ScaleMemoryIn(BaseModel):
    run_id: str
    memory_mb: int
    
class ScaleMemoryOut(BaseModel):
    run_id: str
    memory_mb: int
    
class UseCacheIn(BaseModel):
    run_id: str
    enabled: bool = True
    
class UseCacheOut(BaseModel):
    run_id: str
    use_cache: bool
    
class IncreaseConcurrencyIn(BaseModel):
    run_id: str
    concurrency: int = Field(ge=1, le=64)
    
class IncreaseConcurrencyOut(BaseModel):
    run_id: str
    concurrency: int
    
class VerifyHealthIn(BaseModel):
    pipeline: str
    
class VerifyHealthOut(BaseModel):
    pipeline: str
    checks: Dict[str, bool]
    
class DqCheckIn(BaseModel):
    pipeline: str
    
class DqCheckOut(BaseModel):
    pipeline: str
    dq: Dict[str, bool]
    
class ConsecutiveIn(BaseModel):
    pipeline: str
    n: int = 2
    
class ConsecutiveOut(BaseModel):
    pipeline: str
    count: int