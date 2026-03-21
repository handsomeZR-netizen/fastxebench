#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def median(values: list[float]) -> float:
    return percentile(values, 0.5)


def load_records(root: Path) -> list[dict]:
    records: list[dict] = []
    for path in root.rglob("result.json"):
        parts = {part.lower() for part in path.parts}
        if "_references" in parts or "_scratch" in parts:
            continue
        records.append(json.loads(path.read_text(encoding="utf-8-sig")))
    return records


def get_measure_ms(record: dict) -> float:
    value = record.get("measure_elapsed_ms", record.get("elapsed_ms", 0.0))
    return float(value or 0.0)


def get_prime_ms(record: dict) -> float:
    value = record.get("prime_elapsed_ms", 0.0)
    return float(value or 0.0)


def get_storage_mode(record: dict) -> str:
    if record.get("requested_storage_mode"):
        return str(record.get("requested_storage_mode"))
    storage = record.get("storage_metadata") or {}
    return str(storage.get("requested_storage_mode") or "")


def get_storage_field(record: dict, key: str) -> str:
    storage = record.get("storage_metadata") or {}
    value = storage.get(key)
    return "" if value is None else str(value)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate benchmark result.json files into summary and per-run CSV files.")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--csv-out", required=True)
    parser.add_argument("--per-run-out")
    args = parser.parse_args()

    root = Path(args.input_root).resolve()
    csv_out = Path(args.csv_out).resolve()
    per_run_out = Path(args.per_run_out).resolve() if args.per_run_out else csv_out.with_name("per_run.csv")

    records = load_records(root)
    grouped: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    baseline_medians: dict[tuple[str, str, str], float] = {}

    for record in records:
        key = (
            record.get("protocol_version", "unknown"),
            get_storage_mode(record),
            record["workload"],
            record["scenario"],
            record["config"],
        )
        grouped[key].append(record)

    for (protocol_version, requested_storage_mode, workload, scenario, config), items in grouped.items():
        if config != "B0_baseline_xelatex":
            continue
        successful = [get_measure_ms(item) for item in items if item.get("success")]
        if successful:
            baseline_medians[(protocol_version, requested_storage_mode, workload, scenario)] = median(successful)

    summary_rows: list[dict] = []
    per_run_rows: list[dict] = []

    for record in sorted(
        records,
        key=lambda item: (
            item.get("protocol_version", "unknown"),
            get_storage_mode(item),
            item["workload"],
            item["scenario"],
            item["config"],
            item.get("run_id", ""),
        ),
    ):
        per_run_rows.append(
            {
                "protocol_version": record.get("protocol_version", "unknown"),
                "requested_storage_mode": get_storage_mode(record),
                "workload": record["workload"],
                "scenario": record["scenario"],
                "config": record["config"],
                "run_id": record.get("run_id", ""),
                "reference_mode": record.get("reference_mode", False),
                "success": record.get("success", False),
                "status": record.get("status", ""),
                "prime_elapsed_ms": round(get_prime_ms(record), 3),
                "measure_elapsed_ms": round(get_measure_ms(record), 3),
                "total_wall_clock_ms": round(float(record.get("total_wall_clock_ms", 0.0) or 0.0), 3),
                "fidelity_binary_equal": record.get("fidelity_binary_equal"),
                "fidelity_visual_equal": record.get("fidelity_visual_equal"),
                "changed_pages_count": record.get("changed_pages_count"),
                "missing_tool": ";".join(record.get("missing_tool", []) or []),
                "storage_drive_letter": get_storage_field(record, "drive_letter"),
                "storage_file_system": get_storage_field(record, "file_system"),
                "defender_performance_mode_status": get_storage_field(record, "defender_performance_mode_status"),
                "reference_pdf": record.get("reference_pdf"),
                "pdf_path": record.get("pdf_path"),
            }
        )

    for (protocol_version, requested_storage_mode, workload, scenario, config), items in sorted(grouped.items()):
        successful_measure = [get_measure_ms(item) for item in items if item.get("success")]
        successful_prime = [get_prime_ms(item) for item in items if item.get("success") and get_prime_ms(item) > 0.0]
        changed_pages = [float(item.get("changed_pages_count", 0) or 0) for item in items if item.get("success")]
        statuses = Counter(str(item.get("status", "")) for item in items)

        success_rate = sum(1 for item in items if item.get("success")) / len(items)
        binary_equal_rate = sum(1 for item in items if item.get("fidelity_binary_equal") is True) / len(items)
        visual_equal_rate = sum(1 for item in items if item.get("fidelity_visual_equal") is True) / len(items)
        current_median = median(successful_measure) if successful_measure else 0.0
        baseline = baseline_medians.get((protocol_version, requested_storage_mode, workload, scenario))
        speedup = (baseline / current_median) if baseline and current_median else 0.0
        sample_record = items[0]

        summary_rows.append(
            {
                "protocol_version": protocol_version,
                "requested_storage_mode": requested_storage_mode,
                "workload": workload,
                "scenario": scenario,
                "config": config,
                "runs": len(items),
                "success_rate": round(success_rate, 4),
                "measure_median_ms": round(current_median, 3),
                "q1_ms": round(percentile(successful_measure, 0.25), 3) if successful_measure else 0.0,
                "q3_ms": round(percentile(successful_measure, 0.75), 3) if successful_measure else 0.0,
                "prime_median_ms": round(median(successful_prime), 3) if successful_prime else 0.0,
                "speedup_vs_baseline": round(speedup, 4),
                "binary_equal_rate": round(binary_equal_rate, 4),
                "visual_equal_rate": round(visual_equal_rate, 4),
                "median_changed_pages": round(median(changed_pages), 3) if changed_pages else 0.0,
                "storage_drive_letter": get_storage_field(sample_record, "drive_letter"),
                "storage_file_system": get_storage_field(sample_record, "file_system"),
                "defender_performance_mode_status": get_storage_field(sample_record, "defender_performance_mode_status"),
                "status_counts": json.dumps(dict(sorted(statuses.items())), ensure_ascii=False),
            }
        )

    write_csv(
        csv_out,
        summary_rows,
        [
            "protocol_version",
            "requested_storage_mode",
            "workload",
            "scenario",
            "config",
            "runs",
            "success_rate",
            "measure_median_ms",
            "q1_ms",
            "q3_ms",
            "prime_median_ms",
            "speedup_vs_baseline",
            "binary_equal_rate",
            "visual_equal_rate",
            "median_changed_pages",
            "storage_drive_letter",
            "storage_file_system",
            "defender_performance_mode_status",
            "status_counts",
        ],
    )
    write_csv(
        per_run_out,
        per_run_rows,
        [
            "protocol_version",
            "requested_storage_mode",
            "workload",
            "scenario",
            "config",
            "run_id",
            "reference_mode",
            "success",
            "status",
            "prime_elapsed_ms",
            "measure_elapsed_ms",
            "total_wall_clock_ms",
            "fidelity_binary_equal",
            "fidelity_visual_equal",
            "changed_pages_count",
            "missing_tool",
            "storage_drive_letter",
            "storage_file_system",
            "defender_performance_mode_status",
            "reference_pdf",
            "pdf_path",
        ],
    )

    print(
        json.dumps(
            {
                "records": len(records),
                "groups": len(summary_rows),
                "csv_out": str(csv_out),
                "per_run_out": str(per_run_out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
