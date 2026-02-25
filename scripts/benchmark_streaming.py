from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def gib(nbytes: float) -> float:
    return float(nbytes / (1024.0**3))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark in-memory vs streaming output modes for telefd2d workflow.")
    parser.add_argument("--width-km", type=float, default=100.0)
    parser.add_argument("--depth-km", type=float, default=40.0)
    parser.add_argument("--topo-amplitude-km", type=float, default=5.0)
    parser.add_argument("--topo-mean-depth-km", type=float, default=5.0)
    parser.add_argument("--topo-cycles", type=float, default=4.0)
    parser.add_argument("--n-snapshots", type=int, default=60)
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--alt-threads", type=int, default=max(1, (os.cpu_count() or 1) // 2))
    parser.add_argument("--runtime-overhead-threshold", type=float, default=1.20)
    parser.add_argument("--seismo-stride-t", type=int, default=1)
    parser.add_argument("--seismo-stride-x", type=int, default=1)
    parser.add_argument("--snapshot-stride-x", type=int, default=1)
    parser.add_argument("--snapshot-stride-z", type=int, default=1)
    parser.add_argument("--work-prefix", type=str, default="bench_stream")
    parser.add_argument("--output-json", type=Path, default=Path("output/memory/streaming_benchmark.json"))
    parser.add_argument("--output-md", type=Path, default=Path("output/memory/streaming_benchmark.md"))
    parser.add_argument("--memory-breakdown-md", type=Path, default=Path("docs/memory_breakdown.md"))
    return parser.parse_args()


def run_compute(args: argparse.Namespace, output_mode: str, threads: int, subdir: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_acceptance_case.py"),
        "--mode",
        "compute",
        "--backend",
        "boost_parallel",
        "--threads",
        str(max(1, int(threads))),
        "--output-mode",
        output_mode,
        "--output-subdir",
        subdir,
        "--width-km",
        str(args.width_km),
        "--depth-km",
        str(args.depth_km),
        "--topo-amplitude-km",
        str(args.topo_amplitude_km),
        "--topo-mean-depth-km",
        str(args.topo_mean_depth_km),
        "--topo-cycles",
        str(args.topo_cycles),
        "--n-snapshots",
        str(max(0, int(args.n_snapshots))),
        "--seismo-stride-t",
        str(max(1, int(args.seismo_stride_t))),
        "--seismo-stride-x",
        str(max(1, int(args.seismo_stride_x))),
        "--snapshot-stride-x",
        str(max(1, int(args.snapshot_stride_x))),
        "--snapshot-stride-z",
        str(max(1, int(args.snapshot_stride_z))),
        "--progress-step",
        "0",
        "--monitor-memory",
    ]
    print("[benchmark] run:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    out_dir = ROOT / "output" / subdir
    meta = json.loads((out_dir / "compute_metadata.json").read_text(encoding="utf-8"))

    raw_files = {}
    raw_sizes = {}
    for name, rel in meta["artifacts"]["raw_outputs"].items():
        p = out_dir / rel
        raw_files[name] = str(p)
        raw_sizes[name] = int(p.stat().st_size)

    return {
        "output_subdir": subdir,
        "output_mode": output_mode,
        "threads": int(threads),
        "runtime_s": float(meta["runtime_s"]),
        "rss_peak_gib": float(meta["memory_rss_gib"]["peak"]),
        "rss_before_gib": float(meta["memory_rss_gib"]["before"]),
        "rss_after_gib": float(meta["memory_rss_gib"]["after"]),
        "uss_peak_gib": float(meta.get("memory_uss_gib", meta["memory_rss_gib"])["peak"]),
        "uss_before_gib": float(meta.get("memory_uss_gib", meta["memory_rss_gib"])["before"]),
        "uss_after_gib": float(meta.get("memory_uss_gib", meta["memory_rss_gib"])["after"]),
        "grid": meta["grid"],
        "output_controls": meta["output_controls"],
        "raw_file_sizes_bytes": raw_sizes,
        "raw_files": raw_files,
    }


def estimate_core_memory_bytes(grid: dict[str, Any]) -> dict[str, float]:
    nx = int(grid["nx_total"])
    nz = int(grid["nz_total"])
    nxy = nx * nz
    bx = (nx - 1) * nz
    bz = nx * (nz - 1)
    mu_xz = (nx - 1) * (nz - 1)
    runtime_state = 13 * nxy * 8
    pm_inputs = (4 * nxy + bx + bz + mu_xz) * 8
    return {
        "runtime_state_bytes": float(runtime_state),
        "pm_inputs_bytes": float(pm_inputs),
        "runtime_state_gib": gib(runtime_state),
        "pm_inputs_gib": gib(pm_inputs),
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Streaming Output Benchmark")
    lines.append("")
    lines.append("## Target")
    lines.append(
        f"- Physical domain: {payload['target']['width_km']} km x {payload['target']['depth_km']} km (excluding PML)"
    )
    lines.append(f"- Threads primary: {payload['target']['threads_primary']}")
    lines.append(f"- Threads alternative: {payload['target']['threads_alternative']}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| case | mode | threads | runtime_s | rss_peak_gib | uss_peak_gib |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    lines.append(
        f"| baseline | {payload['baseline']['output_mode']} | {payload['baseline']['threads']} | "
        f"{payload['baseline']['runtime_s']:.2f} | {payload['baseline']['rss_peak_gib']:.3f} | "
        f"{payload['baseline']['uss_peak_gib']:.3f} |"
    )
    lines.append(
        f"| stream_attempt_a | {payload['stream_attempt_a']['output_mode']} | {payload['stream_attempt_a']['threads']} | "
        f"{payload['stream_attempt_a']['runtime_s']:.2f} | {payload['stream_attempt_a']['rss_peak_gib']:.3f} | "
        f"{payload['stream_attempt_a']['uss_peak_gib']:.3f} |"
    )
    if payload.get("stream_attempt_b") is not None:
        b = payload["stream_attempt_b"]
        lines.append(
            f"| stream_attempt_b | {b['output_mode']} | {b['threads']} | "
            f"{b['runtime_s']:.2f} | {b['rss_peak_gib']:.3f} | {b['uss_peak_gib']:.3f} |"
        )

    lines.append("")
    lines.append("## Decision")
    lines.append(f"- Selected stream run: `{payload['selected_stream']['output_subdir']}`")
    lines.append(f"- Peak RSS reduced: `{payload['decision']['peak_rss_reduced']}`")
    lines.append(f"- Peak USS reduced: `{payload['decision']['peak_uss_reduced']}`")
    lines.append(
        f"- Runtime overhead ratio (stream/base): `{payload['decision']['runtime_overhead_ratio']:.3f}` "
        f"(threshold `{payload['decision']['runtime_overhead_threshold']:.3f}`)"
    )
    lines.append(f"- Runtime gate passed: `{payload['decision']['runtime_gate_passed']}`")
    if payload.get("failure_analysis") is not None:
        lines.append("")
        lines.append("## Failure Analysis + Alternative Attempt")
        lines.append(f"- Issue: {payload['failure_analysis']['issue']}")
        lines.append(f"- Root cause hypothesis: {payload['failure_analysis']['root_cause_hypothesis']}")
        lines.append(f"- Alternative action: {payload['failure_analysis']['alternative_action']}")
        lines.append(f"- Alternative outcome: {payload['failure_analysis']['alternative_outcome']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_memory_breakdown(path: Path, payload: dict[str, Any]) -> None:
    selected = payload["selected_stream"]
    baseline = payload["baseline"]
    core_mem = payload["memory_breakdown"]["estimated_core"]
    files = selected["raw_file_sizes_bytes"]

    bytes_snapshot = float(files["snap_vx"] + files["snap_vz"] + files["snap_it"])
    bytes_seismo = float(files["seismo_vx"] + files["seismo_vz"])
    bytes_outputs = bytes_snapshot + bytes_seismo

    lines: list[str] = []
    lines.append("# Memory Breakdown (telefd2d)")
    lines.append("")
    lines.append("## Grid and Case")
    lines.append(
        f"- Domain (excluding PML): {payload['target']['width_km']} km x {payload['target']['depth_km']} km"
    )
    lines.append(
        f"- Grid total: nx={selected['grid']['nx_total']}, nz={selected['grid']['nz_total']}, nt={selected['grid']['nt']}"
    )
    lines.append("")
    lines.append("## Estimated Solver-Core Memory")
    lines.append(
        f"- Runtime state (`vx`, `vz`, `tau*`, `memo*`): {core_mem['runtime_state_gib']:.3f} GiB"
    )
    lines.append(f"- PM parameter arrays (`bx/bz/mu_xz/eta*`): {core_mem['pm_inputs_gib']:.3f} GiB")
    lines.append("")
    lines.append("## Output Memory/Storage Footprint")
    lines.append(f"- Snapshot files (`snap_vx/snap_vz/snap_it`): {gib(bytes_snapshot):.3f} GiB")
    lines.append(f"- Seismogram files (`seismo_vx/seismo_vz`): {gib(bytes_seismo):.3f} GiB")
    lines.append(f"- Total output files: {gib(bytes_outputs):.3f} GiB")
    lines.append("")
    lines.append("## Measured Peak RSS")
    lines.append(f"- In-memory mode peak RSS: {baseline['rss_peak_gib']:.3f} GiB")
    lines.append(f"- Streaming mode peak RSS: {selected['rss_peak_gib']:.3f} GiB")
    lines.append(f"- Peak RSS reduction: {baseline['rss_peak_gib'] - selected['rss_peak_gib']:.3f} GiB")
    lines.append("")
    lines.append("## Measured Peak USS")
    lines.append(f"- In-memory mode peak USS: {baseline['uss_peak_gib']:.3f} GiB")
    lines.append(f"- Streaming mode peak USS: {selected['uss_peak_gib']:.3f} GiB")
    lines.append(f"- Peak USS reduction: {baseline['uss_peak_gib'] - selected['uss_peak_gib']:.3f} GiB")
    lines.append("")
    lines.append("## Conclusion")
    lines.append(
        "- Streaming mode moves output buffers to disk-backed files during runtime, reducing resident memory pressure."
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.alt_threads = max(1, int(args.alt_threads))
    args.threads = max(1, int(args.threads))

    base_subdir = f"{args.work_prefix}_memory"
    stream_a_subdir = f"{args.work_prefix}_stream_t{args.threads}"
    stream_b_subdir = f"{args.work_prefix}_stream_t{args.alt_threads}"

    baseline = run_compute(args, output_mode="memory", threads=args.threads, subdir=base_subdir)
    stream_attempt_a = run_compute(args, output_mode="stream_to_disk", threads=args.threads, subdir=stream_a_subdir)

    selected_stream = stream_attempt_a
    stream_attempt_b: dict[str, Any] | None = None
    failure_analysis: dict[str, str] | None = None

    overhead_a = stream_attempt_a["runtime_s"] / max(baseline["runtime_s"], 1e-9)
    runtime_gate_a = overhead_a <= float(args.runtime_overhead_threshold)

    if not runtime_gate_a and args.alt_threads != args.threads:
        stream_attempt_b = run_compute(
            args,
            output_mode="stream_to_disk",
            threads=args.alt_threads,
            subdir=stream_b_subdir,
        )
        overhead_b = stream_attempt_b["runtime_s"] / max(baseline["runtime_s"], 1e-9)
        selected_stream = stream_attempt_b if stream_attempt_b["runtime_s"] < stream_attempt_a["runtime_s"] else stream_attempt_a
        failure_analysis = {
            "issue": (
                "Initial streaming attempt exceeded runtime-overhead gate "
                f"({overhead_a:.3f} > {args.runtime_overhead_threshold:.3f})."
            ),
            "root_cause_hypothesis": (
                "High thread count amplified memory-bandwidth and disk-page contention for this output pattern."
            ),
            "alternative_action": f"Retried streaming with reduced threads: {args.alt_threads}.",
            "alternative_outcome": (
                f"New overhead ratio={overhead_b:.3f}, selected run={selected_stream['output_subdir']}."
            ),
        }

    selected_overhead = selected_stream["runtime_s"] / max(baseline["runtime_s"], 1e-9)
    peak_rss_reduced = selected_stream["rss_peak_gib"] < baseline["rss_peak_gib"]
    peak_uss_reduced = selected_stream["uss_peak_gib"] < baseline["uss_peak_gib"]
    runtime_gate_passed = selected_overhead <= float(args.runtime_overhead_threshold)

    payload: dict[str, Any] = {
        "target": {
            "width_km": float(args.width_km),
            "depth_km": float(args.depth_km),
            "threads_primary": int(args.threads),
            "threads_alternative": int(args.alt_threads),
            "runtime_overhead_threshold": float(args.runtime_overhead_threshold),
        },
        "baseline": baseline,
        "stream_attempt_a": stream_attempt_a,
        "stream_attempt_b": stream_attempt_b,
        "selected_stream": selected_stream,
        "memory_breakdown": {
            "estimated_core": estimate_core_memory_bytes(selected_stream["grid"]),
        },
        "decision": {
            "peak_rss_reduced": bool(peak_rss_reduced),
            "peak_uss_reduced": bool(peak_uss_reduced),
            "runtime_overhead_ratio": float(selected_overhead),
            "runtime_overhead_threshold": float(args.runtime_overhead_threshold),
            "runtime_gate_passed": bool(runtime_gate_passed),
            "streaming_effective": bool((peak_rss_reduced or peak_uss_reduced) and runtime_gate_passed),
        },
        "failure_analysis": failure_analysis,
    }

    out_json = ROOT / args.output_json
    out_md = ROOT / args.output_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(out_md, payload)
    write_memory_breakdown(ROOT / args.memory_breakdown_md, payload)

    print(f"[report] {out_json}")
    print(f"[report] {out_md}")
    print(f"[report] {ROOT / args.memory_breakdown_md}")
    print(
        "[decision] streaming_effective="
        f"{payload['decision']['streaming_effective']} "
        f"peak_rss_reduced={payload['decision']['peak_rss_reduced']} "
        f"peak_uss_reduced={payload['decision']['peak_uss_reduced']} "
        f"runtime_gate_passed={payload['decision']['runtime_gate_passed']}"
    )


if __name__ == "__main__":
    main()
