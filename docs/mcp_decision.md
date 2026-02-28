# telefd2d MCP Decision Record

## Context
- Goal from `prompt_0.docx`: let AI agents quickly and safely run telefd2d forward modeling.
- Existing state: telefd2d already has a stable CLI workflow (`scripts/run_acceptance_case.py`) with machine-readable metadata outputs.
- Need: lower agent integration cost while preserving existing solver behavior and reproducibility.

## Options Evaluated

### Option A: Build an MCP server on top of existing workflow runner
- Pros:
  - Native fit for AI tooling ecosystems that already speak MCP.
  - Keeps current solver and scripts unchanged as the execution core.
  - Supports structured, typed tool contracts with explicit parameter validation.
  - Easy to expose high-value operations: run case, query metadata, list outputs.
- Cons:
  - Adds one dependency (`mcp`) and one thin integration layer.

### Option B: Build REST API only
- Pros:
  - Familiar for web integrations.
  - Good for remote orchestration.
- Cons:
  - AI clients still need custom API adapters.
  - Requires additional service lifecycle management and auth surface.
  - Duplicates intent of MCP tool protocol for this use case.

### Option C: Prompt-only wrapper (no protocol/service)
- Pros:
  - Minimal code changes.
- Cons:
  - Fragile and non-typed.
  - Harder to enforce argument constraints and deterministic output contracts.
  - Poor interoperability across AI clients.

## Decision
- Adopt **Option A (MCP server)** as the primary integration path.
- Keep existing CLI workflow as the execution engine for backward compatibility.
- Provide a lightweight smoke-test path with small-scale parameters for quick verification.

## Decision Drivers
- Fastest path to AI-callable integration with low regression risk.
- Structured input/output and deterministic artifacts (`compute_metadata.json`, `run_metadata.json`).
- Minimal invasive changes to numerical core.

## Consequences
- New module: `src/telefd2d_mcp/server.py`.
- New entrypoint: `scripts/run_mcp_server.py`.
- New validation helper: `scripts/mcp_smoke_test.py`.
- Documentation updates for MCP onboarding and tool-level usage.

