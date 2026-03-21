#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home()
WINDOWS_HOME_PATTERN = re.compile(r"[A-Za-z]:\\Users\\[^\\]+")
REPO_ROOT_STR = str(REPO_ROOT)
HOME_STR = str(HOME)


def redact_text(value: str) -> str:
    text = value.replace(REPO_ROOT_STR, "<repo-root>")
    text = text.replace(HOME_STR, "<user-home>")
    text = WINDOWS_HOME_PATTERN.sub("<user-home>", text)
    return text


def sanitize_json(obj):
    if isinstance(obj, dict):
        sanitized = {}
        for key, value in obj.items():
            if key == "repo_root":
                sanitized[key] = "<repo-root>"
            elif key == "python":
                sanitized[key] = "python.exe"
            elif key == "path":
                sanitized[key] = "[redacted in public artifact]"
            else:
                sanitized[key] = sanitize_json(value)
        return sanitized
    if isinstance(obj, list):
        return [sanitize_json(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def sanitize_env_json(path: Path) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload = sanitize_json(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_versions_txt(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    lines = []
    for line in text.splitlines():
        if line.startswith("Repo root:"):
            lines.append("Repo root: <repo-root>")
        elif line.startswith("Python:"):
            lines.append("Python: python.exe")
        else:
            lines.append(redact_text(line))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sanitize_csv(path: Path, blank_fields: set[str]) -> None:
    if not path.exists():
        return
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    for row in rows:
        for field in fieldnames:
            if field in blank_fields:
                row[field] = ""
            elif row.get(field):
                row[field] = redact_text(row[field])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sanitize_triage_json(path: Path) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                item["run_directory"] = ""
                item["summary_json"] = ""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    env_files = [
        REPO_ROOT / "artifact" / "env.json",
        REPO_ROOT / "results" / "datasets" / "protocol_v0_2_core_formal_20x3" / "artifact" / "env.json",
        REPO_ROOT / "results" / "datasets" / "external_validation_r1_20260321" / "artifact" / "env.json",
    ]
    versions_files = [
        REPO_ROOT / "artifact" / "versions.txt",
        REPO_ROOT / "results" / "datasets" / "protocol_v0_2_core_formal_20x3" / "artifact" / "versions.txt",
        REPO_ROOT / "results" / "datasets" / "external_validation_r1_20260321" / "artifact" / "versions.txt",
    ]
    csv_jobs = [
        (
            REPO_ROOT / "results" / "datasets" / "protocol_v0_2_core_formal_20x3" / "csv" / "per_run.csv",
            {"reference_pdf", "pdf_path"},
        ),
        (
            REPO_ROOT / "results" / "datasets" / "external_validation_r1_20260321" / "csv" / "per_run.csv",
            {"reference_pdf", "pdf_path"},
        ),
        (
            REPO_ROOT / "results" / "datasets" / "b7_storage_study_r2_20260321" / "artifact" / "b7_combined_per_run.csv",
            {"reference_pdf", "pdf_path"},
        ),
        (
            REPO_ROOT / "results" / "datasets" / "fidelity_triage_b3_b6_20260321" / "artifact" / "triage-summary.csv",
            {"run_directory", "summary_json"},
        ),
    ]

    for path in env_files:
        sanitize_env_json(path)
    for path in versions_files:
        sanitize_versions_txt(path)
    for path, blank_fields in csv_jobs:
        sanitize_csv(path, blank_fields)

    sanitize_triage_json(
        REPO_ROOT / "results" / "datasets" / "fidelity_triage_b3_b6_20260321" / "artifact" / "triage-summary.json"
    )

    print(
        json.dumps(
            {
                "sanitized_env": [str(path.relative_to(REPO_ROOT)) for path in env_files if path.exists()],
                "sanitized_versions": [str(path.relative_to(REPO_ROOT)) for path in versions_files if path.exists()],
                "sanitized_csv": [str(path.relative_to(REPO_ROOT)) for path, _ in csv_jobs if path.exists()],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
