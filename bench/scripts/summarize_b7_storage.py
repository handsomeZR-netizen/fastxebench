#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine multiple B7 storage-mode datasets into one rollup.")
    parser.add_argument("--study-root", required=True)
    parser.add_argument(
        "--mode",
        action="append",
        required=True,
        help="Mode spec in the form label=dataset_root",
    )
    return parser.parse_args()


def parse_modes(items: list[str]) -> list[tuple[str, Path]]:
    modes: list[tuple[str, Path]] = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --mode value: {item}")
        label, raw_path = item.split("=", 1)
        modes.append((label, Path(raw_path).resolve()))
    return modes


def load_csv(root: Path, relative: str) -> pd.DataFrame:
    path = root / relative
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def main() -> int:
    args = parse_args()
    study_root = Path(args.study_root).resolve()
    artifact_root = study_root / "artifact"
    artifact_root.mkdir(parents=True, exist_ok=True)

    modes = parse_modes(args.mode)
    summary_frames = []
    per_run_frames = []

    for label, root in modes:
        summary = load_csv(root, "csv/summary.csv").copy()
        per_run = load_csv(root, "csv/per_run.csv").copy()
        summary["mode_label"] = label
        per_run["mode_label"] = label
        summary_frames.append(summary)
        per_run_frames.append(per_run)

    combined_summary = pd.concat(summary_frames, ignore_index=True)
    combined_per_run = pd.concat(per_run_frames, ignore_index=True)
    combined_summary["measure_median_ms"] = pd.to_numeric(combined_summary["measure_median_ms"], errors="coerce")
    combined_summary["visual_equal_rate"] = pd.to_numeric(combined_summary["visual_equal_rate"], errors="coerce")
    combined_summary["success_rate"] = pd.to_numeric(combined_summary["success_rate"], errors="coerce")
    combined_summary.to_csv(artifact_root / "b7_combined_summary.csv", index=False)
    combined_per_run.to_csv(artifact_root / "b7_combined_per_run.csv", index=False)

    baseline_label = modes[0][0]
    baseline = combined_summary[combined_summary["mode_label"] == baseline_label][
        ["workload", "scenario", "config", "measure_median_ms"]
    ].rename(columns={"measure_median_ms": "baseline_measure_median_ms"})
    rollup = combined_summary.merge(baseline, on=["workload", "scenario", "config"], how="left")
    rollup["latency_ratio_vs_baseline_mode"] = rollup["measure_median_ms"] / rollup["baseline_measure_median_ms"]
    rollup.to_csv(artifact_root / "b7_rollup.csv", index=False)

    lines = [
        "# B7 Storage Study Summary",
        "",
        f"Baseline mode: `{baseline_label}`",
        "",
    ]
    for label, _ in modes:
        subset = rollup[rollup["mode_label"] == label]
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"- groups: {subset.shape[0]}")
        lines.append(f"- minimum success rate: {subset['success_rate'].min():.4f}")
        lines.append(f"- median success rate: {subset['success_rate'].median():.4f}")
        if label == baseline_label:
            lines.append("- comparison: baseline mode")
        else:
            ratio = subset["latency_ratio_vs_baseline_mode"].median()
            lines.append(f"- median latency ratio vs {baseline_label}: {ratio:.4f}")
        lines.append(f"- visual equality minimum: {subset['visual_equal_rate'].min():.4f}")
        failed = subset[subset["success_rate"] < 1.0][["workload", "scenario", "success_rate"]]
        if failed.empty:
            lines.append("- unstable groups: none")
        else:
            details = ", ".join(
                "{} {} ({:.2f})".format(row["workload"], row["scenario"], row["success_rate"])
                for _, row in failed.iterrows()
            )
            lines.append(f"- unstable groups: {details}")
        lines.append("")

    (artifact_root / "b7_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        {
            "combined_summary": str(artifact_root / "b7_combined_summary.csv"),
            "combined_per_run": str(artifact_root / "b7_combined_per_run.csv"),
            "rollup": str(artifact_root / "b7_rollup.csv"),
            "summary_md": str(artifact_root / "b7_summary.md"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
