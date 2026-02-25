"""FD workflow package for the acceptance forward-model case."""

from .config import GridSpec, SimulationConfig, auto_grid_from_frequency
from .model import PMMediumParameters, build_pm_medium_parameters, build_surface_topography, build_uniform_model
from .postprocess import compute_p_and_curl
from .solver import run_fd_plane_wave
from .solver_boost import run_fd_plane_wave_boost
from .wavelet import make_scaled_ricker

__all__ = [
    "GridSpec",
    "SimulationConfig",
    "auto_grid_from_frequency",
    "PMMediumParameters",
    "build_pm_medium_parameters",
    "build_surface_topography",
    "build_uniform_model",
    "compute_p_and_curl",
    "run_fd_plane_wave",
    "run_fd_plane_wave_boost",
    "make_scaled_ricker",
]
