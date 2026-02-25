from __future__ import annotations

import numpy as np


def make_scaled_ricker(f0_hz: float, nt: int, dt_s: float, source_scale: float) -> np.ndarray:
    t = np.arange(nt, dtype=np.float64) * dt_s
    t0 = 1.5 / f0_hz
    a = (np.pi * f0_hz * (t - t0)) ** 2
    ricker = (1.0 - 2.0 * a) * np.exp(-a)

    # Source-time function: direct Ricker wavelet.
    ricker /= np.max(np.abs(ricker)) + 1e-12
    return ricker * source_scale
