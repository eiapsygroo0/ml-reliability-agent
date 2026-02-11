# Architecture

## Overview

agent_ai is an SRE agent for ML/data pipelines: it diagnoses failures, plans remediation, and executes steps with optional human approval. Tools run in a separate process; a simulator provides deterministic scenarios for development and evaluation.

## Data flow

```
Incident (run_id, pipeline, stage, symptom)
    → diagnose (logs, health, DQ) → Diagnosis (root_cause, notes)
    → plan (incident, diagnosis)   → Plan (steps, risk, cost)
    → act (plan)                  → step results
    → verify (pipeline)           → VerificationResult (healthy, checks)
    → finalize (memory record)
```

- **Diagnose**: Fetches logs and optionally health/DQ; uses LLM (if configured) or rule-based logic to produce a `Diagnosis` (root cause category, subtype, confidence).
- **Plan**: Builds a `Plan` (list of `PlanStep` with tool, action, args, risk, cost). Policy sets `approval_required` on each step; high-risk or low-confidence steps require human approval before execution.
- **Act**: Executes steps via `ToolHelpers` (stdio RPC or MCP); records outcomes for audit.
- **Verify**: Checks schema, DQ, and consecutive successes; `healthy` is true only if all pass.
- **Finalize**: Records (pipeline, diagnosis, plan, verify) in `IncidentMemory` for success-rate tracking.

## Diagram

```
┌─────────────┐     ┌───────────────────────────────────────────┐
│  main/eval  │────▶│  SREAgent (diagnose → plan → act → verify)  │
└─────────────┘     │  + PolicyEngine, IncidentMemory, RAG, LLM   │
                   └─────────────────┬────────────────────────────┘
                                     │ ToolHelpers
                                     ▼
                   ┌────────────────────────────────────────────┐
                   │  StdioJsonRpcClient → Tool Server (stdio)   │
                   │  Registry → SimulatorToolImpl → Simulator   │
                   └────────────────────────────────────────────┘
```

## Design choices

1. **Tools in a separate process**: The agent talks to tools via JSON-RPC over stdio (or MCP). The tool server holds simulator state; the agent stays stateless and transport-agnostic via `ToolClient` and `ToolHelpers`.

2. **Policy returns a new plan**: `PolicyEngine.apply(plan, diagnosis)` returns a new `Plan` with `approval_required` set on each step (via `model_copy`). The original plan is not mutated, which avoids surprises if the same plan is reused or cached.

3. **Single tool definition list**: Tool names, descriptions, and input/output schemas live in `tool_registry` (`get_tool_definitions()`). Both the stdio server and the MCP server use this list; the stdio server uses `build_registry(impl)`, and the MCP server registers tools from the same registry via `make_mcp_callable(spec, reg)`. Adding a new tool requires one entry in the registry and one handler on the implementation.

4. **Rule-based fallback**: When the LLM is not configured or raises, diagnosis and planning fall back to `_diagnose_from_rules` and `_build_plan_from_rules`. Behavior is deterministic and testable without an API key.
