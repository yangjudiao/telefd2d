#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <string>
#include <stdexcept>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace py = pybind11;

using ArrayD1 = py::array_t<double, py::array::c_style | py::array::forcecast>;
using ArrayD2 = py::array_t<double, py::array::c_style | py::array::forcecast>;
using ArrayI1 = py::array_t<long long, py::array::c_style | py::array::forcecast>;

inline std::size_t idx2(const int i, const int j, const int n2) {
    return static_cast<std::size_t>(i) * static_cast<std::size_t>(n2) + static_cast<std::size_t>(j);
}

bool has_openmp() {
#ifdef _OPENMP
    return true;
#else
    return false;
#endif
}

int max_threads() {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

py::tuple run_fd_pm_core_cpp(
    const ArrayD2 &bx_in,
    const ArrayD2 &bz_in,
    const ArrayD2 &mu_xz_in,
    const ArrayD2 &eta_xx_x_in,
    const ArrayD2 &eta_xx_z_in,
    const ArrayD2 &eta_zz_x_in,
    const ArrayD2 &eta_zz_z_in,
    const ArrayI1 &receiver_idx_in,
    const ArrayD1 &p0s_in,
    const ArrayD1 &wav_in,
    const int ifleft,
    const double fp,
    const double pml_velocity,
    const double dx,
    const double dz,
    const double dt,
    const int nbx,
    const int nbz,
    int source_z_idx,
    int n_snapshots,
    const double pml_reflect_coeff,
    const int pml_power,
    const double pml_kappa_max,
    int n_threads,
    const int seismo_stride_t,
    const int seismo_stride_x,
    const int snapshot_stride_x,
    const int snapshot_stride_z,
    const int progress_stride_t,
    const double progress_min_interval_s,
    const py::object &snap_vx_out_obj,
    const py::object &snap_vz_out_obj,
    const py::object &seismo_vx_out_obj,
    const py::object &seismo_vz_out_obj,
    const py::object &snap_it_out_obj) {
    const auto eta_xx_x_buf = eta_xx_x_in.request();
    const auto eta_xx_z_buf = eta_xx_z_in.request();
    const auto eta_zz_x_buf = eta_zz_x_in.request();
    const auto eta_zz_z_buf = eta_zz_z_in.request();
    const auto bx_buf = bx_in.request();
    const auto bz_buf = bz_in.request();
    const auto mu_xz_buf = mu_xz_in.request();
    const auto receiver_idx_buf = receiver_idx_in.request();
    const auto p0s_buf = p0s_in.request();
    const auto wav_buf = wav_in.request();

    if (eta_xx_x_buf.ndim != 2 || eta_xx_z_buf.ndim != 2 || eta_zz_x_buf.ndim != 2 || eta_zz_z_buf.ndim != 2) {
        throw std::invalid_argument("eta arrays must be 2D.");
    }
    if (bx_buf.ndim != 2 || bz_buf.ndim != 2 || mu_xz_buf.ndim != 2) {
        throw std::invalid_argument("bx/bz/mu_xz arrays must be 2D.");
    }
    if (receiver_idx_buf.ndim != 1 || p0s_buf.ndim != 1 || wav_buf.ndim != 1) {
        throw std::invalid_argument("receiver_idx, p0s, wav must be 1D.");
    }

    const int nx = static_cast<int>(eta_xx_x_buf.shape[0]);
    const int nz = static_cast<int>(eta_xx_x_buf.shape[1]);
    const int nt = static_cast<int>(wav_buf.shape[0]);

    if (eta_xx_z_buf.shape[0] != nx || eta_xx_z_buf.shape[1] != nz || eta_zz_x_buf.shape[0] != nx ||
        eta_zz_x_buf.shape[1] != nz || eta_zz_z_buf.shape[0] != nx || eta_zz_z_buf.shape[1] != nz) {
        throw std::invalid_argument("eta arrays must share identical shape.");
    }
    if (bx_buf.shape[0] != nx - 1 || bx_buf.shape[1] != nz) {
        throw std::invalid_argument("bx must have shape (nx-1, nz).");
    }
    if (bz_buf.shape[0] != nx || bz_buf.shape[1] != nz - 1) {
        throw std::invalid_argument("bz must have shape (nx, nz-1).");
    }
    if (mu_xz_buf.shape[0] != nx - 1 || mu_xz_buf.shape[1] != nz - 1) {
        throw std::invalid_argument("mu_xz must have shape (nx-1, nz-1).");
    }
    if (receiver_idx_buf.shape[0] != nx || p0s_buf.shape[0] != nx) {
        throw std::invalid_argument("receiver_idx and p0s lengths must be nx.");
    }

    const double *eta_xx_x = static_cast<const double *>(eta_xx_x_buf.ptr);
    const double *eta_xx_z = static_cast<const double *>(eta_xx_z_buf.ptr);
    const double *eta_zz_x = static_cast<const double *>(eta_zz_x_buf.ptr);
    const double *eta_zz_z = static_cast<const double *>(eta_zz_z_buf.ptr);
    const double *bx = static_cast<const double *>(bx_buf.ptr);
    const double *bz = static_cast<const double *>(bz_buf.ptr);
    const double *mu_xz = static_cast<const double *>(mu_xz_buf.ptr);
    const long long *receiver_idx = static_cast<const long long *>(receiver_idx_buf.ptr);
    const double *p0s = static_cast<const double *>(p0s_buf.ptr);
    const double *wav = static_cast<const double *>(wav_buf.ptr);

    n_snapshots = std::max(0, n_snapshots);
    const int seis_t_stride = std::max(1, seismo_stride_t);
    const int seis_x_stride = std::max(1, seismo_stride_x);
    const int snap_x_stride = std::max(1, snapshot_stride_x);
    const int snap_z_stride = std::max(1, snapshot_stride_z);
    const int progress_stride = std::max(0, progress_stride_t);
    const double progress_min_interval = std::max(0.0, progress_min_interval_s);

    const int t_step = (n_snapshots > 0) ? std::max(1, nt / n_snapshots) : (nt + 1);
    const int n_seis_t = (nt + seis_t_stride - 1) / seis_t_stride;
    const int n_seis_x = (nx + seis_x_stride - 1) / seis_x_stride;
    const int nx_snap = (nx + snap_x_stride - 1) / snap_x_stride;
    const int nz_snap = (nz + snap_z_stride - 1) / snap_z_stride;

    const std::size_t nxy = static_cast<std::size_t>(nx) * static_cast<std::size_t>(nz);
    const std::size_t n_seis = static_cast<std::size_t>(n_seis_t) * static_cast<std::size_t>(n_seis_x);
    const std::size_t n_snap_grid =
        static_cast<std::size_t>(n_snapshots) * static_cast<std::size_t>(nx_snap) * static_cast<std::size_t>(nz_snap);

    const auto ensure_or_alloc_d3 = [&](const py::object &obj, const std::array<py::ssize_t, 3> &shape,
                                        const char *name) -> py::array_t<double> {
        if (obj.is_none()) {
            return py::array_t<double>({shape[0], shape[1], shape[2]});
        }
        auto arr = py::cast<py::array_t<double>>(obj);
        const auto buf = arr.request();
        if (buf.ndim != 3 || buf.shape[0] != shape[0] || buf.shape[1] != shape[1] || buf.shape[2] != shape[2]) {
            throw std::invalid_argument(std::string(name) + " shape mismatch.");
        }
        return arr;
    };

    const auto ensure_or_alloc_d2 = [&](const py::object &obj, const std::array<py::ssize_t, 2> &shape,
                                        const char *name) -> py::array_t<double> {
        if (obj.is_none()) {
            return py::array_t<double>({shape[0], shape[1]});
        }
        auto arr = py::cast<py::array_t<double>>(obj);
        const auto buf = arr.request();
        if (buf.ndim != 2 || buf.shape[0] != shape[0] || buf.shape[1] != shape[1]) {
            throw std::invalid_argument(std::string(name) + " shape mismatch.");
        }
        return arr;
    };

    const auto ensure_or_alloc_i1 = [&](const py::object &obj, const py::ssize_t length,
                                        const char *name) -> py::array_t<long long> {
        if (obj.is_none()) {
            return py::array_t<long long>({length});
        }
        auto arr = py::cast<py::array_t<long long>>(obj);
        const auto buf = arr.request();
        if (buf.ndim != 1 || buf.shape[0] != length) {
            throw std::invalid_argument(std::string(name) + " shape mismatch.");
        }
        return arr;
    };

    py::array_t<double> snap_vx_out =
        ensure_or_alloc_d3(snap_vx_out_obj, {n_snapshots, nx_snap, nz_snap}, "snap_vx_out");
    py::array_t<double> snap_vz_out =
        ensure_or_alloc_d3(snap_vz_out_obj, {n_snapshots, nx_snap, nz_snap}, "snap_vz_out");
    py::array_t<double> seismo_vx_out =
        ensure_or_alloc_d2(seismo_vx_out_obj, {n_seis_t, n_seis_x}, "seismo_vx_out");
    py::array_t<double> seismo_vz_out =
        ensure_or_alloc_d2(seismo_vz_out_obj, {n_seis_t, n_seis_x}, "seismo_vz_out");
    py::array_t<long long> snap_it_out = ensure_or_alloc_i1(snap_it_out_obj, n_snapshots, "snap_it_out");

    auto snap_vx_buf = snap_vx_out.request();
    auto snap_vz_buf = snap_vz_out.request();
    auto seismo_vx_buf = seismo_vx_out.request();
    auto seismo_vz_buf = seismo_vz_out.request();
    auto snap_it_buf = snap_it_out.request();

    auto *snap_vx_ptr = static_cast<double *>(snap_vx_buf.ptr);
    auto *snap_vz_ptr = static_cast<double *>(snap_vz_buf.ptr);
    auto *seismo_vx_ptr = static_cast<double *>(seismo_vx_buf.ptr);
    auto *seismo_vz_ptr = static_cast<double *>(seismo_vz_buf.ptr);
    auto *snap_it_ptr = static_cast<long long *>(snap_it_buf.ptr);

    std::fill(snap_vx_ptr, snap_vx_ptr + n_snap_grid, 0.0);
    std::fill(snap_vz_ptr, snap_vz_ptr + n_snap_grid, 0.0);
    std::fill(seismo_vx_ptr, seismo_vx_ptr + n_seis, 0.0);
    std::fill(seismo_vz_ptr, seismo_vz_ptr + n_seis, 0.0);
    std::fill(snap_it_ptr, snap_it_ptr + n_snapshots, 0LL);

    std::vector<double> vx(nxy, 0.0);
    std::vector<double> vz(nxy, 0.0);
    std::vector<double> tauxx(nxy, 0.0);
    std::vector<double> tauzz(nxy, 0.0);
    std::vector<double> tauxz(nxy, 0.0);

    std::vector<double> memo_dvx_x(nxy, 0.0);
    std::vector<double> memo_dvz_x(nxy, 0.0);
    std::vector<double> memo_dtauxx_x(nxy, 0.0);
    std::vector<double> memo_dtauxz_x(nxy, 0.0);

    std::vector<double> memo_dvx_z(nxy, 0.0);
    std::vector<double> memo_dvz_z(nxy, 0.0);
    std::vector<double> memo_dtauxz_z(nxy, 0.0);
    std::vector<double> memo_dtauzz_z(nxy, 0.0);

    constexpr double kPi = 3.14159265358979323846;
    const double alpha_max = kPi * fp;
    const double kappa_max_v = pml_kappa_max;
    const double R = pml_reflect_coeff;
    const int npower = pml_power;

    std::vector<double> d_x(2 * nx, 0.0);
    std::vector<double> kappa_x(2 * nx, 1.0);
    std::vector<double> alpha_x(2 * nx, 0.0);
    std::vector<double> a_x(2 * nx, 0.0);

    const double thi_x = static_cast<double>(std::max(1, nbx)) * dx;
    const double ori_left = thi_x;
    const double ori_right = (2.0 * static_cast<double>(nx) - 1.0) * dx / 2.0 - thi_x;
    const double d0_x = -(npower + 1.0) * pml_velocity * std::log(R) / (2.0 * thi_x);

    for (int i = 0; i < 2 * nx; ++i) {
        const double ax = static_cast<double>(i) * dx / 2.0;

        const double dis_left = ori_left - ax;
        if (dis_left >= 0.0) {
            const double ratio = dis_left / thi_x;
            d_x[i] = d0_x * std::pow(ratio, npower);
            kappa_x[i] = 1.0 + (kappa_max_v - 1.0) * ratio * ratio;
            alpha_x[i] = alpha_max * (1.0 - ratio);
        }

        const double dis_right = ax - ori_right;
        if (dis_right >= 0.0) {
            const double ratio = dis_right / thi_x;
            d_x[i] = d0_x * std::pow(ratio, npower);
            kappa_x[i] = 1.0 + (kappa_max_v - 1.0) * ratio * ratio;
            alpha_x[i] = alpha_max * (1.0 - ratio);
        }
    }

    std::vector<double> b_x(2 * nx, 0.0);
    for (int i = 0; i < 2 * nx; ++i) {
        b_x[i] = std::exp(-(d_x[i] / kappa_x[i] + alpha_x[i]) * dt);
        if (d_x[i] > 1e-6) {
            a_x[i] = d_x[i] * (b_x[i] - 1.0) / (kappa_x[i] * (d_x[i] + kappa_x[i] * alpha_x[i]));
        }
    }

    std::vector<double> kappa_x_cen(nx, 1.0);
    std::vector<double> kappa_x_half(nx, 1.0);
    std::vector<double> a_x_cen(nx, 0.0);
    std::vector<double> a_x_half(nx, 0.0);
    std::vector<double> b_x_cen(nx, 0.0);
    std::vector<double> b_x_half(nx, 0.0);
    for (int i = 0; i < nx; ++i) {
        kappa_x_cen[i] = kappa_x[2 * i];
        kappa_x_half[i] = kappa_x[2 * i + 1];
        a_x_cen[i] = a_x[2 * i];
        a_x_half[i] = a_x[2 * i + 1];
        b_x_cen[i] = b_x[2 * i];
        b_x_half[i] = b_x[2 * i + 1];
    }

    std::vector<double> d_z(2 * nz, 0.0);
    std::vector<double> kappa_z(2 * nz, 1.0);
    std::vector<double> alpha_z(2 * nz, 0.0);
    std::vector<double> a_z(2 * nz, 0.0);

    const double thi_z = static_cast<double>(std::max(1, nbz)) * dz;
    const double ori_lower = (2.0 * static_cast<double>(nz) - 1.0) * dz / 2.0 - thi_z;
    const double d0_z = -(npower + 1.0) * pml_velocity * std::log(R) / (2.0 * thi_z);

    for (int i = 0; i < 2 * nz; ++i) {
        const double az = static_cast<double>(i) * dz / 2.0;
        const double dis_lower = az - ori_lower;
        if (dis_lower >= 0.0) {
            const double ratio = dis_lower / thi_z;
            d_z[i] = d0_z * std::pow(ratio, npower);
            kappa_z[i] = 1.0 + (kappa_max_v - 1.0) * ratio * ratio;
            alpha_z[i] = alpha_max * (1.0 - ratio);
        }
    }

    std::vector<double> b_z(2 * nz, 0.0);
    for (int i = 0; i < 2 * nz; ++i) {
        b_z[i] = std::exp(-(d_z[i] / kappa_z[i] + alpha_z[i]) * dt);
        if (d_z[i] > 1e-6) {
            a_z[i] = d_z[i] * (b_z[i] - 1.0) / (kappa_z[i] * (d_z[i] + kappa_z[i] * alpha_z[i]));
        }
    }

    std::vector<double> kappa_z_cen(nz, 1.0);
    std::vector<double> kappa_z_half(nz, 1.0);
    std::vector<double> a_z_cen(nz, 0.0);
    std::vector<double> a_z_half(nz, 0.0);
    std::vector<double> b_z_cen(nz, 0.0);
    std::vector<double> b_z_half(nz, 0.0);
    for (int i = 0; i < nz; ++i) {
        kappa_z_cen[i] = kappa_z[2 * i];
        kappa_z_half[i] = kappa_z[2 * i + 1];
        a_z_cen[i] = a_z[2 * i];
        a_z_half[i] = a_z[2 * i + 1];
        b_z_cen[i] = b_z[2 * i];
        b_z_half[i] = b_z[2 * i + 1];
    }

    std::vector<double> tdif(nx, 0.0);
    if (nx > 1) {
        if (ifleft == 0) {
            double accum = 0.0;
            for (int i = 1; i < nx; ++i) {
                const double p0s_mid = (p0s[i] + p0s[i - 1]) / 2.0;
                accum += p0s_mid * dx / 1000.0;
                tdif[i] = accum;
            }
        } else {
            double accum = 0.0;
            for (int i = nx - 2; i >= 0; --i) {
                const double p0s_mid = (p0s[i + 1] + p0s[i]) / 2.0;
                accum += p0s_mid * dx / 1000.0;
                tdif[i] = accum;
            }
        }
    }

    source_z_idx = std::min(std::max(source_z_idx, 0), nz - 2);

    if (n_threads < 1) {
        n_threads = 1;
    }
    const bool use_parallel = n_threads > 1;
#ifdef _OPENMP
    if (use_parallel) {
        omp_set_num_threads(n_threads);
    }
#endif

    int snap_ind = 0;
    const auto progress_t0 = std::chrono::steady_clock::now();
    auto progress_last = progress_t0;
    bool progress_printed = false;

    const auto maybe_print_progress = [&](const int it, const bool force) {
        if (progress_stride <= 0) {
            return;
        }
        if (!force && (it % progress_stride != 0)) {
            return;
        }
        const auto now = std::chrono::steady_clock::now();
        if (!force) {
            const double sec_since_last = std::chrono::duration<double>(now - progress_last).count();
            if (progress_printed && sec_since_last < progress_min_interval) {
                return;
            }
        }

        const int done = it + 1;
        const double elapsed_s = std::chrono::duration<double>(now - progress_t0).count();
        const double percent = 100.0 * static_cast<double>(done) / static_cast<double>(nt);
        const double speed_it_per_s = (elapsed_s > 1e-12) ? static_cast<double>(done) / elapsed_s : 0.0;
        const double eta_s = (speed_it_per_s > 1e-12) ? static_cast<double>(nt - done) / speed_it_per_s : 0.0;

        std::cout << "\r[fd_core] it " << done << "/" << nt << " (" << std::fixed << std::setprecision(2)
                  << percent << "%)"
                  << " elapsed=" << std::setprecision(1) << elapsed_s << "s"
                  << " eta=" << std::setprecision(1) << eta_s << "s" << std::flush;
        progress_last = now;
        progress_printed = true;
    };

    {
        py::gil_scoped_release release;

        for (int it = 0; it < nt; ++it) {
            const double current_t = static_cast<double>(it) * dt;

#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (use_parallel)
#endif
        for (int i = 1; i < nx; ++i) {
            for (int j = 0; j < nz; ++j) {
                const std::size_t id = idx2(i, j, nz);
                const std::size_t id_im1 = idx2(i - 1, j, nz);

                double dvx_x = (vx[id] - vx[id_im1]) / dx;
                double dvz_z = 0.0;
                if (j > 0) {
                    dvz_z = (vz[id] - vz[idx2(i, j - 1, nz)]) / dz;
                }

                memo_dvx_x[id] = b_x_half[i] * memo_dvx_x[id] + a_x_half[i] * dvx_x;
                memo_dvz_z[id] = b_z_cen[j] * memo_dvz_z[id] + a_z_cen[j] * dvz_z;

                dvx_x = dvx_x / kappa_x_half[i] + memo_dvx_x[id];
                dvz_z = dvz_z / kappa_z_cen[j] + memo_dvz_z[id];

                tauxx[id] += (eta_xx_x[id] * dvx_x + eta_xx_z[id] * dvz_z) * dt;
                tauzz[id] += (eta_zz_x[id] * dvx_x + eta_zz_z[id] * dvz_z) * dt;
            }
        }

#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (use_parallel)
#endif
        for (int i = 0; i < nx - 1; ++i) {
            for (int j = 0; j < nz - 1; ++j) {
                const std::size_t id = idx2(i, j, nz);
                const double dvx_z = (vx[idx2(i, j + 1, nz)] - vx[id]) / dz;
                const double dvz_x = (vz[idx2(i + 1, j, nz)] - vz[id]) / dx;

                memo_dvz_x[id] = b_x_cen[i] * memo_dvz_x[id] + a_x_cen[i] * dvz_x;
                memo_dvx_z[id] = b_z_half[j] * memo_dvx_z[id] + a_z_half[j] * dvx_z;

                const double dvz_x_m = dvz_x / kappa_x_cen[i] + memo_dvz_x[id];
                const double dvx_z_m = dvx_z / kappa_z_half[j] + memo_dvx_z[id];

                tauxz[id] += mu_xz[idx2(i, j, nz - 1)] * (dvx_z_m + dvz_x_m) * dt;
            }
        }

#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (use_parallel)
#endif
        for (int i = 0; i < nx - 1; ++i) {
            for (int j = 0; j < nz; ++j) {
                const std::size_t id = idx2(i, j, nz);
                const double dtauxx_x = (tauxx[idx2(i + 1, j, nz)] - tauxx[id]) / dx;

                double dtauxz_z = 0.0;
                if (j == 0) {
                    dtauxz_z = tauxz[idx2(i, 0, nz)] / dz;
                } else {
                    dtauxz_z = (tauxz[idx2(i, j, nz)] - tauxz[idx2(i, j - 1, nz)]) / dz;
                }

                memo_dtauxx_x[id] = b_x_cen[i] * memo_dtauxx_x[id] + a_x_cen[i] * dtauxx_x;
                memo_dtauxz_z[id] = b_z_half[j] * memo_dtauxz_z[id] + a_z_half[j] * dtauxz_z;

                const double dtauxx_x_m = dtauxx_x / kappa_x_cen[i] + memo_dtauxx_x[id];
                const double dtauxz_z_m = dtauxz_z / kappa_z_half[j] + memo_dtauxz_z[id];

                vx[id] += (dtauxx_x_m + dtauxz_z_m) * dt * bx[idx2(i, j, nz)];
            }
        }

#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (use_parallel)
#endif
        for (int i = 1; i < nx; ++i) {
            for (int j = 0; j < nz - 1; ++j) {
                const std::size_t id = idx2(i, j, nz);
                const double dtauzx_x = (tauxz[id] - tauxz[idx2(i - 1, j, nz)]) / dx;
                const double dtauzz_z = (tauzz[idx2(i, j + 1, nz)] - tauzz[id]) / dz;

                memo_dtauxz_x[id] = b_x_half[i] * memo_dtauxz_x[id] + a_x_half[i] * dtauzx_x;
                memo_dtauzz_z[id] = b_z_cen[j] * memo_dtauzz_z[id] + a_z_cen[j] * dtauzz_z;

                const double dtauzx_x_m = dtauzx_x / kappa_x_half[i] + memo_dtauxz_x[id];
                const double dtauzz_z_m = dtauzz_z / kappa_z_cen[j] + memo_dtauzz_z[id];

                vz[id] += (dtauzx_x_m + dtauzz_z_m) * dt * bz[idx2(i, j, nz - 1)];
            }
        }

        for (int i = 0; i < nx; ++i) {
            const int tind = static_cast<int>((-tdif[i] + current_t) / dt);
            if (tind >= 0 && tind < nt) {
                const std::size_t id_src = idx2(i, source_z_idx, nz);
                const double amp = wav[tind];
                tauxx[id_src] += amp;
                tauzz[id_src] += amp;
            }
        }

        if (it % seis_t_stride == 0) {
            const int seis_ti = it / seis_t_stride;
#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (use_parallel)
#endif
            for (int ri = 0; ri < n_seis_x; ++ri) {
                int i = ri * seis_x_stride;
                if (i >= nx) {
                    i = nx - 1;
                }
                const std::size_t sid =
                    static_cast<std::size_t>(seis_ti) * static_cast<std::size_t>(n_seis_x) + static_cast<std::size_t>(ri);

                int rec_z_vz = static_cast<int>(receiver_idx[i]);
                rec_z_vz = std::min(std::max(rec_z_vz, 0), nz - 1);
                const std::size_t rid_vz = idx2(i, rec_z_vz, nz);
                seismo_vz_ptr[sid] = vz[rid_vz];

                // vx is defined on x-staggered points. Use a depth below both adjacent
                // surface samples to avoid sampling half-air nodes on stepped topography.
                const int i_vx = std::min(i, nx - 2);
                int rec_l = static_cast<int>(receiver_idx[i_vx]);
                int rec_r = static_cast<int>(receiver_idx[std::min(i_vx + 1, nx - 1)]);
                int rec_z_vx = std::max(rec_l, rec_r);
                rec_z_vx = std::min(std::max(rec_z_vx, 0), nz - 1);
                const std::size_t rid_vx = idx2(i_vx, rec_z_vx, nz);
                seismo_vx_ptr[sid] = vx[rid_vx];
            }
        }

        if ((it % t_step == 0) && (snap_ind < n_snapshots)) {
            const std::size_t off = static_cast<std::size_t>(snap_ind) * static_cast<std::size_t>(nx_snap) *
                                    static_cast<std::size_t>(nz_snap);
#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (use_parallel)
#endif
            for (int ix = 0; ix < nx_snap; ++ix) {
                int i = ix * snap_x_stride;
                if (i >= nx) {
                    i = nx - 1;
                }
                for (int iz = 0; iz < nz_snap; ++iz) {
                    int j = iz * snap_z_stride;
                    if (j >= nz) {
                        j = nz - 1;
                    }
                    const std::size_t dst = off + static_cast<std::size_t>(ix) * static_cast<std::size_t>(nz_snap) +
                                            static_cast<std::size_t>(iz);
                    const std::size_t src = idx2(i, j, nz);
                    snap_vx_ptr[dst] = vx[src];
                    snap_vz_ptr[dst] = vz[src];
                }
            }
            snap_it_ptr[snap_ind] = static_cast<long long>(it);
            ++snap_ind;
        }

            maybe_print_progress(it, it == nt - 1);
        }

        if (progress_printed) {
            std::cout << std::endl;
        }
    }

    return py::make_tuple(snap_vx_out, snap_vz_out, seismo_vx_out, seismo_vz_out, snap_it_out);
}

PYBIND11_MODULE(_fd_core, m) {
    m.doc() = "C++ accelerated FD PM core with optional OpenMP parallelization";

    m.def("run_fd_pm_core_cpp", &run_fd_pm_core_cpp, py::arg("bx"), py::arg("bz"), py::arg("mu_xz"),
          py::arg("eta_xx_x"), py::arg("eta_xx_z"), py::arg("eta_zz_x"), py::arg("eta_zz_z"),
          py::arg("receiver_idx"), py::arg("p0s"), py::arg("wav"), py::arg("ifleft"), py::arg("fp"),
          py::arg("pml_velocity"), py::arg("dx"), py::arg("dz"), py::arg("dt"), py::arg("nbx"),
          py::arg("nbz"), py::arg("source_z_idx"), py::arg("n_snapshots"), py::arg("pml_reflect_coeff"),
          py::arg("pml_power"), py::arg("pml_kappa_max"), py::arg("n_threads") = 1,
          py::arg("seismo_stride_t") = 1, py::arg("seismo_stride_x") = 1, py::arg("snapshot_stride_x") = 1,
          py::arg("snapshot_stride_z") = 1, py::arg("progress_stride_t") = 0,
          py::arg("progress_min_interval_s") = 1.0, py::arg("snap_vx_out") = py::none(),
          py::arg("snap_vz_out") = py::none(), py::arg("seismo_vx_out") = py::none(),
          py::arg("seismo_vz_out") = py::none(), py::arg("snap_it_out") = py::none());

    m.def("has_openmp", &has_openmp);
    m.def("max_threads", &max_threads);
}
