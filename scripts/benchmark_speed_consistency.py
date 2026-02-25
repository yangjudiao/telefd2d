from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark telefd2d speed-up against a reference run with consistency checks."
    )
    parser.add_argument("--baseline-subdir", type=str, default="forward_case_telefd2d")
    parser.add_argument("--width-km", type=float, default=100.0)
    parser.add_argument("--depth-km", type=float, default=40.0)
    parser.add_argument("--topo-amplitude-km", type=float, default=5.0)
    parser.add_argument("--topo-mean-depth-km", type=float, default=5.0)
    parser.add_argument("--topo-cycles", type=float, default=4.0)
    parser.add_argument("--n-snapshots", type=int, default=60)
    parser.add_argument("--seismo-stride-t", type=int, default=1)
    parser.add_argument("--seismo-stride-x", type=int, default=1)
    parser.add_argument("--snapshot-stride-x", type=int, default=1)
    parser.add_argument("--snapshot-stride-z", type=int, default=1)
    parser.add_argument("--progress-step", type=int, default=200)
    parser.add_argument("--progress-sec", type=float, default=0.5)
    parser.add_argument("--threads", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--alt-threads", type=int, default=max(1, (os.cpu_count() or 1) - 2))
    parser.add_argument("--speedup-threshold", type=float, default=1.02)
    parser.add_argument("--consistency-rel-l2-threshold", type=float, default=1.0e-5)
    parser.add_argument("--monitor-memory", action="store_true")
    parser.add_argument("--work-prefix", type=str, default="telefd2d_speed")
    parser.add_argument("--output-json", type=Path, default=Path("output/speed/speed_consistency_benchmark.json"))
    parser.add_argument("--output-md", type=Path, default=Path("output/speed/speed_consistency_benchmark.md"))
    parser.add_argument("--no-enforce", action="store_true", help="Do not raise exception when gates fail.")
    return parser.parse_args()


def _load_compute_meta(subdir: str) -> dict[str, Any]:
    out_dir = ROOT / "output" / subdir
    meta_path = out_dir / "compute_metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing reference compute metadata: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("stage") != "compute":
        raise RuntimeError(f"Invalid compute metadata stage in {meta_path}: {meta.get('stage')}")
    return meta


def _run_compute(args: argparse.Namespace, threads: int, subdir: str) -> dict[str, Any]:
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
        "stream_to_disk",
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
        str(max(0, int(args.progress_step))),
        "--progress-sec",
        str(max(0.0, float(args.progress_sec))),
    ]
    if args.monitor_memory:
        cmd.append("--monitor-memory")
    print("[speed-bench] run:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    out_dir = ROOT / "output" / subdir
    meta = json.loads((out_dir / "compute_metadata.json").read_text(encoding="utf-8"))
    return {
        "output_subdir": subdir,
        "threads": int(threads),
        "runtime_s": float(meta["runtime_s"]),
        "memory_rss_peak_gib": float(meta["memory_rss_gib"]["peak"]),
        "memory_uss_peak_gib": float(meta.get("memory_uss_gib", meta["memory_rss_gib"])["peak"]),
        "grid": meta["grid"],
        "output_controls": meta["output_controls"],
        "artifacts": meta["artifacts"],
    }


def _compute_array_metrics(candidate: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    cand = np.asarray(candidate, dtype=np.float64)
    ref = np.asarray(reference, dtype=np.float64)
    if cand.shape != ref.shape:
        return {"shape_match": 0.0, "rel_l2": float("inf"), "max_abs": float("inf")}
    diff = cand - ref
    ref_norm = float(np.linalg.norm(ref.ravel()))
    diff_norm = float(np.linalg.norm(diff.ravel()))
    rel_l2 = diff_norm / (ref_norm + 1e-12)
    max_abs = float(np.max(np.abs(diff)))
    return {"shape_match": 1.0, "rel_l2": rel_l2, "max_abs": max_abs}


def _consistency_metrics(reference_subdir: str, candidate_subdir: str) -> dict[str, Any]:
    ref_meta = _load_compute_meta(reference_subdir)
    cand_meta = _load_compute_meta(candidate_subdir)
    ref_dir = ROOT / "output" / reference_subdir
    cand_dir = ROOT / "output" / candidate_subdir

    ref_raw = ref_meta["artifacts"]["raw_outputs"]
    cand_raw = cand_meta["artifacts"]["raw_outputs"]

    keys = ["snap_vx", "snap_vz", "seismo_vx", "seismo_vz"]
    metrics: dict[str, Any] = {}
    for key in keys:
        ref_arr = np.load(ref_dir / ref_raw[key], mmap_mode="r")
        cand_arr = np.load(cand_dir / cand_raw[key], mmap_mode="r")
        metrics[key] = _compute_array_metrics(cand_arr, ref_arr)

    ref_it = np.load(ref_dir / ref_raw["snap_it"], mmap_mode="r")
    cand_it = np.load(cand_dir / cand_raw["snap_it"], mmap_mode="r")
    snap_it_equal = bool(np.array_equal(np.asarray(cand_it), np.asarray(ref_it)))
    metrics["snap_it"] = {
        "shape_match": bool(np.asarray(cand_it).shape == np.asarray(ref_it).shape),
        "exact_equal": snap_it_equal,
        "max_abs": float(np.max(np.abs(np.asarray(cand_it, dtype=np.int64) - np.asarray(ref_it, dtype=np.int64)))),
    }

    return metrics


def _consistency_gate(metrics: dict[str, Any], rel_l2_threshold: float) -> bool:
    for key in ("snap_vx", "snap_vz", "seismo_vx", "seismo_vz"):
        item = metrics[key]
        if float(item["shape_match"]) < 0.5:
            return False
        if float(item["rel_l2"]) > rel_l2_threshold:
            return False
    if not bool(metrics["snap_it"]["shape_match"]):
        return False
    if not bool(metrics["snap_it"]["exact_equal"]):
        return False
    return True


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# telefd2d Speed and Consistency Benchmark")
    lines.append("")
    lines.append("## Target")
    lines.append(f"- Reference subdir: `{payload['reference']['baseline_subdir']}`")
    lines.append(
        f"- Physical domain: {payload['target']['width_km']} km x {payload['target']['depth_km']} km (excluding PML)"
    )
    lines.append(f"- Speedup threshold: {payload['target']['speedup_threshold']:.3f}x")
    lines.append(f"- Consistency rel-L2 threshold: {payload['target']['consistency_rel_l2_threshold']:.2e}")
    lines.append("")
    lines.append("## Runtime Results")
    lines.append("")
    lines.append("| case | threads | runtime_s | speedup_vs_reference |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        f"| reference | {payload['reference']['threads']} | {payload['reference']['runtime_s']:.3f} | 1.000 |"
    )
    a = payload["attempt_a"]
    lines.append(
        f"| attempt_a | {a['threads']} | {a['runtime_s']:.3f} | {a['speedup_vs_reference']:.3f} |"
    )
    if payload.get("attempt_b") is not None:
        b = payload["attempt_b"]
        lines.append(
            f"| attempt_b | {b['threads']} | {b['runtime_s']:.3f} | {b['speedup_vs_reference']:.3f} |"
        )
    s = payload["selected"]
    lines.append(
        f"| selected | {s['threads']} | {s['runtime_s']:.3f} | {s['speedup_vs_reference']:.3f} |"
    )
    lines.append("")
    lines.append("## Consistency")
    for key in ("snap_vx", "snap_vz", "seismo_vx", "seismo_vz"):
        item = payload["consistency"][key]
        lines.append(
            f"- {key}: rel_l2={item['rel_l2']:.3e}, max_abs={item['max_abs']:.3e}, shape_match={bool(item['shape_match'])}"
        )
    lines.append(
        f"- snap_it: exact_equal={payload['consistency']['snap_it']['exact_equal']}, "
        f"max_abs={payload['consistency']['snap_it']['max_abs']:.0f}"
    )
    lines.append("")
    lines.append("## Decision")
    lines.append(f"- Speed gate passed: `{payload['decision']['speed_gate_passed']}`")
    lines.append(f"- Consistency gate passed: `{payload['decision']['consistency_gate_passed']}`")
    lines.append(f"- Overall passed: `{payload['decision']['overall_passed']}`")
    if payload.get("failure_analysis") is not None:
        lines.append("")
        lines.append("## Failure Analysis + Alternative Attempt")
        lines.append(f"- Issue: {payload['failure_analysis']['issue']}")
        lines.append(f"- Root cause hypothesis: {payload['failure_analysis']['root_cause_hypothesis']}")
        lines.append(f"- Alternative action: {payload['failure_analysis']['alternative_action']}")
        lines.append(f"- Alternative outcome: {payload['failure_analysis']['alternative_outcome']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    baseline_subdir = args.baseline_subdir.strip() or "forward_case_telefd2d"
    work_prefix = args.work_prefix.strip() or "telefd2d_speed"
    candidate_a_subdir = f"{work_prefix}_t{max(1, int(args.threads))}"
    candidate_b_subdir = f"{work_prefix}_t{max(1, int(args.alt_threads))}"

    baseline_meta = _load_compute_meta(baseline_subdir)
    reference_runtime = float(baseline_meta["runtime_s"])
    reference_threads = int(baseline_meta.get("backend_runtime", {}).get("threads_requested", -1))

    attempt_a = _run_compute(args, threads=max(1, int(args.threads)), subdir=candidate_a_subdir)
    attempt_a_speedup = reference_runtime / max(float(attempt_a["runtime_s"]), 1e-9)
    attempt_a["speedup_vs_reference"] = float(attempt_a_speedup)

    attempt_b: dict[str, Any] | None = None
    selected = dict(attempt_a)
    failure_analysis: dict[str, str] | None = None

    if attempt_a_speedup < float(args.speedup_threshold) and int(args.alt_threads) != int(args.threads):
        attempt_b = _run_compute(args, threads=max(1, int(args.alt_threads)), subdir=candidate_b_subdir)
        attempt_b_speedup = reference_runtime / max(float(attempt_b["runtime_s"]), 1e-9)
        attempt_b["speedup_vs_reference"] = float(attempt_b_speedup)
        selected = dict(attempt_b if attempt_b["runtime_s"] < attempt_a["runtime_s"] else attempt_a)

        failure_analysis = {
            "issue": (
                "Attempt A did not reach the speedup threshold "
                f"({attempt_a_speedup:.3f}x < {float(args.speedup_threshold):.3f}x)."
            ),
            "root_cause_hypothesis": (
                "The initial thread setting likely caused suboptimal CPU scheduling or memory-bandwidth pressure."
            ),
            "alternative_action": f"Retried with alternative thread count: {int(args.alt_threads)}.",
            "alternative_outcome": (
                f"Attempt B speedup={attempt_b_speedup:.3f}x; selected run={selected['output_subdir']}."
            ),
        }

    consistency = _consistency_metrics(reference_subdir=baseline_subdir, candidate_subdir=selected["output_subdir"])
    consistency_gate_passed = _consistency_gate(consistency, rel_l2_threshold=float(args.consistency_rel_l2_threshold))
    speed_gate_passed = float(selected["speedup_vs_reference"]) >= float(args.speedup_threshold)
    overall_passed = bool(speed_gate_passed and consistency_gate_passed)

    payload: dict[str, Any] = {
        "target": {
            "width_km": float(args.width_km),
            "depth_km": float(args.depth_km),
            "speedup_threshold": float(args.speedup_threshold),
            "consistency_rel_l2_threshold": float(args.consistency_rel_l2_threshold),
        },
        "reference": {
            "baseline_subdir": baseline_subdir,
            "runtime_s": reference_runtime,
            "threads": reference_threads,
            "grid": baseline_meta["grid"],
            "output_controls": baseline_meta["output_controls"],
        },
        "attempt_a": attempt_a,
        "attempt_b": attempt_b,
        "selected": selected,
        "consistency": consistency,
        "decision": {
            "speed_gate_passed": bool(speed_gate_passed),
            "consistency_gate_passed": bool(consistency_gate_passed),
            "overall_passed": bool(overall_passed),
        },
        "failure_analysis": failure_analysis,
    }

    out_json = ROOT / args.output_json
    out_md = ROOT / args.output_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(out_md, payload)

    print(f"[report] {out_json}")
    print(f"[report] {out_md}")
    print(
        "[decision] overall_passed="
        f"{payload['decision']['overall_passed']} "
        f"speed_gate_passed={payload['decision']['speed_gate_passed']} "
        f"consistency_gate_passed={payload['decision']['consistency_gate_passed']}"
    )

    if (not args.no_enforce) and (not overall_passed):
        raise RuntimeError(
            "telefd2d benchmark gate failed: "
            f"speed_gate={speed_gate_passed}, consistency_gate={consistency_gate_passed}"
        )


if __name__ == "__main__":
    main()
