#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
import scienceplots  # noqa: F401
import seaborn as sns


WORKLOAD_ORDER = ["W1_text_math", "W2_cjk_font", "W4_tikz", "W5_minted"]
SCENARIO_ORDER = [
    "S0_clean_build",
    "S1_text_edit",
    "S2_bib_edit",
    "S3_figure_edit",
    "S4_preamble_edit",
]
CONFIG_ORDER = ["B0_baseline_xelatex", "B1_latexmk", "B4_minted_cache"]

WORKLOAD_LABELS = {
    "W1_text_math": "W1 Text+Math",
    "W2_cjk_font": "W2 CJK+Font",
    "W4_tikz": "W4 TikZ",
    "W5_minted": "W5 Minted",
    "R1_fontspec_example": "R1 fontspec",
    "R2_pgfplots_example": "R2 pgfplots",
}
SCENARIO_LABELS = {
    "S0_clean_build": "S0\nClean",
    "S1_text_edit": "S1\nText",
    "S2_bib_edit": "S2\nBib",
    "S3_figure_edit": "S3\nFigure",
    "S4_preamble_edit": "S4\nPreamble",
}
SCENARIO_INLINE_LABELS = {
    "S0_clean_build": "S0 clean",
    "S1_text_edit": "S1 text",
    "S2_bib_edit": "S2 bib",
    "S3_figure_edit": "S3 figure",
    "S4_preamble_edit": "S4 preamble",
}
CONFIG_LABELS = {
    "B0_baseline_xelatex": "B0 baseline",
    "B1_latexmk": "B1 latexmk",
    "B4_minted_cache": "B4 minted cache",
    "B3_latexmk_tikz_externalize": "B3 externalize",
    "B6_tectonic": "B6 tectonic",
}

PALETTE = {
    "B0_baseline_xelatex": "#6E7074",
    "B1_latexmk": "#2E6F7E",
    "B4_minted_cache": "#C67C2E",
    "B3_latexmk_tikz_externalize": "#8D5A97",
    "B6_tectonic": "#A14A3B",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_SOURCE_ROOT = REPO_ROOT / "bench" / "workloads"

WORKLOAD_BOTTLENECKS = {
    "W1_text_math": "Auxiliary reruns plus one lightweight TikZ figure.",
    "W2_cjk_font": "Windows-local CJK and native-font typesetting path.",
    "W4_tikz": "TikZ/pgfplots rendering and figure-page regeneration.",
    "W5_minted": "Pygments highlighting, minted cache reuse, and auxiliary reruns.",
}

EXTERNAL_VALIDATION_ORDER = ["R1_fontspec_example", "R2_pgfplots_example"]
EXTERNAL_VALIDATION_ROLES = {
    "R1_fontspec_example": "Native-font article example outside the synthetic core matrix.",
    "R2_pgfplots_example": "Plot-heavy figure example outside the synthetic core matrix.",
}

PRACTICAL_GUIDANCE_ROWS = [
    {
        "case": "Ordinary incremental writing",
        "recommendation": r"\texttt{B1 latexmk}",
        "notes": "Best default for steady S1/S3/S4 loops on W1, W2, and W4.",
    },
    {
        "case": "Code-heavy minted documents",
        "recommendation": r"\texttt{B4 minted cache}",
        "notes": "Strongest safe path in the current matrix: about 7.16x and roughly 37 seconds saved on incremental edits.",
    },
    {
        "case": "Clean-build or bib-sensitive loops",
        "recommendation": r"\texttt{Measure B0 and B1 locally}",
        "notes": r"\texttt{latexmk} is not guaranteed to win on S0 or S2.",
    },
    {
        "case": "Fidelity-risk acceleration paths",
        "recommendation": r"\texttt{Do not enable by default}",
        "notes": r"\texttt{B3} and \texttt{B6} remain diagnostic paths rather than default recommendations.",
    },
]

SCENARIO_DEFINITIONS = [
    {
        "scenario": "S0_clean_build",
        "prime_required": "No",
        "mutation": "No source mutation; direct clean build.",
        "edit_size": "N/A",
        "scope": "Whole document from scratch.",
    },
    {
        "scenario": "S1_text_edit",
        "prime_required": "Yes",
        "mutation": r"\texttt{\textbackslash benchtexttoken}: \texttt{ALPHA} $\rightarrow$ \texttt{BETA}",
        "edit_size": "Single body-token replacement",
        "scope": "Body text update with possible local page reflow; no bibliography or preamble invalidation.",
    },
    {
        "scenario": "S2_bib_edit",
        "prime_required": "Yes",
        "mutation": r"\texttt{\textbackslash cite\{refalpha\}} $\rightarrow$ \texttt{\textbackslash cite\{refalpha,refbeta\}}",
        "edit_size": "Single cite expansion",
        "scope": r"Triggers \texttt{.aux}/\texttt{.bbl} updates and a bibliography rerun.",
    },
    {
        "scenario": "S3_figure_edit",
        "prime_required": "Yes",
        "mutation": r"\texttt{\textbackslash benchfiguretoken}: \texttt{1.00} $\rightarrow$ \texttt{1.25}",
        "edit_size": "Single numeric figure parameter",
        "scope": "Forces figure/TikZ regeneration without changing bibliography or preamble state.",
    },
    {
        "scenario": "S4_preamble_edit",
        "prime_required": "Yes",
        "mutation": r"\texttt{\textbackslash benchpreambletoken}: \texttt{P0} $\rightarrow$ \texttt{P1}",
        "edit_size": "Single preamble-token replacement",
        "scope": "Invalidates the preamble and forces the document back through the XeLaTeX path.",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate paper-ready figures, tables, and statistics from the FastXeBench datasets."
    )
    parser.add_argument(
        "--dataset-root",
        default=r"D:\desktop\arxiv\results\datasets\protocol_v0_2_core_formal_20x3",
    )
    parser.add_argument(
        "--triage-root",
        default=r"D:\desktop\arxiv\results\datasets\fidelity_triage_b3_b6_20260321",
    )
    parser.add_argument(
        "--external-root",
        default=r"D:\desktop\arxiv\results\datasets\external_validation_r1_20260321",
    )
    parser.add_argument(
        "--b7-root",
        default=r"D:\desktop\arxiv\results\datasets\b7_storage_study_r2_20260321",
    )
    parser.add_argument(
        "--paper-root",
        default=r"D:\desktop\arxiv\paper",
    )
    parser.add_argument("--bootstrap-iters", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def apply_theme() -> None:
    plt.style.use(["science", "nature", "no-latex"])
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "STIX Two Text", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "axes.titlesize": 9.5,
            "axes.labelsize": 8.5,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#444444",
            "axes.facecolor": "#FBFAF7",
            "axes.grid": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "figure.dpi": 180,
            "savefig.dpi": 600,
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "grid.color": "#D9D4C7",
            "grid.linewidth": 0.5,
            "grid.alpha": 0.35,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "svg.fonttype": "none",
        }
    )
    sns.set_palette([PALETTE["B0_baseline_xelatex"], PALETTE["B1_latexmk"], PALETTE["B4_minted_cache"]])


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_figure(fig: plt.Figure, output_base: Path) -> None:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".png", ".pdf", ".svg"):
        fig.savefig(output_base.with_suffix(suffix))


def bootstrap_ci(values: np.ndarray, iterations: int, seed: int) -> tuple[float, float]:
    if values.size == 0:
        return 0.0, 0.0
    if values.size == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(seed)
    resamples = rng.choice(values, size=(iterations, values.size), replace=True)
    medians = np.median(resamples, axis=1)
    return float(np.percentile(medians, 2.5)), float(np.percentile(medians, 97.5))


def latex_escape(text: object) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    value = str(text)
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def bytes_to_gib(total_bytes: int | float | None) -> float:
    if total_bytes is None:
        return 0.0
    return float(total_bytes) / float(1024**3)


def normalize_os_caption(caption: str | None) -> str:
    if not caption:
        return "Unknown OS"
    return caption.replace("家庭中文版", "Home (Chinese edition)")


def normalize_power_plan(power_plan: str | None) -> str:
    if not power_plan:
        return "Unknown"
    if "(平衡)" in power_plan or "(Balanced)" in power_plan:
        return "Balanced"
    return power_plan


def parse_pdf_page_count(pdf_path: Path) -> int | None:
    if not pdf_path.exists():
        return None
    try:
        completed = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return None

    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    match = re.search(r"^Pages:\s+(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def count_bibliography_entries(path: Path) -> int:
    text = path.read_text(encoding="utf-8-sig")
    return len(re.findall(r"^\s*@", text, re.MULTILINE))


def build_workload_anatomy(dataset_root: Path) -> pd.DataFrame:
    rows: list[dict] = []
    for workload in WORKLOAD_ORDER:
        main_tex = WORKLOAD_SOURCE_ROOT / workload / "main.tex"
        refs_bib = WORKLOAD_SOURCE_ROOT / workload / "refs.bib"
        text = main_tex.read_text(encoding="utf-8-sig")
        pdf_path = dataset_root / "raw" / "_references" / workload / "S0_clean_build" / "source" / "main.pdf"

        rows.append(
            {
                "workload": workload,
                "pages": parse_pdf_page_count(pdf_path),
                "main_tex_lines": len(main_tex.read_text(encoding="utf-8-sig").splitlines()),
                "bib_entries": count_bibliography_entries(refs_bib),
                "tikz_figures": len(re.findall(r"\\begin\{tikzpicture\}", text)),
                "minted_blocks": len(re.findall(r"\\begin\{minted\}", text)),
                "has_cjk": bool(re.search(r"[\u4e00-\u9fff]", text)) or "\\documentclass[UTF8]{ctexart}" in text,
                "uses_native_font_path": "\\documentclass[UTF8]{ctexart}" in text or "\\usepackage{fontspec}" in text,
                "uses_minted": "\\usepackage" in text and "minted" in text,
                "expected_bottleneck": WORKLOAD_BOTTLENECKS[workload],
            }
        )

    return pd.DataFrame(rows)


def build_baseline_rollup(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    baseline = summary[summary["config"] == "B0_baseline_xelatex"].copy()
    for workload in WORKLOAD_ORDER:
        subset = baseline[baseline["workload"] == workload].copy()
        if subset.empty:
            continue
        incremental = subset[subset["scenario"].isin(["S1_text_edit", "S3_figure_edit", "S4_preamble_edit"])]
        clean = subset[subset["scenario"] == "S0_clean_build"].iloc[0]
        bib = subset[subset["scenario"] == "S2_bib_edit"].iloc[0]
        rows.append(
            {
                "workload": workload,
                "clean_ms": float(clean["measure_median_ms"]),
                "bib_ms": float(bib["measure_median_ms"]),
                "incremental_ms": float(incremental["measure_median_ms"].median()),
            }
        )
    return pd.DataFrame(rows)


def build_external_validation_anatomy(external_root: Path) -> pd.DataFrame:
    rows: list[dict] = []
    for workload in EXTERNAL_VALIDATION_ORDER:
        main_tex = WORKLOAD_SOURCE_ROOT / workload / "main.tex"
        refs_bib = WORKLOAD_SOURCE_ROOT / workload / "refs.bib"
        text = main_tex.read_text(encoding="utf-8-sig")
        pdf_path = external_root / "raw" / "_references" / workload / "S0_clean_build" / "source" / "main.pdf"

        rows.append(
            {
                "workload": workload,
                "pages": parse_pdf_page_count(pdf_path),
                "main_tex_lines": len(text.splitlines()),
                "bib_entries": count_bibliography_entries(refs_bib),
                "uses_fontspec": "\\usepackage{fontspec}" in text,
                "bibliography_active": "\\cite{" in text,
                "uses_pgfplots": "\\usepackage{pgfplots}" in text or "\\begin{loglogaxis}" in text,
                "why_validation": EXTERNAL_VALIDATION_ROLES[workload],
            }
        )

    return pd.DataFrame(rows)


def extract_command_version(env_payload: dict, command_name: str) -> str:
    def probe_live_version(name: str) -> str | None:
        args = {
            "xelatex": ["--version"],
            "xetex": ["--version"],
            "latexmk": ["-v"],
            "bibtex": ["--version"],
            "kpsewhich": ["--version"],
            "latexminted": ["--version"],
            "pdftoppm": ["-v"],
            "tectonic": ["--version"],
            "hyperfine": ["--version"],
            "conda": ["--version"],
        }.get(name, ["--version"])
        try:
            completed = subprocess.run(
                [name, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            text = (completed.stdout or completed.stderr or "").strip()
            if not text:
                return None
            return "\n".join(line.strip() for line in text.splitlines() if line.strip())
        except Exception:
            return None

    for record in env_payload.get("commands", []):
        if record.get("command") != command_name:
            continue
        raw_text = str(record.get("version", "")).strip()
        needs_probe = any(
            marker in raw_text
            for marker in [
                "I can't find file `-'",
                "Need exactly one file argument",
                "Document stream is empty",
                "invalid choice: '-'",
                "Found argument '-'",
                "Command terminated with non-zero exit code 1",
            ]
        )
        if command_name == "latexmk" and "Version" not in raw_text:
            needs_probe = True
        if command_name == "kpsewhich" and ".tex" in raw_text:
            needs_probe = True
        if needs_probe:
            probed = probe_live_version(command_name)
            if probed:
                raw_text = probed

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return "Unavailable"
        if command_name == "latexmk":
            for line in lines:
                if "Version" in line:
                    return line
        if command_name == "tectonic":
            match = re.search(r"(Tectonic\s+\d+(?:\.\d+)+)", " ".join(lines), re.IGNORECASE)
            if match:
                return match.group(1)
        if command_name == "hyperfine":
            match = re.search(r"(hyperfine\s+\d+(?:\.\d+)+)", " ".join(lines), re.IGNORECASE)
            if match:
                return match.group(1)
        return lines[0]
    return "Unavailable"


def format_interval_seconds(low_ms: float, high_ms: float) -> str:
    return f"[{low_ms / 1000.0:.2f}, {high_ms / 1000.0:.2f}]"


def format_iqr_seconds(q1_ms: float, q3_ms: float) -> str:
    return f"[{q1_ms / 1000.0:.2f}, {q3_ms / 1000.0:.2f}]"


def format_pvalue(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "--"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def holm_correction(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    corrected = [0.0] * len(p_values)
    running_max = 0.0
    total = len(p_values)
    for rank, (original_index, p_value) in enumerate(indexed):
        adjusted = min(1.0, (total - rank) * p_value)
        running_max = max(running_max, adjusted)
        corrected[original_index] = min(1.0, running_max)
    return corrected


def load_core_csvs(dataset_root: Path, triage_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary = pd.read_csv(dataset_root / "csv" / "summary.csv")
    per_run = pd.read_csv(dataset_root / "csv" / "per_run.csv")

    numeric_columns = [
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
    ]
    for column in numeric_columns:
        summary[column] = pd.to_numeric(summary[column], errors="coerce")

    per_run_numeric = [
        "prime_elapsed_ms",
        "measure_elapsed_ms",
        "total_wall_clock_ms",
        "changed_pages_count",
    ]
    for column in per_run_numeric:
        per_run[column] = pd.to_numeric(per_run[column], errors="coerce")

    for column in ("success", "reference_mode", "fidelity_binary_equal", "fidelity_visual_equal"):
        per_run[column] = per_run[column].astype(str).str.lower().map({"true": True, "false": False})

    triage_path = triage_root / "artifact" / "triage-summary.csv"
    triage = pd.read_csv(triage_path) if triage_path.exists() else pd.DataFrame()
    if not triage.empty:
        triage["fidelity_visual_equal"] = triage["fidelity_visual_equal"].astype(str).str.lower().map(
            {"true": True, "false": False}
        )
        triage["changed_pages_count"] = pd.to_numeric(triage["changed_pages_count"], errors="coerce")

    return summary, per_run, triage


def load_followups(external_root: Path, b7_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    external_rollup = pd.read_csv(external_root / "artifact" / "external_validation_rollup.csv")
    b7_rollup = pd.read_csv(b7_root / "artifact" / "b7_rollup.csv")

    for column in (
        "clean_ms",
        "clean_speedup",
        "bib_ms",
        "bib_speedup",
        "incremental_ms",
        "incremental_speedup",
        "visual_equal_rate",
    ):
        external_rollup[column] = pd.to_numeric(external_rollup[column], errors="coerce")

    b7_numeric = [
        "runs",
        "success_rate",
        "measure_median_ms",
        "q1_ms",
        "q3_ms",
        "prime_median_ms",
        "binary_equal_rate",
        "visual_equal_rate",
        "median_changed_pages",
        "baseline_measure_median_ms",
        "latency_ratio_vs_baseline_mode",
    ]
    for column in b7_numeric:
        b7_rollup[column] = pd.to_numeric(b7_rollup[column], errors="coerce")

    return external_rollup, b7_rollup


def load_env_payload(dataset_root: Path) -> dict:
    return json.loads((dataset_root / "artifact" / "env.json").read_text(encoding="utf-8-sig"))


def build_group_stats(summary: pd.DataFrame, per_run: pd.DataFrame, iterations: int, seed: int) -> pd.DataFrame:
    grouped_rows: list[dict] = []
    for keys, group in per_run.groupby(["protocol_version", "workload", "scenario", "config"], sort=False):
        values = group["measure_elapsed_ms"].dropna().to_numpy(dtype=float)
        ci_low, ci_high = bootstrap_ci(values, iterations=iterations, seed=seed)
        grouped_rows.append(
            {
                "protocol_version": keys[0],
                "workload": keys[1],
                "scenario": keys[2],
                "config": keys[3],
                "measure_ci95_low_ms": round(ci_low, 3),
                "measure_ci95_high_ms": round(ci_high, 3),
            }
        )

    stats = pd.DataFrame(grouped_rows)
    merged = summary.merge(stats, on=["protocol_version", "workload", "scenario", "config"], how="left")
    return merged.sort_values(["workload", "scenario", "config"]).reset_index(drop=True)


def build_inferential_stats(group_stats: pd.DataFrame, per_run: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    tests: list[float] = []
    test_row_indexes: list[int] = []

    baseline_lookup: dict[tuple[str, str], np.ndarray] = {}
    for (workload, scenario), group in per_run[per_run["config"] == "B0_baseline_xelatex"].groupby(
        ["workload", "scenario"],
        sort=False,
    ):
        baseline_lookup[(workload, scenario)] = group.sort_values("run_id")["measure_elapsed_ms"].to_numpy(dtype=float)

    non_baseline = group_stats[group_stats["config"] != "B0_baseline_xelatex"].copy()
    non_baseline = non_baseline.sort_values(["workload", "scenario", "config"]).reset_index(drop=True)

    for _, row in non_baseline.iterrows():
        workload = row["workload"]
        scenario = row["scenario"]
        config = row["config"]
        treatment = (
            per_run[
                (per_run["workload"] == workload)
                & (per_run["scenario"] == scenario)
                & (per_run["config"] == config)
            ]
            .sort_values("run_id")["measure_elapsed_ms"]
            .to_numpy(dtype=float)
        )
        baseline = baseline_lookup.get((workload, scenario), np.array([], dtype=float))
        paired_runs = int(min(treatment.size, baseline.size))

        raw_p = np.nan
        statistic = np.nan
        if paired_runs > 0:
            left = baseline[:paired_runs]
            right = treatment[:paired_runs]
            try:
                test = wilcoxon(right, left, alternative="two-sided", zero_method="wilcox", method="auto")
                statistic = float(test.statistic)
                raw_p = float(test.pvalue)
            except ValueError:
                statistic = 0.0
                raw_p = 1.0

        rows.append(
            {
                "workload": workload,
                "scenario": scenario,
                "config": config,
                "paired_runs": paired_runs,
                "measure_median_ms": float(row["measure_median_ms"]),
                "q1_ms": float(row["q1_ms"]),
                "q3_ms": float(row["q3_ms"]),
                "measure_ci95_low_ms": float(row["measure_ci95_low_ms"]),
                "measure_ci95_high_ms": float(row["measure_ci95_high_ms"]),
                "speedup_vs_baseline": float(row["speedup_vs_baseline"]),
                "wilcoxon_statistic": statistic,
                "wilcoxon_raw_p": raw_p,
                "holm_p": np.nan,
                "reject_holm_0_05": False,
                "pairing_rule": "sorted_run_id_within_group",
            }
        )
        if not pd.isna(raw_p):
            test_row_indexes.append(len(rows) - 1)
            tests.append(raw_p)

    corrected = holm_correction(tests)
    for row_index, corrected_value in zip(test_row_indexes, corrected):
        rows[row_index]["holm_p"] = corrected_value
        rows[row_index]["reject_holm_0_05"] = corrected_value <= 0.05

    return pd.DataFrame(rows)


def build_rollup(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    targets = [
        ("W1_text_math", "B1_latexmk"),
        ("W2_cjk_font", "B1_latexmk"),
        ("W4_tikz", "B1_latexmk"),
        ("W5_minted", "B1_latexmk"),
        ("W5_minted", "B4_minted_cache"),
    ]

    for workload, config in targets:
        subset = summary[(summary["workload"] == workload) & (summary["config"] == config)].copy()
        baseline_subset = summary[
            (summary["workload"] == workload) & (summary["config"] == "B0_baseline_xelatex")
        ].copy()
        inc = subset[subset["scenario"].isin(["S1_text_edit", "S3_figure_edit", "S4_preamble_edit"])]
        baseline_inc = baseline_subset[
            baseline_subset["scenario"].isin(["S1_text_edit", "S3_figure_edit", "S4_preamble_edit"])
        ]
        clean = subset[subset["scenario"] == "S0_clean_build"].iloc[0]
        bib = subset[subset["scenario"] == "S2_bib_edit"].iloc[0]
        incremental_ms = float(inc["measure_median_ms"].median())
        baseline_incremental_ms = float(baseline_inc["measure_median_ms"].median())
        rows.append(
            {
                "workload": workload,
                "config": config,
                "clean_ms": round(float(clean["measure_median_ms"]), 3),
                "clean_speedup": round(float(clean["speedup_vs_baseline"]), 4),
                "bib_ms": round(float(bib["measure_median_ms"]), 3),
                "bib_speedup": round(float(bib["speedup_vs_baseline"]), 4),
                "incremental_ms": round(incremental_ms, 3),
                "incremental_saved_ms": round(baseline_incremental_ms - incremental_ms, 3),
                "incremental_speedup": round(float(inc["speedup_vs_baseline"].median()), 4),
                "visual_equal_rate": round(float(subset["visual_equal_rate"].min()), 4),
            }
        )

    return pd.DataFrame(rows)


def write_rollup_table(rollup: pd.DataFrame, output_path: Path) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Formal core rollup for non-baseline configurations. Incremental latency is the median over S1, S3, and S4, and saved seconds are measured against the same-workload XeLaTeX baseline.}",
        r"\label{tab:formal-rollup}",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{llrrrrrrr}",
        r"\toprule",
        r"Workload & Config & Clean (s) & Clean $\times$ & Bib (s) & Bib $\times$ & Incremental (s) & Incremental $\times$ & Inc. saved (s) \\",
        r"\midrule",
    ]

    for _, row in rollup.iterrows():
        lines.append(
            "{} & {} & {:.2f} & {:.2f} & {:.2f} & {:.2f} & {:.2f} & {:.2f} & {:.2f} \\\\".format(
                WORKLOAD_LABELS[row["workload"]],
                CONFIG_LABELS[row["config"]],
                row["clean_ms"] / 1000.0,
                row["clean_speedup"],
                row["bib_ms"] / 1000.0,
                row["bib_speedup"],
                row["incremental_ms"] / 1000.0,
                row["incremental_speedup"],
                row["incremental_saved_ms"] / 1000.0,
            )
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_setup_table(env_payload: dict, output_path: Path) -> None:
    cpu = env_payload.get("processor_name", "Unknown CPU")
    cores = env_payload.get("processor_cores", "?")
    threads = env_payload.get("processor_logical_processors", "?")
    memory_gib = bytes_to_gib(env_payload.get("total_physical_memory_bytes"))
    storage = env_payload.get("storage_metadata", {})

    rows = [
        ("Host CPU", f"{cpu} ({cores} cores / {threads} threads)"),
        ("Memory", f"{memory_gib:.1f} GiB physical RAM"),
        (
            "OS",
            f"{normalize_os_caption(env_payload.get('os_caption'))}, version {env_payload.get('os_version')} (build {env_payload.get('os_build_number')})",
        ),
        ("Machine", f"{env_payload.get('system_model')}"),
        ("Power plan", normalize_power_plan(env_payload.get("power_plan"))),
        (
            "Repository volume",
            f"{storage.get('drive_letter', '?')}: {storage.get('file_system', 'Unknown')} fixed volume; Defender performance mode status {storage.get('defender_performance_mode_status', 'unknown')}",
        ),
        ("Primary TeX engine", extract_command_version(env_payload, "xelatex")),
        ("Automation", f"{extract_command_version(env_payload, 'latexmk')}; {extract_command_version(env_payload, 'hyperfine')}"),
        ("Follow-up engine", extract_command_version(env_payload, "tectonic")),
        ("PDF comparison", f"{extract_command_version(env_payload, 'pdftoppm')} at 144 dpi plus per-page PNG SHA-256"),
        ("Font path", r"\texttt{ctexart} on the local Windows CJK path; R1 validation uses TeX Gyre Pagella, Heros, and Cursor."),
        ("Formal protocol", r"\texttt{v0.2-prime-measure}; 4 workloads, 5 scenarios, 3 main configurations"),
        ("Runs per group", "3 warmups and 20 recorded runs for the formal core matrix"),
    ]

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Experimental setup for the formal core dataset.}",
        r"\label{tab:setup}",
        r"\small",
        r"\begin{tabular}{p{0.28\linewidth}p{0.66\linewidth}}",
        r"\toprule",
        r"Item & Value \\",
        r"\midrule",
    ]
    for item, value in rows:
        rendered = value if value.startswith(r"\texttt") else latex_escape(value)
        lines.append(f"{latex_escape(item)} & {rendered} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_workload_anatomy_table(workload_anatomy: pd.DataFrame, output_path: Path) -> None:
    ordered = workload_anatomy.copy()
    ordered["workload"] = pd.Categorical(ordered["workload"], WORKLOAD_ORDER, ordered=True)
    ordered = ordered.sort_values("workload").reset_index(drop=True)

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Workload anatomy for the four main-matrix workloads.}",
        r"\label{tab:workload-anatomy}",
        r"\small",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{lrrrrcccp{0.28\linewidth}}",
        r"\toprule",
        r"Workload & Pages & Lines & Bib & TikZ & CJK & Native-font & Minted & Expected bottleneck \\",
        r"\midrule",
    ]
    for _, row in ordered.iterrows():
        lines.append(
            "{} & {} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                WORKLOAD_LABELS[row["workload"]],
                "--" if pd.isna(row["pages"]) else int(row["pages"]),
                int(row["main_tex_lines"]),
                int(row["bib_entries"]),
                int(row["tikz_figures"]),
                "yes" if row["has_cjk"] else "no",
                "yes" if row["uses_native_font_path"] else "no",
                "yes" if row["uses_minted"] else "no",
                latex_escape(row["expected_bottleneck"]),
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_scenario_definitions_table(output_path: Path) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Operational scenario definitions used by protocol \texttt{v0.2-prime-measure}.}",
        r"\label{tab:scenario-definitions}",
        r"\small",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{p{0.13\linewidth}p{0.08\linewidth}p{0.30\linewidth}p{0.17\linewidth}p{0.24\linewidth}}",
        r"\toprule",
        r"Scenario & Prime? & Mutation & Edit size & Expected rebuild scope \\",
        r"\midrule",
    ]
    for row in SCENARIO_DEFINITIONS:
        lines.append(
            "{} & {} & {} & {} & {} \\\\".format(
                latex_escape(SCENARIO_INLINE_LABELS[row["scenario"]]),
                row["prime_required"],
                row["mutation"],
                latex_escape(row["edit_size"]),
                row["scope"],
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_baseline_rollup_table(baseline_rollup: pd.DataFrame, output_path: Path) -> None:
    ordered = baseline_rollup.copy()
    ordered["workload"] = pd.Categorical(ordered["workload"], WORKLOAD_ORDER, ordered=True)
    ordered = ordered.sort_values("workload").reset_index(drop=True)

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Baseline latencies for \texttt{B0\_baseline\_xelatex}. Incremental latency is the median over S1, S3, and S4.}",
        r"\label{tab:baseline-rollup}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Workload & Clean (s) & Bib (s) & Incremental (s) \\",
        r"\midrule",
    ]
    for _, row in ordered.iterrows():
        lines.append(
            "{} & {:.2f} & {:.2f} & {:.2f} \\\\".format(
                WORKLOAD_LABELS[row["workload"]],
                row["clean_ms"] / 1000.0,
                row["bib_ms"] / 1000.0,
                row["incremental_ms"] / 1000.0,
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_external_validation_table(external_rollup: pd.DataFrame, output_path: Path) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{External validation rollup for the two real-project-derived workloads.}",
        r"\label{tab:external-validation}",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Workload & Clean $\times$ & Bib $\times$ & Incremental $\times$ & Visual eq. \\",
        r"\midrule",
    ]
    for _, row in external_rollup.iterrows():
        lines.append(
            "{} & {:.2f} & {:.2f} & {:.2f} & {:.2f} \\\\".format(
                WORKLOAD_LABELS.get(row["workload"], row["workload"]),
                row["clean_speedup"],
                row["bib_speedup"],
                row["incremental_speedup"],
                row["visual_equal_rate"],
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_external_validation_anatomy_table(external_anatomy: pd.DataFrame, output_path: Path) -> None:
    ordered = external_anatomy.copy()
    ordered["workload"] = pd.Categorical(ordered["workload"], EXTERNAL_VALIDATION_ORDER, ordered=True)
    ordered = ordered.sort_values("workload").reset_index(drop=True)

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Anatomy of the two real-project-derived external-validation workloads.}",
        r"\label{tab:external-anatomy}",
        r"\small",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{lrrrrccp{0.33\linewidth}}",
        r"\toprule",
        r"Workload & Pages & Lines & Bib & \texttt{fontspec} & Bib-active & PGFPlots & Why this workload matters \\",
        r"\midrule",
    ]
    for _, row in ordered.iterrows():
        lines.append(
            "{} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                WORKLOAD_LABELS[row["workload"]],
                "--" if pd.isna(row["pages"]) else int(row["pages"]),
                int(row["main_tex_lines"]),
                int(row["bib_entries"]),
                "yes" if row["uses_fontspec"] else "no",
                "yes" if row["bibliography_active"] else "no",
                "yes" if row["uses_pgfplots"] else "no",
                latex_escape(row["why_validation"]),
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_practical_guidance_table(output_path: Path) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Practical guidance distilled from the present artifact.}",
        r"\label{tab:practical-guidance}",
        r"\small",
        r"\begin{tabular}{p{0.30\linewidth}p{0.22\linewidth}p{0.38\linewidth}}",
        r"\toprule",
        r"Case & Recommendation & Notes \\",
        r"\midrule",
    ]
    for row in PRACTICAL_GUIDANCE_ROWS:
        lines.append(
            "{} & {} & {} \\\\".format(
                latex_escape(row["case"]),
                row["recommendation"],
                row["notes"],
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_b7_table(b7_rollup: pd.DataFrame, output_path: Path) -> None:
    rows: list[dict] = []
    for mode_label in ["d_repo_ntfs", "c_profile_ntfs"]:
        subset = b7_rollup[b7_rollup["mode_label"] == mode_label].copy()
        if subset.empty:
            continue
        rows.append(
            {
                "mode_label": mode_label,
                "drive": subset["storage_drive_letter"].iloc[0],
                "file_system": subset["storage_file_system"].iloc[0],
                "groups": int(subset.shape[0]),
                "ratio": float(subset["latency_ratio_vs_baseline_mode"].median()),
                "visual_equal_rate": float(subset["visual_equal_rate"].min()),
            }
        )

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Scoped Windows storage follow-up. The baseline mode is the repository-local \texttt{D:} root.}",
        r"\label{tab:b7-storage}",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Mode & Groups & Volume & Median ratio & Visual eq. \\",
        r"\midrule",
    ]
    for row in rows:
        volume = rf"\texttt{{{row['drive']}:/{row['file_system']}}}"
        lines.append(
            "{} & {} & {} & {:.2f} & {:.2f} \\\\".format(
                latex_escape(row["mode_label"]),
                row["groups"],
                volume,
                row["ratio"],
                row["visual_equal_rate"],
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_stats_appendix_table(inferential_stats: pd.DataFrame, output_path: Path) -> None:
    ordered = inferential_stats.copy()
    ordered["workload"] = pd.Categorical(ordered["workload"], WORKLOAD_ORDER, ordered=True)
    ordered["scenario"] = pd.Categorical(ordered["scenario"], SCENARIO_ORDER, ordered=True)
    ordered["config"] = pd.Categorical(ordered["config"], ["B1_latexmk", "B4_minted_cache"], ordered=True)
    ordered = ordered.sort_values(["workload", "scenario", "config"]).reset_index(drop=True)

    lines = [
        r"\begin{table}[p]",
        r"\centering",
        r"\caption{Appendix statistics for the non-baseline main-matrix configurations. IQR is reported as $[Q_1, Q_3]$, CI is the 95\% bootstrap interval for the group median, and Holm-adjusted $p$ values come from two-sided Wilcoxon signed-rank tests that pair runs by within-group recorded order after sorting by \texttt{run\_id}.}",
        r"\label{tab:appendix-stats}",
        r"\small",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{lllrrrrr}",
        r"\toprule",
        r"Workload & Scenario & Config & Median (s) & IQR (s) & 95\% CI (s) & Speedup & Holm $p$ \\",
        r"\midrule",
    ]
    for _, row in ordered.iterrows():
        lines.append(
            "{} & {} & {} & {:.2f} & {} & {} & {:.2f} & {} \\\\".format(
                WORKLOAD_LABELS[row["workload"]],
                SCENARIO_INLINE_LABELS[row["scenario"]],
                CONFIG_LABELS[row["config"]],
                row["measure_median_ms"] / 1000.0,
                format_iqr_seconds(row["q1_ms"], row["q3_ms"]),
                format_interval_seconds(row["measure_ci95_low_ms"], row["measure_ci95_high_ms"]),
                row["speedup_vs_baseline"],
                format_pvalue(row["holm_p"]),
            )
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_speedup_heatmap(summary: pd.DataFrame, output_base: Path) -> None:
    subset = summary[summary["config"] != "B0_baseline_xelatex"].copy()
    subset["row_label"] = subset.apply(
        lambda row: f"{WORKLOAD_LABELS[row['workload']]}\n{CONFIG_LABELS[row['config']]}",
        axis=1,
    )
    row_order = [
        f"{WORKLOAD_LABELS['W1_text_math']}\n{CONFIG_LABELS['B1_latexmk']}",
        f"{WORKLOAD_LABELS['W2_cjk_font']}\n{CONFIG_LABELS['B1_latexmk']}",
        f"{WORKLOAD_LABELS['W4_tikz']}\n{CONFIG_LABELS['B1_latexmk']}",
        f"{WORKLOAD_LABELS['W5_minted']}\n{CONFIG_LABELS['B1_latexmk']}",
        f"{WORKLOAD_LABELS['W5_minted']}\n{CONFIG_LABELS['B4_minted_cache']}",
    ]
    heatmap = subset.pivot(index="row_label", columns="scenario", values="speedup_vs_baseline").reindex(
        index=row_order,
        columns=SCENARIO_ORDER,
    )
    labels = heatmap.apply(lambda column: column.map(lambda value: "" if pd.isna(value) else f"{value:.2f}x"))

    cmap = LinearSegmentedColormap.from_list("fx_speedup", ["#8B9098", "#F6F3ED", "#1F1F1F"])
    norm = TwoSlopeNorm(vmin=float(np.nanmin(heatmap.values)), vcenter=1.0, vmax=float(np.nanmax(heatmap.values)))

    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    sns.heatmap(
        heatmap,
        ax=ax,
        annot=labels,
        fmt="",
        cmap=cmap,
        norm=norm,
        linewidths=0.6,
        linecolor="#F2ECDD",
        annot_kws={"fontsize": 7.4},
        cbar_kws={"label": "Speedup vs baseline"},
    )
    flat_values = heatmap.to_numpy().flatten()
    for text_obj, value in zip(ax.texts, flat_values):
        if pd.isna(value):
            continue
        text_obj.set_color("white" if (value >= 1.35 or value <= 0.9) else "#222222")
        text_obj.set_fontweight("semibold")
    ax.set_xlabel("Scenario")
    ax.set_ylabel("")
    ax.set_xticklabels([SCENARIO_LABELS[item] for item in SCENARIO_ORDER], rotation=0)
    ax.set_title("Formal core speedups by workload and scenario")
    export_figure(fig, output_base)
    plt.close(fig)


def add_distribution_panel(
    ax: plt.Axes,
    per_run: pd.DataFrame,
    summary: pd.DataFrame,
    workload: str,
    scenario: str,
    configs: list[str],
    panel_label: str,
) -> None:
    subset = per_run[
        (per_run["workload"] == workload)
        & (per_run["scenario"] == scenario)
        & (per_run["config"].isin(configs))
    ].copy()
    subset["config_label"] = subset["config"].map(CONFIG_LABELS)
    order = [CONFIG_LABELS[item] for item in configs]
    palette = [PALETTE[item] for item in configs]

    sns.violinplot(
        data=subset,
        x="measure_elapsed_ms",
        y="config_label",
        hue="config_label",
        order=order,
        palette=palette,
        inner=None,
        cut=0,
        linewidth=0.8,
        saturation=1.0,
        legend=False,
        ax=ax,
    )
    sns.stripplot(
        data=subset,
        x="measure_elapsed_ms",
        y="config_label",
        hue="config_label",
        order=order,
        palette=palette,
        size=2.8,
        alpha=0.55,
        jitter=0.13,
        linewidth=0,
        legend=False,
        ax=ax,
    )

    for idx, config in enumerate(configs):
        median_value = float(
            summary[
                (summary["workload"] == workload)
                & (summary["scenario"] == scenario)
                & (summary["config"] == config)
            ]["measure_median_ms"].iloc[0]
        )
        ax.scatter([median_value], [idx], s=28, color="#111111", zorder=4)

    ax.grid(axis="x", color="#D9D4C7", alpha=0.45)
    ax.set_title(f"{panel_label}  {WORKLOAD_LABELS[workload]} | {SCENARIO_LABELS[scenario].replace(chr(10), ' ')}")
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("")


def plot_latency_panels(per_run: pd.DataFrame, summary: pd.DataFrame, output_base: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.7), sharex=False)
    add_distribution_panel(
        axes[0],
        per_run,
        summary,
        workload="W2_cjk_font",
        scenario="S1_text_edit",
        configs=["B0_baseline_xelatex", "B1_latexmk"],
        panel_label="A",
    )
    add_distribution_panel(
        axes[1],
        per_run,
        summary,
        workload="W4_tikz",
        scenario="S3_figure_edit",
        configs=["B0_baseline_xelatex", "B1_latexmk"],
        panel_label="B",
    )
    add_distribution_panel(
        axes[2],
        per_run,
        summary,
        workload="W5_minted",
        scenario="S1_text_edit",
        configs=["B0_baseline_xelatex", "B1_latexmk", "B4_minted_cache"],
        panel_label="C",
    )

    fig.suptitle("Representative latency distributions from the formal core dataset", y=1.03, fontsize=9.8)
    fig.tight_layout()
    export_figure(fig, output_base)
    plt.close(fig)


def plot_fidelity_summary(summary: pd.DataFrame, triage: pd.DataFrame, output_base: Path) -> None:
    rows = []
    for config in CONFIG_ORDER:
        subset = summary[summary["config"] == config]
        if subset.empty:
            continue
        rows.append(
            {
                "label": CONFIG_LABELS[config],
                "visual_equal_rate": float(subset["visual_equal_rate"].mean()),
                "cases": int(subset.shape[0]),
                "changed_pages": float(subset["median_changed_pages"].median()),
                "color": PALETTE[config],
            }
        )

    if not triage.empty:
        for config in ["B3_latexmk_tikz_externalize", "B6_tectonic"]:
            subset = triage[triage["config"] == config]
            if subset.empty:
                continue
            rows.append(
                {
                    "label": CONFIG_LABELS.get(config, config),
                    "visual_equal_rate": float(subset["fidelity_visual_equal"].mean()),
                    "cases": int(subset.shape[0]),
                    "changed_pages": float(subset["changed_pages_count"].median()),
                    "color": PALETTE[config],
                }
            )

    fidelity = pd.DataFrame(rows)
    fidelity = fidelity.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    ax.barh(
        fidelity["label"],
        fidelity["visual_equal_rate"],
        color=fidelity["color"],
        alpha=0.92,
        height=0.58,
    )
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Visual equality rate")
    ax.set_ylabel("")
    ax.grid(axis="x", color="#D9D4C7", alpha=0.45)
    ax.set_title("Fidelity summary for main-matrix and excluded configurations")
    for idx, row in fidelity.iterrows():
        ax.text(
            row["visual_equal_rate"] + 0.02,
            idx,
            f"n={row['cases']}, pages={row['changed_pages']:.0f}",
            va="center",
            ha="left",
            fontsize=7.2,
            color="#333333",
        )
    export_figure(fig, output_base)
    plt.close(fig)


def write_analysis_outputs(
    dataset_root: Path,
    group_stats: pd.DataFrame,
    rollup: pd.DataFrame,
    baseline_rollup: pd.DataFrame,
    workload_anatomy: pd.DataFrame,
    external_anatomy: pd.DataFrame,
    summary: pd.DataFrame,
    triage: pd.DataFrame,
    inferential_stats: pd.DataFrame,
) -> None:
    analysis_root = ensure_dir(dataset_root / "analysis")
    group_stats.to_csv(analysis_root / "formal_group_stats.csv", index=False)
    rollup.to_csv(analysis_root / "formal_rollup.csv", index=False)
    baseline_rollup.to_csv(analysis_root / "formal_baseline_rollup.csv", index=False)
    workload_anatomy.to_csv(analysis_root / "formal_workload_anatomy.csv", index=False)
    external_anatomy.to_csv(analysis_root / "external_validation_anatomy.csv", index=False)
    pd.DataFrame(SCENARIO_DEFINITIONS).to_csv(analysis_root / "formal_scenario_definitions.csv", index=False)
    inferential_stats.to_csv(analysis_root / "formal_inferential_stats.csv", index=False)

    fidelity_rows = []
    for config, label in CONFIG_LABELS.items():
        subset = summary[summary["config"] == config]
        if subset.empty:
            continue
        fidelity_rows.append(
            {
                "config": config,
                "label": label,
                "dataset": "formal_core",
                "visual_equal_rate": round(float(subset["visual_equal_rate"].mean()), 4),
                "median_changed_pages": round(float(subset["median_changed_pages"].median()), 3),
                "cases": int(subset.shape[0]),
            }
        )
    if not triage.empty:
        for config in sorted(triage["config"].dropna().unique()):
            subset = triage[triage["config"] == config]
            fidelity_rows.append(
                {
                    "config": config,
                    "label": CONFIG_LABELS.get(config, config),
                    "dataset": "triage",
                    "visual_equal_rate": round(float(subset["fidelity_visual_equal"].mean()), 4),
                    "median_changed_pages": round(float(subset["changed_pages_count"].median()), 3),
                    "cases": int(subset.shape[0]),
                }
            )
    pd.DataFrame(fidelity_rows).to_csv(analysis_root / "formal_fidelity_summary.csv", index=False)


def main() -> int:
    args = parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    triage_root = Path(args.triage_root).resolve()
    external_root = Path(args.external_root).resolve()
    b7_root = Path(args.b7_root).resolve()
    paper_root = Path(args.paper_root).resolve()

    figures_root = ensure_dir(paper_root / "figures")
    tables_root = ensure_dir(paper_root / "tables")

    apply_theme()
    summary, per_run, triage = load_core_csvs(dataset_root, triage_root)
    external_rollup, b7_rollup = load_followups(external_root, b7_root)
    env_payload = load_env_payload(dataset_root)

    group_stats = build_group_stats(summary, per_run, iterations=args.bootstrap_iters, seed=args.seed)
    inferential_stats = build_inferential_stats(group_stats, per_run)
    rollup = build_rollup(summary)
    baseline_rollup = build_baseline_rollup(summary)
    workload_anatomy = build_workload_anatomy(dataset_root)
    external_anatomy = build_external_validation_anatomy(external_root)

    write_analysis_outputs(
        dataset_root,
        group_stats,
        rollup,
        baseline_rollup,
        workload_anatomy,
        external_anatomy,
        summary,
        triage,
        inferential_stats,
    )
    write_rollup_table(rollup, tables_root / "formal_core_rollup.tex")
    write_baseline_rollup_table(baseline_rollup, tables_root / "formal_baseline_rollup.tex")
    write_workload_anatomy_table(workload_anatomy, tables_root / "formal_workload_anatomy.tex")
    write_scenario_definitions_table(tables_root / "formal_scenario_definitions.tex")
    write_setup_table(env_payload, tables_root / "formal_setup.tex")
    write_practical_guidance_table(tables_root / "practical_guidance.tex")
    write_external_validation_table(external_rollup, tables_root / "external_validation_rollup.tex")
    write_external_validation_anatomy_table(external_anatomy, tables_root / "external_validation_anatomy.tex")
    write_b7_table(b7_rollup, tables_root / "b7_storage_rollup.tex")
    write_stats_appendix_table(inferential_stats, tables_root / "appendix_formal_stats.tex")

    plot_speedup_heatmap(summary, figures_root / "formal_speedup_heatmap")
    plot_latency_panels(per_run, summary, figures_root / "formal_latency_panels")
    plot_fidelity_summary(summary, triage, figures_root / "formal_fidelity_summary")

    print(
        json.dumps(
            {
                "group_stats": str(dataset_root / "analysis" / "formal_group_stats.csv"),
                "inferential_stats": str(dataset_root / "analysis" / "formal_inferential_stats.csv"),
                "rollup": str(dataset_root / "analysis" / "formal_rollup.csv"),
                "baseline_rollup": str(dataset_root / "analysis" / "formal_baseline_rollup.csv"),
                "workload_anatomy": str(dataset_root / "analysis" / "formal_workload_anatomy.csv"),
                "external_anatomy": str(dataset_root / "analysis" / "external_validation_anatomy.csv"),
                "figures": [
                    str(figures_root / "formal_speedup_heatmap.pdf"),
                    str(figures_root / "formal_latency_panels.pdf"),
                    str(figures_root / "formal_fidelity_summary.pdf"),
                ],
                "tables": [
                    str(tables_root / "formal_setup.tex"),
                    str(tables_root / "formal_core_rollup.tex"),
                    str(tables_root / "formal_baseline_rollup.tex"),
                    str(tables_root / "formal_workload_anatomy.tex"),
                    str(tables_root / "formal_scenario_definitions.tex"),
                    str(tables_root / "practical_guidance.tex"),
                    str(tables_root / "external_validation_rollup.tex"),
                    str(tables_root / "external_validation_anatomy.tex"),
                    str(tables_root / "b7_storage_rollup.tex"),
                    str(tables_root / "appendix_formal_stats.tex"),
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
