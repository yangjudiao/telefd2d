from __future__ import annotations

import argparse
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fd_workflow.config import SimulationConfig, auto_grid_from_frequency
from fd_workflow.model import build_pm_medium_parameters, build_surface_topography, build_uniform_model
from fd_workflow.postprocess import boundary_energy_ratio
from fd_workflow.solver import run_fd_plane_wave
from fd_workflow.wavelet import make_scaled_ricker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune PML parameters for selected backend.")
    parser.add_argument(
        "--backend",
        choices=["baseline", "boost_serial", "boost_parallel"],
        default="boost_parallel",
    )
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--width-km", type=float, default=100.0)
    parser.add_argument("--depth-km", type=float, default=40.0)
    parser.add_argument("--topo-amplitude-km", type=float, default=5.0)
    parser.add_argument("--topo-mean-depth-km", type=float, default=5.0)
    parser.add_argument("--topo-cycles", type=float, default=4.0)
    parser.add_argument("--nt-scale", type=float, default=0.35)
    parser.add_argument("--output-subdir", type=str, default="forward_case_telefd2d")
    return parser.parse_args()


def ensure_boost_solver_module() -> object:
    import fd_workflow.solver_boost as solver_boost

    if not solver_boost.extension_available():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_fd_boost.py")], cwd=str(ROOT))
        solver_boost = importlib.reload(solver_boost)

    if not solver_boost.extension_available():
        raise RuntimeError("C++ extension build failed. Cannot run boost backend.")

    return solver_boost


def run_case(
    backend: str,
    threads: int,
    cfg: SimulationConfig,
    grid,
    pm,
    p0s: np.ndarray,
    wavelet: np.ndarray,
    source_z_idx: int,
    candidate: dict[str, float],
) -> dict[str, np.ndarray]:
    kwargs = dict(
        bx=pm.bx,
        bz=pm.bz,
        mu_xz=pm.mu_xz,
        eta_xx_x=pm.eta_xx_x,
        eta_xx_z=pm.eta_xx_z,
        eta_zz_x=pm.eta_zz_x,
        eta_zz_z=pm.eta_zz_z,
        receiver_idx=pm.receiver_idx,
        p0s=p0s,
        wav=wavelet,
        ifleft=0,
        fp=cfg.f0_hz,
        pml_velocity=cfg.vp_m_s,
        dx=grid.dx_m,
        dz=grid.dz_m,
        dt=grid.dt_s,
        nbx=grid.nbx,
        nbz=grid.nbz,
        source_z_idx=source_z_idx,
        n_snapshots=24,
        pml_reflect_coeff=candidate["reflect_coeff"],
        pml_power=int(candidate["power"]),
        pml_kappa_max=candidate["kappa_max"],
    )

    if backend == "baseline":
        return run_fd_plane_wave(**kwargs)

    solver_boost = ensure_boost_solver_module()
    n_threads = 1 if backend == "boost_serial" else max(1, int(threads))
    return solver_boost.run_fd_plane_wave_boost(**kwargs, n_threads=n_threads)


def main() -> None:
    args = parse_args()

    cfg = replace(
        SimulationConfig(),
        width_km=float(args.width_km),
        depth_km=float(args.depth_km),
        topo_amplitude_km=float(args.topo_amplitude_km),
        topo_mean_depth_km=float(args.topo_mean_depth_km),
        topo_cycles=float(args.topo_cycles),
    )
    grid = auto_grid_from_frequency(cfg)
    vp, vs, rho = build_uniform_model(cfg, grid)
    surface_idx = build_surface_topography(cfg, grid)
    pm = build_pm_medium_parameters(cfg, grid, vp, vs, rho, surface_idx)

    p0 = np.sin(np.deg2rad(cfg.angle_from_z_deg)) / (cfg.vp_m_s / 1_000.0)
    p0s = np.full(grid.nx_total, p0, dtype=np.float64)

    nt_tune = max(600, int(float(args.nt_scale) * grid.nt))
    wavelet = make_scaled_ricker(cfg.f0_hz, nt_tune, grid.dt_s, cfg.source_scale)
    source_z_idx = max(surface_idx.max() + 8, grid.nz_phys - grid.nbz - cfg.source_depth_margin_cells)
    source_z_idx = int(min(source_z_idx, grid.nz_phys - cfg.source_depth_margin_cells))

    candidates = [
        {"reflect_coeff": 1.0e-6, "power": 2, "kappa_max": 1.0},
        {"reflect_coeff": 1.0e-7, "power": 2, "kappa_max": 1.0},
        {"reflect_coeff": 1.0e-7, "power": 2, "kappa_max": 1.3},
        {"reflect_coeff": 1.0e-8, "power": 3, "kappa_max": 1.3},
    ]

    records: list[dict[str, float]] = []
    for idx, cand in enumerate(candidates, start=1):
        print(f"[{idx}/{len(candidates)}] testing {cand} via {args.backend}")
        start = time.time()
        result = run_case(args.backend, args.threads, cfg, grid, pm, p0s, wavelet, source_z_idx, cand)
        ratio = boundary_energy_ratio(result["snap_vz"], grid)
        runtime_s = time.time() - start
        records.append(
            {
                "backend": args.backend,
                "threads": float(1 if args.backend != "boost_parallel" else max(1, args.threads)),
                "reflect_coeff": cand["reflect_coeff"],
                "power": float(cand["power"]),
                "kappa_max": cand["kappa_max"],
                "boundary_energy_ratio": ratio,
                "runtime_s": runtime_s,
            }
        )

    records.sort(key=lambda x: x["boundary_energy_ratio"])
    best = records[0]

    output_subdir = args.output_subdir.strip() or default_output_subdir(args.backend)
    output_dir = ROOT / "output" / output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pml_tuning_results.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    lines = [
        "# PML Tuning Report",
        "",
        "Short-run tuning was executed before final full forward modeling.",
        "",
        f"- Backend: `{args.backend}`",
        f"- Threads: `{1 if args.backend != 'boost_parallel' else max(1, args.threads)}`",
        f"- Tune run nt: `{nt_tune}`",
        f"- Grid: `{grid.nx_total} x {grid.nz_total}`",
        f"- Target domain (no PML): `{cfg.width_km} km x {cfg.depth_km} km`",
        "",
        "## Candidates",
        "",
        "| backend | threads | reflect_coeff | power | kappa_max | boundary_energy_ratio | runtime_s |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in records:
        lines.append(
            f"| {r['backend']} | {int(r['threads'])} | {r['reflect_coeff']:.1e} | {int(r['power'])} | "
            f"{r['kappa_max']:.2f} | {r['boundary_energy_ratio']:.6e} | {r['runtime_s']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Final Choice",
            "",
            f"- `reflect_coeff={best['reflect_coeff']:.1e}`",
            f"- `power={int(best['power'])}`",
            f"- `kappa_max={best['kappa_max']:.2f}`",
            f"- Best boundary-energy ratio: `{best['boundary_energy_ratio']:.6e}`",
            "",
            "This selected set can be passed into `scripts/run_acceptance_case.py` via:",
            f"- `--pml-reflect-coeff {best['reflect_coeff']:.1e}`",
            f"- `--pml-power {int(best['power'])}`",
            f"- `--pml-kappa-max {best['kappa_max']:.2f}`",
        ]
    )

    (ROOT / "docs" / "pml_tuning.md").write_text("\n".join(lines), encoding="utf-8")
    print("Best:", best)


def default_output_subdir(backend: str) -> str:
    if backend == "baseline":
        return "forward_case_baseline"
    if backend == "boost_serial":
        return "forward_case_boost_serial"
    return "forward_case"


if __name__ == "__main__":
    main()
