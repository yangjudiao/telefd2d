# telefd2d Workflow Plan and Evidence

## Execution Mode
- Mode: optimize-and-run
- Prompt source: `prompt_0.docx`
- Stage order: `/init` -> `main`
- Execution date: 2026-02-25

## Step Plan (Plan-First)

| Step | Action | Acceptance Criteria (AC) | Status |
| --- | --- | --- | --- |
| S1 | Create/refresh governance and prompt files | AC-S1: `AGENTS.md`, `prompts/init_prompt.md`, `prompts/cli_prompt.md`, `prompts/optimized_prompt_package.md` exist and reference `telefd2d`. | Pass |
| S2 | Normalize naming and docs for public repo | AC-S2: `README.md` is bilingual and old repo name is not used as primary identity. | Pass |
| S3 | Produce runnable acceptance artifacts | AC-S3: `python scripts/run_acceptance_case.py --mode all --output-subdir forward_case_telefd2d` exits 0 and writes required media files. | Pass |
| S4 | Extract README-visible demo assets | AC-S4: `assets/topo_demo/wavefield_vx.gif`, `assets/topo_demo/wavefield_vz.gif`, `assets/topo_demo/surface_seismogram_vz.png` exist. | Pass |
| S5 | Git initialization and publish readiness | AC-S5: `git status` succeeds; if GitHub push is blocked, exact blocker + remediation commands are recorded. | Pass |

## Failure Handling Policy
- On failure, capture:
  - failed command
  - error output
  - root-cause hypothesis
  - at least one bounded retry/fallback attempt
- 429/rate-limit handling: exponential backoff `8s -> 16s -> 32s -> 64s`, max 5 retries, reduce concurrency to 1 after two consecutive 429s.

## Execution Log
- [S1] Created and refreshed governance + prompt package files:
  - `AGENTS.md`
  - `prompts/init_prompt.md`
  - `prompts/cli_prompt.md`
  - `prompts/optimized_prompt_package.md`
- [S2] Rewrote `README.md` for bilingual intro and demo-first display.
- [S2] Renamed user-facing benchmarking entry to `scripts/benchmark_speed_consistency.py`; kept compatibility shim `scripts/benchmark_prompt2_speed.py`.
- [S3] Ran command:
  - `python scripts/run_acceptance_case.py --mode all --backend boost_parallel --threads 14 --output-mode stream_to_disk --output-subdir forward_case_telefd2d --progress-step 200 --progress-sec 0.5`
- [S3] Result: pass; generated compute and postprocess artifacts in `output/forward_case_telefd2d/`.
- [S4] Copied demo assets into `assets/topo_demo/` for README visibility.
- [S5] Initialized git repository, committed on `main`, and pushed to GitHub:
  - `https://github.com/yangjudiao/telefd2d`
- [S5] Failure + retry evidence:
  - Failed command: initial `git commit` (missing `user.name` / `user.email`).
  - RCA: local git identity was not configured for this machine.
  - Fallback action: set repo-local identity and retried commit.
  - Retry command sequence:
    - `git config user.name \"yangjudiao\"`
    - `git config user.email \"yangjudiao@users.noreply.github.com\"`
    - `git commit -m \"...\"`
  - Retry result: pass.

## Evidence Paths
- Governance/prompt:
  - `AGENTS.md`
  - `prompts/init_prompt.md`
  - `prompts/cli_prompt.md`
  - `prompts/optimized_prompt_package.md`
- Runtime:
  - `output/forward_case_telefd2d/compute_metadata.json`
  - `output/forward_case_telefd2d/run_metadata.json`
  - `output/forward_case_telefd2d/wavefield_vx.gif`
  - `output/forward_case_telefd2d/wavefield_vz.gif`
  - `output/forward_case_telefd2d/surface_seismogram_vx.png`
  - `output/forward_case_telefd2d/surface_seismogram_vz.png`
- Demo assets:
  - `assets/topo_demo/wavefield_vx.gif`
  - `assets/topo_demo/wavefield_vz.gif`
  - `assets/topo_demo/surface_seismogram_vx.png`
  - `assets/topo_demo/surface_seismogram_vz.png`

## 2026-02-25 Update (Plane-Wave Emphasis + PML x2 Demo)
- Request:
  - highlight plane-wave incidence in project introduction,
  - replace displayed GIF/seismogram with doubled-PML case,
  - remove source-position mark from seismogram,
  - keep only one source line on GIF overlays,
  - add project license.
- Implementation:
  - Updated `README.md` intro and demo section for plane-wave emphasis and PML x2 case.
  - Added `--pml-z-scale` to `scripts/run_acceptance_case.py`, and produced `output/forward_case_telefd2d_pml2x/`.
  - Updated plotting logic in `src/fd_workflow/postprocess.py`:
    - removed source x-line from seismogram,
    - removed source point marker from GIF overlays, keeping source injection line only.
  - Replaced README assets with outputs from `forward_case_telefd2d_pml2x`.
  - Added `LICENSE` (MIT).
- Validation:
  - Command passed:
    - `python scripts/run_acceptance_case.py --mode all --backend boost_parallel --threads 14 --output-mode stream_to_disk --output-subdir forward_case_telefd2d_pml2x --pml-x-scale 2 --pml-z-scale 2 --progress-step 200 --progress-sec 0.5`
  - Metadata check:
    - baseline `nbx=122`, `nbz=41`
    - pml2x case `nbx=244`, `nbz=82`
