from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import GridSpec, SimulationConfig


AIR = np.int8(0)
INTERIOR = np.int8(1)
H_BOUNDARY = np.int8(2)
VL_BOUNDARY = np.int8(3)
VR_BOUNDARY = np.int8(4)
OUTER_CORNER = np.int8(5)
INNER_CORNER = np.int8(6)


@dataclass(frozen=True)
class PMMediumParameters:
    bx: np.ndarray
    bz: np.ndarray
    mu_xz: np.ndarray
    eta_xx_x: np.ndarray
    eta_xx_z: np.ndarray
    eta_zz_x: np.ndarray
    eta_zz_z: np.ndarray
    surface_idx: np.ndarray
    receiver_idx: np.ndarray
    category: np.ndarray


def build_uniform_model(cfg: SimulationConfig, grid: GridSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vp = np.full((grid.nx_total, grid.nz_total), cfg.vp_m_s, dtype=np.float64)
    vs = np.full((grid.nx_total, grid.nz_total), cfg.vs_m_s, dtype=np.float64)
    rho = np.full((grid.nx_total, grid.nz_total), cfg.rho_kg_m3, dtype=np.float64)
    return vp, vs, rho


def build_surface_topography(cfg: SimulationConfig, grid: GridSpec) -> np.ndarray:
    x_phys = np.linspace(0.0, cfg.width_km, grid.nx_phys, dtype=np.float64)
    phase = 2.0 * np.pi * cfg.topo_cycles * x_phys / max(cfg.width_km, 1e-6)
    relief = cfg.topo_amplitude_km * np.sin(phase)
    depth_km = cfg.topo_mean_depth_km + relief

    # Keep the free surface within the simulated rectangle.
    max_depth_km = max(0.0, cfg.depth_km - 2.0 * grid.dz_m / 1_000.0)
    depth_km = np.clip(depth_km, 0.0, max_depth_km)
    depth_idx_phys = np.rint(depth_km * 1_000.0 / grid.dz_m).astype(np.int64)

    surface_idx = np.zeros(grid.nx_total, dtype=np.int64)
    surface_idx[grid.x0 : grid.x1] = depth_idx_phys

    # Extend edge values into side-PML columns to avoid artificial steps at x-PML interfaces.
    surface_idx[: grid.x0] = depth_idx_phys[0]
    surface_idx[grid.x1 :] = depth_idx_phys[-1]
    return surface_idx


def classify_grid_points(surface_idx: np.ndarray, grid: GridSpec) -> np.ndarray:
    nx = grid.nx_total
    nz = grid.nz_total
    category = np.full((nx, nz), INTERIOR, dtype=np.int8)

    for i in range(nx):
        s = int(surface_idx[i])
        if s > 0:
            category[i, :s] = AIR

    for i in range(nx):
        for j in range(int(surface_idx[i]), nz):
            air_u = j == 0 or j - 1 < surface_idx[i]
            air_l = False if i == 0 else j < surface_idx[i - 1]
            air_r = False if i == nx - 1 else j < surface_idx[i + 1]

            if air_u and (air_l or air_r):
                category[i, j] = OUTER_CORNER
            elif air_u:
                category[i, j] = H_BOUNDARY
            elif air_l and not air_r:
                category[i, j] = VL_BOUNDARY
            elif air_r and not air_l:
                category[i, j] = VR_BOUNDARY
            elif (air_l or air_r) and not air_u:
                category[i, j] = INNER_CORNER
            else:
                category[i, j] = INTERIOR
    return category


def _harmonic2(a: float, b: float) -> float:
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return 2.0 * a * b / (a + b)


def _harmonic4(a: float, b: float, c: float, d: float) -> float:
    if a <= 0.0 or b <= 0.0 or c <= 0.0 or d <= 0.0:
        return 0.0
    return 4.0 / (1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d)


def build_pm_medium_parameters(
    cfg: SimulationConfig,
    grid: GridSpec,
    vp: np.ndarray,
    vs: np.ndarray,
    rho: np.ndarray,
    surface_idx: np.ndarray,
) -> PMMediumParameters:
    nx = grid.nx_total
    nz = grid.nz_total
    eps = 1e-12

    lam = rho * vp**2 - 2.0 * rho * vs**2
    mu = rho * vs**2
    b = 1.0 / rho

    category = classify_grid_points(surface_idx, grid)
    air_mask = category == AIR
    lam = np.where(air_mask, 0.0, lam)
    mu = np.where(air_mask, 0.0, mu)
    b = np.where(air_mask, 0.0, b)

    bx = np.zeros((nx - 1, nz), dtype=np.float64)
    for i in range(nx - 1):
        for j in range(nz):
            bx[i, j] = _harmonic2(b[i, j], b[i + 1, j])

    bz = np.zeros((nx, nz - 1), dtype=np.float64)
    for i in range(nx):
        for j in range(nz - 1):
            bz[i, j] = _harmonic2(b[i, j], b[i, j + 1])

    mu_xz = np.zeros((nx - 1, nz - 1), dtype=np.float64)
    for i in range(nx - 1):
        for j in range(nz - 1):
            mu_xz[i, j] = _harmonic4(mu[i, j], mu[i + 1, j], mu[i, j + 1], mu[i + 1, j + 1])

    eta_xx_x = np.zeros((nx, nz), dtype=np.float64)
    eta_xx_z = np.zeros((nx, nz), dtype=np.float64)
    eta_zz_x = np.zeros((nx, nz), dtype=np.float64)
    eta_zz_z = np.zeros((nx, nz), dtype=np.float64)

    internal = ~air_mask
    eta_xx_x[internal] = lam[internal] + 2.0 * mu[internal]
    eta_xx_z[internal] = lam[internal]
    eta_zz_x[internal] = lam[internal]
    eta_zz_z[internal] = lam[internal] + 2.0 * mu[internal]

    alpha = np.zeros((nx, nz), dtype=np.float64)
    denom = lam + 2.0 * mu + eps
    alpha[internal] = 2.0 * mu[internal] * (lam[internal] + mu[internal]) / denom[internal]

    h_mask = category == H_BOUNDARY
    vlvr_mask = (category == VL_BOUNDARY) | (category == VR_BOUNDARY)
    outer_mask = category == OUTER_CORNER

    eta_xx_x[h_mask] = alpha[h_mask]
    eta_xx_z[h_mask] = 0.0
    eta_zz_x[h_mask] = 0.0
    eta_zz_z[h_mask] = 0.0

    eta_xx_x[vlvr_mask] = 0.0
    eta_xx_z[vlvr_mask] = 0.0
    eta_zz_x[vlvr_mask] = 0.0
    eta_zz_z[vlvr_mask] = alpha[vlvr_mask]

    eta_xx_x[outer_mask] = 0.0
    eta_xx_z[outer_mask] = 0.0
    eta_zz_x[outer_mask] = 0.0
    eta_zz_z[outer_mask] = 0.0

    # Density/parameter adjustments at boundary and transition zones (Cao2018 PM idea).
    for i in range(nx):
        for j in range(nz):
            cat = category[i, j]
            if cat == H_BOUNDARY:
                if i < nx - 1 and bx[i, j] > 0.0:
                    bx[i, j] *= 2.0
            elif cat == VL_BOUNDARY or cat == VR_BOUNDARY:
                if j < nz - 1 and bz[i, j] > 0.0:
                    bz[i, j] *= 2.0
            elif cat == OUTER_CORNER or cat == INNER_CORNER:
                if i < nx - 1 and bx[i, j] > 0.0:
                    bx[i, j] *= 2.0
                if j < nz - 1 and bz[i, j] > 0.0:
                    bz[i, j] *= 2.0
                if i < nx - 1 and j < nz - 1 and mu_xz[i, j] > 0.0:
                    mu_xz[i, j] *= 0.5

    receiver_idx = surface_idx.copy()
    receiver_idx = np.clip(receiver_idx, 0, nz - 2)

    return PMMediumParameters(
        bx=bx,
        bz=bz,
        mu_xz=mu_xz,
        eta_xx_x=eta_xx_x,
        eta_xx_z=eta_xx_z,
        eta_zz_x=eta_zz_x,
        eta_zz_z=eta_zz_z,
        surface_idx=surface_idx,
        receiver_idx=receiver_idx,
        category=category,
    )
