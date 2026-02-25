from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SimulationConfig:
    width_km: float = 1000.0
    depth_km: float = 60.0
    vp_m_s: float = 3200.0
    vs_m_s: float = 1850.0
    rho_kg_m3: float = 2400.0
    f0_hz: float = 0.25
    angle_from_z_deg: float = 20.0
    # Cao2018 recommends ~15 PPW to control staircase diffraction.
    points_per_min_wavelength: float = 15.0
    fmax_factor: float = 2.5
    cfl: float = 0.35
    pml_ratio_x: float = 0.24
    pml_ratio_z: float = 0.20
    pml_min_cells_x: int = 48
    pml_min_cells_z: int = 16
    pml_reflect_coeff: float = 1.0e-6
    pml_power: int = 2
    pml_kappa_max: float = 1.0
    source_scale: float = 2.0e7
    n_snapshots: int = 60
    topo_amplitude_km: float = 5.0
    topo_mean_depth_km: float = 5.0
    topo_cycles: float = 4.0
    source_depth_margin_cells: int = 3


@dataclass(frozen=True)
class GridSpec:
    dx_m: float
    dz_m: float
    dt_s: float
    nt: int
    nx_phys: int
    nz_phys: int
    nbx: int
    nbz: int
    nx_total: int
    nz_total: int

    @property
    def x0(self) -> int:
        return self.nbx

    @property
    def x1(self) -> int:
        return self.nbx + self.nx_phys

    @property
    def z0(self) -> int:
        return 0

    @property
    def z1(self) -> int:
        return self.nz_phys


def auto_grid_from_frequency(cfg: SimulationConfig) -> GridSpec:
    width_m = cfg.width_km * 1_000.0
    depth_m = cfg.depth_km * 1_000.0

    fmax = cfg.f0_hz * cfg.fmax_factor
    vmin = min(cfg.vp_m_s, cfg.vs_m_s)
    target_spacing = vmin / (cfg.points_per_min_wavelength * fmax)

    nx_phys = max(160, math.ceil(width_m / target_spacing))
    nz_phys = max(64, math.ceil(depth_m / target_spacing))

    dx_m = width_m / nx_phys
    dz_m = depth_m / nz_phys

    nbx = max(cfg.pml_min_cells_x, math.ceil(nx_phys * cfg.pml_ratio_x))
    nbz = max(cfg.pml_min_cells_z, math.ceil(nz_phys * cfg.pml_ratio_z))

    nx_total = nx_phys + 2 * nbx
    nz_total = nz_phys + nbz

    dt_stable = cfg.cfl * min(dx_m, dz_m) / (math.sqrt(2.0) * cfg.vp_m_s)
    travel_time = math.sqrt(width_m**2 + depth_m**2) / cfg.vp_m_s
    source_time = 8.0 / cfg.f0_hz
    tmax = travel_time + source_time + 20.0
    nt = max(1_200, math.ceil(tmax / dt_stable))
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
