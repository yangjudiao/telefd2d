from __future__ import annotations

import argparse
from dataclasses import replace
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fd_workflow.config import GridSpec, SimulationConfig, auto_grid_from_frequency
from fd_workflow.model import build_pm_medium_parameters, build_surface_topography, build_uniform_model
from fd_workflow.postprocess import (
    boundary_energy_ratio,
    compute_p_and_curl,
    save_surface_seismogram,
    save_wavefield_gif,
    write_run_metadata,
)
from fd_workflow.solver import run_fd_plane_wave
from fd_workflow.wavelet import make_scaled_ricker


def gib(nbytes: float) -> float:
    return float(nbytes / (1024.0**3))


def category_counts(category: np.ndarray) -> dict[str, int]:
    return {
        "air": int(np.sum(category == 0)),
        "interior": int(np.sum(category == 1)),
        "h_boundary": int(np.sum(category == 2)),
        "vl_boundary": int(np.sum(category == 3)),
        "vr_boundary": int(np.sum(category == 4)),
        "outer_corner": int(np.sum(category == 5)),
        "inner_corner": int(np.sum(category == 6)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run telefd2d acceptance workflow with decoupled compute/postprocess.")
    parser.add_argument("--mode", choices=["all", "compute", "postprocess"], default="all")
    parser.add_argument("--backend", choices=["baseline", "boost_serial", "boost_parallel"], default="boost_parallel")
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--output-mode", choices=["memory", "stream_to_disk"], default="stream_to_disk")
    parser.add_argument("--output-subdir", type=str, default="forward_case_telefd2d")
    parser.add_argument("--raw-prefix", type=str, default="raw")

    parser.add_argument("--width-km", type=float, default=100.0)
    parser.add_argument("--depth-km", type=float, default=40.0)
    parser.add_argument("--f0-hz", type=float, default=0.25)
    parser.add_argument("--dx-m", type=float, default=None)
    parser.add_argument("--dz-m", type=float, default=None)
    parser.add_argument("--pml-x-scale", type=float, default=1.0)
    parser.add_argument("--topo-amplitude-km", type=float, default=5.0)
    parser.add_argument("--topo-mean-depth-km", type=float, default=5.0)
    parser.add_argument("--topo-cycles", type=float, default=4.0)
    parser.add_argument("--n-snapshots", type=int, default=60)

    parser.add_argument("--pml-reflect-coeff", type=float, default=None)
    parser.add_argument("--pml-power", type=int, default=None)
    parser.add_argument("--pml-kappa-max", type=float, default=None)

    parser.add_argument("--seismo-stride-t", type=int, default=1)
    parser.add_argument("--seismo-stride-x", type=int, default=1)
    parser.add_argument("--snapshot-stride-x", type=int, default=1)
    parser.add_argument("--snapshot-stride-z", type=int, default=1)
    parser.add_argument("--progress-step", type=int, default=200)
    parser.add_argument("--progress-sec", type=float, default=0.5)

    parser.add_argument("--monitor-memory", action="store_true")
    parser.add_argument("--monitor-interval-s", type=float, default=0.2)
    return parser.parse_args()


def build_grid_spec(cfg: SimulationConfig, args: argparse.Namespace) -> GridSpec:
    if args.dx_m is None and args.dz_m is None:
        return auto_grid_from_frequency(cfg)
    if args.dx_m is None or args.dz_m is None:
        raise ValueError("Both --dx-m and --dz-m must be provided together.")

    dx_m = float(args.dx_m)
    dz_m = float(args.dz_m)
    if dx_m <= 0.0 or dz_m <= 0.0:
        raise ValueError("--dx-m and --dz-m must be > 0.")

    width_m = cfg.width_km * 1_000.0
    depth_m = cfg.depth_km * 1_000.0
    nx_phys = max(1, int(math.ceil(width_m / dx_m)))
    nz_phys = max(1, int(math.ceil(depth_m / dz_m)))

    nbx = max(cfg.pml_min_cells_x, int(math.ceil(nx_phys * cfg.pml_ratio_x)))
    nbz = max(cfg.pml_min_cells_z, int(math.ceil(nz_phys * cfg.pml_ratio_z)))

    nx_total = nx_phys + 2 * nbx
    nz_total = nz_phys + nbz

    dt_stable = cfg.cfl * min(dx_m, dz_m) / (math.sqrt(2.0) * cfg.vp_m_s)
    travel_time = math.sqrt(width_m**2 + depth_m**2) / cfg.vp_m_s
    source_time = 8.0 / cfg.f0_hz
    tmax = travel_time + source_time + 20.0
    nt = max(1_200, int(math.ceil(tmax / dt_stable)))
    dt_s = tmax / nt

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


def ensure_boost_solver_module() -> tuple[object, dict[str, int | bool]]:
    import fd_workflow.solver_boost as solver_boost

    if not solver_boost.extension_available():
        print("[build] fd_workflow._fd_core not found, building extension...")
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_fd_boost.py")], cwd=str(ROOT))
        solver_boost = importlib.reload(solver_boost)

    if not solver_boost.extension_available():
        raise RuntimeError("C++ extension build failed. Cannot run boost backend.")

    return solver_boost, solver_boost.extension_capabilities()


def _rel_to(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _start_rss_monitor(enabled: bool, interval_s: float) -> tuple[dict[str, float], threading.Event, threading.Thread | None]:
    proc = psutil.Process(os.getpid())
    rss0 = float(proc.memory_info().rss)
    uss0 = float(getattr(proc.memory_full_info(), "uss", rss0))
    state = {
        "rss_before": rss0,
        "rss_after": rss0,
        "rss_peak": rss0,
        "uss_before": uss0,
        "uss_after": uss0,
        "uss_peak": uss0,
    }
    stop_event = threading.Event()

    if not enabled:
        return state, stop_event, None

    interval_s = max(0.02, float(interval_s))

    def _run() -> None:
        while not stop_event.is_set():
            rss = float(proc.memory_info().rss)
            uss = float(getattr(proc.memory_full_info(), "uss", rss))
            if rss > state["rss_peak"]:
                state["rss_peak"] = rss
            if uss > state["uss_peak"]:
                state["uss_peak"] = uss
            time.sleep(interval_s)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return state, stop_event, thread


def _stop_rss_monitor(
    state: dict[str, float],
    stop_event: threading.Event,
    thread: threading.Thread | None,
) -> None:
    stop_event.set()
    if thread is not None:
        thread.join(timeout=2.0)
    proc = psutil.Process(os.getpid())
    rss_after = float(proc.memory_info().rss)
    uss_after = float(getattr(proc.memory_full_info(), "uss", rss_after))
    state["rss_after"] = rss_after
    state["rss_peak"] = max(state["rss_peak"], rss_after)
    state["uss_after"] = uss_after
    state["uss_peak"] = max(state["uss_peak"], uss_after)


def run_compute_stage(args: argparse.Namespace, out_dir: Path) -> dict:
    cfg = replace(
        SimulationConfig(),
        width_km=float(args.width_km),
        depth_km=float(args.depth_km),
        f0_hz=float(args.f0_hz),
        pml_ratio_x=float(SimulationConfig().pml_ratio_x * max(0.1, float(args.pml_x_scale))),
        pml_min_cells_x=int(max(1, round(SimulationConfig().pml_min_cells_x * max(0.1, float(args.pml_x_scale))))),
        topo_amplitude_km=float(args.topo_amplitude_km),
        topo_mean_depth_km=float(args.topo_mean_depth_km),
        topo_cycles=float(args.topo_cycles),
        n_snapshots=max(0, int(args.n_snapshots)),
    )
    if args.pml_reflect_coeff is not None:
        cfg = replace(cfg, pml_reflect_coeff=float(args.pml_reflect_coeff))
    if args.pml_power is not None:
        cfg = replace(cfg, pml_power=int(args.pml_power))
    if args.pml_kappa_max is not None:
        cfg = replace(cfg, pml_kappa_max=float(args.pml_kappa_max))

    grid = build_grid_spec(cfg, args)

    vp, vs, rho = build_uniform_model(cfg, grid)
    surface_idx = build_surface_topography(cfg, grid)
    pm = build_pm_medium_parameters(cfg, grid, vp, vs, rho, surface_idx)

    p0 = np.sin(np.deg2rad(cfg.angle_from_z_deg)) / (cfg.vp_m_s / 1_000.0)
    p0s = np.full(grid.nx_total, p0, dtype=np.float64)
    wavelet = make_scaled_ricker(cfg.f0_hz, grid.nt, grid.dt_s, cfg.source_scale)

    source_x_idx = grid.nbx + grid.nx_phys // 2
    source_z_idx = max(surface_idx.max() + 8, grid.nz_phys - grid.nbz - cfg.source_depth_margin_cells)
    source_z_idx = int(min(source_z_idx, grid.nz_phys - cfg.source_depth_margin_cells))

    raw_paths = {
        "snap_vx": out_dir / f"{args.raw_prefix}_snap_vx.npy",
        "snap_vz": out_dir / f"{args.raw_prefix}_snap_vz.npy",
        "seismo_vx": out_dir / f"{args.raw_prefix}_seismo_vx.npy",
        "seismo_vz": out_dir / f"{args.raw_prefix}_seismo_vz.npy",
        "snap_it": out_dir / f"{args.raw_prefix}_snap_it.npy",
    }
    free_surface_path = out_dir / "free_surface_index.npy"

    thread_count = 1
    boost_caps: dict[str, int | bool] = {"available": False, "openmp": False, "max_threads": 1}
    output_mode_used = args.output_mode

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
        n_snapshots=cfg.n_snapshots,
        pml_reflect_coeff=cfg.pml_reflect_coeff,
        pml_power=cfg.pml_power,
        pml_kappa_max=cfg.pml_kappa_max,
    )

    print(f"[compute] backend={args.backend} output_mode={args.output_mode} ...", flush=True)
    monitor_state, monitor_stop, monitor_thread = _start_rss_monitor(args.monitor_memory, args.monitor_interval_s)
    t0 = time.time()
    try:
        if args.backend == "baseline":
            output_mode_used = "memory"
            result = run_fd_plane_wave(**kwargs)
        else:
            solver_boost, boost_caps = ensure_boost_solver_module()
            thread_count = 1 if args.backend == "boost_serial" else max(1, int(args.threads))
            result = solver_boost.run_fd_plane_wave_boost(
                **kwargs,
                n_threads=thread_count,
                seismo_stride_t=max(1, int(args.seismo_stride_t)),
                seismo_stride_x=max(1, int(args.seismo_stride_x)),
                snapshot_stride_x=max(1, int(args.snapshot_stride_x)),
                snapshot_stride_z=max(1, int(args.snapshot_stride_z)),
                progress_stride_t=max(0, int(args.progress_step)),
                progress_min_interval_s=max(0.0, float(args.progress_sec)),
                output_mode=args.output_mode,
                output_dir=str(out_dir),
                output_prefix=args.raw_prefix,
            )
    finally:
        _stop_rss_monitor(monitor_state, monitor_stop, monitor_thread)
    runtime_s = time.time() - t0

    if output_mode_used == "stream_to_disk":
        missing = [str(p) for p in raw_paths.values() if not p.exists()]
        if missing:
            raise RuntimeError(f"Streaming mode expected disk outputs but missing files: {missing}")
    else:
        np.save(raw_paths["snap_vx"], np.asarray(result["snap_vx"]))
        np.save(raw_paths["snap_vz"], np.asarray(result["snap_vz"]))
        np.save(raw_paths["seismo_vx"], np.asarray(result["seismo_vx"]))
        np.save(raw_paths["seismo_vz"], np.asarray(result["seismo_vz"]))
        np.save(raw_paths["snap_it"], np.asarray(result["snap_it"], dtype=np.int64))

    np.save(free_surface_path, surface_idx)

    metadata = {
        "stage": "compute",
        "backend": args.backend,
        "backend_runtime": {
            "threads_requested": int(thread_count),
            "boost_extension": boost_caps,
        },
        "output_mode": output_mode_used,
        "output_controls": {
            "n_snapshots": int(cfg.n_snapshots),
            "seismo_stride_t": int(max(1, args.seismo_stride_t)),
            "seismo_stride_x": int(max(1, args.seismo_stride_x)),
            "snapshot_stride_x": int(max(1, args.snapshot_stride_x)),
            "snapshot_stride_z": int(max(1, args.snapshot_stride_z)),
        },
        "config": {
            "width_km": cfg.width_km,
            "depth_km": cfg.depth_km,
            "vp_m_s": cfg.vp_m_s,
            "vs_m_s": cfg.vs_m_s,
            "rho_kg_m3": cfg.rho_kg_m3,
            "f0_hz": cfg.f0_hz,
            "angle_from_z_deg": cfg.angle_from_z_deg,
            "points_per_min_wavelength": cfg.points_per_min_wavelength,
            "topo_amplitude_km": cfg.topo_amplitude_km,
            "topo_mean_depth_km": cfg.topo_mean_depth_km,
            "topo_cycles": cfg.topo_cycles,
            "source_scale": cfg.source_scale,
        },
        "grid": {
            "dx_m": grid.dx_m,
            "dz_m": grid.dz_m,
            "dt_s": grid.dt_s,
            "nt": grid.nt,
            "nx_phys": grid.nx_phys,
            "nz_phys": grid.nz_phys,
            "nbx": grid.nbx,
            "nbz": grid.nbz,
            "nx_total": grid.nx_total,
            "nz_total": grid.nz_total,
        },
        "pml": {
            "reflect_coeff": cfg.pml_reflect_coeff,
            "power": cfg.pml_power,
            "kappa_max": cfg.pml_kappa_max,
        },
        "topography": {
            "surface_min_km": float(surface_idx.min() * grid.dz_m / 1_000.0),
            "surface_max_km": float(surface_idx.max() * grid.dz_m / 1_000.0),
            "surface_mean_km": float(surface_idx.mean() * grid.dz_m / 1_000.0),
            "category_counts": category_counts(pm.category),
        },
        "source": {
            "type": "delayed_line_source_for_plane_wave",
            "source_x_idx_marker": int(source_x_idx),
            "source_z_idx": int(source_z_idx),
            "source_x_km_marker": float(source_x_idx * grid.dx_m / 1_000.0),
            "source_z_km": float(source_z_idx * grid.dz_m / 1_000.0),
        },
        "runtime_s": float(runtime_s),
        "memory_rss_gib": {
            "before": gib(monitor_state["rss_before"]),
            "peak": gib(monitor_state["rss_peak"]),
            "after": gib(monitor_state["rss_after"]),
        },
        "memory_uss_gib": {
            "before": gib(monitor_state["uss_before"]),
            "peak": gib(monitor_state["uss_peak"]),
            "after": gib(monitor_state["uss_after"]),
        },
        "artifacts": {
            "raw_outputs": {k: _rel_to(v, out_dir) for k, v in raw_paths.items()},
            "free_surface_index_npy": _rel_to(free_surface_path, out_dir),
        },
    }

    write_run_metadata(out_dir / "compute_metadata.json", metadata)
    print(f"[compute] wrote {out_dir / 'compute_metadata.json'}")
    return metadata


def _grid_from_dict(d: dict) -> GridSpec:
    return GridSpec(
        dx_m=float(d["dx_m"]),
        dz_m=float(d["dz_m"]),
        dt_s=float(d["dt_s"]),
        nt=int(d["nt"]),
        nx_phys=int(d["nx_phys"]),
        nz_phys=int(d["nz_phys"]),
        nbx=int(d["nbx"]),
        nbz=int(d["nbz"]),
        nx_total=int(d["nx_total"]),
        nz_total=int(d["nz_total"]),
    )


def run_postprocess_stage(out_dir: Path) -> dict:
    compute_meta_path = out_dir / "compute_metadata.json"
    if not compute_meta_path.exists():
        raise FileNotFoundError(f"Missing compute metadata: {compute_meta_path}")
    compute_meta = json.loads(compute_meta_path.read_text(encoding="utf-8"))

    grid = _grid_from_dict(compute_meta["grid"])
    source_x_idx = int(compute_meta["source"]["source_x_idx_marker"])
    source_z_idx = int(compute_meta["source"]["source_z_idx"])

    artifact_map = compute_meta["artifacts"]["raw_outputs"]
    raw_paths = {k: out_dir / artifact_map[k] for k in artifact_map}
    surface_idx = np.load(out_dir / compute_meta["artifacts"]["free_surface_index_npy"], mmap_mode="r")

    print("[postprocess] loading saved raw outputs...")
    snap_vx = np.load(raw_paths["snap_vx"], mmap_mode="r")
    snap_vz = np.load(raw_paths["snap_vz"], mmap_mode="r")
    seismo_vx = np.load(raw_paths["seismo_vx"], mmap_mode="r")
    seismo_vz = np.load(raw_paths["seismo_vz"], mmap_mode="r")
    snap_it = np.load(raw_paths["snap_it"], mmap_mode="r")

    snap_t = np.asarray(snap_it, dtype=np.float64) * float(grid.dt_s)
    print("[postprocess] computing p and curl...")
    snap_p, snap_curl = compute_p_and_curl(np.asarray(snap_vx), np.asarray(snap_vz), grid.dx_m, grid.dz_m)

    print("[postprocess] writing wavefield GIFs...")
    save_wavefield_gif(
        snap_p,
        grid,
        snap_t,
        out_dir / "wavefield_p.gif",
        "p = div(v)",
        surface_idx=surface_idx,
        source_x_idx=source_x_idx,
        source_z_idx=source_z_idx,
    )
    save_wavefield_gif(
        snap_curl,
        grid,
        snap_t,
        out_dir / "wavefield_curl.gif",
        "curl = dvz/dx - dvx/dz",
        surface_idx=surface_idx,
        source_x_idx=source_x_idx,
        source_z_idx=source_z_idx,
    )
    save_wavefield_gif(
        np.asarray(snap_vx),
        grid,
        snap_t,
        out_dir / "wavefield_vx.gif",
        "vx",
        surface_idx=surface_idx,
        source_x_idx=source_x_idx,
        source_z_idx=source_z_idx,
    )
    save_wavefield_gif(
        np.asarray(snap_vz),
        grid,
        snap_t,
        out_dir / "wavefield_vz.gif",
        "vz",
        surface_idx=surface_idx,
        source_x_idx=source_x_idx,
        source_z_idx=source_z_idx,
    )

    print("[postprocess] writing surface seismograms...")
    save_surface_seismogram(
        seismogram=np.asarray(seismo_vx),
        grid=grid,
        dt_s=grid.dt_s * int(compute_meta["output_controls"]["seismo_stride_t"]),
        out_png=out_dir / "surface_seismogram_vx.png",
        out_npy=out_dir / "surface_seismogram_vx.npy",
        source_x_idx=source_x_idx,
        component="Vx",
    )
    save_surface_seismogram(
        seismogram=np.asarray(seismo_vz),
        grid=grid,
        dt_s=grid.dt_s * int(compute_meta["output_controls"]["seismo_stride_t"]),
        out_png=out_dir / "surface_seismogram_vz.png",
        out_npy=out_dir / "surface_seismogram_vz.npy",
        source_x_idx=source_x_idx,
        component="Vz",
    )

    ratio = boundary_energy_ratio(np.asarray(snap_vz), grid)
    outputs = [
        "wavefield_p.gif",
        "wavefield_curl.gif",
        "wavefield_vx.gif",
        "wavefield_vz.gif",
        "surface_seismogram_vx.png",
        "surface_seismogram_vx.npy",
        "surface_seismogram_vz.png",
        "surface_seismogram_vz.npy",
    ]

    full_meta = dict(compute_meta)
    full_meta["stage"] = "all" if compute_meta.get("stage") == "compute" else compute_meta.get("stage")
    full_meta["quality"] = {
        "boundary_energy_ratio": float(ratio),
        "note": "Lower is better for absorbing boundaries.",
    }
    full_meta["outputs"] = outputs

    write_run_metadata(out_dir / "run_metadata.json", full_meta)
    (out_dir / "run_summary.txt").write_text(json.dumps(full_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[postprocess] wrote {out_dir / 'run_metadata.json'}")
    return full_meta


def main() -> None:
    args = parse_args()
    out_subdir = args.output_subdir.strip() or "forward_case_telefd2d"
    out_dir = ROOT / "output" / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode in {"compute", "all"}:
        run_compute_stage(args, out_dir)
    if args.mode in {"postprocess", "all"}:
        run_postprocess_stage(out_dir)

    print(f"Done. Output: {out_dir}")


if __name__ == "__main__":
    main()
