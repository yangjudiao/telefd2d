# telefd2d MCP Integration Guide

This guide explains how to run telefd2d through MCP so AI agents can call forward modeling with typed tool interfaces.

## 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

## 2. Start MCP server

```powershell
python scripts/run_mcp_server.py
```

Server transport is stdio. Configure your MCP client to launch the command above.

## 3. Exposed tools

### `telefd2d_summarize_project`
- Returns defaults, allowed enum values, and workflow notes.
- Use it first to let the agent discover constraints.

### `telefd2d_run_forward_case`
- Runs `scripts/run_acceptance_case.py` with typed parameters.
- Validates:
  - `mode` in `all|compute|postprocess`
  - `backend` in `baseline|boost_serial|boost_parallel`
  - `output_subdir` path-safe format (no traversal)
- Returns command, duration, stdout/stderr tails, quality summary, and generated outputs.

### `telefd2d_get_case_report`
- Reads output folder metadata for one case.
- Returns grid/PML/runtime summary and output file list.

### `telefd2d_list_cases`
- Lists recently modified `output/*` cases for discovery.

## 4. Recommended execution patterns

### Pattern A: Lightweight smoke test
Use small grid and baseline backend for fast checks.

```json
{
  "tool": "telefd2d_run_forward_case",
  "arguments": {
    "output_subdir": "forward_case_telefd2d_mcp_smoke",
    "mode": "all",
    "backend": "baseline",
    "threads": 1,
    "output_mode": "stream_to_disk",
    "width_km": 1.0,
    "depth_km": 1.0,
    "f0_hz": 20.0,
    "dx_m": 200.0,
    "dz_m": 200.0,
    "n_snapshots": 4
  }
}
```

### Pattern B: Production-like run
Use `boost_parallel` with explicit thread count and output naming.

```json
{
  "tool": "telefd2d_run_forward_case",
  "arguments": {
    "output_subdir": "forward_case_telefd2d_prod",
    "mode": "all",
    "backend": "boost_parallel",
    "threads": 14,
    "output_mode": "stream_to_disk",
    "pml_x_scale": 2.0,
    "pml_z_scale": 2.0
  }
}
```

## 5. Acceptance checks

- `telefd2d_run_forward_case` returns `ok: true`.
- `compute_metadata.json` exists in output case.
- `run_metadata.json` exists in output case for `mode=all`.
- `quality.boundary_energy_ratio` is present.
- `outputs` include wavefield GIF and seismogram files.

## 6. Troubleshooting

- `ModuleNotFoundError: mcp`
  - Re-run dependency install: `python -m pip install -r requirements.txt`.
- Boost backend build failure
  - Run `python scripts/build_fd_boost.py`.
  - For quick validation, switch backend to `baseline`.
- Bad output path
  - Keep `output_subdir` to letters/digits/`._-`, max 80 chars.

