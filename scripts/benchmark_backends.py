from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Benchmark baseline vs C++ boost serial/parallel solvers.")
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--nt-scale", type=float, default=1.0, help="Scale factor for nt to shorten benchmark.")
    parser.add_argument("--n-snapshots", type=int, default=12)
    parser.add_argument("--output", type=str, default="output/benchmark/benchmark_report.json")
    return parser.parse_args()


def ensure_boost_solver_module() -> object:
    import fd_workflow.solver_boost as solver_boost

    if not solver_boost.extension_available():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_fd_boost.py")], cwd=str(ROOT))
        solver_boost = importlib.reload(solver_boost)

    if not solver_boost.extension_available():
        raise RuntimeError("C++ extension build failed. Cannot benchmark boost backend.")

    return solver_boost


def run_one(
    name: str,
    run_callable,
) -> tuple[float, dict[str, np.ndarray]]:
    t0 = time.perf_counter()
    result = run_callable()
    elapsed = time.perf_counter() - t0
    print(f"{name:<18} {elapsed:8.3f} s")
    return elapsed, result


def main() -> None:
    args = parse_args()

    cfg = SimulationConfig()
    grid = auto_grid_from_frequency(cfg)

    vp, vs, rho = build_uniform_model(cfg, grid)
    surface_idx = build_surface_topography(cfg, grid)
    pm = build_pm_medium_parameters(cfg, grid, vp, vs, rho, surface_idx)

    nt_bench = max(1200, int(grid.nt * max(0.05, min(1.0, args.nt_scale))))
    wavelet = make_scaled_ricker(cfg.f0_hz, nt_bench, grid.dt_s, cfg.source_scale)
    p0 = np.sin(np.deg2rad(cfg.angle_from_z_deg)) / (cfg.vp_m_s / 1_000.0)
    p0s = np.full(grid.nx_total, p0, dtype=np.float64)
    source_z_idx = max(surface_idx.max() + 8, grid.nz_phys - grid.nbz - cfg.source_depth_margin_cells)
    source_z_idx = int(min(source_z_idx, grid.nz_phys - cfg.source_depth_margin_cells))

    common_kwargs = dict(
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
        n_snapshots=args.n_snapshots,
        pml_reflect_coeff=cfg.pml_reflect_coeff,
        pml_power=cfg.pml_power,
        pml_kappa_max=cfg.pml_kappa_max,
    )

    solver_boost = ensure_boost_solver_module()

    print("Running benchmark with solver-only timing (no GIF generation):")
    print(f"  nt={nt_bench}, nx_total={grid.nx_total}, nz_total={grid.nz_total}, threads={args.threads}")

    baseline_cold_s, baseline_result = run_one(
        "baseline_cold",
        lambda: run_fd_plane_wave(**common_kwargs),
    )
    baseline_hot_s, baseline_result_hot = run_one(
        "baseline_hot",
        lambda: run_fd_plane_wave(**common_kwargs),
    )

    boost_serial_s, boost_serial_result = run_one(
        "boost_serial",
        lambda: solver_boost.run_fd_plane_wave_boost(**common_kwargs, n_threads=1),
    )
    boost_parallel_s, boost_parallel_result = run_one(
        "boost_parallel",
        lambda: solver_boost.run_fd_plane_wave_boost(**common_kwargs, n_threads=max(1, int(args.threads))),
    )

    # Use a single quality proxy to ensure all backends produce physically reasonable fields.
    quality = {
        "baseline_hot_boundary_energy_ratio": boundary_energy_ratio(baseline_result_hot["snap_vz"], grid),
        "boost_serial_boundary_energy_ratio": boundary_energy_ratio(boost_serial_result["snap_vz"], grid),
        "boost_parallel_boundary_energy_ratio": boundary_energy_ratio(boost_parallel_result["snap_vz"], grid),
    }

    speedup_vs_baseline_hot = baseline_hot_s / boost_parallel_s if boost_parallel_s > 0 else 0.0
    speedup_parallel_vs_serial = boost_serial_s / boost_parallel_s if boost_parallel_s > 0 else 0.0

    report = {
        "benchmark_setup": {
            "nt": nt_bench,
            "nt_scale": args.nt_scale,
            "n_snapshots": args.n_snapshots,
            "threads_parallel": int(max(1, int(args.threads))),
            "grid": {
                "nx_total": grid.nx_total,
                "nz_total": grid.nz_total,
                "dx_m": grid.dx_m,
                "dz_m": grid.dz_m,
                "dt_s": grid.dt_s,
            },
        },
        "timings_s": {
            "baseline_cold": baseline_cold_s,
            "baseline_hot": baseline_hot_s,
            "boost_serial": boost_serial_s,
            "boost_parallel": boost_parallel_s,
        },
        "speedups": {
            "boost_parallel_vs_baseline_hot": speedup_vs_baseline_hot,
            "boost_parallel_vs_boost_serial": speedup_parallel_vs_serial,
        },
        "quality": quality,
        "acceptance": {
            "boost_faster_than_baseline": bool(boost_parallel_s < baseline_hot_s),
            "parallel_faster_than_serial": bool(boost_parallel_s < boost_serial_s),
        },
    }

    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nBenchmark summary:")
    print(f"  baseline_hot         : {baseline_hot_s:.3f} s")
    print(f"  boost_serial         : {boost_serial_s:.3f} s")
    print(f"  boost_parallel       : {boost_parallel_s:.3f} s")
    print(f"  speedup boost/baseline_hot : {speedup_vs_baseline_hot:.3f}x")
    print(f"  speedup parallel/serial    : {speedup_parallel_vs_serial:.3f}x")
    print(f"  report: {out_path}")

    if not report["acceptance"]["boost_faster_than_baseline"]:
        raise RuntimeError("Acceptance failed: boost_parallel is not faster than baseline_hot.")
    if not report["acceptance"]["parallel_faster_than_serial"]:
        raise RuntimeError("Acceptance failed: boost_parallel is not faster than boost_serial.")


if __name__ == "__main__":
    main()
