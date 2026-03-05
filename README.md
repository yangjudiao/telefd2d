[Switch to Chinese](README_ZH.md)

# telefd2d

telefd2d is a 2D staggered-grid elastic finite-difference (FD/FDM) seismic wave propagation toolkit for rugged topography and near-surface geophysics.

Search keywords: telefd2d, seismic, seismology, 2D elastic wave, finite difference, staggered grid, wave propagation, topography, CPML, geophysics.
Repository: https://github.com/yangjudiao/telefd2d

## Demo Gallery (PML x2 Case)

This gallery uses a case with doubled PML thickness in both x and z directions (`--pml-x-scale 2 --pml-z-scale 2`).

### Wavefield Vx
![Wavefield Vx](assets/topo_demo/wavefield_vx.gif)

### Wavefield Vz
![Wavefield Vz](assets/topo_demo/wavefield_vz.gif)

### Surface Seismogram Vx
![Surface Seismogram Vx](assets/topo_demo/surface_seismogram_vx.png)

### Surface Seismogram Vz
![Surface Seismogram Vz](assets/topo_demo/surface_seismogram_vz.png)

## Core Features

- Staggered-grid elastic FD solver built for 2D near-surface and regional-scale experiments.
- Topography-aware free-surface treatment through parameter-modified medium handling.
- CPML-style absorbing boundaries with tunable reflectivity, power, and kappa parameters.
- Multiple compute backends: baseline Python, C++ serial, and C++ OpenMP parallel.
- Decoupled workflow: run compute first, then postprocess independently.
- Streaming output mode for snapshots and seismograms to reduce resident memory pressure.
- Reproducible metadata and artifact layout for benchmarking and regression checks.

## Technical Route

### 1. Governing Equations and Discretization
telefd2d uses the first-order velocity-stress elastic wave equations on a staggered grid. This arrangement gives stable and efficient coupling between stress and velocity updates, and remains a reliable baseline for heterogeneous media.

### 2. Rugged Topography and Free Surface
The rugged top boundary is represented on a discrete grid and handled with a parameter-modified (PM) strategy. Instead of rewriting boundary logic at every time step, medium parameters around topography boundary points are prepared before time marching and then used in the regular update loop.

### 3. Absorbing Boundary Strategy
Left, right, and bottom sides use CPML-style absorption. The implementation is parameterized (`pml_reflect_coeff`, `pml_power`, `pml_kappa_max`, and scale factors) so users can tune boundary behavior for different frequencies, incidence angles, and domain sizes.

### 4. Source and Acquisition Abstraction
The solver supports physically interpretable source controls (for example Ricker wavelets and incident-wave setup) and surface receiver extraction. This keeps scenario definition explicit and reproducible.

### 5. Compute Pipeline
The compute stage writes raw arrays and metadata (`compute_metadata.json`) and can run in memory or streaming-to-disk mode. This design allows large runs to stay tractable on workstation-class hardware.

### 6. Postprocess Pipeline
The postprocess stage reads saved raw outputs and generates derived fields (`p`, `curl`), wavefield GIFs, and seismograms. Since it is decoupled, visualization can be re-generated without re-running the full solver.

### 7. Validation and Performance Loop
Benchmark scripts separate three concerns: memory behavior, runtime speed, and output consistency. This keeps optimization measurable and prevents accidental regressions when changing numerical kernels or runtime settings.

## Quick Start

### 1) Install dependencies
```powershell
python -m pip install -r requirements.txt
```

### 2) Build the accelerated extension (recommended)
```powershell
python scripts/build_fd_boost.py
```

### 3) Run a standard acceptance case
```powershell
python scripts/run_acceptance_case.py --mode all --backend boost_parallel --threads 14 --output-mode stream_to_disk --output-subdir forward_case_telefd2d --progress-step 200 --progress-sec 0.5
```

### 4) Run the doubled-PML gallery case
```powershell
python scripts/run_acceptance_case.py --mode all --backend boost_parallel --threads 14 --output-mode stream_to_disk --output-subdir forward_case_telefd2d_pml2x --pml-x-scale 2 --pml-z-scale 2 --progress-step 200 --progress-sec 0.5
```

## MCP Integration (AI-Callable Workflow)

telefd2d now provides an MCP server so AI agents can call forward modeling through typed tools instead of brittle shell-only prompts.

### 1) Start MCP server
```powershell
python scripts/run_mcp_server.py
```

### 2) Main MCP tools
- `telefd2d_summarize_project`
- `telefd2d_run_forward_case`
- `telefd2d_get_case_report`
- `telefd2d_list_cases`

### 3) Run a lightweight smoke test
```powershell
python scripts/mcp_smoke_test.py --backend baseline
```

### 4) MCP documentation
- Decision record: `docs/mcp_decision.md`
- Integration guide with examples: `docs/mcp_integration.md`

## Repository Structure

- `src/fd_workflow/`: solver, model, and postprocess modules.
- `src/telefd2d_mcp/`: MCP adapter layer for AI tool invocation.
- `scripts/run_acceptance_case.py`: main workflow entry.
- `scripts/run_mcp_server.py`: stdio MCP server entrypoint.
- `scripts/mcp_smoke_test.py`: lightweight end-to-end MCP validation script.
- `scripts/benchmark_streaming.py`: memory/streaming benchmark.
- `scripts/benchmark_speed_consistency.py`: speed and consistency benchmark.
- `assets/topo_demo/`: media shown in documentation.
- `output/`: run artifacts.
- `docs/`: workflow notes and reports.

## References

1. Virieux, J. (1986). *P-SV wave propagation in heterogeneous media; velocity-stress finite-difference method*. Geophysics, 51(4), 889-901. https://doi.org/10.1190/1.1442147
2. Komatitsch, D., and Martin, R. (2007). *An unsplit convolutional perfectly matched layer improved at grazing incidence for the seismic wave equation*. Geophysics, 72(5), SM155-SM167. https://doi.org/10.1190/1.2757586
3. Cao, J., and Chen, J.-B. (2018). *A parameter-modified method for implementing surface topography in elastic-wave finite-difference modeling*. Geophysics, 83(6), T313-T332. https://doi.org/10.1190/GEO2018-0098.1

## License

This project is licensed under the MIT License. See `LICENSE`.
