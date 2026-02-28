from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from telefd2d_mcp.server import get_case_report, run_forward_case


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a lightweight telefd2d MCP smoke test.")
    p.add_argument("--output-subdir", default="forward_case_telefd2d_mcp_smoke")
    p.add_argument("--backend", choices=["baseline", "boost_serial", "boost_parallel"], default="baseline")
    p.add_argument("--timeout-sec", type=int, default=1200)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = run_forward_case(
        output_subdir=args.output_subdir,
        mode="all",
        backend=args.backend,
        threads=1,
        output_mode="stream_to_disk",
        width_km=1.0,
        depth_km=1.0,
        f0_hz=20.0,
        dx_m=200.0,
        dz_m=200.0,
        n_snapshots=4,
        progress_step=100,
        progress_sec=0.2,
        timeout_sec=args.timeout_sec,
    )
    report = get_case_report(args.output_subdir)
    print(
        json.dumps(
            {
                "run_result": result,
                "case_report": report,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

