from __future__ import annotations

import argparse
from dataclasses import replace
import gc
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fd_workflow.config import GridSpec, SimulationConfig
from fd_workflow.model import build_pm_medium_parameters, build_surface_topography, build_uniform_model
from fd_workflow.solver_boost import extension_available, run_fd_plane_wave_boost
from fd_workflow.wavelet import make_scaled_ricker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Study memory/time feasibility for 900km x 60km at fixed spacing on local machine."
    )
    parser.add_argument("--width-km", type=float, default=900.0)
    parser.add_argument("--depth-km", type=float, default=60.0)
    parser.add_argument("--dx-m", type=float, default=20.0)
    parser.add_argument("--dz-m", type=float, default=20.0)
    parser.add_argument("--pml-x-cells", type=int, default=150)
    parser.add_argument("--pml-z-cells", type=int, default=100)
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--memory-headroom", type=float, default=0.85)
    parser.add_argument("--runtime-safety-factor", type=float, default=1.35)

    parser.add_argument("--full-n-snapshots", type=int, default=24)
    parser.add_argument("--full-seismo-stride-t", type=int, default=40)
    parser.add_argument("--full-seismo-stride-x", type=int, default=8)
    parser.add_argument("--full-snapshot-stride-x", type=int, default=10)
    parser.add_argument("--full-snapshot-stride-z", type=int, default=6)

    parser.add_argument("--probe-width-km", type=float, default=90.0)
    parser.add_argument("--probe-depth-km", type=float, default=8.0)
    parser.add_argument("--probe-nt", type=int, default=300)
    parser.add_argument("--probe-snapshots", type=int, default=2)
    parser.add_argument("--probe-seismo-stride-t", type=int, default=4)
    parser.add_argument("--probe-seismo-stride-x", type=int, default=2)
    parser.add_argument("--probe-snapshot-stride-x", type=int, default=2)
    parser.add_argument("--probe-snapshot-stride-z", type=int, default=2)
    parser.add_argument("--skip-probe", action="store_true")

    parser.add_argument("--output-json", type=Path, default=Path("output/large_case/resource_study.json"))
    parser.add_argument("--output-md", type=Path, default=Path("output/large_case/resource_study.md"))
    return parser.parse_args()


def gib(nbytes: float) -> float:
    return float(nbytes / (1024.0**3))


def build_fixed_grid(
    cfg: SimulationConfig,
    width_km: float,
    depth_km: float,
    dx_m: float,
    dz_m: float,
    pml_x_cells: int,
    pml_z_cells: int,
    nt_override: int | None = None,
) -> GridSpec:
    width_m = width_km * 1_000.0
    depth_m = depth_km * 1_000.0
    nx_phys = int(math.ceil(width_m / dx_m))
    nz_phys = int(math.ceil(depth_m / dz_m))
    nbx = max(1, int(pml_x_cells))
    nbz = max(1, int(pml_z_cells))

    nx_total = nx_phys + 2 * nbx
    nz_total = nz_phys + nbz

    dt_stable = cfg.cfl * min(dx_m, dz_m) / (math.sqrt(2.0) * cfg.vp_m_s)
    if nt_override is not None:
        nt = max(1, int(nt_override))
        dt_s = dt_stable
    else:
        travel_time = math.sqrt(width_m**2 + depth_m**2) / cfg.vp_m_s
        source_time = 8.0 / cfg.f0_hz
        tmax = travel_time + source_time + 20.0
        nt = max(1, int(math.ceil(tmax / dt_stable)))
        dt_s = dt_stable

    return GridSpec(
        dx_m=dx_m,
        dz_m=dz_m,
        dt_s=dt_s,
        nt=nt,
        nx_phys=nx_phys,
        nz_phys=nz_phys,
        nbx=nbx,
        nbz=nbz,
        nx_total=nx_total,
        nz_total=nz_total,
    )


def estimate_peak_memory_bytes(
    nx: int,
    nz: int,
    nt: int,
    n_snapshots: int,
    seismo_stride_t: int,
    seismo_stride_x: int,
    snapshot_stride_x: int,
    snapshot_stride_z: int,
    include_model_arrays: bool = True,
) -> dict[str, float]:
    nxy = nx * nz
    bx = (nx - 1) * nz
    bz = nx * (nz - 1)
    mu_xz = (nx - 1) * (nz - 1)

    seismo_t = (nt + seismo_stride_t - 1) // seismo_stride_t
    seismo_x = (nx + seismo_stride_x - 1) // seismo_stride_x
    snap_x = (nx + snapshot_stride_x - 1) // snapshot_stride_x
    snap_z = (nz + snapshot_stride_z - 1) // snapshot_stride_z

    # C++ runtime state vectors.
    bytes_runtime_state = 13 * nxy * 8
    # Static PM parameter arrays fed into the solver.
    bytes_pm_inputs = (4 * nxy + bx + bz + mu_xz) * 8
    # Solver outputs.
    bytes_snapshots = (2 * n_snapshots * snap_x * snap_z) * 8
    bytes_seismograms = (2 * seismo_t * seismo_x) * 8
    # Model construction arrays held on Python side.
    bytes_model = (3 * nxy * 8) if include_model_arrays else 0
    bytes_category = nxy  # int8 category map

    peak_bytes = bytes_runtime_state + bytes_pm_inputs + bytes_snapshots + bytes_seismograms + bytes_category + bytes_model
    return {
        "runtime_state_gib": gib(bytes_runtime_state),
        "pm_inputs_gib": gib(bytes_pm_inputs),
        "snapshots_gib": gib(bytes_snapshots),
        "seismograms_gib": gib(bytes_seismograms),
        "model_arrays_gib": gib(bytes_model),
        "category_gib": gib(bytes_category),
        "estimated_peak_gib": gib(peak_bytes),
    }


def run_probe(
    cfg: SimulationConfig,
    grid: GridSpec,
    threads: int,
    probe_nt: int,
    probe_snapshots: int,
    probe_seismo_stride_t: int,
    probe_seismo_stride_x: int,
    probe_snapshot_stride_x: int,
    probe_snapshot_stride_z: int,
) -> dict[str, float | int]:
    if not extension_available():
        raise RuntimeError("fd_workflow._fd_core is not available. Run: python scripts/build_fd_boost.py")

    t0 = time.perf_counter()
    vp, vs, rho = build_uniform_model(cfg, grid)
    surface_idx = build_surface_topography(cfg, grid)
    pm = build_pm_medium_parameters(cfg, grid, vp, vs, rho, surface_idx)
    t_build = time.perf_counter() - t0

    p0 = np.sin(np.deg2rad(cfg.angle_from_z_deg)) / (cfg.vp_m_s / 1_000.0)
    p0s = np.full(grid.nx_total, p0, dtype=np.float64)
    wavelet = make_scaled_ricker(cfg.f0_hz, probe_nt, grid.dt_s, cfg.source_scale)

    source_z_idx = max(surface_idx.max() + 8, grid.nz_phys - grid.nbz - cfg.source_depth_margin_cells)
    source_z_idx = int(min(source_z_idx, grid.nz_phys - cfg.source_depth_margin_cells))

    # Keep peak memory lower in probe phase by releasing model arrays before solver.
    del vp, vs, rho
    gc.collect()

    t1 = time.perf_counter()
    result = run_fd_plane_wave_boost(
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
        n_snapshots=probe_snapshots,
        pml_reflect_coeff=cfg.pml_reflect_coeff,
        pml_power=cfg.pml_power,
        pml_kappa_max=cfg.pml_kappa_max,
        n_threads=threads,
        seismo_stride_t=probe_seismo_stride_t,
        seismo_stride_x=probe_seismo_stride_x,
        snapshot_stride_x=probe_snapshot_stride_x,
        snapshot_stride_z=probe_snapshot_stride_z,
    )
    t_solver = time.perf_counter() - t1

    nxy = grid.nx_total * grid.nz_total
    throughput_cells_per_sec = float(nxy * probe_nt / max(t_solver, 1e-9))

    out = {
        "probe_build_s": float(t_build),
        "probe_solver_s": float(t_solver),
        "probe_total_s": float(t_build + t_solver),
        "probe_nt": int(probe_nt),
        "probe_nxy": int(nxy),
        "throughput_cells_per_s": throughput_cells_per_sec,
        "probe_snap_shape": list(result["snap_vx"].shape),
        "probe_seismo_shape": list(result["seismo_vz"].shape),
    }

    del result, pm, p0s, wavelet
    gc.collect()
    return out


def write_markdown(path: Path, payload: dict) -> None:
    lines = []
    lines.append("# Large Case Resource Study")
    lines.append("")
    lines.append("## Input Target")
    lines.append(f"- Domain: {payload['target']['width_km']} km x {payload['target']['depth_km']} km")
    lines.append(f"- Spacing: dx=dz={payload['target']['dx_m']} m")
    lines.append(f"- Grid total: nx={payload['target']['nx_total']}, nz={payload['target']['nz_total']}, nt={payload['target']['nt']}")
    lines.append("")
    lines.append("## Memory Feasibility")
    lines.append(f"- Machine RAM: {payload['machine']['ram_gib']:.2f} GiB")
    lines.append(f"- Baseline peak estimate: {payload['memory']['baseline_mode']['estimated_peak_gib']:.2f} GiB")
    lines.append(f"- Constrained peak estimate: {payload['memory']['constrained_mode']['estimated_peak_gib']:.2f} GiB")
    lines.append(f"- Headroom limit ({payload['machine']['memory_headroom']:.0%}): {payload['machine']['headroom_gib']:.2f} GiB")
    lines.append("")
    lines.append("## Runtime Projection")
    if payload.get("probe") is None:
        lines.append("- Probe skipped.")
    else:
        lines.append(f"- Probe throughput: {payload['probe']['throughput_cells_per_s']:.2e} cell-updates/s")
        lines.append(f"- Full run estimate (raw): {payload['runtime']['estimated_hours_raw']:.2f} h")
        lines.append(f"- Full run estimate (safety-factor): {payload['runtime']['estimated_hours_safe']:.2f} h")
        lines.append(f"- Probe build time: {payload['probe']['probe_build_s']:.2f} s")
        lines.append(f"- Probe solver time: {payload['probe']['probe_solver_s']:.2f} s")
    lines.append("")
    lines.append("## Recommendation")
    lines.append(f"- Baseline mode feasible: {payload['decision']['baseline_memory_feasible']}")
    lines.append(f"- Constrained mode feasible: {payload['decision']['constrained_memory_feasible']}")
    lines.append(f"- Estimated local-run feasible: {payload['decision']['local_run_feasible']}")
    lines.append(
        f"- Suggested output controls: seismo_stride_t={payload['recommendation']['seismo_stride_t']}, "
        f"seismo_stride_x={payload['recommendation']['seismo_stride_x']}, "
        f"snapshot_stride_x={payload['recommendation']['snapshot_stride_x']}, "
        f"snapshot_stride_z={payload['recommendation']['snapshot_stride_z']}, "
        f"n_snapshots={payload['recommendation']['n_snapshots']}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    cfg = replace(SimulationConfig(), width_km=args.width_km, depth_km=args.depth_km)
    full_grid = build_fixed_grid(
        cfg=cfg,
        width_km=args.width_km,
        depth_km=args.depth_km,
        dx_m=args.dx_m,
        dz_m=args.dz_m,
        pml_x_cells=args.pml_x_cells,
        pml_z_cells=args.pml_z_cells,
    )

    baseline_mem = estimate_peak_memory_bytes(
        nx=full_grid.nx_total,
        nz=full_grid.nz_total,
        nt=full_grid.nt,
        n_snapshots=60,
        seismo_stride_t=1,
        seismo_stride_x=1,
        snapshot_stride_x=1,
        snapshot_stride_z=1,
    )
    constrained_mem = estimate_peak_memory_bytes(
        nx=full_grid.nx_total,
        nz=full_grid.nz_total,
        nt=full_grid.nt,
        n_snapshots=args.full_n_snapshots,
        seismo_stride_t=max(1, args.full_seismo_stride_t),
        seismo_stride_x=max(1, args.full_seismo_stride_x),
        snapshot_stride_x=max(1, args.full_snapshot_stride_x),
        snapshot_stride_z=max(1, args.full_snapshot_stride_z),
    )

    vm = psutil.virtual_memory()
    ram_gib = gib(float(vm.total))
    headroom_gib = ram_gib * args.memory_headroom

    probe_result: dict | None = None
    runtime = {
        "estimated_hours_raw": None,
        "estimated_hours_safe": None,
        "throughput_cells_per_s": None,
    }
    if not args.skip_probe:
        probe_cfg = replace(cfg, width_km=args.probe_width_km, depth_km=args.probe_depth_km)
        probe_grid = build_fixed_grid(
            cfg=probe_cfg,
            width_km=args.probe_width_km,
            depth_km=args.probe_depth_km,
            dx_m=args.dx_m,
            dz_m=args.dz_m,
            pml_x_cells=args.pml_x_cells,
            pml_z_cells=args.pml_z_cells,
            nt_override=args.probe_nt,
        )
        probe_result = run_probe(
            cfg=probe_cfg,
            grid=probe_grid,
            threads=max(1, int(args.threads)),
            probe_nt=max(1, int(args.probe_nt)),
            probe_snapshots=max(0, int(args.probe_snapshots)),
            probe_seismo_stride_t=max(1, int(args.probe_seismo_stride_t)),
            probe_seismo_stride_x=max(1, int(args.probe_seismo_stride_x)),
            probe_snapshot_stride_x=max(1, int(args.probe_snapshot_stride_x)),
            probe_snapshot_stride_z=max(1, int(args.probe_snapshot_stride_z)),
        )
        full_updates = float(full_grid.nx_total * full_grid.nz_total * full_grid.nt)
        throughput = float(probe_result["throughput_cells_per_s"])
        est_raw_s = full_updates / max(throughput, 1e-9)
        est_safe_s = est_raw_s * max(1.0, float(args.runtime_safety_factor))
        runtime = {
            "estimated_hours_raw": est_raw_s / 3600.0,
            "estimated_hours_safe": est_safe_s / 3600.0,
            "throughput_cells_per_s": throughput,
        }

    payload = {
        "machine": {
            "logical_cpus": int(os.cpu_count() or 1),
            "ram_gib": ram_gib,
            "memory_headroom": float(args.memory_headroom),
            "headroom_gib": headroom_gib,
        },
        "target": {
            "width_km": float(args.width_km),
            "depth_km": float(args.depth_km),
            "dx_m": float(args.dx_m),
            "dz_m": float(args.dz_m),
            "pml_x_cells": int(args.pml_x_cells),
            "pml_z_cells": int(args.pml_z_cells),
            "nx_total": int(full_grid.nx_total),
            "nz_total": int(full_grid.nz_total),
            "nt": int(full_grid.nt),
            "dt_s": float(full_grid.dt_s),
        },
        "memory": {
            "baseline_mode": baseline_mem,
            "constrained_mode": constrained_mem,
        },
        "probe": probe_result,
        "runtime": runtime,
        "recommendation": {
            "n_snapshots": int(args.full_n_snapshots),
            "seismo_stride_t": int(args.full_seismo_stride_t),
            "seismo_stride_x": int(args.full_seismo_stride_x),
            "snapshot_stride_x": int(args.full_snapshot_stride_x),
            "snapshot_stride_z": int(args.full_snapshot_stride_z),
            "threads": int(args.threads),
        },
    }

    baseline_ok = baseline_mem["estimated_peak_gib"] <= headroom_gib
    constrained_ok = constrained_mem["estimated_peak_gib"] <= headroom_gib
    runtime_ok = (runtime["estimated_hours_safe"] is not None) and (runtime["estimated_hours_safe"] <= 48.0)

    payload["decision"] = {
        "baseline_memory_feasible": bool(baseline_ok),
        "constrained_memory_feasible": bool(constrained_ok),
        "runtime_within_48h": bool(runtime_ok),
        "local_run_feasible": bool(constrained_ok and (runtime_ok or runtime["estimated_hours_safe"] is None)),
    }

    out_json = ROOT / args.output_json
    out_md = ROOT / args.output_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(out_md, payload)

    print(f"[report] {out_json}")
    print(f"[report] {out_md}")
    print(
        "[decision] baseline_memory_feasible="
        f"{payload['decision']['baseline_memory_feasible']} "
        f"constrained_memory_feasible={payload['decision']['constrained_memory_feasible']} "
        f"local_run_feasible={payload['decision']['local_run_feasible']}"
    )


if __name__ == "__main__":
    main()
