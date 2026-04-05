from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.gridspec as gridspec
import matplotlib.image as mpimg
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scienceplots  # noqa: F401
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import Bbox
from mpl_toolkits.axes_grid1.inset_locator import inset_axes


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "tmp" / "figures_v1"
EXPORT_PROFILE = "manuscript"
SHOW_PANEL_TITLES = EXPORT_PROFILE != "manuscript"
# Hard default: explanatory notes should live in captions, legends, or figure margins.
# Internal note overlays require an explicit opt-in and are off even for standalone exports.
SHOW_AUX_NOTES = False
FONT_SCALE = 2.15 if EXPORT_PROFILE == "manuscript" else 1.0
MAX_INLINE_NOTE_CHARS = 32

PALETTE = {
    "sky": "#96CCEA",
    "lavender": "#B2A3DD",
    "rose": "#ED949A",
    "mint": "#A4DDD3",
    "deep_blue": "#4D8FC4",
    "violet": "#7A70D6",
    "ink": "#2D3A46",
    "warm": "#F0B27A",
    "sand": "#F6E6D5",
    "paper": "#FBFBFA",
    "grid": "#D9E1EA",
    "soft_grey": "#A0AAB4",
    "dark_grey": "#586471",
    "success": "#53A89B",
}

DATASET_LABELS = {
    "feedback_prize_ell": "Feedback Prize ELL",
    "asap_aes_kaggle_parquet": "ASAP-AES",
}

MODEL_LABELS = {
    "openai/gpt-5.4-mini": "GPT-5.4-mini",
    "deepseek/deepseek-chat": "DeepSeek",
    "z-ai/glm-5": "GLM-5",
}

SHORT_MODEL_LABELS = {
    "GPT-5.4-mini": "GPT-5.4",
    "DeepSeek": "DeepSeek",
    "GLM-5": "GLM-5",
}

CONDITION_LABELS = {
    "hybrid": "Hybrid",
    "llm_direct_feedback": "Direct Feedback",
    "llm_direct_rewrite_supplement": "Direct Rewrite",
    "rule_only": "Rule-only",
}

MODEL_COLORS = {
    "GPT-5.4-mini": PALETTE["deep_blue"],
    "DeepSeek": PALETTE["warm"],
    "GLM-5": PALETTE["violet"],
}

CONDITION_COLORS = {
    "Direct Feedback": PALETTE["sky"],
    "Hybrid": PALETTE["rose"],
    "Direct Rewrite": PALETTE["warm"],
    "Rule-only": PALETTE["soft_grey"],
}

CONDITION_MARKERS = {
    "Direct Feedback": "o",
    "Hybrid": "s",
    "Direct Rewrite": "D",
    "Rule-only": "X",
}

REASON_LABELS = {
    "empty_feedback": "Empty outputs",
    "placeholder_probe": "Placeholder probe",
    "placeholder_flagged_in_review": "Review-flagged placeholder",
}

REASON_COLORS = {
    "empty_feedback": PALETTE["rose"],
    "placeholder_probe": PALETTE["deep_blue"],
    "placeholder_flagged_in_review": PALETTE["success"],
}

DIMENSION_LABELS = {
    "actionable_mean": "Actionable",
    "clarity_mean": "Clarity",
    "pedagogical_usefulness_mean": "Pedagogical\nUsefulness",
    "dimension_coverage_mean": "Dimension\nCoverage",
    "over_rewriting_risk_mean": "Over-rewriting\nSafety",
    "learner_autonomy_support_mean": "Learner\nAutonomy",
}

METRIC_DISPLAY = {
    "pedagogical_depth_score": "Pedagogical depth",
    "student_text_preservation_rate": "Preservation",
    "non_overwriting_score": "Non-overwriting",
    "learner_autonomy_support_score": "Autonomy",
    "schema_validity_score": "Schema validity",
}


def apply_publication_theme() -> None:
    plt.style.use(["science", "nature", "no-latex"])
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [
                "Times New Roman",
                "Noto Serif CJK SC",
                "STIXGeneral",
                "DejaVu Serif",
            ],
            "mathtext.fontset": "stix",
            "figure.facecolor": "white",
            "axes.facecolor": PALETTE["paper"],
            "axes.edgecolor": "#29323A",
            "axes.linewidth": 1.0,
            "axes.labelsize": 17.8,
            "axes.titlesize": 18.8,
            "axes.titleweight": "semibold",
            "xtick.labelsize": 16.8,
            "ytick.labelsize": 16.8,
            "xtick.color": "#202A32",
            "ytick.color": "#202A32",
            "xtick.major.width": 1.0,
            "ytick.major.width": 1.0,
            "xtick.major.size": 5.0,
            "ytick.major.size": 5.0,
            "grid.color": PALETTE["grid"],
            "grid.linewidth": 0.65,
            "grid.alpha": 0.7,
            "legend.frameon": False,
            "legend.fontsize": 16.0,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
        }
    )


def fs(value: float) -> float:
    return value * FONT_SCALE


def export_figure(fig: plt.Figure, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf", "svg"):
        save_args = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == "png":
            save_args["dpi"] = 600
        fig.savefig(stem.with_suffix(f".{suffix}"), **save_args)


def maybe_set_panel_title(ax: plt.Axes, title: str | None, *, loc: str = "left", pad: float = 8) -> None:
    if SHOW_PANEL_TITLES and title:
        ax.set_title(title, loc=loc, pad=pad)


def add_panel_label(
    ax: plt.Axes,
    label: str,
    *,
    x: float = -0.08,
    y: float = 1.02,
    fontsize: float = 12.2,
) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=fs(fontsize),
        fontweight="bold",
        color=PALETTE["ink"],
        ha="left",
        va="bottom",
    )


def validate_inline_note(text: str) -> str:
    raw = str(text)
    if "\n" in raw:
        raise ValueError("Inline explanatory notes must stay single-line; move longer explanations to the caption or figure margin.")
    compact = " ".join(raw.split())
    if len(compact) > MAX_INLINE_NOTE_CHARS:
        raise ValueError("Inline explanatory notes must remain short; move longer copy to the caption, legend, or figure margin.")
    return compact


def open_spines(ax: plt.Axes, visible: list[str]) -> None:
    visible_set = set(visible)
    for name, spine in ax.spines.items():
        spine.set_visible(name in visible_set)


def darken_color(color: str, factor: float = 0.78) -> tuple[float, float, float]:
    rgb = np.array(mpl.colors.to_rgb(color))
    return tuple(np.clip(rgb * factor, 0.0, 1.0))


def add_offset_label(
    ax: plt.Axes,
    x: float,
    y: float,
    text: str,
    color: str,
    dx: float = 6,
    dy: float = 4,
    ha: str = "left",
    va: str = "center",
    fontsize: float = 7.9,
    with_arrow: bool = False,
) -> None:
    note = validate_inline_note(text)
    label = ax.annotate(
        note,
        xy=(x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        ha=ha,
        va=va,
        fontsize=fs(fontsize),
        color=darken_color(color),
        zorder=6,
        clip_on=False,
        arrowprops=(
            {
                "arrowstyle": "-",
                "color": mpl.colors.to_rgba(darken_color(color), 0.55),
                "linewidth": 0.75,
                "shrinkA": 2,
                "shrinkB": 4,
            }
            if with_arrow
            else None
        ),
    )
    label.set_path_effects([pe.withStroke(linewidth=1.3, foreground="white", alpha=0.98)])
    return label


def _alignment_from_offset(dx: float, dy: float) -> tuple[str, str]:
    if dx > 2:
        ha = "left"
    elif dx < -2:
        ha = "right"
    else:
        ha = "center"
    if dy > 2:
        va = "bottom"
    elif dy < -2:
        va = "top"
    else:
        va = "center"
    return ha, va


def _offset_candidates(dx: float, dy: float) -> list[tuple[float, float, str, str]]:
    base_x = max(abs(dx), 7.0)
    base_y = max(abs(dy), 7.0)
    x_dir = 1.0 if dx >= 0 else -1.0
    y_dir = 1.0 if dy >= 0 else -1.0
    candidates = [
        (x_dir * base_x, y_dir * base_y),
        (x_dir * base_x, -y_dir * base_y),
        (-x_dir * (base_x + 2.0), y_dir * base_y),
        (-x_dir * (base_x + 2.0), -y_dir * base_y),
        (x_dir * (base_x + 7.0), 0.0),
        (-x_dir * (base_x + 7.0), 0.0),
        (0.0, y_dir * (base_y + 7.0)),
        (0.0, -y_dir * (base_y + 7.0)),
    ]
    unique_candidates: list[tuple[float, float, str, str]] = []
    seen: set[tuple[float, float, str, str]] = set()
    for cand_dx, cand_dy in candidates:
        ha, va = _alignment_from_offset(cand_dx, cand_dy)
        key = (round(cand_dx, 2), round(cand_dy, 2), ha, va)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append((cand_dx, cand_dy, ha, va))
    return unique_candidates


def _annotation_bbox(annotation: plt.Annotation, renderer: mpl.backend_bases.RendererBase) -> Bbox:
    return annotation.get_window_extent(renderer=renderer).expanded(1.06, 1.16)


def place_avoiding_labels(
    ax: plt.Axes,
    label_specs: list[dict[str, object]],
    *,
    fontsize: float = 7.8,
    inside_pad: float = 6.0,
    default_with_arrow: bool = True,
) -> list[plt.Annotation]:
    if not label_specs:
        return []

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_bbox = ax.get_window_extent(renderer).padded(-inside_pad)
    occupied_bboxes: list[Bbox] = []
    annotations: list[plt.Annotation] = []

    ordered_specs = sorted(label_specs, key=lambda item: float(item.get("priority", 0.0)))
    for spec in ordered_specs:
        x = float(spec["x"])
        y = float(spec["y"])
        text = str(spec["text"])
        color = str(spec["color"])
        with_arrow = bool(spec.get("with_arrow", default_with_arrow))
        best_choice: tuple[float, tuple[float, float, str, str]] | None = None

        for candidate in _offset_candidates(float(spec.get("dx", 7.0)), float(spec.get("dy", 7.0))):
            cand_dx, cand_dy, cand_ha, cand_va = candidate
            trial = add_offset_label(
                ax,
                x,
                y,
                text,
                color=color,
                dx=cand_dx,
                dy=cand_dy,
                ha=cand_ha,
                va=cand_va,
                fontsize=fontsize,
                with_arrow=with_arrow,
            )
            fig.canvas.draw()
            bbox = _annotation_bbox(trial, renderer)
            overflow = 0.0
            overflow += max(0.0, axes_bbox.x0 - bbox.x0)
            overflow += max(0.0, bbox.x1 - axes_bbox.x1)
            overflow += max(0.0, axes_bbox.y0 - bbox.y0)
            overflow += max(0.0, bbox.y1 - axes_bbox.y1)
            overlap_count = sum(1 for occupied in occupied_bboxes if bbox.overlaps(occupied))
            distance_penalty = abs(cand_dx) + abs(cand_dy)
            score = overlap_count * 10000.0 + overflow * 100.0 + distance_penalty
            trial.remove()
            if best_choice is None or score < best_choice[0]:
                best_choice = (score, candidate)
                if overlap_count == 0 and overflow == 0:
                    break

        if best_choice is None:
            continue

        cand_dx, cand_dy, cand_ha, cand_va = best_choice[1]
        annotation = add_offset_label(
            ax,
            x,
            y,
            text,
            color=color,
            dx=cand_dx,
            dy=cand_dy,
            ha=cand_ha,
            va=cand_va,
            fontsize=fontsize,
            with_arrow=with_arrow,
        )
        fig.canvas.draw()
        occupied_bboxes.append(_annotation_bbox(annotation, renderer))
        annotations.append(annotation)

    return annotations


def add_axis_edge_note(
    ax: plt.Axes,
    text: str,
    *,
    x: float,
    y: float,
    ha: str = "right",
    va: str = "bottom",
    fontsize: float = 6.8,
    color: str | None = None,
) -> None:
    note = validate_inline_note(text)
    artist = ax.text(
        x,
        y,
        note,
        transform=ax.transAxes,
        ha=ha,
        va=va,
        fontsize=fs(fontsize),
        color=color or PALETTE["dark_grey"],
        clip_on=False,
    )
    artist.set_path_effects([pe.withStroke(linewidth=1.2, foreground="white", alpha=0.98)])


def pretty_dataset(name: str) -> str:
    return DATASET_LABELS.get(name, name)


def pretty_model(name: str) -> str:
    return MODEL_LABELS.get(name, name)


def short_model(name: str) -> str:
    return SHORT_MODEL_LABELS.get(name, name)


def pretty_condition(name: str) -> str:
    return CONDITION_LABELS.get(name, name)


def percentile_clip(series: pd.Series, low: float = 0.02, high: float = 0.98) -> pd.Series:
    left = series.quantile(low)
    right = series.quantile(high)
    return series.clip(left, right)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_kappa_table(path: Path) -> pd.DataFrame:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^\|\s*([a-z_]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9]+)\s*\|$", re.MULTILINE)
    rows = []
    for dimension, kappa, paired_items in pattern.findall(text):
        if dimension == "dimension":
            continue
        rows.append(
            {
                "dimension": dimension,
                "kappa": float(kappa),
                "paired_items": int(paired_items),
            }
        )
    return pd.DataFrame(rows)


def build_review_type_average(df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:
    merged = df1.merge(df2, on="feedback_type", suffixes=("_r1", "_r2"))
    rows = []
    for _, row in merged.iterrows():
        item = {"feedback_type": row["feedback_type"]}
        for metric in DIMENSION_LABELS:
            item[metric] = (row[f"{metric}_r1"] + row[f"{metric}_r2"]) / 2.0
        rows.append(item)
    return pd.DataFrame(rows)


def load_data() -> dict[str, object]:
    outputs = ROOT / "outputs"
    review_dir = outputs / "review_round1_first24"
    refine_dir = outputs / "tightened_hybrid_refinement_openai_gpt-5.4-mini"
    repair_dir = outputs / "repair_recheck_v3"
    subset_dir = outputs / "experiment_subsets"

    summary = pd.read_csv(outputs / "cross_model_lowtoken_summary.csv")
    metrics_full = pd.read_csv(outputs / "cross_model_lowtoken_metrics_full.csv")
    review = pd.read_csv(review_dir / "review_summary_scored.csv")
    review_type_r1 = pd.read_csv(review_dir / "review_summary_by_feedback_type_rater1.csv")
    review_type_r2 = pd.read_csv(review_dir / "review_summary_by_feedback_type_rater2.csv")
    kappa = parse_kappa_table(review_dir / "review_summary_scored.md")
    refinement = pd.read_csv(refine_dir / "openai_gpt-5.4-mini_hybrid_tight_comparison.csv")
    tight_metrics = pd.read_csv(refine_dir / "openai_gpt-5.4-mini_hybrid_tight_metrics.csv")
    selection_report = load_json(refine_dir / "selection_report.json")
    repair = pd.read_csv(repair_dir / "repair_recheck_comparison.csv")
    ell_summary = load_json(subset_dir / "feedback_prize_ell_train_80_summary.json")
    asap_summary = load_json(subset_dir / "asap_full_80_summary.json")

    summary["dataset_label"] = summary["dataset_name"].map(pretty_dataset)
    summary["model_label"] = summary["model_id"].map(pretty_model)
    summary["condition_label"] = summary["condition"].map(pretty_condition)

    metrics_full["dataset_label"] = metrics_full["dataset_name"].map(pretty_dataset)
    metrics_full["model_label"] = metrics_full["model_id"].map(pretty_model)
    metrics_full["condition_label"] = metrics_full["condition"].map(pretty_condition)

    review["condition_label"] = review["condition"].map(pretty_condition)
    review_type_avg = build_review_type_average(review_type_r1, review_type_r2)

    return {
        "summary": summary,
        "metrics_full": metrics_full,
        "review": review,
        "review_type_avg": review_type_avg,
        "kappa": kappa,
        "refinement": refinement,
        "tight_metrics": tight_metrics,
        "selection_report": selection_report,
        "repair": repair,
        "ell_summary": ell_summary,
        "asap_summary": asap_summary,
    }


def draw_dumbbell(
    ax: plt.Axes,
    y_positions: np.ndarray,
    before: np.ndarray,
    after: np.ndarray,
    before_color: str,
    after_color: str,
) -> None:
    for y, x0, x1 in zip(y_positions, before, after):
        ax.plot([x0, x1], [y, y], color=PALETTE["grid"], linewidth=2.0, zorder=1)
    ax.scatter(before, y_positions, s=34, facecolors="white", edgecolors=before_color, linewidths=1.4, zorder=3)
    ax.scatter(after, y_positions, s=40, color=after_color, edgecolors="white", linewidths=0.6, zorder=4)


def compact_case_label(dataset_name: str, source_id: object) -> str:
    source = str(source_id)
    if dataset_name == "feedback_prize_ell":
        return f"ELL-{source[-4:]}"
    return f"ASAP-{source}"


def selection_report_frame(selection_report: dict) -> pd.DataFrame:
    rows = []
    for dataset in selection_report["datasets"]:
        dataset_name = dataset["dataset_name"]
        for item in dataset["selected"]:
            rows.append(
                {
                    "dataset_name": dataset_name,
                    "dataset_label": pretty_dataset(dataset_name),
                    "source_id": str(item["source_id"]),
                    "case_label": compact_case_label(dataset_name, item["source_id"]),
                    "failure_score": item["failure_score"],
                    "depth_gap": item["depth_gap"],
                    "preservation_gap": item["preservation_gap"],
                    "non_overwrite_gap": item["non_overwrite_gap"],
                    "budget_penalty": item["budget_penalty"],
                }
            )
    return pd.DataFrame(rows)


def refinement_case_delta_frame(data: dict[str, object]) -> pd.DataFrame:
    selection = selection_report_frame(data["selection_report"])
    baseline = data["metrics_full"].copy()
    baseline = baseline.loc[
        (baseline["model_id"] == "openai/gpt-5.4-mini")
        & (baseline["condition"] == "hybrid")
    ].copy()
    tightened = data["tight_metrics"].copy()

    for frame in (baseline, tightened):
        frame["source_id"] = frame["source_id"].astype(str)

    merged = selection.merge(
        baseline[
            [
                "dataset_name",
                "source_id",
                "pedagogical_depth_score",
                "student_text_preservation_rate",
                "non_overwriting_score",
                "learner_autonomy_support_score",
                "schema_validity_score",
            ]
        ].rename(
            columns={
                "pedagogical_depth_score": "baseline_depth",
                "student_text_preservation_rate": "baseline_preservation",
                "non_overwriting_score": "baseline_non_overwriting",
                "learner_autonomy_support_score": "baseline_autonomy",
                "schema_validity_score": "baseline_schema",
            }
        ),
        on=["dataset_name", "source_id"],
        how="left",
    ).merge(
        tightened[
            [
                "dataset_name",
                "source_id",
                "pedagogical_depth_score",
                "student_text_preservation_rate",
                "non_overwriting_score",
                "learner_autonomy_support_score",
                "schema_validity_score",
            ]
        ].rename(
            columns={
                "pedagogical_depth_score": "tightened_depth",
                "student_text_preservation_rate": "tightened_preservation",
                "non_overwriting_score": "tightened_non_overwriting",
                "learner_autonomy_support_score": "tightened_autonomy",
                "schema_validity_score": "tightened_schema",
            }
        ),
        on=["dataset_name", "source_id"],
        how="left",
    )

    merged["depth_delta"] = merged["tightened_depth"] - merged["baseline_depth"]
    merged["preservation_delta"] = merged["tightened_preservation"] - merged["baseline_preservation"]
    merged["non_overwriting_delta"] = merged["tightened_non_overwriting"] - merged["baseline_non_overwriting"]
    merged["autonomy_delta"] = merged["tightened_autonomy"] - merged["baseline_autonomy"]
    merged["schema_delta"] = merged["tightened_schema"] - merged["baseline_schema"]
    return merged


def draw_dataset_distribution_panel(
    ax: plt.Axes,
    frame: pd.DataFrame,
    value_col: str,
    title: str,
    xlabel: str,
    median_fmt: str,
) -> None:
    order = ["Feedback Prize ELL", "ASAP-AES"]
    sns.violinplot(
        data=frame,
        x=value_col,
        y="dataset_label",
        hue="dataset_label",
        order=order,
        hue_order=order,
        orient="h",
        cut=0,
        inner=None,
        linewidth=1.0,
        saturation=1.0,
        palette={
            "Feedback Prize ELL": PALETTE["lavender"],
            "ASAP-AES": PALETTE["sky"],
        },
        legend=False,
        ax=ax,
    )
    sns.boxplot(
        data=frame,
        x=value_col,
        y="dataset_label",
        order=order,
        orient="h",
        width=0.24,
        showcaps=True,
        showfliers=False,
        boxprops={"facecolor": "white", "edgecolor": PALETTE["ink"], "linewidth": 1.0, "zorder": 4},
        medianprops={"color": PALETTE["ink"], "linewidth": 1.2},
        whiskerprops={"color": PALETTE["dark_grey"], "linewidth": 0.9},
        capprops={"color": PALETTE["dark_grey"], "linewidth": 0.9},
        ax=ax,
    )
    sample_points = pd.concat(
        [
            sub_frame.sample(min(90, len(sub_frame)), random_state=20260403)
            for _, sub_frame in frame.groupby("dataset_label", observed=False)
        ],
        ignore_index=True,
    )
    sns.stripplot(
        data=sample_points,
        x=value_col,
        y="dataset_label",
        hue="dataset_label",
        order=order,
        hue_order=order,
        orient="h",
        jitter=0.16,
        size=2.9,
        alpha=0.23,
        palette={
            "Feedback Prize ELL": PALETTE["violet"],
            "ASAP-AES": PALETTE["deep_blue"],
        },
        linewidth=0,
        legend=False,
        ax=ax,
    )
    maybe_set_panel_title(ax, title, loc="left", pad=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("")
    ax.grid(axis="x", linestyle=(0, (2, 3)))
    open_spines(ax, ["left", "bottom"])
    for idx, dataset_label in enumerate(order):
        series = frame.loc[frame["dataset_label"] == dataset_label, value_col]
        ax.text(
            series.median(),
            idx - 0.28,
            median_fmt.format(series.median()),
            ha="center",
            va="bottom",
            fontsize=fs(8.0),
            color=PALETTE["dark_grey"],
        )


def plot_fig01_data_profile(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    ell_summary = data["ell_summary"]
    asap_summary = data["asap_summary"]
    metrics_full = data["metrics_full"]

    source_profile = (
        metrics_full.loc[:, ["dataset_name", "source_id", "essay_word_count", "diagnosis_density_per_100_words"]]
        .drop_duplicates()
        .copy()
    )
    source_profile["dataset_label"] = source_profile["dataset_name"].map(pretty_dataset)
    source_profile["essay_word_count_clipped"] = source_profile.groupby("dataset_label", observed=False)["essay_word_count"].transform(percentile_clip)
    source_profile["diagnosis_density_clipped"] = source_profile.groupby("dataset_label", observed=False)["diagnosis_density_per_100_words"].transform(percentile_clip)

    ell_rows = []
    total_sum = sum(ell_summary["total_by_stratum"].values())
    selected_sum = sum(ell_summary["selected_by_stratum"].values())
    for key, total in ell_summary["total_by_stratum"].items():
        selected = ell_summary["selected_by_stratum"][key]
        ell_rows.append(
            {
                "band": key.replace("avg_", "").replace("_", " to "),
                "pool_share": total / total_sum,
                "selected_share": selected / selected_sum,
                "pool_count": total,
                "selected_count": selected,
            }
        )
    ell_df = pd.DataFrame(ell_rows).sort_values("band")

    asap_rows = []
    for key, total in asap_summary["total_by_stratum"].items():
        match = re.match(r"prompt_(\d+)_score_(low|mid|high)", key)
        if not match:
            continue
        prompt, score = match.groups()
        asap_rows.append(
            {
                "prompt": f"P{prompt}",
                "score_band": score.title(),
                "selected_count": asap_summary["selected_by_stratum"][key],
                "pool_count": total,
            }
        )
    asap_df = pd.DataFrame(asap_rows)
    heat_selected = (
        asap_df.pivot(index="score_band", columns="prompt", values="selected_count")
        .reindex(index=["High", "Mid", "Low"], columns=[f"P{i}" for i in range(1, 9)])
    )
    heat_pool = (
        asap_df.pivot(index="score_band", columns="prompt", values="pool_count")
        .reindex(index=["High", "Mid", "Low"], columns=[f"P{i}" for i in range(1, 9)])
    )

    fig = plt.figure(figsize=(12.2, 8.4))
    gs = gridspec.GridSpec(
        2,
        2,
        figure=fig,
        width_ratios=[1.12, 1.0],
        height_ratios=[1.0, 1.0],
        wspace=0.28,
        hspace=0.38,
    )
    ell_ax = fig.add_subplot(gs[0, 0])
    heat_ax = fig.add_subplot(gs[1, 0])
    length_ax = fig.add_subplot(gs[0, 1])
    density_ax = fig.add_subplot(gs[1, 1])

    y_positions = np.arange(len(ell_df))[::-1]
    draw_dumbbell(
        ell_ax,
        y_positions=y_positions,
        before=ell_df["pool_share"].to_numpy(),
        after=ell_df["selected_share"].to_numpy(),
        before_color=PALETTE["soft_grey"],
        after_color=PALETTE["rose"],
    )
    ell_ax.set_yticks(y_positions, ell_df["band"])
    ell_ax.set_xlim(0, max(ell_df["pool_share"].max(), ell_df["selected_share"].max()) * 1.12)
    ell_ax.set_xlabel("Share within source pool / selected subset")
    maybe_set_panel_title(ell_ax, "ELL Stratified Sampling Balance", loc="left", pad=8)
    ell_ax.grid(axis="x", linestyle=(0, (2, 3)))
    open_spines(ell_ax, ["left", "bottom"])
    for y, row in zip(y_positions, ell_df.itertuples()):
        ell_ax.text(
            row.selected_share + 0.004,
            y,
            f"{row.selected_count} / {row.pool_count}",
            va="center",
            ha="left",
            fontsize=fs(8.2),
            color=PALETTE["dark_grey"],
        )
    ell_ax.legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=PALETTE["soft_grey"], markeredgewidth=1.4, label="Pool share"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=PALETTE["rose"], markeredgecolor="white", markeredgewidth=0.6, label="Selected share"),
        ],
        loc="lower right",
    )
    add_panel_label(ell_ax, "A")

    heat_map = LinearSegmentedColormap.from_list(
        "sample_heat",
        ["#FBF7F2", "#F2D6C4", "#E8AA95", "#CA6A56"],
    )
    im = heat_ax.imshow(heat_selected, cmap=heat_map, vmin=heat_selected.values.min(), vmax=heat_selected.values.max())
    for row_idx in range(heat_selected.shape[0]):
        for col_idx in range(heat_selected.shape[1]):
            selected = int(heat_selected.iloc[row_idx, col_idx])
            pool = int(heat_pool.iloc[row_idx, col_idx])
            value = heat_selected.iloc[row_idx, col_idx]
            color = "white" if value >= heat_selected.values.max() * 0.7 else PALETTE["ink"]
            heat_ax.text(
                col_idx,
                row_idx,
                f"{selected}\n/{pool}",
                ha="center",
                va="center",
                fontsize=fs(7.9),
                color=color,
                fontweight="semibold",
            )
    heat_ax.set_xticks(range(heat_selected.shape[1]), labels=heat_selected.columns.tolist())
    heat_ax.set_yticks(range(heat_selected.shape[0]), labels=heat_selected.index.tolist())
    maybe_set_panel_title(heat_ax, "ASAP Prompt x Score Stratification", loc="left", pad=8)
    heat_ax.set_xlabel("Prompt")
    heat_ax.set_ylabel("Score band")
    heat_ax.set_xticks(np.arange(-0.5, heat_selected.shape[1], 1), minor=True)
    heat_ax.set_yticks(np.arange(-0.5, heat_selected.shape[0], 1), minor=True)
    heat_ax.grid(which="minor", color="white", linewidth=1.0)
    heat_ax.tick_params(which="minor", bottom=False, left=False)
    open_spines(heat_ax, [])
    add_panel_label(heat_ax, "B")
    cbar = fig.colorbar(im, ax=heat_ax, fraction=0.046, pad=0.03)
    cbar.set_label("Selected count", rotation=90, labelpad=9)
    cbar.outline.set_visible(False)

    draw_dataset_distribution_panel(
        length_ax,
        source_profile,
        "essay_word_count_clipped",
        "Essay Length Distribution in Selected Subsets",
        "Essay word count (2%-98% clipped)",
        "median {:.0f} words",
    )
    add_panel_label(length_ax, "C")

    draw_dataset_distribution_panel(
        density_ax,
        source_profile,
        "diagnosis_density_clipped",
        "Rule-hit Density by Dataset",
        "Diagnosis density per 100 words (2%-98% clipped)",
        "median {:.2f}",
    )
    add_panel_label(density_ax, "D")

    stem = output_dir / "fig01_data_profile_overview"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def plot_fig02_main_depth(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    metrics_full = data["metrics_full"]
    summary = data["summary"]
    subset = metrics_full.loc[metrics_full["condition"].isin(["hybrid", "llm_direct_feedback"])].copy()
    subset["condition_label"] = subset["condition"].map(pretty_condition)
    subset["model_label"] = pd.Categorical(
        subset["model_label"],
        categories=["GPT-5.4-mini", "DeepSeek", "GLM-5"],
        ordered=True,
    )
    subset["dataset_label"] = pd.Categorical(
        subset["dataset_label"],
        categories=["Feedback Prize ELL", "ASAP-AES"],
        ordered=True,
    )

    agg = (
        summary.loc[summary["condition"].isin(["hybrid", "llm_direct_feedback"]), ["dataset_label", "model_label", "condition_label", "pedagogical_depth_score"]]
        .pivot(index=["dataset_label", "model_label"], columns="condition_label", values="pedagogical_depth_score")
        .reset_index()
    )
    agg["delta"] = agg["Hybrid"] - agg["Direct Feedback"]

    fig = plt.figure(figsize=(12.0, 9.1))
    gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.26)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
    condition_order = ["Direct Feedback", "Hybrid"]
    for ax, dataset_label in zip(axes, ["Feedback Prize ELL", "ASAP-AES"]):
        plot_df = subset.loc[subset["dataset_label"] == dataset_label].copy()
        point_samples = pd.concat(
            [
                frame.sample(min(42, len(frame)), random_state=20260403)
                for _, frame in plot_df.groupby(["model_label", "condition_label"], observed=False)
            ],
            ignore_index=True,
        )
        sns.violinplot(
            data=plot_df,
            x="model_label",
            y="pedagogical_depth_score",
            hue="condition_label",
            hue_order=condition_order,
            split=True,
            inner=None,
            cut=0,
            linewidth=1.0,
            palette=[CONDITION_COLORS[label] for label in condition_order],
            ax=ax,
        )
        sns.boxplot(
            data=plot_df,
            x="model_label",
            y="pedagogical_depth_score",
            hue="condition_label",
            hue_order=condition_order,
            width=0.18,
            dodge=True,
            showfliers=False,
            showcaps=True,
            boxprops={"facecolor": "white", "edgecolor": PALETTE["ink"], "linewidth": 0.9},
            medianprops={"color": PALETTE["ink"], "linewidth": 1.0},
            whiskerprops={"color": PALETTE["dark_grey"], "linewidth": 0.8},
            capprops={"color": PALETTE["dark_grey"], "linewidth": 0.8},
            ax=ax,
        )
        sns.stripplot(
            data=point_samples,
            x="model_label",
            y="pedagogical_depth_score",
            hue="condition_label",
            hue_order=condition_order,
            dodge=True,
            jitter=0.18,
            size=2.5,
            alpha=0.22,
            palette=[CONDITION_COLORS[label] for label in condition_order],
            linewidth=0,
            ax=ax,
        )
        ax.legend_.remove()
        maybe_set_panel_title(ax, dataset_label, loc="left", pad=8)
        ax.set_xlabel("")
        ax.grid(axis="y", linestyle=(0, (2, 3)))
        open_spines(ax, ["left", "bottom"])
        ax.set_ylim(0.55, 0.91)
        ax.tick_params(axis="x", labelsize=fs(7.6), pad=4)
        ax.set_facecolor(PALETTE["paper"])
        deltas = agg.loc[agg["dataset_label"] == dataset_label]
        for xpos, row in enumerate(deltas.itertuples()):
            color = PALETTE["success"] if row.delta >= 0 else PALETTE["rose"]
            y_top = min(
                max(plot_df["pedagogical_depth_score"].max() + 0.018, 0.898),
                0.910,
            )
            delta_text = ax.text(
                xpos,
                y_top,
                f"\u0394 {row.delta:+.4f}",
                ha="center",
                va="top",
                fontsize=fs(9.2),
                color=color,
                fontweight="semibold",
            )
            delta_text.set_path_effects([pe.withStroke(linewidth=1.35, foreground="white", alpha=0.98)])
    axes[0].set_ylabel("Pedagogical depth score")
    axes[1].set_ylabel("")
    add_panel_label(axes[0], "A")
    add_panel_label(axes[1], "B")

    legend_handles = [
        Line2D([0], [0], marker="s", linestyle="none", markerfacecolor=CONDITION_COLORS[label], markeredgecolor="white", markeredgewidth=0.7, markersize=8, label=label)
        for label in condition_order
    ]
    fig.legend(
        legend_handles,
        condition_order,
        loc="upper center",
        ncol=2,
        bbox_to_anchor=(0.5, 0.985),
        columnspacing=1.1,
        handletextpad=0.55,
    )
    fig.subplots_adjust(top=0.87, bottom=0.10)
    stem = output_dir / "fig02_main_pedagogical_depth"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def plot_fig03_tradeoff(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    top_label_offsets = {
        ("Feedback Prize ELL", "GPT-5.4-mini"): (7, 7, "left"),
        ("Feedback Prize ELL", "DeepSeek"): (7, -8, "left"),
        ("Feedback Prize ELL", "GLM-5"): (7, 7, "left"),
        ("ASAP-AES", "GPT-5.4-mini"): (7, 7, "left"),
        ("ASAP-AES", "DeepSeek"): (7, -8, "left"),
        ("ASAP-AES", "GLM-5"): (7, 7, "left"),
    }
    frontier_label_offsets = {
        ("Feedback Prize ELL", "GPT-5.4-mini"): (10, 8, "left"),
        ("ASAP-AES", "GPT-5.4-mini"): (10, -11, "left"),
        ("Feedback Prize ELL", "DeepSeek"): (10, 10, "left"),
        ("Feedback Prize ELL", "GLM-5"): (10, 8, "left"),
        ("ASAP-AES", "GLM-5"): (10, -8, "left"),
        ("ASAP-AES", "DeepSeek"): (8, -10, "left"),
    }

    summary = data["summary"].copy()
    summary = summary.loc[summary["condition"].isin(["llm_direct_feedback", "hybrid", "llm_direct_rewrite_supplement"])].copy()
    summary["dataset_label"] = pd.Categorical(
        summary["dataset_label"],
        categories=["Feedback Prize ELL", "ASAP-AES"],
        ordered=True,
    )
    summary["model_label"] = pd.Categorical(
        summary["model_label"],
        categories=["GPT-5.4-mini", "DeepSeek", "GLM-5"],
        ordered=True,
    )
    summary["condition_label"] = pd.Categorical(
        summary["condition_label"],
        categories=["Direct Feedback", "Hybrid", "Direct Rewrite"],
        ordered=True,
    )

    pivot = (
        summary.pivot(index=["dataset_label", "model_label"], columns="condition_label", values=["student_text_preservation_rate", "non_overwriting_score", "pedagogical_depth_score"])
        .reset_index()
    )
    pivot.columns = [
        col if isinstance(col, str) else f"{col[0]}__{str(col[1]).lower().replace(' ', '_')}" if col[1] else col[0]
        for col in pivot.columns.to_flat_index()
    ]
    pivot["row_label"] = (
        pivot["dataset_label"].map({"Feedback Prize ELL": "ELL", "ASAP-AES": "ASAP"}).astype(str)
        + " | "
        + pivot["model_label"].astype(str).map(short_model)
    )
    pivot["dataset_short"] = pivot["dataset_label"].map({"Feedback Prize ELL": "ELL", "ASAP-AES": "ASAP"})
    pivot["depth_gain_vs_direct"] = pivot["pedagogical_depth_score__hybrid"] - pivot["pedagogical_depth_score__direct_feedback"]
    pivot["preservation_gap_vs_direct"] = pivot["student_text_preservation_rate__hybrid"] - pivot["student_text_preservation_rate__direct_feedback"]
    pivot["safety_gain_vs_rewrite"] = pivot["non_overwriting_score__hybrid"] - pivot["non_overwriting_score__direct_rewrite"]

    fig = plt.figure(figsize=(13.4, 10.5))
    gs = gridspec.GridSpec(
        2,
        2,
        figure=fig,
        height_ratios=[1.35, 1.0],
        width_ratios=[1.0, 1.0],
        wspace=0.29,
        hspace=0.48,
    )
    ell_ax = fig.add_subplot(gs[0, 0])
    asap_ax = fig.add_subplot(gs[0, 1])
    heat_ax = fig.add_subplot(gs[1, 0])
    frontier_ax = fig.add_subplot(gs[1, 1])

    for ax, dataset_label in zip([ell_ax, asap_ax], ["Feedback Prize ELL", "ASAP-AES"]):
        dataset_df = summary.loc[summary["dataset_label"] == dataset_label]
        x_min = max(0.18, dataset_df["student_text_preservation_rate"].min() - 0.055)
        x_max = min(1.02, dataset_df["student_text_preservation_rate"].max() + 0.045)
        y_min = max(0.56, dataset_df["pedagogical_depth_score"].min() - 0.04)
        y_max = min(0.88, dataset_df["pedagogical_depth_score"].max() + 0.03)
        x_anchor = np.quantile(dataset_df["student_text_preservation_rate"], 0.62)
        y_anchor = np.quantile(dataset_df["pedagogical_depth_score"], 0.62)
        ax.axvspan(x_anchor, x_max, color=PALETTE["mint"], alpha=0.08, zorder=0)
        ax.axhspan(y_anchor, y_max, color=PALETTE["mint"], alpha=0.08, zorder=0)
        top_label_specs: list[dict[str, object]] = []
        for model_label in ["GPT-5.4-mini", "DeepSeek", "GLM-5"]:
            model_df = dataset_df.loc[dataset_df["model_label"] == model_label].sort_values("condition_label")
            color = MODEL_COLORS[model_label]
            direct = model_df.loc[model_df["condition_label"] == "Direct Feedback"].iloc[0]
            hybrid = model_df.loc[model_df["condition_label"] == "Hybrid"].iloc[0]
            rewrite = model_df.loc[model_df["condition_label"] == "Direct Rewrite"].iloc[0]
            path_x = [
                direct["student_text_preservation_rate"],
                hybrid["student_text_preservation_rate"],
                rewrite["student_text_preservation_rate"],
            ]
            path_y = [
                direct["pedagogical_depth_score"],
                hybrid["pedagogical_depth_score"],
                rewrite["pedagogical_depth_score"],
            ]
            ax.plot(path_x[:2], path_y[:2], color=color, linewidth=2.35, solid_capstyle="round", zorder=2)
            ax.annotate(
                "",
                xy=(path_x[1], path_y[1]),
                xytext=(path_x[0], path_y[0]),
                arrowprops={"arrowstyle": "-|>", "color": color, "linewidth": 0.0, "shrinkA": 0, "shrinkB": 0},
            )
            ax.plot(path_x[1:], path_y[1:], color=color, linewidth=1.55, linestyle=(0, (4, 2)), alpha=0.9, zorder=2)
            ax.annotate(
                "",
                xy=(path_x[2], path_y[2]),
                xytext=(path_x[1], path_y[1]),
                arrowprops={"arrowstyle": "-|>", "color": color, "linewidth": 0.0, "shrinkA": 0, "shrinkB": 0},
            )
            for point in [direct, hybrid, rewrite]:
                ax.scatter(
                    point["student_text_preservation_rate"],
                    point["pedagogical_depth_score"],
                    s=74 if str(point["condition_label"]) != "Hybrid" else 92,
                    color=color,
                    marker=CONDITION_MARKERS[str(point["condition_label"])],
                    edgecolors="white",
                    linewidths=0.9,
                    zorder=4,
                )
            ax.scatter(
                hybrid["student_text_preservation_rate"],
                hybrid["pedagogical_depth_score"],
                s=170,
                facecolors="none",
                edgecolors=color,
                linewidths=0.9,
                alpha=0.35,
                zorder=3,
            )
            dx, dy, _ha = top_label_offsets[(dataset_label, model_label)]
            top_label_specs.append(
                {
                    "x": hybrid["student_text_preservation_rate"],
                    "y": hybrid["pedagogical_depth_score"],
                    "text": short_model(model_label),
                    "color": color,
                    "dx": dx,
                    "dy": dy,
                    "priority": 0.0,
                    "with_arrow": True,
                }
            )
        ax.axhline(y_anchor, color=PALETTE["grid"], linewidth=0.9, linestyle=(0, (3, 3)))
        ax.axvline(x_anchor, color=PALETTE["grid"], linewidth=0.9, linestyle=(0, (3, 3)))
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.grid(linestyle=(0, (2, 3)))
        open_spines(ax, ["left", "bottom"])
        maybe_set_panel_title(ax, dataset_label, loc="left", pad=8)
        ax.set_xlabel("Student-text preservation")
        ax.set_ylabel("Pedagogical depth" if dataset_label == "Feedback Prize ELL" else "")
        place_avoiding_labels(ax, top_label_specs, fontsize=7.6, inside_pad=6.0, default_with_arrow=True)
        if SHOW_AUX_NOTES:
            ax.text(
                0.98,
                0.96,
                "Preferred corner",
                transform=ax.transAxes,
                fontsize=fs(7.8),
                color=PALETTE["dark_grey"],
                ha="right",
                va="top",
            )

    effect_frame = pivot.set_index("row_label")[
        ["depth_gain_vs_direct", "preservation_gap_vs_direct", "safety_gain_vs_rewrite"]
    ].rename(
        columns={
            "depth_gain_vs_direct": "Depth vs\nDirect",
            "preservation_gap_vs_direct": "Preservation\nvs Direct",
            "safety_gain_vs_rewrite": "Safety vs\nRewrite",
        }
    )
    contrast_cmap = LinearSegmentedColormap.from_list(
        "tradeoff_contrast",
        [PALETTE["warm"], "#FBF7F1", PALETTE["deep_blue"]],
    )
    contrast_limit = max(abs(effect_frame.to_numpy()).max(), 0.15)
    heat_im = heatmap_with_labels(
        heat_ax,
        effect_frame.to_numpy(),
        effect_frame.index.tolist(),
        effect_frame.columns.tolist(),
        "Annotated Contrast Matrix",
        contrast_cmap,
        vmin=-contrast_limit,
        vmax=contrast_limit,
        fmt="{value:+.3f}",
        center=0.0,
        aspect="auto",
    )
    heat_ax.set_ylabel("")
    add_panel_label(heat_ax, "C")
    contrast_cbar = fig.colorbar(heat_im, ax=heat_ax, fraction=0.034, pad=0.035)
    contrast_cbar.set_label("Hybrid contrast", rotation=90, labelpad=10)
    contrast_cbar.outline.set_visible(False)

    frontier_ax.axvline(0, color=PALETTE["soft_grey"], linewidth=1.0, linestyle=(0, (4, 3)))
    frontier_ax.axhline(0, color=PALETTE["soft_grey"], linewidth=1.0, linestyle=(0, (4, 3)))
    frontier_ax.axvspan(-0.055, 0.008, color=PALETTE["mint"], alpha=0.08, zorder=0)
    frontier_ax.axhspan(0.0, 0.03, color=PALETTE["mint"], alpha=0.08, zorder=0)
    marker_map = {"Feedback Prize ELL": "o", "ASAP-AES": "^"}
    frontier_label_specs: list[dict[str, object]] = []
    for row in pivot.itertuples():
        point_size = 120 + 360 * row.safety_gain_vs_rewrite
        frontier_ax.scatter(
            row.preservation_gap_vs_direct,
            row.depth_gain_vs_direct,
            s=point_size,
            color=MODEL_COLORS[row.model_label],
            marker=marker_map[row.dataset_label],
            edgecolors="white",
            linewidths=0.9,
            alpha=0.9,
            zorder=3,
        )
        dx, dy, _ha = frontier_label_offsets[(row.dataset_label, row.model_label)]
        frontier_label_specs.append(
            {
                "x": row.preservation_gap_vs_direct,
                "y": row.depth_gain_vs_direct,
                "text": f"{row.dataset_short} / {short_model(row.model_label)}",
                "color": MODEL_COLORS[row.model_label],
                "dx": dx,
                "dy": dy,
                "priority": 0.0,
                "with_arrow": True,
            }
        )
    x_pad = 0.014
    y_pad = 0.018
    frontier_ax.set_xlim(pivot["preservation_gap_vs_direct"].min() - 0.03 - x_pad, 0.02 + x_pad)
    frontier_ax.set_ylim(pivot["depth_gain_vs_direct"].min() - 0.02 - y_pad, pivot["depth_gain_vs_direct"].max() + 0.03 + y_pad)
    frontier_ax.grid(linestyle=(0, (2, 3)))
    open_spines(frontier_ax, ["left", "bottom"])
    frontier_ax.set_xlabel("Preservation cost vs Direct Feedback")
    frontier_ax.set_ylabel("Depth gain vs Direct Feedback")
    maybe_set_panel_title(frontier_ax, "Hybrid Efficiency Frontier", loc="left", pad=8)
    place_avoiding_labels(frontier_ax, frontier_label_specs, fontsize=7.4, inside_pad=7.0, default_with_arrow=True)
    add_panel_label(frontier_ax, "D")

    add_panel_label(ell_ax, "A")
    add_panel_label(asap_ax, "B")

    model_handles = [
        Line2D([0], [0], color=color, linewidth=1.8, label=label)
        for label, color in MODEL_COLORS.items()
    ]
    condition_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="none",
            markerfacecolor=PALETTE["ink"],
            markeredgecolor="white",
            markeredgewidth=0.6,
            markersize=7.5,
            label=label,
        )
        for label, marker in {
            "Direct Feedback": "o",
            "Hybrid": "s",
            "Direct Rewrite": "D",
        }.items()
    ]
    combined_handles = model_handles + condition_handles
    combined_labels = list(MODEL_COLORS.keys()) + ["Direct Feedback", "Hybrid", "Direct Rewrite"]
    fig.legend(
        combined_handles,
        combined_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.988),
        ncol=3,
        columnspacing=1.15,
        handletextpad=0.5,
    )
    fig.subplots_adjust(top=0.88, bottom=0.08)
    stem = output_dir / "fig03_preservation_tradeoff"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def refinement_long_df(refinement: pd.DataFrame) -> pd.DataFrame:
    metric_order = [
        "pedagogical_depth_score",
        "student_text_preservation_rate",
        "non_overwriting_score",
        "learner_autonomy_support_score",
        "schema_validity_score",
    ]
    rows = []
    for row in refinement.itertuples():
        for metric in metric_order:
            rows.append(
                {
                    "dataset_label": pretty_dataset(row.dataset_name),
                    "metric": METRIC_DISPLAY[metric],
                    "baseline": getattr(row, f"baseline_{metric}"),
                    "tightened": getattr(row, f"tightened_{metric}"),
                    "delta": getattr(row, f"delta_{metric}"),
                }
            )
    return pd.DataFrame(rows)


def plot_fig04_refinement(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    refinement = data["refinement"]
    selection = selection_report_frame(data["selection_report"])
    case_delta = refinement_case_delta_frame(data)

    fig = plt.figure(figsize=(13.1, 8.9))
    gs = gridspec.GridSpec(
        2,
        2,
        figure=fig,
        height_ratios=[1.2, 1.0],
        width_ratios=[1.0, 1.0],
        hspace=0.48,
        wspace=0.42,
    )
    ell_ax = fig.add_subplot(gs[0, 0])
    asap_ax = fig.add_subplot(gs[0, 1])
    heat_ax = fig.add_subplot(gs[1, 0])
    dist_ax = fig.add_subplot(gs[1, 1])

    failure_cmap = LinearSegmentedColormap.from_list(
        "failure_gap",
        ["#FAF4EC", "#E9CEAB", PALETTE["rose"]],
    )
    gap_vmax = max(0.20, selection["non_overwrite_gap"].max())
    top_axes = [ell_ax, asap_ax]
    scatter_reference = None
    for ax, dataset_label in zip(top_axes, ["Feedback Prize ELL", "ASAP-AES"]):
        plot_df = selection.loc[selection["dataset_label"] == dataset_label].copy().sort_values("failure_score", ascending=False)
        x_anchor = plot_df["preservation_gap"].median()
        y_anchor = plot_df["depth_gap"].median()
        x_max = plot_df["preservation_gap"].max() + 0.03
        y_max = plot_df["depth_gap"].max() + 0.03
        ax.axvspan(x_anchor, x_max, color=PALETTE["rose"], alpha=0.06, zorder=0)
        ax.axhspan(y_anchor, y_max, color=PALETTE["rose"], alpha=0.06, zorder=0)
        ax.axvline(x_anchor, color=PALETTE["grid"], linewidth=0.9, linestyle=(0, (3, 3)))
        ax.axhline(y_anchor, color=PALETTE["grid"], linewidth=0.9, linestyle=(0, (3, 3)))
        sizes = 110 + 260 * (plot_df["failure_score"] / plot_df["failure_score"].max())
        edgecolors = np.where(plot_df["budget_penalty"] > 0, PALETTE["ink"], PALETTE["soft_grey"])
        linewidths = np.where(plot_df["budget_penalty"] > 0, 1.5, 0.8)
        top_label_specs: list[dict[str, object]] = []
        scatter_reference = ax.scatter(
            plot_df["preservation_gap"],
            plot_df["depth_gap"],
            s=sizes,
            c=plot_df["non_overwrite_gap"],
            cmap=failure_cmap,
            vmin=0.0,
            vmax=gap_vmax,
            edgecolors=edgecolors,
            linewidths=linewidths,
            alpha=0.92,
            zorder=3,
        )
        for rank, row in enumerate(plot_df.head(2).itertuples()):
            near_right = row.preservation_gap > (x_anchor + 0.45 * max(x_max - x_anchor, 1e-6))
            near_top = row.depth_gap > (y_anchor + 0.40 * max(y_max - y_anchor, 1e-6))
            top_label_specs.append(
                {
                    "x": row.preservation_gap,
                    "y": row.depth_gap,
                    "text": row.case_label,
                    "color": PALETTE["ink"],
                    "dx": -8 if near_right else 7,
                    "dy": (-8 if near_top else 8) + (-2 if rank else 0),
                    "priority": float(rank),
                    "with_arrow": True,
                }
            )
        ax.set_xlim(-0.005, x_max)
        ax.set_ylim(-0.005, y_max)
        ax.grid(linestyle=(0, (2, 3)))
        open_spines(ax, ["left", "bottom"])
        maybe_set_panel_title(ax, f"{dataset_label}: Failure landscape", loc="left", pad=7)
        ax.set_xlabel("Preservation drop (Direct Feedback - Hybrid)")
        ax.set_ylabel("Depth drop (Direct Feedback - Hybrid)" if dataset_label == "Feedback Prize ELL" else "")
        place_avoiding_labels(ax, top_label_specs, fontsize=7.0, inside_pad=6.0, default_with_arrow=True)

    gap_cbar = fig.colorbar(scatter_reference, ax=top_axes, fraction=0.022, pad=0.032)
    gap_cbar.set_label("Non-overwriting gap", rotation=90, labelpad=10)
    gap_cbar.outline.set_visible(False)

    delta_frame = refinement.set_index("dataset_name")[
        [
            "delta_pedagogical_depth_score",
            "delta_student_text_preservation_rate",
            "delta_non_overwriting_score",
            "delta_learner_autonomy_support_score",
            "delta_schema_validity_score",
        ]
    ].rename(
        index=DATASET_LABELS,
        columns={
            "delta_pedagogical_depth_score": "Depth",
            "delta_student_text_preservation_rate": "Preservation",
            "delta_non_overwriting_score": "Non-overwriting",
            "delta_learner_autonomy_support_score": "Autonomy",
            "delta_schema_validity_score": "Schema",
        },
    )
    delta_limit = max(0.01, np.abs(delta_frame.to_numpy()).max())
    delta_cmap = LinearSegmentedColormap.from_list(
        "tightened_delta",
        [PALETTE["warm"], "#FBF7F1", PALETTE["success"]],
    )
    heat_im = heatmap_with_labels(
        heat_ax,
        delta_frame.to_numpy(),
        delta_frame.index.tolist(),
        delta_frame.columns.tolist(),
        "Aggregate Metric Recovery",
        delta_cmap,
        vmin=-delta_limit,
        vmax=delta_limit,
        fmt="{value:+.3f}",
        center=0.0,
        aspect="auto",
    )
    delta_cbar = fig.colorbar(heat_im, ax=heat_ax, fraction=0.030, pad=0.070)
    delta_cbar.set_label("Tightened - baseline hybrid", rotation=90, labelpad=10)
    delta_cbar.outline.set_visible(False)

    long_rows = []
    metric_map = {
        "depth_delta": "Depth",
        "preservation_delta": "Preservation",
        "non_overwriting_delta": "Non-overwriting",
        "autonomy_delta": "Autonomy",
    }
    for row in case_delta.itertuples():
        for metric, label in metric_map.items():
            long_rows.append(
                {
                    "dataset_label": row.dataset_label,
                    "metric": label,
                    "delta": getattr(row, metric),
                }
            )
    dist_df = pd.DataFrame(long_rows)
    dist_df["metric"] = pd.Categorical(
        dist_df["metric"],
        categories=["Depth", "Preservation", "Non-overwriting", "Autonomy"],
        ordered=True,
    )
    dataset_palette = {
        "Feedback Prize ELL": PALETTE["lavender"],
        "ASAP-AES": PALETTE["sky"],
    }
    sns.violinplot(
        data=dist_df,
        x="delta",
        y="metric",
        hue="dataset_label",
        orient="h",
        cut=0,
        inner=None,
        linewidth=0.95,
        saturation=1.0,
        palette=dataset_palette,
        ax=dist_ax,
    )
    sns.stripplot(
        data=dist_df,
        x="delta",
        y="metric",
        hue="dataset_label",
        orient="h",
        dodge=True,
        size=3.4,
        alpha=0.68,
        linewidth=0.45,
        edgecolor="white",
        palette=dataset_palette,
        ax=dist_ax,
    )
    handles, labels = dist_ax.get_legend_handles_labels()
    dist_ax.legend(
        handles[:2],
        labels[:2],
        loc="lower center",
        bbox_to_anchor=(0.5, 1.03),
        ncol=2,
        title="",
        columnspacing=0.9,
        handletextpad=0.5,
    )
    dist_ax.axvline(0, color=PALETTE["soft_grey"], linewidth=1.0, linestyle=(0, (4, 3)))
    dist_ax.grid(axis="x", linestyle=(0, (2, 3)))
    open_spines(dist_ax, ["left", "bottom"])
    dist_ax.set_xlabel("Case-level delta after tightened prompting")
    dist_ax.set_ylabel("")
    maybe_set_panel_title(dist_ax, "Per-case Recovery Distribution", loc="left", pad=7)

    add_panel_label(ell_ax, "A")
    add_panel_label(asap_ax, "B")
    add_panel_label(heat_ax, "C")
    add_panel_label(dist_ax, "D")
    fig.subplots_adjust(top=0.94, bottom=0.08)
    stem = output_dir / "fig04_tightened_refinement_before_after"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def heatmap_with_labels(
    ax: plt.Axes,
    matrix: np.ndarray,
    row_labels: list[str],
    col_labels: list[str],
    title: str,
    cmap: LinearSegmentedColormap,
    vmin: float,
    vmax: float,
    fmt: str = "{value:.2f}",
    center: float | None = None,
    aspect: str = "equal",
):
    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect=aspect)
    threshold = center if center is not None else (vmin + vmax) / 2
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = matrix[row, col]
            color = "white" if value >= threshold else PALETTE["ink"]
            ax.text(
                col,
                row,
                fmt.format(value=value),
                ha="center",
                va="center",
                fontsize=fs(8.2),
                color=color,
                fontweight="semibold",
            )
    ax.set_xticks(range(len(col_labels)), labels=col_labels)
    ax.set_yticks(range(len(row_labels)), labels=row_labels)
    maybe_set_panel_title(ax, title, loc="left", pad=8)
    ax.set_xticks(np.arange(-0.5, len(col_labels), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(row_labels), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.05)
    ax.tick_params(which="minor", bottom=False, left=False)
    open_spines(ax, [])
    return im


def plot_fig05_human_review(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    review = data["review"]
    review_type_avg = data["review_type_avg"]
    kappa = data["kappa"].copy()
    kappa["display"] = kappa["dimension"].map(
        {
            "actionable": "Actionable",
            "clarity": "Clarity",
            "pedagogical_usefulness": "Pedagogical\nUsefulness",
            "dimension_coverage": "Dimension\nCoverage",
            "over_rewriting_risk": "Over-rewriting\nSafety",
            "learner_autonomy_support": "Learner\nAutonomy",
        }
    )

    review_matrix = review[[*DIMENSION_LABELS]].to_numpy()
    review_rows = [pretty_condition(value) for value in review["condition"].tolist()]

    type_order = ["structured_feedback", "rule_minimal_output", "empty_feedback"]
    review_type_avg = review_type_avg.set_index("feedback_type").loc[type_order].reset_index()
    type_matrix = review_type_avg[[*DIMENSION_LABELS]].to_numpy()
    type_rows = [label.replace("_", " ").title() for label in review_type_avg["feedback_type"].tolist()]

    heat_cmap = LinearSegmentedColormap.from_list(
        "review_heat",
        ["#F8F4EE", "#E9D5C1", "#CF9B84", "#B25B54", "#6D79C5"],
    )

    fig = plt.figure(figsize=(12.4, 6.6))
    gs = gridspec.GridSpec(
        2,
        2,
        figure=fig,
        width_ratios=[1.45, 1.0],
        height_ratios=[1.0, 1.0],
        wspace=0.3,
        hspace=0.35,
    )
    heat_ax = fig.add_subplot(gs[:, 0])
    kappa_ax = fig.add_subplot(gs[0, 1])
    type_ax = fig.add_subplot(gs[1, 1])

    heat_im = heatmap_with_labels(
        heat_ax,
        review_matrix,
        review_rows,
        list(DIMENSION_LABELS.values()),
        "Condition-level Mean Ratings",
        heat_cmap,
        vmin=1.0,
        vmax=5.0,
    )
    add_panel_label(heat_ax, "A")
    cbar = fig.colorbar(heat_im, ax=heat_ax, fraction=0.028, pad=0.02)
    cbar.set_label("Mean score", rotation=90, labelpad=10)
    cbar.outline.set_visible(False)

    kappa = kappa.sort_values("kappa")
    y_positions = np.arange(len(kappa))
    for y, row in zip(y_positions, kappa.itertuples()):
        kappa_ax.plot([0.90, row.kappa], [y, y], color=PALETTE["grid"], linewidth=2.0)
        kappa_ax.scatter(row.kappa, y, s=46, color=PALETTE["deep_blue"], edgecolors="white", linewidths=0.6, zorder=3)
        kappa_ax.text(row.kappa + 0.0015, y, f"{row.kappa:.4f}", va="center", ha="left", fontsize=fs(8.0), color=PALETTE["ink"])
    kappa_ax.set_yticks(y_positions, kappa["display"])
    kappa_ax.set_xlim(0.90, 1.005)
    kappa_ax.set_xlabel("Quadratic weighted kappa")
    maybe_set_panel_title(kappa_ax, "Inter-rater Agreement", loc="left", pad=8)
    kappa_ax.grid(axis="x", linestyle=(0, (2, 3)))
    open_spines(kappa_ax, ["left", "bottom"])
    add_panel_label(kappa_ax, "B")

    type_im = heatmap_with_labels(
        type_ax,
        type_matrix,
        type_rows,
        list(DIMENSION_LABELS.values()),
        "Averaged Ratings by Output Type",
        heat_cmap,
        vmin=1.0,
        vmax=5.0,
    )
    add_panel_label(type_ax, "C")
    type_ax.text(
        0.0,
        -0.26,
        "Structured feedback remains competitive; empty outputs and rule-minimal outputs explain the low condition averages.",
        transform=type_ax.transAxes,
        fontsize=fs(8.0),
        color=PALETTE["dark_grey"],
        ha="left",
        va="top",
    )
    stem = output_dir / "fig05_human_review_overview"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def plot_fig06_repair(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    repair = data["repair"].copy()
    repair["reason_label"] = repair["selection_reason"].map(REASON_LABELS)
    repair["source_id"] = repair["source_id"].astype(str)
    repair["case_label"] = [compact_case_label(ds, sid) for ds, sid in zip(repair["dataset_name"], repair["source_id"])]
    repair["depth_delta"] = repair["depth_after"] - repair["depth_before"]
    repair["preservation_delta"] = repair["preservation_after"] - repair["preservation_before"]
    repair["non_overwriting_delta"] = repair["non_overwriting_after"] - repair["non_overwriting_before"]
    repair["placeholder_removed_flag"] = (repair["placeholder_issue_count_removed"] > 0).astype(int)
    repair["reason_order"] = pd.Categorical(
        repair["selection_reason"],
        categories=["empty_feedback", "placeholder_flagged_in_review", "placeholder_probe"],
        ordered=True,
    )

    audit_counts = pd.DataFrame(
        [
            {
                "metric": "Empty outputs",
                "before": int(repair["empty_before"].sum()),
                "after": int(repair["empty_after"].sum()),
            },
            {
                "metric": "Placeholder mentions",
                "before": int(repair["placeholder_mentioned_before"].sum()),
                "after": int(repair["placeholder_mentioned_after"].sum()),
            },
            {
                "metric": "Filtered during repair",
                "before": 0,
                "after": int(repair["placeholder_filtered_after"].sum()),
            },
        ]
    )
    audit_matrix = audit_counts[["before", "after"]].to_numpy()

    case_matrix = repair.sort_values(["reason_order", "depth_delta"], ascending=[True, False]).reset_index(drop=True)
    matrix_cols = [
        ("empty_before", "Empty\nbefore"),
        ("placeholder_mentioned_before", "Placeholder\nbefore"),
        ("placeholder_removed_flag", "Issue\nremoved"),
        ("placeholder_filtered_after", "Filtered\nafter"),
    ]
    action_matrix = case_matrix[[col for col, _ in matrix_cols]].to_numpy()

    fig = plt.figure(figsize=(13.0, 8.8))
    gs = gridspec.GridSpec(
        2,
        2,
        figure=fig,
        width_ratios=[0.95, 1.35],
        height_ratios=[0.9, 1.2],
        wspace=0.34,
        hspace=0.36,
    )
    audit_ax = fig.add_subplot(gs[0, 0])
    matrix_ax = fig.add_subplot(gs[0, 1])
    tradeoff_ax = fig.add_subplot(gs[1, 0])
    outcome_ax = fig.add_subplot(gs[1, 1])

    count_cmap = LinearSegmentedColormap.from_list(
        "repair_counts",
        ["#FBF7F2", "#E2CCB6", PALETTE["deep_blue"]],
    )
    heatmap_with_labels(
        audit_ax,
        audit_matrix,
        audit_counts["metric"].tolist(),
        ["Before", "After"],
        "Failure Modes Neutralized",
        count_cmap,
        vmin=0,
        vmax=max(1, int(audit_matrix.max())),
        fmt="{value:.0f}",
    )
    add_panel_label(audit_ax, "A")

    binary_cmap = LinearSegmentedColormap.from_list(
        "repair_binary",
        [PALETTE["paper"], PALETTE["sky"], PALETTE["deep_blue"]],
    )
    matrix_ax.imshow(action_matrix, cmap=binary_cmap, vmin=0, vmax=1, aspect="auto")
    matrix_ax.set_xticks(range(len(matrix_cols)), [label for _, label in matrix_cols])
    matrix_ax.set_yticks(range(len(case_matrix)), case_matrix["case_label"])
    maybe_set_panel_title(matrix_ax, "Case-level Audit Matrix", loc="left", pad=8)
    matrix_ax.set_xticks(np.arange(-0.5, len(matrix_cols), 1), minor=True)
    matrix_ax.set_yticks(np.arange(-0.5, len(case_matrix), 1), minor=True)
    matrix_ax.grid(which="minor", color="white", linewidth=1.0)
    matrix_ax.tick_params(which="minor", bottom=False, left=False)
    open_spines(matrix_ax, [])
    for tick, reason in zip(matrix_ax.get_yticklabels(), case_matrix["selection_reason"]):
        tick.set_color(REASON_COLORS[reason])
    group_breaks = np.where(case_matrix["selection_reason"].to_numpy()[:-1] != case_matrix["selection_reason"].to_numpy()[1:])[0]
    for breakpoint in group_breaks:
        matrix_ax.axhline(breakpoint + 0.5, color=PALETTE["ink"], linewidth=0.9)
    add_panel_label(matrix_ax, "B")

    label_offsets = {
        "empty_feedback": (8, 10, "left", "bottom"),
        "placeholder_probe": (-10, -10, "right", "top"),
        "placeholder_flagged_in_review": (8, 10, "left", "bottom"),
    }
    extreme_mask = (repair["preservation_delta"] < -0.30) | (repair["non_overwriting_delta"] < -0.30)
    tradeoff_main = repair.loc[~extreme_mask].copy()
    tradeoff_outlier = repair.loc[extreme_mask].copy()
    tradeoff_ax.axvline(0, color=PALETTE["soft_grey"], linewidth=1.0, linestyle=(0, (4, 3)))
    tradeoff_ax.axhline(0, color=PALETTE["soft_grey"], linewidth=1.0, linestyle=(0, (4, 3)))
    tradeoff_ax.axvspan(-0.035, 0.04, color=PALETTE["mint"], alpha=0.08, zorder=0)
    tradeoff_ax.axhspan(-0.005, 0.04, color=PALETTE["mint"], alpha=0.08, zorder=0)
    for reason, group in tradeoff_main.groupby("selection_reason"):
        size_scale = 75 + 520 * group["depth_delta"].clip(lower=0)
        tradeoff_ax.scatter(
            group["preservation_delta"],
            group["non_overwriting_delta"],
            s=size_scale,
            color=REASON_COLORS[reason],
            edgecolors="white",
            linewidths=0.8,
            alpha=0.82,
            zorder=3,
            label=REASON_LABELS[reason],
        )
        centroid_x = group["preservation_delta"].mean()
        centroid_y = group["non_overwriting_delta"].mean()
        dx, dy, ha, va = label_offsets[reason]
        add_offset_label(
            tradeoff_ax,
            centroid_x,
            centroid_y,
            REASON_LABELS[reason],
            color=REASON_COLORS[reason],
            dx=dx,
            dy=dy,
            ha=ha,
            va=va,
            fontsize=7.6,
            with_arrow=True,
        )
    tradeoff_ax.set_xlim(tradeoff_main["preservation_delta"].min() - 0.03, 0.045)
    tradeoff_ax.set_ylim(tradeoff_main["non_overwriting_delta"].min() - 0.05, 0.04)
    tradeoff_ax.grid(linestyle=(0, (2, 3)))
    open_spines(tradeoff_ax, ["left", "bottom"])
    tradeoff_ax.set_xlabel("Preservation delta")
    tradeoff_ax.set_ylabel("Non-overwriting delta")
    maybe_set_panel_title(tradeoff_ax, "Collateral Effects of Repair", loc="left", pad=8)
    if not tradeoff_outlier.empty:
        inset_ax = inset_axes(
            tradeoff_ax,
            width="28%",
            height="31%",
            loc="lower right",
            bbox_to_anchor=(0.0, 0.04, 1, 1),
            bbox_transform=tradeoff_ax.transAxes,
            borderpad=0.0,
        )
        outlier_row = tradeoff_outlier.iloc[0]
        inset_ax.scatter(
            [outlier_row["preservation_delta"]],
            [outlier_row["non_overwriting_delta"]],
            s=float(75 + 520 * max(outlier_row["depth_delta"], 0.0)),
            color=REASON_COLORS[str(outlier_row["selection_reason"])],
            edgecolors="white",
            linewidths=0.8,
            alpha=0.82,
            zorder=3,
        )
        inset_ax.scatter(
            [outlier_row["preservation_delta"]],
            [outlier_row["non_overwriting_delta"]],
            s=110,
            marker="X",
            color=REASON_COLORS[str(outlier_row["selection_reason"])],
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
        )
        inset_ax.set_xlim(-0.60, -0.45)
        inset_ax.set_ylim(-0.85, -0.68)
        inset_ax.grid(linestyle=(0, (2, 3)))
        open_spines(inset_ax, ["left", "bottom"])
        inset_ax.tick_params(labelsize=fs(6.6), length=3.0)
        inset_ax.set_facecolor("white")
        if SHOW_AUX_NOTES:
            inset_ax.text(
                0.03,
                0.97,
                "Extreme outlier",
                transform=inset_ax.transAxes,
                ha="left",
                va="top",
                fontsize=fs(7.1),
                color=PALETTE["ink"],
            )
    add_panel_label(tradeoff_ax, "C")

    outcome_df = repair.sort_values("depth_delta", ascending=False).reset_index(drop=True)
    y_positions = np.arange(len(outcome_df))[::-1]
    outcome_ax.barh(
        y_positions,
        outcome_df["depth_delta"],
        color=[REASON_COLORS[value] for value in outcome_df["selection_reason"]],
        alpha=0.78,
        height=0.68,
        zorder=2,
    )
    outcome_ax.scatter(
        outcome_df["preservation_delta"],
        y_positions,
        s=34,
        facecolors="white",
        edgecolors=PALETTE["deep_blue"],
        linewidths=1.0,
        zorder=4,
        label="Preservation delta",
    )
    outcome_ax.scatter(
        outcome_df["non_overwriting_delta"],
        y_positions,
        s=44,
        marker="^",
        color=PALETTE["success"],
        edgecolors="white",
        linewidths=0.6,
        zorder=5,
        label="Non-overwriting delta",
    )
    outcome_ax.axvline(0, color=PALETTE["soft_grey"], linewidth=1.0, linestyle=(0, (4, 3)))
    outcome_ax.set_yticks(y_positions, outcome_df["case_label"])
    outcome_ax.set_xlabel("Delta after repair")
    maybe_set_panel_title(outcome_ax, "Per-case Recovery and Side-effects", loc="left", pad=8)
    outcome_ax.grid(axis="x", linestyle=(0, (2, 3)))
    open_spines(outcome_ax, ["left", "bottom"])
    reason_handles = [
        Line2D([0], [0], color=REASON_COLORS[key], linewidth=6, alpha=0.78, label=label)
        for key, label in REASON_LABELS.items()
    ]
    marker_handles = [
        Line2D([0], [0], marker="o", linestyle="none", markerfacecolor="white", markeredgecolor=PALETTE["deep_blue"], markeredgewidth=1.0, markersize=6.2, label="Preservation delta"),
        Line2D([0], [0], marker="^", linestyle="none", markerfacecolor=PALETTE["success"], markeredgecolor="white", markeredgewidth=0.6, markersize=7.0, label="Non-overwriting delta"),
    ]
    outcome_ax.legend(handles=reason_handles + marker_handles, loc="lower right", ncol=1)
    add_panel_label(outcome_ax, "D")

    stem = output_dir / "fig06_repair_recheck_audit"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def plot_fig07_followup_summary(data: dict[str, object], output_dir: Path) -> Path:
    apply_publication_theme()

    refinement = data["refinement"].copy()
    repair = data["repair"].copy()

    refinement_small = refinement.set_index("dataset_name")[
        [
            "delta_pedagogical_depth_score",
            "delta_student_text_preservation_rate",
            "delta_non_overwriting_score",
        ]
    ].rename(
        index={
            "feedback_prize_ell": "ELL",
            "asap_aes_kaggle_parquet": "ASAP",
        },
        columns={
            "delta_pedagogical_depth_score": "Depth",
            "delta_student_text_preservation_rate": "Preservation",
            "delta_non_overwriting_score": "Non-overwriting",
        },
    )

    repair_counts = pd.DataFrame(
        [
            {
                "metric": "Empty",
                "before": int(repair["empty_before"].sum()),
                "after": int(repair["empty_after"].sum()),
                "color": PALETTE["rose"],
            },
            {
                "metric": "Placeholder",
                "before": int(repair["placeholder_mentioned_before"].sum()),
                "after": int(repair["placeholder_mentioned_after"].sum()),
                "color": PALETTE["deep_blue"],
            },
            {
                "metric": "Filter",
                "before": 0,
                "after": int(repair["placeholder_filtered_after"].sum()),
                "color": PALETTE["success"],
            },
        ]
    )

    fig = plt.figure(figsize=(11.8, 5.2))
    gs = gridspec.GridSpec(1, 2, figure=fig, width_ratios=[1.00, 1.00], wspace=0.42)
    heat_ax = fig.add_subplot(gs[0, 0])
    repair_ax = fig.add_subplot(gs[0, 1])

    seq_cmap = LinearSegmentedColormap.from_list(
        "followup_seq",
        ["#F8FBFD", "#D7ECF6", "#96CCEA", "#53A89B"],
    )
    heat_im = heat_ax.imshow(
        refinement_small.to_numpy(),
        cmap=seq_cmap,
        aspect="auto",
        vmin=0.0,
        vmax=max(float(refinement_small.to_numpy().max()), 0.10),
    )
    heat_ax.set_xticks(
        np.arange(len(refinement_small.columns)),
        ["Depth", "Preserv.", "No-overwr."],
    )
    heat_ax.set_yticks(np.arange(len(refinement_small.index)), refinement_small.index)
    heat_ax.tick_params(axis="x", labelsize=fs(7.1), pad=3)
    heat_ax.tick_params(axis="y", labelsize=fs(8.0), pad=4)
    for i in range(refinement_small.shape[0]):
        for j in range(refinement_small.shape[1]):
            value = refinement_small.iloc[i, j]
            text_color = "white" if value > 0.16 else PALETTE["ink"]
            heat_ax.text(
                j,
                i,
                f"+{value:.3f}",
                ha="center",
                va="center",
                fontsize=fs(7.8),
                fontweight="semibold",
                color=text_color,
            )
    heat_ax.set_xlabel("")
    heat_ax.set_ylabel("")
    heat_ax.grid(False)
    open_spines(heat_ax, [])
    for xpos in np.arange(-0.5, refinement_small.shape[1], 1.0):
        heat_ax.axvline(xpos, color="white", linewidth=1.1, alpha=0.9)
    for ypos in np.arange(-0.5, refinement_small.shape[0], 1.0):
        heat_ax.axhline(ypos, color="white", linewidth=1.1, alpha=0.9)
    cbar = fig.colorbar(heat_im, ax=heat_ax, fraction=0.042, pad=0.025)
    cbar.set_label("")
    cbar.ax.set_title("Δ", pad=6, fontsize=fs(7.2), color=PALETTE["ink"])
    cbar.outline.set_visible(False)
    add_panel_label(heat_ax, "A")

    y_positions = np.arange(len(repair_counts))[::-1]
    offset = 0.17
    bar_height = 0.25
    x_max = max(repair_counts["before"].max(), repair_counts["after"].max()) + 1.8
    for y, row in zip(y_positions, repair_counts.itertuples()):
        before_y = y + offset
        after_y = y - offset
        repair_ax.barh(
            before_y,
            row.before,
            height=bar_height,
            color="white",
            edgecolor=row.color,
            linewidth=1.7,
            hatch="///",
            zorder=3,
        )
        repair_ax.barh(
            after_y,
            row.after,
            height=bar_height,
            color=row.color,
            edgecolor="white",
            linewidth=0.8,
            alpha=0.86,
            zorder=4,
        )
        if row.before > 0:
            repair_ax.text(
                row.before + 0.12,
                before_y,
                f"{row.before}",
                ha="left",
                va="center",
                fontsize=fs(7.2),
                color=row.color,
                fontweight="semibold",
            )
        if row.after > 0:
            repair_ax.text(
                row.after + 0.12,
                after_y,
                f"{row.after}",
                ha="left",
                va="center",
                fontsize=fs(7.2),
                color=row.color,
                fontweight="semibold",
            )
    repair_ax.set_yticks(y_positions, repair_counts["metric"])
    repair_ax.tick_params(axis="y", labelsize=fs(7.2), pad=6)
    repair_ax.set_xlim(0, x_max)
    repair_ax.set_xlabel("Audited cases")
    repair_ax.grid(axis="x", linestyle=(0, (2, 3)))
    open_spines(repair_ax, ["left", "bottom"])
    add_panel_label(repair_ax, "B")

    stem = output_dir / "fig07_followup_summary"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def create_contact_sheet(output_dir: Path, stems: list[Path]) -> Path:
    apply_publication_theme()
    ncols = 3
    nrows = int(np.ceil(len(stems) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(13.2, 4.2 * nrows))
    axes_flat = np.atleast_1d(axes).flat
    title_map = {
        "fig01_data_profile_overview": "Fig. 1 Dataset Profile",
        "fig02_main_pedagogical_depth": "Fig. 2 Pedagogical Depth",
        "fig03_preservation_tradeoff": "Fig. 3 Ownership Trade-off",
        "fig04_tightened_refinement_before_after": "Fig. 4 Tightened Refinement",
        "fig05_human_review_overview": "Fig. 5 Human Review",
        "fig06_repair_recheck_audit": "Fig. 6 Repair Audit",
        "fig07_followup_summary": "Fig. 7 Follow-up Summary",
    }
    for ax, stem in zip(axes_flat, stems):
        image = mpimg.imread(stem.with_suffix(".png"))
        ax.imshow(image)
        ax.set_title(title_map.get(stem.stem, stem.stem), pad=8)
        ax.axis("off")
    for ax in list(axes_flat)[len(stems):]:
        ax.axis("off")
    fig.suptitle("Temporary Figure Contact Sheet", y=0.98)
    fig.text(
        0.5,
        0.02,
        "All figures are staged under tmp/figures_v1 and are not inserted into the manuscript PDF.",
        ha="center",
        fontsize=fs(8.4),
        color=PALETTE["dark_grey"],
    )
    stem = output_dir / "00_contact_sheet"
    export_figure(fig, stem)
    plt.close(fig)
    return stem


def write_manifest(output_dir: Path, stems: list[Path]) -> None:
    manifest = [
        {
            "stem": stem.name,
            "png": str(stem.with_suffix(".png")),
            "pdf": str(stem.with_suffix(".pdf")),
            "svg": str(stem.with_suffix(".svg")),
        }
        for stem in stems
    ]
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    readme = "\n".join(
        [
            "# 临时绘图输出",
            "",
            "这些图片仅用于迭代审稿，不会自动插入论文 PDF。",
            "",
            "已生成图件：",
            "",
        ]
        + [f"- `{stem.name}`" for stem in stems]
        + [
            "",
            "流程图暂未绘制；当前批次只包含实验与数据结果图。",
            "",
            "## 当前导出 profile",
            "",
            "当前批次面向论文落版，采用 `manuscript` 导出模式：",
            "",
            "- 删除图内总标题 `suptitle`",
            "- 删除可由 `caption` 代替的 panel title",
            "- 删除底部解释性小字与过渡性提示语",
            "- 保留必要坐标轴、图例、panel label 与关键 callout",
            "",
            "## 图内文本与遮挡硬约束",
            "",
            "- 默认不要在坐标轴内部放大段 `ax.text(...)` 说明框",
            "- 不使用覆盖柱子、折线、marker、误差线或热力格点的大面积文本框",
            "- 趋势解释优先放进 `caption`、精简 legend、图外留白或短 `annotate()`",
            "- 即使使用 `annotate()`，文本也必须短小、单行、不遮挡关键数据",
            "- 数据已经足够清楚时，不为了“丰富”额外添加图内解释文字",
            "",
            "## 复用规则",
            "",
            "后续项目如果需要复用，建议沿用以下做法：",
            "",
            "- 在绘图脚本里显式区分 `standalone` 与 `manuscript` 两种导出模式",
            "- 所有点标注统一走受控偏移标注函数，不直接裸写解释性 `ax.text(...)`",
            "- 标签优先放轴内空白区；放不下时再改引导线或 inset",
            "- 极端离群点优先拆到局部放大 inset，避免把主簇拉空",
            "- panel title 被删除后，要把 A/B/C/D 的语义映射补进 caption",
            "- 说明性文字优先迁移到 `caption`、legend 或图外边缘，不在主绘图区堆文字",
            "",
        ]
    )
    (output_dir / "README.md").write_text(readme, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate temporary result figures for the paper.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for generated figures.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_data()

    stems = [
        plot_fig01_data_profile(data, output_dir),
        plot_fig02_main_depth(data, output_dir),
        plot_fig03_tradeoff(data, output_dir),
        plot_fig04_refinement(data, output_dir),
        plot_fig05_human_review(data, output_dir),
        plot_fig06_repair(data, output_dir),
        plot_fig07_followup_summary(data, output_dir),
    ]
    stems.insert(0, create_contact_sheet(output_dir, stems))
    write_manifest(output_dir, stems)

    print(f"Exported {len(stems)} figure sets to {output_dir}")
    for stem in stems:
        print(stem.name)


if __name__ == "__main__":
    main()
