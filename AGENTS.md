# Project AGENTS Rules (telefd2d)

## Project Identity
- Repository name: `telefd2d`
- Primary objective: 2D elastic-wave FD forward modeling for topography scenarios.
- New integration objective: expose AI-callable workflows through MCP.

## Scope
- Keep numerical behavior and existing workflow stable:
  - free-surface topography handling,
  - CPML absorbing boundaries,
  - decoupled compute and postprocess stages.
- Add an MCP adapter so AI agents can invoke forward modeling safely.
- Keep user documentation clear in both Chinese and English.

## Mandatory Execution Contract
- Plan first, execute second.
- Every execution step must define measurable acceptance criteria (AC).
- On failure, provide RCA and run at least one bounded retry or fallback.
- Maximum parallel subagents: 2.
- Stage order remains:
  1. `/init` stage prompt
  2. main CLI stage prompt

## Naming and Consistency
- Public project name is always `telefd2d`.
- MCP-facing tool names must use `telefd2d_*` prefix.
- Keep internal package `fd_workflow` stable unless correctness requires changes.

## Required Deliverables
- Governance and prompt package:
  - `AGENTS.md`
  - `prompts/init_prompt.md`
  - `prompts/cli_prompt.md`
  - `prompts/optimized_prompt_package.md`
- MCP implementation:
  - `src/telefd2d_mcp/server.py`
  - `scripts/run_mcp_server.py`
  - `scripts/mcp_smoke_test.py`
- Documentation:
  - `docs/mcp_decision.md`
  - `docs/mcp_integration.md`
  - `docs/workflow_plan.md`
  - `README.md`, `README_EN.md`, `README_ZH.md`

## Validation Gates
- `python scripts/mcp_smoke_test.py --backend baseline` succeeds.
- MCP tools can:
  - summarize project capabilities,
  - run one forward case,
  - report output metadata.
- Smoke test output contains:
  - `compute_metadata.json`
  - `run_metadata.json`
  - wavefield and seismogram outputs.
- README family documents include MCP quick start and usage examples.
