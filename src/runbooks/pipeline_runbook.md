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

## null_spike
Symptoms:
- DQ_FAIL or high null rate in data
- Downstream checks fail on completeness

Actions:
1. Enable cached fallback data if available to unblock.
2. Rerun once upstream data is fixed.
3. Open ticket for data quality / upstream fix if persistent.

## dependency_outage
Symptoms:
- Timeout or 5xx from external dependency
- Dependency down or rate limited

Actions:
1. Enable use_cache for the run to fall back to cached data.
2. Rerun the pipeline after cache is used.
3. Monitor dependency status; open ticket if prolonged.

## sla_miss
Symptoms:
- SLA breach, backlog building, slow runtime

Actions:
1. Increase concurrency for the pipeline to process backlog.
2. Rerun the job with higher concurrency.
3. Verify runtime and backlog decrease.
