#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a compact rollup for external validation datasets.")
    parser.add_argument("--dataset-root", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    artifact_root = dataset_root / "artifact"
    artifact_root.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(dataset_root / "csv" / "summary.csv")
    summary["measure_median_ms"] = pd.to_numeric(summary["measure_median_ms"], errors="coerce")
    summary["speedup_vs_baseline"] = pd.to_numeric(summary["speedup_vs_baseline"], errors="coerce")
    summary["visual_equal_rate"] = pd.to_numeric(summary["visual_equal_rate"], errors="coerce")

    rows = []
    for (workload, config), group in summary.groupby(["workload", "config"], sort=False):
        if config == "B0_baseline_xelatex":
            continue
        subset = group.copy()
        inc = subset[subset["scenario"].isin(["S1_text_edit", "S3_figure_edit", "S4_preamble_edit"])]
        clean = subset[subset["scenario"] == "S0_clean_build"].iloc[0]
        bib = subset[subset["scenario"] == "S2_bib_edit"].iloc[0]
        rows.append(
            {
                "workload": workload,
                "config": config,
                "clean_ms": round(float(clean["measure_median_ms"]), 3),
                "clean_speedup": round(float(clean["speedup_vs_baseline"]), 4),
                "bib_ms": round(float(bib["measure_median_ms"]), 3),
                "bib_speedup": round(float(bib["speedup_vs_baseline"]), 4),
                "incremental_ms": round(float(inc["measure_median_ms"].median()), 3),
                "incremental_speedup": round(float(inc["speedup_vs_baseline"].median()), 4),
                "visual_equal_rate": round(float(subset["visual_equal_rate"].min()), 4),
            }
        )

    rollup = pd.DataFrame(rows)
    rollup.to_csv(artifact_root / "external_validation_rollup.csv", index=False)

    lines = [
        "# External Validation Summary",
        "",
        f"- groups: {summary.shape[0]}",
        "",
    ]
    for _, row in rollup.iterrows():
        lines.append(
            "- {} {}: clean {:.2f}x, bib {:.2f}x, incremental {:.2f}x, visual_equal_rate={:.2f}".format(
                row["workload"],
                row["config"],
                row["clean_speedup"],
                row["bib_speedup"],
                row["incremental_speedup"],
                row["visual_equal_rate"],
            )
        )
    lines.append("")
    (artifact_root / "external_validation_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(
        {
            "rollup": str(artifact_root / "external_validation_rollup.csv"),
            "summary_md": str(artifact_root / "external_validation_summary.md"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
