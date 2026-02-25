# Project AGENTS Rules (telefd2d)

## Project Identity
- Repository name: `telefd2d`
- Source project alias: `myfd_topo_boost`
- This repository is the cleaned, publish-ready version for public GitHub delivery.

## Scope
- Organize the 2D staggered-grid elastic FD project with rugged topography support into a standalone repository.
- Keep the existing physics workflow intact (free-surface topography, absorbing boundaries, plane-wave injection).
- Keep compute and postprocess decoupled.
- Ensure README is bilingual (Chinese + English).
- Ensure project intro shows one topo demo including:
  - `vx` GIF
  - `vz` GIF
  - seismogram figure(s)

## Mandatory Execution Contract
- Plan first, execute second.
- Every execution step must define measurable acceptance criteria.
- On failure, perform RCA and at least one bounded retry/fallback.
- Maximum parallel subagents: 2.
- Stage order is fixed:
  1. `/init` stage prompt
  2. main CLI stage prompt

## Naming and Consistency
- Use `telefd2d` as public-facing project name in docs and workflow files.
- Avoid legacy naming (`prompt_1`, `prompt_2`) in user-facing docs unless explicitly used as historical context.
- Keep module/package internals stable unless a rename is required for correctness.

## Required Deliverables
- Rules and prompts:
  - `AGENTS.md`
  - `prompts/init_prompt.md`
  - `prompts/cli_prompt.md`
  - `prompts/optimized_prompt_package.md`
- Execution plan/evidence:
  - `docs/workflow_plan.md`
- Publish-ready documentation:
  - `README.md` (bilingual)
- Demo artifacts for README:
  - `assets/topo_demo/wavefield_vx.gif`
  - `assets/topo_demo/wavefield_vz.gif`
  - `assets/topo_demo/surface_seismogram_vx.png`
  - `assets/topo_demo/surface_seismogram_vz.png`

## Validation Gates
- `scripts/run_acceptance_case.py --mode all --output-subdir forward_case_telefd2d` succeeds.
- Demo assets exist and are referenced by README.
- `README.md` includes clear setup/run commands and output locations.
- Repository is initialized as git and ready to push to GitHub.
