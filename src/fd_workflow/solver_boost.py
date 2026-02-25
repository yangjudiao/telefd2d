from __future__ import annotations

import os
from pathlib import Path

import numpy as np

try:
    from . import _fd_core
except ImportError:  # pragma: no cover - handled at runtime by build script
    _fd_core = None


def extension_available() -> bool:
    return _fd_core is not None


def extension_capabilities() -> dict[str, int | bool]:
    if _fd_core is None:
        return {"available": False, "openmp": False, "max_threads": 1}
    return {
        "available": True,
        "openmp": bool(_fd_core.has_openmp()),
        "max_threads": int(_fd_core.max_threads()),
    }


def _compute_output_shapes(
    nx: int,
    nz: int,
    nt: int,
    n_snapshots: int,
    seismo_stride_t: int,
    seismo_stride_x: int,
    snapshot_stride_x: int,
    snapshot_stride_z: int,
) -> dict[str, tuple[int, ...]]:
    n_snapshots = max(0, int(n_snapshots))
    n_seis_t = (nt + seismo_stride_t - 1) // seismo_stride_t
    n_seis_x = (nx + seismo_stride_x - 1) // seismo_stride_x
    nx_snap = (nx + snapshot_stride_x - 1) // snapshot_stride_x
    nz_snap = (nz + snapshot_stride_z - 1) // snapshot_stride_z
    return {
        "snap": (n_snapshots, nx_snap, nz_snap),
        "seismo": (n_seis_t, n_seis_x),
        "snap_it": (n_snapshots,),
    }


def _prepare_stream_outputs(
    output_dir: Path,
    output_prefix: str,
    shapes: dict[str, tuple[int, ...]],
) -> tuple[dict[str, np.memmap], dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_prefix.strip() or "raw"

    paths = {
        "snap_vx": output_dir / f"{prefix}_snap_vx.npy",
        "snap_vz": output_dir / f"{prefix}_snap_vz.npy",
        "seismo_vx": output_dir / f"{prefix}_seismo_vx.npy",
        "seismo_vz": output_dir / f"{prefix}_seismo_vz.npy",
        "snap_it": output_dir / f"{prefix}_snap_it.npy",
    }
    outputs: dict[str, np.memmap] = {
        "snap_vx": np.lib.format.open_memmap(paths["snap_vx"], mode="w+", dtype=np.float64, shape=shapes["snap"]),
        "snap_vz": np.lib.format.open_memmap(paths["snap_vz"], mode="w+", dtype=np.float64, shape=shapes["snap"]),
        "seismo_vx": np.lib.format.open_memmap(
            paths["seismo_vx"], mode="w+", dtype=np.float64, shape=shapes["seismo"]
        ),
        "seismo_vz": np.lib.format.open_memmap(
            paths["seismo_vz"], mode="w+", dtype=np.float64, shape=shapes["seismo"]
        ),
        "snap_it": np.lib.format.open_memmap(paths["snap_it"], mode="w+", dtype=np.int64, shape=shapes["snap_it"]),
    }
    return outputs, {k: str(v) for k, v in paths.items()}


def run_fd_plane_wave_boost(
    bx: np.ndarray,
    bz: np.ndarray,
    mu_xz: np.ndarray,
    eta_xx_x: np.ndarray,
    eta_xx_z: np.ndarray,
    eta_zz_x: np.ndarray,
    eta_zz_z: np.ndarray,
    receiver_idx: np.ndarray,
    p0s: np.ndarray,
    wav: np.ndarray,
    ifleft: int,
    fp: float,
    pml_velocity: float,
    dx: float,
    dz: float,
    dt: float,
    nbx: int,
    nbz: int,
    source_z_idx: int,
    n_snapshots: int,
    pml_reflect_coeff: float,
    pml_power: int,
    pml_kappa_max: float,
    n_threads: int = 1,
    seismo_stride_t: int = 1,
    seismo_stride_x: int = 1,
    snapshot_stride_x: int = 1,
    snapshot_stride_z: int = 1,
    progress_stride_t: int = 0,
    progress_min_interval_s: float = 1.0,
    output_mode: str = "memory",
    output_dir: str | os.PathLike[str] | None = None,
    output_prefix: str = "raw",
) -> dict[str, object]:
    if _fd_core is None:
        raise RuntimeError(
            "fd_workflow._fd_core is not available. Run: python scripts/build_fd_boost.py"
        )

    n_threads = max(1, int(n_threads))
    seismo_stride_t = max(1, int(seismo_stride_t))
    seismo_stride_x = max(1, int(seismo_stride_x))
    snapshot_stride_x = max(1, int(snapshot_stride_x))
    snapshot_stride_z = max(1, int(snapshot_stride_z))
    progress_stride_t = max(0, int(progress_stride_t))
    progress_min_interval_s = max(0.0, float(progress_min_interval_s))
    output_mode = str(output_mode).strip().lower()
    if output_mode not in {"memory", "stream_to_disk"}:
        raise ValueError("output_mode must be one of: memory, stream_to_disk")

    stream_outputs: dict[str, np.memmap] | None = None
    stream_paths: dict[str, str] | None = None
    stream_shapes: dict[str, tuple[int, ...]] | None = None

    if output_mode == "stream_to_disk":
        if output_dir is None:
            raise ValueError("output_dir is required when output_mode=stream_to_disk")
        nx = int(receiver_idx.shape[0])
        nz = int(eta_xx_x.shape[1])
        nt = int(wav.shape[0])
        stream_shapes = _compute_output_shapes(
            nx=nx,
            nz=nz,
            nt=nt,
            n_snapshots=n_snapshots,
            seismo_stride_t=seismo_stride_t,
            seismo_stride_x=seismo_stride_x,
            snapshot_stride_x=snapshot_stride_x,
            snapshot_stride_z=snapshot_stride_z,
        )
        stream_outputs, stream_paths = _prepare_stream_outputs(Path(output_dir), output_prefix, stream_shapes)

    snap_vx_arg = None if stream_outputs is None else stream_outputs["snap_vx"]
    snap_vz_arg = None if stream_outputs is None else stream_outputs["snap_vz"]
    seismo_vx_arg = None if stream_outputs is None else stream_outputs["seismo_vx"]
    seismo_vz_arg = None if stream_outputs is None else stream_outputs["seismo_vz"]
    snap_it_arg = None if stream_outputs is None else stream_outputs["snap_it"]

    snap_vx, snap_vz, seismo_vx, seismo_vz, snap_it = _fd_core.run_fd_pm_core_cpp(
        np.ascontiguousarray(bx, dtype=np.float64),
        np.ascontiguousarray(bz, dtype=np.float64),
        np.ascontiguousarray(mu_xz, dtype=np.float64),
        np.ascontiguousarray(eta_xx_x, dtype=np.float64),
        np.ascontiguousarray(eta_xx_z, dtype=np.float64),
        np.ascontiguousarray(eta_zz_x, dtype=np.float64),
        np.ascontiguousarray(eta_zz_z, dtype=np.float64),
        np.ascontiguousarray(receiver_idx, dtype=np.int64),
        np.ascontiguousarray(p0s, dtype=np.float64),
        np.ascontiguousarray(wav, dtype=np.float64),
        int(ifleft),
        float(fp),
        float(pml_velocity),
        float(dx),
        float(dz),
        float(dt),
        int(nbx),
        int(nbz),
        int(source_z_idx),
        int(n_snapshots),
        float(pml_reflect_coeff),
        int(pml_power),
        float(pml_kappa_max),
        int(n_threads),
        int(seismo_stride_t),
        int(seismo_stride_x),
        int(snapshot_stride_x),
        int(snapshot_stride_z),
        int(progress_stride_t),
        float(progress_min_interval_s),
        snap_vx_arg,
        snap_vz_arg,
        seismo_vx_arg,
        seismo_vz_arg,
        snap_it_arg,
    )

    result: dict[str, np.ndarray | str | dict[str, str] | dict[str, tuple[int, ...]]] = {
        "snap_vx": snap_vx,
        "snap_vz": snap_vz,
        "seismo_vx": seismo_vx,
        "seismo_vz": seismo_vz,
        "snap_it": snap_it,
        "output_mode": output_mode,
    }
    if stream_outputs is not None and stream_paths is not None and stream_shapes is not None:
        for arr in stream_outputs.values():
            arr.flush()
        result["stream_paths"] = stream_paths
        result["stream_shapes"] = stream_shapes
    return result


def default_parallel_threads() -> int:
    return max(1, os.cpu_count() or 1)
