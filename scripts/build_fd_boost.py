from __future__ import annotations

from pathlib import Path
import platform
import subprocess
import sys


def ensure_pybind11() -> None:
    try:
        import pybind11  # noqa: F401
    except ImportError:
        print("[build] pybind11 not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pybind11>=2.12"])


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cpp_path = root / "src" / "fd_workflow" / "_fd_core.cpp"
    if not cpp_path.exists():
        raise FileNotFoundError(f"Missing extension source: {cpp_path}")

    ensure_pybind11()

    from pybind11.setup_helpers import Pybind11Extension, build_ext
    from setuptools import setup

    extra_compile_args: list[str]
    extra_link_args: list[str] = []

    if platform.system().lower().startswith("win"):
        extra_compile_args = ["/O2", "/openmp", "/EHsc"]
    else:
        extra_compile_args = ["-O3", "-fopenmp"]
        extra_link_args = ["-fopenmp"]

    ext_modules = [
        Pybind11Extension(
            "fd_workflow._fd_core",
            [str(cpp_path)],
            cxx_std=17,
            extra_compile_args=extra_compile_args,
            extra_link_args=extra_link_args,
        )
    ]

    setup(
        name="fd_workflow_boost_ext",
        version="0.1.0",
        description="C++/OpenMP core for fd_workflow",
        package_dir={"": "src"},
        ext_modules=ext_modules,
        cmdclass={"build_ext": build_ext},
        script_args=["build_ext", "--inplace"],
    )


if __name__ == "__main__":
    main()
