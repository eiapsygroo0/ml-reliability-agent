# Pipeline Runbook

## missing_partition
Symptoms:
- Task fails saying partition not found
- Downstream tables empty for the day

Actions:
1. Backfill the missing partition for the affected date.
2. Rerun the failed task / pipeline.
3. Verify row counts and downstream freshness checks.

## oom
Symptoms:
- OOMKill in Kubernetes
- "CUDA out of memory" or container killed

Actions:
1. Increase memory limit for the job OR reduce batch size.
2. Rerun the job.
3. Verify memory usage trend and job success.

## schema_mismatch
Symptoms:
- Column missing / renamed
- Type mismatch in transform

Actions:
1. Identify upstream schema change (diff).
2. Apply a schema adapter or update transform mappings.
3. Consider temporary fallback to previous schema version if available.
4. Escalate if production impact is high.
