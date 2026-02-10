# agent_ai – SRE Agent for ML/Data Pipelines

An **SRE (Site Reliability Engineer) agent** that diagnoses pipeline failures, plans remediation, and executes steps with or without human approval. It targets ML/data pipeline reliability: root-cause diagnosis from logs and health checks, policy-gated plans, and verification.

## Features

- **Diagnose**: Uses logs, health checks, and DQ (data quality) to infer root cause (rule-based or LLM with Gemini).
- **Plan**: Produces a step-by-step remediation plan (rerun, backfill, scale memory, use cache, increase concurrency, open ticket, noop) with risk and cost.
- **Act**: Executes plan steps; high-risk or low-confidence steps can require human approval.
- **Verify**: Checks schema, DQ, and consecutive successes before closing the incident.
- **Memory**: Tracks success rates per (pipeline, root cause, action) to improve future plans.

Tools run in a **separate process** via stdio JSON-RPC; a **simulator** provides deterministic failure scenarios for development and eval.

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│  main/eval  │────▶│  SREAgent (diagnose → plan → act → verify)│
└─────────────┘     │  + PolicyEngine, IncidentMemory, RAG, LLM │
                    └─────────────────┬────────────────────────┘
                                      │ ToolHelpers
                                      ▼
                    ┌──────────────────────────────────────────┐
                    │  StdioJsonRpcClient → Tool Server (stdio)  │
                    │  Registry → SimulatorToolImpl → Simulator │
                    └──────────────────────────────────────────┘
```

## Setup

1. **Clone and install**

   ```bash
   pip install -r requirements.txt
   ```

2. **Optional: LLM**  
   Set `GEMINI_API_KEY` to use Gemini for diagnosis and planning; otherwise the agent uses rule-based diagnosis and planning.

## Running

- **Single scenario (interactive)**  
  Prompts for approval on high-risk steps unless `--auto_approve` is set:

  ```bash
  python -m src.app.main --scenario oom [--auto_approve] [--dry_run] [--audit_log path] [--config path] [--verify_until_healthy]
  ```

  Scenarios: `oom`, `missing_partition`, `schema_mismatch`, `null_spike`, `dependency_outage`, `sla_miss`. Use `--dry_run` to print steps without executing. Use `--config` for policy/memory path (YAML/JSON). Use `--verify_until_healthy` to loop verify with backoff.

- **Evaluation (all scenarios, auto-approve)**

  ```bash
  python -m src.app.eval [--report path] [--assert_diagnosis]
  ```

  Prints per-scenario success, diagnosis match vs scenario matrix, steps, risk, cost, and time. Use `--report` to write a JSON report. Use `--assert_diagnosis` to exit non-zero if any scenario’s diagnosis does not match `src/app/scenarios.yaml`.

## Runbooks and tools

- Runbooks live in `src/runbooks/` (e.g. `pipeline_runbook.md`). The agent can use a RAG over runbooks when provided via `SimpleRunbookRAG` (keyword retrieval; optional).
- Tools are defined in the stdio tool server (`src/tool_server_stdio/`) and invoked via `ToolHelpers`: `get_logs`, `rerun_pipeline`, `backfill`, `scale_memory`, `use_cache`, `increase_concurrency`, `verify_health`, `dq_check`, `consecutive_successes`. The server is started automatically by the client as a subprocess.

## Project layout

- `src/agent/` – SREAgent, policy, memory, models, LLM client and prompts
- `src/app/` – `main.py` (single scenario), `eval.py` (batch eval)
- `src/rag.py` – Simple runbook RAG (keyword overlap)
- `src/simulator/` – Pipeline simulator and failure scenarios
- `src/tool_api/` – Tool client (stdio JSON-RPC) and helpers
- `src/tool_registry/` – Tool specs and schemas
- `src/tool_server_stdio/` – Stdio tool server and simulator-backed impl
- `src/tool_server_mcp/` – MCP server (optional)
- `src/runbooks/` – Markdown runbooks

## License

See [LICENSE](LICENSE).
