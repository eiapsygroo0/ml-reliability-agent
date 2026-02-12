# SRE Agent for ML/Data Pipelines

An **SRE (Site Reliability Engineer) agent** that diagnoses pipeline failures, plans remediation, and executes steps with or without human approval. It targets ML/data pipeline reliability: root-cause diagnosis from logs and health checks, policy-gated plans, and verification.

## What this demonstrates

- **Agent loop**: Diagnose → Plan → Act → Verify with a single entrypoint (main or eval).
- **Dual strategy**: Rule-based and LLM (Gemini) with fallback so behavior is predictable without an API key.
- **Policy-gated execution**: Approval required by risk, confidence, and category (e.g. code changes).
- **Tool abstraction**: One registry drives both stdio JSON-RPC and MCP; tools run in a separate process.
- **Deterministic eval**: Six failure scenarios with expected diagnosis matrix and optional regression check in CI.
- **Optional RAG**: Keyword retrieval over runbooks when building plans.

Designed so a real pipeline backend can be plugged in via the same tool interface; this repo uses a **simulator** only.

## Features

- **Diagnose**: Uses logs, health checks, and DQ (data quality) to infer root cause (rule-based or LLM with Gemini).
- **Plan**: Produces a step-by-step remediation plan (rerun, backfill, scale memory, use cache, increase concurrency, open ticket, noop) with risk and cost.
- **Act**: Executes plan steps; high-risk or low-confidence steps can require human approval.
- **Verify**: Checks schema, DQ, and consecutive successes before closing the incident.
- **Memory**: Tracks success rates per (pipeline, root cause, action) to improve future plans.

Tools run in a **separate process** via stdio JSON-RPC; a **simulator** provides deterministic failure scenarios for development and eval.

## Architecture

```
┌─────────────┐     ┌───────────────────────────────────────────┐
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

## Quick start

Tested with Python 3.11.

```bash
pip install -r requirements.txt
python -m src.app.main --scenario oom --auto_approve
```

You should see panels for Diagnosis, Plan, and Verification. To run all scenarios and write a report:

```bash
python -m src.app.eval --report eval_report.json
```

## Setup

1. **Clone and install**

   ```bash
   pip install -r requirements.txt
   ```

2. **Optional: LLM**  
   Set `GEMINI_API_KEY` to use Gemini for diagnosis and planning; otherwise the agent uses rule-based diagnosis and planning.

3. **Optional: RAGEngine** (hybrid retrieval + rerank + Gemini in `src.rag`)  
   Install the optional deps listed in `requirements.txt` (numpy, faiss-cpu, rank-bm25; sentence-transformers is already optional above). Set `GEMINI_API_KEY`. RAGEngine expects pre-built `index.faiss` and `chunks.npy` in the working directory (or pass `index_path` / `meta_path` to `RAGEngine(...)`).

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

## Testing

- **Unit and integration tests** (pytest):

  ```bash
  pytest tests/ -v
  ```

- **Evaluation** (all scenarios, diagnosis regression):

  ```bash
  python -m src.app.eval --assert_diagnosis
  ```

  CI runs both; `--assert_diagnosis` fails the build if any scenario’s diagnosis does not match `src/app/scenarios.yaml`.

## Evaluation / Results

The eval report (e.g. `eval_report.json`) contains `success_rate`, `diagnosis_match_rate`, `avg_steps`, `avg_cost_units`, `avg_seconds`, and per-scenario results. **Success** means verification passed (schema + DQ + consecutive successes) after the agent’s plan. Sample: diagnosis match 100% across scenarios; see `eval_report.json` in the repo.

## Runbooks and tools

- Runbooks live in `src/runbooks/` (e.g. `pipeline_runbook.md`). The agent can use a RAG over runbooks when provided via `SimpleRunbookRAG` (keyword retrieval; optional).
- Tools are defined in the stdio tool server (`src/tool_server_stdio/`) and invoked via `ToolHelpers`: `get_logs`, `rerun_pipeline`, `backfill`, `scale_memory`, `use_cache`, `increase_concurrency`, `verify_health`, `dq_check`, `consecutive_successes`. The server is started automatically by the client as a subprocess.

## Project layout

- `src/agent/` – SREAgent, policy, memory, models, LLM client and prompts
- `src/app/` – `main.py` (single scenario), `eval.py` (batch eval), `scenarios.yaml` (expected diagnosis matrix)
- `src/rag.py` – Runbook RAG: `SimpleRunbookRAG` (keyword), `EmbeddingRunbookRAG` (optional embeddings), and optional `RAGEngine` (hybrid + rerank + Gemini; see Setup)
- `src/simulator/` – Pipeline simulator and failure scenarios
- `src/tool_api/` – Tool client (stdio JSON-RPC) and helpers
- `src/tool_registry/` – Tool specs and schemas (single source for stdio and MCP)
- `src/tool_server_stdio/` – Stdio tool server and simulator-backed impl
- `src/tool_server_mcp/` – MCP server (optional; same tools via FastMCP)
- `src/runbooks/` – Markdown runbooks
- `tests/` – Unit tests (policy, memory, agent, registry) and one integration test
- `ARCHITECTURE.md` – Data flow and design choices

## License

See [LICENSE](LICENSE).
