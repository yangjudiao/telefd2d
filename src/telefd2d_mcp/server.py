from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - runtime dependency gate
    FastMCP = None


ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = ROOT / "scripts" / "run_acceptance_case.py"
OUTPUT_ROOT = ROOT / "output"

VALID_MODES = {"all", "compute", "postprocess"}
VALID_BACKENDS = {"baseline", "boost_serial", "boost_parallel"}
VALID_OUTPUT_MODES = {"memory", "stream_to_disk"}
SAFE_SUBDIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _ensure_run_script_exists() -> None:
    if not RUN_SCRIPT.exists():
        raise FileNotFoundError(f"Missing workflow runner: {RUN_SCRIPT}")


def _validate_output_subdir(output_subdir: str) -> str:
    subdir = (output_subdir or "").strip()
    if not subdir:
        raise ValueError("output_subdir must be non-empty.")
    if not SAFE_SUBDIR_RE.match(subdir):
        raise ValueError(
            "output_subdir must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ "
            "(letters/digits/._- only)."
        )
    if ".." in subdir:
        raise ValueError("output_subdir cannot contain path traversal segments.")
    return subdir


def _validate_choice(name: str, value: str, allowed: set[str]) -> str:
    v = (value or "").strip()
    if v not in allowed:
        allowed_txt = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {allowed_txt}")
    return v


def _tail_lines(text: str, n: int = 120) -> str:
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    return "\n".join(lines[-n:])


def _output_dir(output_subdir: str) -> Path:
    return OUTPUT_ROOT / output_subdir


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_run_command(
    *,
    output_subdir: str,
    mode: str,
    backend: str,
    threads: int,
    output_mode: str,
    width_km: float | None,
    depth_km: float | None,
    f0_hz: float | None,
    dx_m: float | None,
    dz_m: float | None,
    n_snapshots: int | None,
    pml_x_scale: float | None,
    pml_z_scale: float | None,
    progress_step: int,
    progress_sec: float,
) -> list[str]:
    cmd = [
        sys.executable,
        str(RUN_SCRIPT),
        "--mode",
        mode,
        "--backend",
        backend,
        "--output-mode",
        output_mode,
        "--output-subdir",
        output_subdir,
        "--progress-step",
        str(progress_step),
        "--progress-sec",
        str(progress_sec),
    ]

    if threads > 0:
        cmd.extend(["--threads", str(threads)])
    if width_km is not None:
        cmd.extend(["--width-km", str(width_km)])
    if depth_km is not None:
        cmd.extend(["--depth-km", str(depth_km)])
    if f0_hz is not None:
        cmd.extend(["--f0-hz", str(f0_hz)])
    if dx_m is not None:
        cmd.extend(["--dx-m", str(dx_m)])
    if dz_m is not None:
        cmd.extend(["--dz-m", str(dz_m)])
    if n_snapshots is not None:
        cmd.extend(["--n-snapshots", str(max(1, int(n_snapshots)))])
    if pml_x_scale is not None:
        cmd.extend(["--pml-x-scale", str(max(0.1, float(pml_x_scale)))])
    if pml_z_scale is not None:
        cmd.extend(["--pml-z-scale", str(max(0.1, float(pml_z_scale)))])

    return cmd


def summarize_project() -> dict[str, Any]:
    """Return static workflow and environment info for AI tool planning."""
    _ensure_run_script_exists()
    return {
        "project": "telefd2d",
        "repo_root": str(ROOT),
        "workflow_runner": str(RUN_SCRIPT),
        "defaults": {
            "mode": "all",
            "backend": "boost_parallel",
            "threads": max(1, os.cpu_count() or 1),
            "output_mode": "stream_to_disk",
            "output_subdir": "forward_case_telefd2d",
        },
        "allowed": {
            "modes": sorted(VALID_MODES),
            "backends": sorted(VALID_BACKENDS),
            "output_modes": sorted(VALID_OUTPUT_MODES),
        },
        "notes": [
            "Use baseline backend for lightweight smoke tests.",
            "Use boost_parallel for production runs after extension build.",
            "Read compute_metadata.json / run_metadata.json for machine-readable outputs.",
        ],
    }


def run_forward_case(
    *,
    output_subdir: str = "forward_case_telefd2d_mcp",
    mode: str = "all",
    backend: str = "boost_parallel",
    threads: int = 0,
    output_mode: str = "stream_to_disk",
    width_km: float | None = None,
    depth_km: float | None = None,
    f0_hz: float | None = None,
    dx_m: float | None = None,
    dz_m: float | None = None,
    n_snapshots: int | None = None,
    pml_x_scale: float | None = None,
    pml_z_scale: float | None = None,
    progress_step: int = 200,
    progress_sec: float = 0.5,
    timeout_sec: int = 0,
) -> dict[str, Any]:
    """
    Execute telefd2d forward workflow and return metadata summary.

    This wrapper is designed for AI agent usage:
    - strongly typed arguments
    - path sanitization for output subdir
    - command/output capture for diagnostics
    """
    _ensure_run_script_exists()
    safe_subdir = _validate_output_subdir(output_subdir)
    safe_mode = _validate_choice("mode", mode, VALID_MODES)
    safe_backend = _validate_choice("backend", backend, VALID_BACKENDS)
    safe_output_mode = _validate_choice("output_mode", output_mode, VALID_OUTPUT_MODES)

    if threads < 0:
        raise ValueError("threads must be >= 0 (0 means workflow default).")
    if progress_step < 0:
        raise ValueError("progress_step must be >= 0.")
    if progress_sec < 0.0:
        raise ValueError("progress_sec must be >= 0.")
    if timeout_sec < 0:
        raise ValueError("timeout_sec must be >= 0.")
    if (dx_m is None) != (dz_m is None):
        raise ValueError("dx_m and dz_m must be set together.")

    out_dir = _output_dir(safe_subdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = _build_run_command(
        output_subdir=safe_subdir,
        mode=safe_mode,
        backend=safe_backend,
        threads=threads,
        output_mode=safe_output_mode,
        width_km=width_km,
        depth_km=depth_km,
        f0_hz=f0_hz,
        dx_m=dx_m,
        dz_m=dz_m,
        n_snapshots=n_snapshots,
        pml_x_scale=pml_x_scale,
        pml_z_scale=pml_z_scale,
        progress_step=progress_step,
        progress_sec=progress_sec,
    )

    started_at = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=None if timeout_sec == 0 else timeout_sec,
        check=False,
    )
    elapsed = time.time() - started_at

    stdout_tail = _tail_lines(proc.stdout)
    stderr_tail = _tail_lines(proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(
            "telefd2d workflow failed.\n"
            f"command: {' '.join(cmd)}\n"
            f"returncode: {proc.returncode}\n"
            f"stdout_tail:\n{stdout_tail}\n"
            f"stderr_tail:\n{stderr_tail}"
        )

    compute_meta = _read_json_if_exists(out_dir / "compute_metadata.json")
    run_meta = _read_json_if_exists(out_dir / "run_metadata.json")

    return {
        "ok": True,
        "command": cmd,
        "duration_s": round(elapsed, 3),
        "output_dir": str(out_dir),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "compute_metadata_present": compute_meta is not None,
        "run_metadata_present": run_meta is not None,
        "quality": None if run_meta is None else run_meta.get("quality"),
        "outputs": [] if run_meta is None else run_meta.get("outputs", []),
    }


def get_case_report(output_subdir: str) -> dict[str, Any]:
    """Return a structured summary for an existing output case."""
    safe_subdir = _validate_output_subdir(output_subdir)
    out_dir = _output_dir(safe_subdir)
    if not out_dir.exists():
        raise FileNotFoundError(f"Output subdir does not exist: {out_dir}")

    compute_meta_path = out_dir / "compute_metadata.json"
    run_meta_path = out_dir / "run_metadata.json"
    compute_meta = _read_json_if_exists(compute_meta_path)
    run_meta = _read_json_if_exists(run_meta_path)

    files = sorted(p.name for p in out_dir.glob("*") if p.is_file())
    return {
        "output_subdir": safe_subdir,
        "output_dir": str(out_dir),
        "files": files,
        "compute_metadata_path": str(compute_meta_path),
        "run_metadata_path": str(run_meta_path),
        "compute": None
        if compute_meta is None
        else {
            "backend": compute_meta.get("backend"),
            "mode": compute_meta.get("stage"),
            "runtime_s": compute_meta.get("runtime_s"),
            "grid": compute_meta.get("grid"),
            "pml": compute_meta.get("pml"),
        },
        "run": None
        if run_meta is None
        else {
            "quality": run_meta.get("quality"),
            "outputs": run_meta.get("outputs", []),
        },
    }


def list_cases(limit: int = 30) -> dict[str, Any]:
    """List generated output subdirectories under output/ for discovery."""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    lim = max(1, min(200, int(limit)))
    items = []
    for entry in sorted(OUTPUT_ROOT.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_dir():
            continue
        files = sorted(p.name for p in entry.glob("*") if p.is_file())
        items.append(
            {
                "name": entry.name,
                "path": str(entry),
                "file_count": len(files),
                "has_run_metadata": "run_metadata.json" in files,
                "has_compute_metadata": "compute_metadata.json" in files,
            }
        )
        if len(items) >= lim:
            break
    return {"cases": items}


mcp = FastMCP("telefd2d-forward-mcp") if FastMCP is not None else None

if mcp is not None:

    @mcp.tool(name="telefd2d_summarize_project")
    def telefd2d_summarize_project() -> dict[str, Any]:
        """Describe runnable capabilities and defaults for telefd2d."""
        return summarize_project()


    @mcp.tool(name="telefd2d_run_forward_case")
    def telefd2d_run_forward_case(
        output_subdir: str = "forward_case_telefd2d_mcp",
        mode: str = "all",
        backend: str = "boost_parallel",
        threads: int = 0,
        output_mode: str = "stream_to_disk",
        width_km: float | None = None,
        depth_km: float | None = None,
        f0_hz: float | None = None,
        dx_m: float | None = None,
        dz_m: float | None = None,
        n_snapshots: int | None = None,
        pml_x_scale: float | None = None,
        pml_z_scale: float | None = None,
        progress_step: int = 200,
        progress_sec: float = 0.5,
        timeout_sec: int = 0,
    ) -> dict[str, Any]:
        """Run forward modeling and postprocess via scripts/run_acceptance_case.py."""
        return run_forward_case(
            output_subdir=output_subdir,
            mode=mode,
            backend=backend,
            threads=threads,
            output_mode=output_mode,
            width_km=width_km,
            depth_km=depth_km,
            f0_hz=f0_hz,
            dx_m=dx_m,
            dz_m=dz_m,
            n_snapshots=n_snapshots,
            pml_x_scale=pml_x_scale,
            pml_z_scale=pml_z_scale,
            progress_step=progress_step,
            progress_sec=progress_sec,
            timeout_sec=timeout_sec,
        )


    @mcp.tool(name="telefd2d_get_case_report")
    def telefd2d_get_case_report(output_subdir: str) -> dict[str, Any]:
        """Read metadata for a previously generated output case."""
        return get_case_report(output_subdir=output_subdir)


    @mcp.tool(name="telefd2d_list_cases")
    def telefd2d_list_cases(limit: int = 30) -> dict[str, Any]:
        """List available output cases under output/."""
        return list_cases(limit=limit)


def run_stdio_server() -> None:
    """Start stdio MCP server."""
    if mcp is None:
        raise RuntimeError(
            "The 'mcp' package is not installed. Install dependencies with:\n"
            "python -m pip install -r requirements.txt"
        )
    mcp.run()


if __name__ == "__main__":
    run_stdio_server()

