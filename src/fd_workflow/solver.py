from __future__ import annotations

import numpy as np
from numba import jit


@jit(nopython=True, cache=True)
def _run_fd_pm_core(
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    nt = wav.shape[0]
    nx = eta_xx_x.shape[0]
    nz = eta_xx_x.shape[1]

    vx = np.zeros((nx, nz))
    vz = np.zeros((nx, nz))
    tauxx = np.zeros((nx, nz))
    tauzz = np.zeros((nx, nz))
    tauxz = np.zeros((nx, nz))

    seismo_vx = np.zeros((nt, nx))
    seismo_vz = np.zeros((nt, nx))

    n_snapshots = max(1, n_snapshots)
    snap_vx = np.zeros((n_snapshots, nx, nz))
    snap_vz = np.zeros((n_snapshots, nx, nz))
    snap_it = np.zeros(n_snapshots, dtype=np.int64)
    t_step = max(1, nt // n_snapshots)
    snap_ind = 0

    alpha_max = np.pi * fp
    kappa_max = pml_kappa_max
    R = pml_reflect_coeff
    npower = pml_power

    # CPML parameters in x.
    d_x = np.zeros(2 * nx)
    kappa_x = np.ones(2 * nx)
    alpha_x = np.zeros(2 * nx)
    a_x = np.zeros(2 * nx)

    thi_x = max(1, nbx) * dx
    ori_left = thi_x
    ori_right = (2 * nx - 1) * dx / 2.0 - thi_x
    d0_x = -(npower + 1.0) * pml_velocity * np.log(R) / (2.0 * thi_x)

    for i in range(2 * nx):
        ax = i * dx / 2.0
        dis_left = ori_left - ax
        if dis_left >= 0.0:
            ratio = dis_left / thi_x
            d_x[i] = d0_x * ratio**npower
            kappa_x[i] = 1.0 + (kappa_max - 1.0) * ratio**2
            alpha_x[i] = alpha_max * (1.0 - ratio)

        dis_right = ax - ori_right
        if dis_right >= 0.0:
            ratio = dis_right / thi_x
            d_x[i] = d0_x * ratio**npower
            kappa_x[i] = 1.0 + (kappa_max - 1.0) * ratio**2
            alpha_x[i] = alpha_max * (1.0 - ratio)

    b_x = np.exp(-(d_x / kappa_x + alpha_x) * dt)
    for i in range(2 * nx):
        if d_x[i] > 1e-6:
            a_x[i] = d_x[i] * (b_x[i] - 1.0) / (kappa_x[i] * (d_x[i] + kappa_x[i] * alpha_x[i]))

    kappa_x_cen = kappa_x[0 : 2 * nx - 1 : 2]
    kappa_x_half = kappa_x[1 : 2 * nx : 2]
    a_x_cen = a_x[0 : 2 * nx - 1 : 2]
    a_x_half = a_x[1 : 2 * nx : 2]
    b_x_cen = b_x[0 : 2 * nx - 1 : 2]
    b_x_half = b_x[1 : 2 * nx : 2]

    # CPML parameters in z (bottom only).
    d_z = np.zeros(2 * nz)
    kappa_z = np.ones(2 * nz)
    alpha_z = np.zeros(2 * nz)
    a_z = np.zeros(2 * nz)

    thi_z = max(1, nbz) * dz
    ori_lower = (2 * nz - 1) * dz / 2.0 - thi_z
    d0_z = -(npower + 1.0) * pml_velocity * np.log(R) / (2.0 * thi_z)

    for i in range(2 * nz):
        az = i * dz / 2.0
        dis_lower = az - ori_lower
        if dis_lower >= 0.0:
            ratio = dis_lower / thi_z
            d_z[i] = d0_z * ratio**npower
            kappa_z[i] = 1.0 + (kappa_max - 1.0) * ratio**2
            alpha_z[i] = alpha_max * (1.0 - ratio)

    b_z = np.exp(-(d_z / kappa_z + alpha_z) * dt)
    for i in range(2 * nz):
        if d_z[i] > 1e-6:
            a_z[i] = d_z[i] * (b_z[i] - 1.0) / (kappa_z[i] * (d_z[i] + kappa_z[i] * alpha_z[i]))

    kappa_z_cen = kappa_z[0 : 2 * nz - 1 : 2]
    kappa_z_half = kappa_z[1 : 2 * nz : 2]
    a_z_cen = a_z[0 : 2 * nz - 1 : 2]
    a_z_half = a_z[1 : 2 * nz : 2]
    b_z_cen = b_z[0 : 2 * nz - 1 : 2]
    b_z_half = b_z[1 : 2 * nz : 2]

    memo_dvx_x = np.zeros((nx, nz))
    memo_dvz_x = np.zeros((nx, nz))
    memo_dtauxx_x = np.zeros((nx, nz))
    memo_dtauxz_x = np.zeros((nx, nz))

    memo_dvx_z = np.zeros((nx, nz))
    memo_dvz_z = np.zeros((nx, nz))
    memo_dtauxz_z = np.zeros((nx, nz))
    memo_dtauzz_z = np.zeros((nx, nz))

    tdif = np.zeros(nx)
    p0s_mid = (p0s[1:] + p0s[:-1]) / 2.0
    if ifleft == 0:
        dts = np.cumsum(p0s_mid * dx / 1e3)
        tdif[1:] = dts
    else:
        dts = np.cumsum(p0s_mid[::-1] * dx / 1e3)
        tdif[:-1] = dts[::-1]

    source_z_idx = min(max(source_z_idx, 0), nz - 2)

    for it in range(nt):
        current_t = it * dt

        # Update normal stresses.
        for i in range(1, nx):
            for j in range(nz):
                dvx_x = (vx[i, j] - vx[i - 1, j]) / dx
                dvz_z = 0.0
                if j > 0:
                    dvz_z = (vz[i, j] - vz[i, j - 1]) / dz

                memo_dvx_x[i, j] = b_x_half[i] * memo_dvx_x[i, j] + a_x_half[i] * dvx_x
                memo_dvz_z[i, j] = b_z_cen[j] * memo_dvz_z[i, j] + a_z_cen[j] * dvz_z

                dvx_x = dvx_x / kappa_x_half[i] + memo_dvx_x[i, j]
                dvz_z = dvz_z / kappa_z_cen[j] + memo_dvz_z[i, j]

                tauxx[i, j] = tauxx[i, j] + (eta_xx_x[i, j] * dvx_x + eta_xx_z[i, j] * dvz_z) * dt
                tauzz[i, j] = tauzz[i, j] + (eta_zz_x[i, j] * dvx_x + eta_zz_z[i, j] * dvz_z) * dt

        # Update shear stress.
        for i in range(nx - 1):
            for j in range(nz - 1):
                dvx_z = (vx[i, j + 1] - vx[i, j]) / dz
                dvz_x = (vz[i + 1, j] - vz[i, j]) / dx

                memo_dvz_x[i, j] = b_x_cen[i] * memo_dvz_x[i, j] + a_x_cen[i] * dvz_x
                memo_dvx_z[i, j] = b_z_half[j] * memo_dvx_z[i, j] + a_z_half[j] * dvx_z

                dvz_x = dvz_x / kappa_x_cen[i] + memo_dvz_x[i, j]
                dvx_z = dvx_z / kappa_z_half[j] + memo_dvx_z[i, j]

                tauxz[i, j] = tauxz[i, j] + mu_xz[i, j] * (dvx_z + dvz_x) * dt

        # Update vx.
        for i in range(nx - 1):
            for j in range(nz):
                dtauxx_x = (tauxx[i + 1, j] - tauxx[i, j]) / dx
                if j == 0:
                    dtauxz_z = tauxz[i, 0] / dz
                else:
                    dtauxz_z = (tauxz[i, j] - tauxz[i, j - 1]) / dz

                memo_dtauxx_x[i, j] = b_x_cen[i] * memo_dtauxx_x[i, j] + a_x_cen[i] * dtauxx_x
                memo_dtauxz_z[i, j] = b_z_half[j] * memo_dtauxz_z[i, j] + a_z_half[j] * dtauxz_z

                dtauxx_x = dtauxx_x / kappa_x_cen[i] + memo_dtauxx_x[i, j]
                dtauxz_z = dtauxz_z / kappa_z_half[j] + memo_dtauxz_z[i, j]

                vx[i, j] = vx[i, j] + (dtauxx_x + dtauxz_z) * dt * bx[i, j]

        # Update vz.
        for i in range(1, nx):
            for j in range(nz - 1):
                dtauzx_x = (tauxz[i, j] - tauxz[i - 1, j]) / dx
                dtauzz_z = (tauzz[i, j + 1] - tauzz[i, j]) / dz

                memo_dtauxz_x[i, j] = b_x_half[i] * memo_dtauxz_x[i, j] + a_x_half[i] * dtauzx_x
                memo_dtauzz_z[i, j] = b_z_cen[j] * memo_dtauzz_z[i, j] + a_z_cen[j] * dtauzz_z

                dtauzx_x = dtauzx_x / kappa_x_half[i] + memo_dtauxz_x[i, j]
                dtauzz_z = dtauzz_z / kappa_z_cen[j] + memo_dtauzz_z[i, j]

                vz[i, j] = vz[i, j] + (dtauzx_x + dtauzz_z) * dt * bz[i, j]

        # Delayed line source for plane-wave incidence.
        for i in range(nx):
            tind = int((-tdif[i] + current_t) / dt)
            if tind >= 0 and tind < nt:
                tauxx[i, source_z_idx] += wav[tind]
                tauzz[i, source_z_idx] += wav[tind]

        # Record seismograms along topography.
        for i in range(nx):
            rec_z_vz = receiver_idx[i]
            seismo_vz[it, i] = vz[i, rec_z_vz]

            i_vx = i if i < nx - 1 else nx - 2
            rec_z_vx = receiver_idx[i_vx]
            rec_r = receiver_idx[i_vx + 1] if i_vx + 1 < nx else receiver_idx[i_vx]
            if rec_r > rec_z_vx:
                rec_z_vx = rec_r
            seismo_vx[it, i] = vx[i_vx, rec_z_vx]

        if it % t_step == 0 and snap_ind < n_snapshots:
            snap_vx[snap_ind] = vx
            snap_vz[snap_ind] = vz
            snap_it[snap_ind] = it
            snap_ind += 1

    return snap_vx, snap_vz, seismo_vx, seismo_vz, snap_it


def run_fd_plane_wave(
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
) -> dict[str, np.ndarray]:
    snap_vx, snap_vz, seismo_vx, seismo_vz, snap_it = _run_fd_pm_core(
        bx=bx,
        bz=bz,
        mu_xz=mu_xz,
        eta_xx_x=eta_xx_x,
        eta_xx_z=eta_xx_z,
        eta_zz_x=eta_zz_x,
        eta_zz_z=eta_zz_z,
        receiver_idx=receiver_idx,
        p0s=p0s,
        wav=wav,
        ifleft=ifleft,
        fp=fp,
        pml_velocity=pml_velocity,
        dx=dx,
        dz=dz,
        dt=dt,
        nbx=nbx,
        nbz=nbz,
        source_z_idx=source_z_idx,
        n_snapshots=n_snapshots,
        pml_reflect_coeff=pml_reflect_coeff,
        pml_power=pml_power,
        pml_kappa_max=pml_kappa_max,
    )
    return {
        "snap_vx": snap_vx,
        "snap_vz": snap_vz,
        "seismo_vx": seismo_vx,
        "seismo_vz": seismo_vz,
        "snap_it": snap_it,
    }
