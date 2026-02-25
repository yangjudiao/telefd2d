from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np

from .config import GridSpec


def compute_p_and_curl(snap_vx: np.ndarray, snap_vz: np.ndarray, dx: float, dz: float) -> tuple[np.ndarray, np.ndarray]:
    dvx_dx = np.gradient(snap_vx, dx, axis=1)
    dvz_dz = np.gradient(snap_vz, dz, axis=2)
    dvz_dx = np.gradient(snap_vz, dx, axis=1)
    dvx_dz = np.gradient(snap_vx, dz, axis=2)
    p = dvx_dx + dvz_dz
    curl = dvz_dx - dvx_dz
    return p, curl


def _boundary_overlay(
    ax: plt.Axes,
    grid: GridSpec,
    surface_idx: np.ndarray,
    source_z_idx: int,
) -> None:
    x_km = np.arange(grid.nx_total) * grid.dx_m / 1_000.0
    z_km = surface_idx * grid.dz_m / 1_000.0

    left_x = grid.nbx * grid.dx_m / 1_000.0
    right_x = (grid.nbx + grid.nx_phys) * grid.dx_m / 1_000.0
    bottom_z = grid.nz_phys * grid.dz_m / 1_000.0

    ax.axvline(left_x, color="k", lw=1.0, ls="--", label="PML boundary")
    ax.axvline(right_x, color="k", lw=1.0, ls="--")
    ax.axhline(bottom_z, color="k", lw=1.0, ls="--")
    ax.plot(x_km, z_km, color="lime", lw=1.2, label="Free surface")

    sz = source_z_idx * grid.dz_m / 1_000.0
    ax.axhline(sz, color="yellow", lw=0.9, ls=":", label="Source injection line")


def save_wavefield_gif(
    field: np.ndarray,
    grid: GridSpec,
    times: np.ndarray,
    out_path: Path,
    title: str,
    surface_idx: np.ndarray,
    source_z_idx: int,
    fps: int = 10,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vmax = np.percentile(np.abs(field), 99.0) + 1e-12
    frames: list[np.ndarray] = []
    extent = [0.0, grid.nx_total * grid.dx_m / 1_000.0, grid.nz_total * grid.dz_m / 1_000.0, 0.0]

    for i in range(field.shape[0]):
        fig, ax = plt.subplots(figsize=(10, 3.8), dpi=120)
        im = ax.imshow(
            field[i].T,
            cmap="seismic",
            vmin=-vmax,
            vmax=vmax,
            aspect="auto",
            origin="upper",
            extent=extent,
        )
        _boundary_overlay(
            ax=ax,
            grid=grid,
            surface_idx=surface_idx,
            source_z_idx=source_z_idx,
        )
        ax.set_title(f"{title} | full domain with PML | t={times[i]:.2f}s")
        ax.set_xlabel("x (km)")
        ax.set_ylabel("z (km)")
        ax.legend(loc="upper right", fontsize=7)
        fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        fig.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        frames.append(imageio.imread(buf))

    imageio.mimsave(out_path, frames, fps=fps)


def save_surface_seismogram(
    seismogram: np.ndarray,
    grid: GridSpec,
    dt_s: float,
    out_png: Path,
    out_npy: Path,
    component: str,
) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_npy, seismogram)

    vmax = np.percentile(np.abs(seismogram), 99.5) + 1e-12
    tmax = seismogram.shape[0] * dt_s
    xmax = seismogram.shape[1] * grid.dx_m / 1_000.0

    left_x = grid.nbx * grid.dx_m / 1_000.0
    right_x = (grid.nbx + grid.nx_phys) * grid.dx_m / 1_000.0

    plt.figure(figsize=(10, 4.2), dpi=140)
    plt.imshow(
        seismogram,
        cmap="Greys",
        aspect="auto",
        origin="upper",
        extent=[0.0, xmax, tmax, 0.0],
        vmin=-vmax,
        vmax=vmax,
    )
    plt.axvline(left_x, color="red", lw=1.0, ls="--", label="PML boundary")
    plt.axvline(right_x, color="red", lw=1.0, ls="--")
    plt.axhline(0.0, color="lime", lw=1.2, label="Free-surface receiver line")
    plt.xlabel("x (km)")
    plt.ylabel("time (s)")
    plt.title(f"Surface Seismogram ({component}) | full x-domain including PML")
    plt.legend(loc="upper right", fontsize=7)
    plt.colorbar(fraction=0.03, pad=0.02)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()


def boundary_energy_ratio(vz_snap: np.ndarray, grid: GridSpec) -> float:
    left = vz_snap[:, : grid.nbx, : grid.nz_phys]
    right = vz_snap[:, grid.nbx + grid.nx_phys :, : grid.nz_phys]
    bottom = vz_snap[:, :, grid.nz_phys :]
    inner = vz_snap[:, grid.nbx : grid.nbx + grid.nx_phys, : grid.nz_phys]

    edge_energy = (np.mean(left**2) + np.mean(right**2) + np.mean(bottom**2)) / 3.0
    inner_energy = np.mean(inner**2) + 1e-12
    return float(edge_energy / inner_energy)


def write_run_metadata(out_json: Path, payload: dict) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
