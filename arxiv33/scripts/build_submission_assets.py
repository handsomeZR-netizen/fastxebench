from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scienceplots  # noqa: F401
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "paper" / "Fig"
DIAG_DIR = ROOT / "outputs" / "submission_diagnostics"

SUMMARY_PATH = ROOT / "outputs" / "cross_model_lowtoken_summary.csv"
METRICS_PATH = ROOT / "outputs" / "cross_model_lowtoken_metrics_full.csv"
REFINE_PATH = ROOT / "outputs" / "tightened_hybrid_refinement_openai_gpt-5.4-mini" / "openai_gpt-5.4-mini_hybrid_tight_comparison.csv"
REPAIR_PATH = ROOT / "outputs" / "repair_recheck_v3" / "repair_recheck_comparison.csv"
REVIEW_PATH = ROOT / "outputs" / "review_round1_first24" / "review_summary_scored.csv"
KAPPA_PATH = ROOT / "outputs" / "review_round1_first24" / "review_summary_scored.md"

DATASET_LABELS = {
    "feedback_prize_ell": "Feedback Prize ELL",
    "asap_aes_kaggle_parquet": "ASAP-AES",
}

DATASET_SHORT = {
    "feedback_prize_ell": "ELL",
    "asap_aes_kaggle_parquet": "ASAP",
}

MODEL_LABELS = {
    "openai/gpt-5.4-mini": "GPT-5.4-mini",
    "deepseek/deepseek-chat": "DeepSeek v3.2",
    "z-ai/glm-5": "GLM-5",
}

MODEL_SHORT = {
    "openai/gpt-5.4-mini": "GPT-5.4",
    "deepseek/deepseek-chat": "DeepSeek",
    "z-ai/glm-5": "GLM-5",
}

COLORS = {
    "direct": "#4C72B0",
    "hybrid": "#DD8452",
    "rewrite": "#9AA5B1",
    "positive": "#55A868",
    "negative": "#C44E52",
    "grid": "#E3E6EA",
    "paper": "#FBFBFA",
    "ink": "#24303A",
    "light_blue": "#DCECF8",
    "light_orange": "#F8E2D3",
    "mint": "#DDEFEA",
    "rose": "#F6D8DB",
}

MODEL_ORDER = [
    "openai/gpt-5.4-mini",
    "deepseek/deepseek-chat",
    "z-ai/glm-5",
]

MAX_INLINE_NOTE_CHARS = 32


def apply_theme() -> None:
    plt.style.use(["science", "nature", "no-latex"])
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": 12.0,
            "axes.titlesize": 13.0,
            "axes.labelsize": 12.0,
            "xtick.labelsize": 11.0,
            "ytick.labelsize": 11.0,
            "legend.fontsize": 10.5,
            "figure.facecolor": "white",
            "axes.facecolor": COLORS["paper"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "grid.color": COLORS["grid"],
            "grid.linewidth": 0.7,
            "grid.alpha": 0.9,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def export(fig: plt.Figure, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".pdf"))
    fig.savefig(stem.with_suffix(".png"))


def label_panel(
    ax: plt.Axes,
    label: str,
    *,
    x: float = -0.08,
    y: float = 1.02,
    fontsize: float = 16.0,
) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=fontsize,
        fontweight="bold",
        ha="left",
        va="bottom",
        color=COLORS["ink"],
    )


def validate_inline_note(text: str) -> str:
    raw = str(text)
    if "\n" in raw:
        raise ValueError("Inline annotations must stay single-line; move longer explanations to the caption or figure margin.")
    compact = " ".join(raw.split())
    if len(compact) > MAX_INLINE_NOTE_CHARS:
        raise ValueError("Inline annotations must remain short; move explanatory text to the caption, legend, or figure margin.")
    return compact


def add_short_callout(
    ax: plt.Axes,
    x: float,
    y: float,
    text: str,
    *,
    dx: float,
    dy: float,
    color: str = COLORS["ink"],
    fontsize: float = 8.2,
    ha: str = "left",
    va: str = "center",
    with_arrow: bool = True,
) -> plt.Annotation:
    note = validate_inline_note(text)
    annotation = ax.annotate(
        note,
        xy=(x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        ha=ha,
        va=va,
        fontsize=fontsize,
        color=color,
        clip_on=False,
        arrowprops=(
            {
                "arrowstyle": "-",
                "linewidth": 0.8,
                "color": matplotlib.colors.to_rgba(color, 0.55),
                "shrinkA": 2,
                "shrinkB": 3,
            }
            if with_arrow
            else None
        ),
        zorder=6,
    )
    annotation.set_path_effects([pe.withStroke(linewidth=1.35, foreground="white", alpha=0.98)])
    return annotation


def add_outside_note(
    ax: plt.Axes,
    text: str,
    *,
    x: float,
    y: float,
    ha: str = "right",
    va: str = "bottom",
    fontsize: float = 8.3,
    color: str = "#5A6672",
) -> None:
    note = validate_inline_note(text)
    artist = ax.text(
        x,
        y,
        note,
        transform=ax.transAxes,
        ha=ha,
        va=va,
        fontsize=fontsize,
        color=color,
        clip_on=False,
    )
    artist.set_path_effects([pe.withStroke(linewidth=1.25, foreground="white", alpha=0.98)])


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator, n_boot: int = 10000) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    n = len(values)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = values[idx].mean(axis=1)
    return float(values.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def bootstrap_delta_ci(diff: np.ndarray, rng: np.random.Generator, n_boot: int = 20000) -> tuple[float, float, float]:
    diff = np.asarray(diff, dtype=float)
    n = len(diff)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = diff[idx].mean(axis=1)
    return float(diff.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def parse_kappa_range() -> tuple[float, float]:
    kappas: list[float] = []
    for line in KAPPA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "dimension" in line or "---" in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) >= 3:
            try:
                kappas.append(float(parts[1]))
            except ValueError:
                pass
    return min(kappas), max(kappas)


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary = pd.read_csv(SUMMARY_PATH)
    metrics = pd.read_csv(METRICS_PATH)
    refine = pd.read_csv(REFINE_PATH)
    repair = pd.read_csv(REPAIR_PATH)
    review = pd.read_csv(REVIEW_PATH)
    return summary, metrics, refine, repair, review


def build_bootstrap_weight_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(20260404)
    rows: list[dict[str, object]] = []
    for dataset_name in DATASET_LABELS:
        for model_id in MODEL_ORDER:
            direct = metrics[
                (metrics["dataset_name"] == dataset_name)
                & (metrics["model_id"] == model_id)
                & (metrics["condition"] == "llm_direct_feedback")
            ][
                [
                    "source_id",
                    "pedagogical_depth_score",
                    "student_text_preservation_rate",
                    "actionability_score",
                    "clarity_score",
                    "dimension_coverage_score",
                    "non_overwriting_score",
                    "hint_count",
                    "strategy_count",
                ]
            ].copy()
            hybrid = metrics[
                (metrics["dataset_name"] == dataset_name)
                & (metrics["model_id"] == model_id)
                & (metrics["condition"] == "hybrid")
            ][
                [
                    "source_id",
                    "pedagogical_depth_score",
                    "student_text_preservation_rate",
                    "actionability_score",
                    "clarity_score",
                    "dimension_coverage_score",
                    "non_overwriting_score",
                    "hint_count",
                    "strategy_count",
                ]
            ].copy()
            merged = direct.merge(hybrid, on="source_id", suffixes=("_direct", "_hybrid"))
            depth_delta = merged["pedagogical_depth_score_hybrid"] - merged["pedagogical_depth_score_direct"]
            preservation_delta = merged["student_text_preservation_rate_hybrid"] - merged["student_text_preservation_rate_direct"]
            depth_mean, depth_lo, depth_hi = bootstrap_delta_ci(depth_delta.to_numpy(), rng)
            preservation_mean, preservation_lo, preservation_hi = bootstrap_delta_ci(preservation_delta.to_numpy(), rng)

            scaffolding_direct = np.minimum((merged["hint_count_direct"] + merged["strategy_count_direct"]) / 4.0, 1.0)
            scaffolding_hybrid = np.minimum((merged["hint_count_hybrid"] + merged["strategy_count_hybrid"]) / 4.0, 1.0)
            component_deltas = np.array(
                [
                    float((merged["actionability_score_hybrid"] - merged["actionability_score_direct"]).mean()),
                    float((merged["clarity_score_hybrid"] - merged["clarity_score_direct"]).mean()),
                    float((merged["dimension_coverage_score_hybrid"] - merged["dimension_coverage_score_direct"]).mean()),
                    float((merged["non_overwriting_score_hybrid"] - merged["non_overwriting_score_direct"]).mean()),
                    float((scaffolding_hybrid - scaffolding_direct).mean()),
                ]
            )
            weights = rng.dirichlet(np.ones(5), size=50000)
            sampled_deltas = weights @ component_deltas
            rows.append(
                {
                    "dataset": DATASET_SHORT[dataset_name],
                    "model": MODEL_LABELS[model_id],
                    "depth_delta": depth_mean,
                    "depth_ci_low": depth_lo,
                    "depth_ci_high": depth_hi,
                    "preservation_delta": preservation_mean,
                    "pres_ci_low": preservation_lo,
                    "pres_ci_high": preservation_hi,
                    "uniform_weight_delta": float(component_deltas.mean()),
                    "positive_weight_share": float((sampled_deltas > 0).mean()),
                }
            )
    frame = pd.DataFrame(rows)
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(DIAG_DIR / "bootstrap_weight_summary.csv", index=False)
    md_lines = [
        "# Submission Diagnostics",
        "",
        "| Dataset | Model | Depth delta | 95% CI | Preservation delta | 95% CI | Uniform-weight delta | Positive-weight share |",
        "| --- | --- | ---: | --- | ---: | --- | ---: | ---: |",
    ]
    for row in frame.itertuples():
        md_lines.append(
            f"| {row.dataset} | {row.model} | {row.depth_delta:+.4f} | [{row.depth_ci_low:+.4f}, {row.depth_ci_high:+.4f}] | "
            f"{row.preservation_delta:+.4f} | [{row.pres_ci_low:+.4f}, {row.pres_ci_high:+.4f}] | "
            f"{row.uniform_weight_delta:+.4f} | {row.positive_weight_share:.2%} |"
        )
    (DIAG_DIR / "bootstrap_weight_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return frame


def plot_pipeline_overview(output_stem: Path) -> None:
    apply_theme()
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.set_axis_off()

    stages = [
        ("Essay Input", "public learner draft", 0.18, 0.74, COLORS["light_blue"]),
        ("Rule Diagnosis", "local issues + masking", 0.50, 0.74, "#F0F3F6"),
        ("Prompt Constructor", "condition + budget control", 0.82, 0.74, COLORS["light_orange"]),
        ("LLM Generation", "layered feedback schema", 0.18, 0.28, "#F0F3F6"),
        ("Schema Check / Repair", "parse, complete, sanitize", 0.50, 0.28, COLORS["mint"]),
        ("Structured Output", "diagnosis + hint + strategy + exemplar", 0.82, 0.28, COLORS["light_blue"]),
    ]

    width = 0.24
    height = 0.24
    for title, subtitle, x, y, color in stages:
        box = FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            facecolor=color,
            edgecolor="#6A7580",
            linewidth=0.9,
        )
        ax.add_patch(box)
        ax.text(x, y + 0.04, title, ha="center", va="center", fontsize=11.2, fontweight="semibold", color=COLORS["ink"])
        ax.text(x, y - 0.04, subtitle, ha="center", va="center", fontsize=8.7, color="#5A6672")
    arrows = [
        ((0.30, 0.74), (0.38, 0.74)),
        ((0.62, 0.74), (0.70, 0.74)),
        ((0.82, 0.60), (0.82, 0.42)),
        ((0.30, 0.28), (0.38, 0.28)),
        ((0.62, 0.28), (0.70, 0.28)),
    ]
    for start, end in arrows:
        ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "-|>", "lw": 1.0, "color": "#6A7580"})
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    export(fig, output_stem)
    plt.close(fig)


def plot_main_depth(metrics: pd.DataFrame, output_stem: Path) -> None:
    apply_theme()
    rng = np.random.default_rng(20260404)
    fig, axes = plt.subplots(1, 2, figsize=(7.3, 3.25), sharey=True)
    width = 0.34

    for panel_idx, (ax, dataset_name) in enumerate(zip(axes, DATASET_LABELS)):
        x = np.arange(len(MODEL_ORDER))
        direct_means, direct_err, hybrid_means, hybrid_err, deltas = [], [], [], [], []
        for model_id in MODEL_ORDER:
            direct = metrics[
                (metrics["dataset_name"] == dataset_name)
                & (metrics["model_id"] == model_id)
                & (metrics["condition"] == "llm_direct_feedback")
            ]["pedagogical_depth_score"].to_numpy()
            hybrid = metrics[
                (metrics["dataset_name"] == dataset_name)
                & (metrics["model_id"] == model_id)
                & (metrics["condition"] == "hybrid")
            ]["pedagogical_depth_score"].to_numpy()
            d_mean, d_lo, d_hi = bootstrap_mean_ci(direct, rng)
            h_mean, h_lo, h_hi = bootstrap_mean_ci(hybrid, rng)
            direct_means.append(d_mean)
            direct_err.append([d_mean - d_lo, d_hi - d_mean])
            hybrid_means.append(h_mean)
            hybrid_err.append([h_mean - h_lo, h_hi - h_mean])
            deltas.append(h_mean - d_mean)

        direct_err_arr = np.asarray(direct_err).T
        hybrid_err_arr = np.asarray(hybrid_err).T

        ax.bar(
            x - width / 2,
            direct_means,
            width,
            color=COLORS["direct"],
            edgecolor="white",
            linewidth=0.8,
            yerr=direct_err_arr,
            error_kw={"elinewidth": 0.9, "ecolor": "#4A4F55", "capsize": 2},
            label="Direct Feedback",
            zorder=3,
        )
        ax.bar(
            x + width / 2,
            hybrid_means,
            width,
            color=COLORS["hybrid"],
            edgecolor="white",
            linewidth=0.8,
            yerr=hybrid_err_arr,
            error_kw={"elinewidth": 0.9, "ecolor": "#4A4F55", "capsize": 2},
            label="Hybrid",
            zorder=3,
        )
        ax.set_title(DATASET_LABELS[dataset_name], pad=7, fontweight="semibold")
        ax.set_xticks(x, [MODEL_SHORT[model] for model in MODEL_ORDER])
        ax.set_ylim(0.55, 0.895)
        ax.grid(axis="y", zorder=0)
        if panel_idx == 0:
            ax.set_ylabel("Pedagogical depth")
        label_panel(ax, "A" if panel_idx == 0 else "B")
        for idx, delta in enumerate(deltas):
            color = COLORS["positive"] if delta > 0 else COLORS["negative"]
            sign = "+" if delta > 0 else ""
            y_top = min(
                max(direct_means[idx] + direct_err_arr[1][idx], hybrid_means[idx] + hybrid_err_arr[1][idx]) + 0.010,
                0.886,
            )
            delta_artist = ax.text(
                x[idx],
                y_top,
                f"Δ{sign}{delta:.3f}",
                ha="center",
                va="bottom",
                fontsize=9.2,
                fontweight="semibold",
                color=color,
            )
            delta_artist.set_path_effects([pe.withStroke(linewidth=1.25, foreground="white", alpha=0.98)])

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 1.015),
        columnspacing=1.15,
        handletextpad=0.55,
    )
    fig.subplots_adjust(top=0.80, bottom=0.18, wspace=0.20)
    export(fig, output_stem)
    plt.close(fig)


def plot_followup_summary(refine: pd.DataFrame, repair: pd.DataFrame, output_stem: Path) -> None:
    apply_theme()
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.0, 3.1), gridspec_kw={"width_ratios": [1.1, 1.0]})

    refine_small = refine.set_index("dataset_name")[
        [
            "delta_pedagogical_depth_score",
            "delta_student_text_preservation_rate",
            "delta_non_overwriting_score",
        ]
    ].rename(
        index={"feedback_prize_ell": "ELL", "asap_aes_kaggle_parquet": "ASAP"},
        columns={
            "delta_pedagogical_depth_score": "Depth",
            "delta_student_text_preservation_rate": "Preservation",
            "delta_non_overwriting_score": "Non-overwriting",
        },
    )
    x = np.arange(len(refine_small.columns))
    width = 0.34
    ell = refine_small.loc["ELL"].to_numpy()
    asap = refine_small.loc["ASAP"].to_numpy()
    ax_a.bar(x - width / 2, ell, width, color="#7FB3D8", edgecolor="white", linewidth=0.8, label="ELL", zorder=3)
    ax_a.bar(x + width / 2, asap, width, color="#F4A582", edgecolor="white", linewidth=0.8, label="ASAP", zorder=3)
    for xpos, value in zip(x - width / 2, ell):
        ax_a.text(xpos, value + 0.008, f"+{value:.3f}", ha="center", va="bottom", fontsize=8.8, color=COLORS["ink"])
    for xpos, value in zip(x + width / 2, asap):
        ax_a.text(xpos, value + 0.008, f"+{value:.3f}", ha="center", va="bottom", fontsize=8.8, color=COLORS["ink"])
    ax_a.set_xticks(x, ["Depth", "Preserv.", "No-overwr."])
    ax_a.set_ylim(0, 0.48)
    ax_a.set_ylabel("Improvement (Δ)")
    ax_a.grid(axis="y", zorder=0)
    ax_a.legend(loc="upper left", frameon=False)
    label_panel(ax_a, "A")

    repair_counts = pd.DataFrame(
        [
            {"metric": "Empty", "before": int(repair["empty_before"].sum()), "after": int(repair["empty_after"].sum()), "color": "#F29CA3"},
            {"metric": "Placeholder", "before": int(repair["placeholder_mentioned_before"].sum()), "after": int(repair["placeholder_mentioned_after"].sum()), "color": "#5A9BD5"},
            {"metric": "Filter hits", "before": 0, "after": int(repair["placeholder_filtered_after"].sum()), "color": "#69B8A9"},
        ]
    )
    y = np.arange(len(repair_counts))[::-1]
    offset = 0.16
    bar_height = 0.24
    for y_pos, row in zip(y, repair_counts.itertuples()):
        ax_b.barh(
            y_pos + offset,
            row.before,
            height=bar_height,
            color="white",
            edgecolor=row.color,
            linewidth=1.6,
            hatch="///",
            zorder=3,
        )
        ax_b.barh(
            y_pos - offset,
            row.after,
            height=bar_height,
            color=row.color,
            edgecolor="white",
            linewidth=0.8,
            alpha=0.90,
            zorder=4,
        )
        if row.before > 0:
            ax_b.text(
                row.before + 0.12,
                y_pos + offset,
                str(row.before),
                ha="left",
                va="center",
                fontsize=9.0,
                color=row.color,
                fontweight="semibold",
            )
        if row.after > 0:
            ax_b.text(
                row.after + 0.12,
                y_pos - offset,
                str(row.after),
                ha="left",
                va="center",
                fontsize=9.0,
                color=row.color,
                fontweight="semibold",
            )
    ax_b.set_yticks(y, repair_counts["metric"])
    ax_b.tick_params(axis="y", pad=6)
    ax_b.set_xlim(0, max(repair_counts["before"].max(), repair_counts["after"].max()) + 1.8)
    ax_b.set_xlabel("Audited cases")
    ax_b.grid(axis="x", zorder=0)
    label_panel(ax_b, "B")
    fig.subplots_adjust(top=0.92, wspace=0.35)
    export(fig, output_stem)
    plt.close(fig)


def plot_tradeoff_scatter(summary: pd.DataFrame, output_stem: Path) -> None:
    apply_theme()
    fig, ax = plt.subplots(figsize=(4.8, 3.6))
    model_markers = {
        "openai/gpt-5.4-mini": "o",
        "deepseek/deepseek-chat": "s",
        "z-ai/glm-5": "D",
    }
    label_offsets = {
        ("feedback_prize_ell", "openai/gpt-5.4-mini"): (9, 8),
        ("feedback_prize_ell", "deepseek/deepseek-chat"): (-86, -16),
        ("feedback_prize_ell", "z-ai/glm-5"): (12, -8),
        ("asap_aes_kaggle_parquet", "openai/gpt-5.4-mini"): (-18, 16),
        ("asap_aes_kaggle_parquet", "deepseek/deepseek-chat"): (10, -15),
        ("asap_aes_kaggle_parquet", "z-ai/glm-5"): (14, -12),
    }
    subset = summary[
        summary["condition"].isin(["llm_direct_feedback", "hybrid", "llm_direct_rewrite_supplement"])
        & summary["model_id"].isin(MODEL_ORDER)
    ].copy()
    for dataset_name in DATASET_LABELS:
        for model_id in MODEL_ORDER:
            direct = subset[
                (subset["dataset_name"] == dataset_name)
                & (subset["model_id"] == model_id)
                & (subset["condition"] == "llm_direct_feedback")
            ].iloc[0]
            hybrid = subset[
                (subset["dataset_name"] == dataset_name)
                & (subset["model_id"] == model_id)
                & (subset["condition"] == "hybrid")
            ].iloc[0]
            rewrite = subset[
                (subset["dataset_name"] == dataset_name)
                & (subset["model_id"] == model_id)
                & (subset["condition"] == "llm_direct_rewrite_supplement")
            ].iloc[0]
            marker = model_markers[model_id]
            ax.scatter(
                direct["student_text_preservation_rate"],
                direct["pedagogical_depth_score"],
                s=58,
                marker=marker,
                color=COLORS["direct"],
                edgecolors="white",
                linewidths=0.7,
                zorder=4,
            )
            ax.scatter(
                hybrid["student_text_preservation_rate"],
                hybrid["pedagogical_depth_score"],
                s=66,
                marker=marker,
                color=COLORS["hybrid"],
                edgecolors="white",
                linewidths=0.7,
                zorder=5,
            )
            ax.scatter(
                rewrite["student_text_preservation_rate"],
                rewrite["pedagogical_depth_score"],
                s=48,
                marker="x",
                color=COLORS["rewrite"],
                linewidths=1.5,
                zorder=3,
            )
            ax.annotate(
                "",
                xy=(hybrid["student_text_preservation_rate"], hybrid["pedagogical_depth_score"]),
                xytext=(direct["student_text_preservation_rate"], direct["pedagogical_depth_score"]),
                arrowprops={"arrowstyle": "->", "lw": 1.0, "color": "#7A8088"},
                zorder=2,
            )
            dx, dy = label_offsets[(dataset_name, model_id)]
            label = f"{DATASET_SHORT[dataset_name]} / {MODEL_SHORT[model_id]}"
            add_short_callout(
                ax,
                hybrid["student_text_preservation_rate"],
                hybrid["pedagogical_depth_score"],
                label,
                dx=dx,
                dy=dy,
                color=COLORS["ink"],
                fontsize=8.2,
                ha="left",
                va="center",
                with_arrow=False,
            )

    ax.set_xlabel("Student-text preservation")
    ax.set_ylabel("Pedagogical depth")
    ax.set_xlim(0.15, 1.02)
    ax.set_ylim(0.58, 0.85)
    ax.grid(True, zorder=0)
    legend_items = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#666666", markersize=6.5, label="GPT-5.4-mini"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#666666", markersize=6.5, label="DeepSeek v3.2"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor="#666666", markersize=6.5, label="GLM-5"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["direct"], markersize=6.5, label="Direct"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["hybrid"], markersize=6.5, label="Hybrid"),
        Line2D([0], [0], marker="x", color=COLORS["rewrite"], markersize=6.5, linestyle="none", label="Rewrite"),
    ]
    ax.legend(handles=legend_items, frameon=False, fontsize=8.6, ncol=2, loc="upper left")
    export(fig, output_stem)
    plt.close(fig)


def main() -> None:
    summary, metrics, refine, repair, _review = load_inputs()
    build_bootstrap_weight_summary(metrics)
    plot_pipeline_overview(FIG_DIR / "pipeline_overview")
    plot_main_depth(metrics, FIG_DIR / "result_main_depth")
    plot_followup_summary(refine, repair, FIG_DIR / "result_followup_summary")
    plot_tradeoff_scatter(summary, FIG_DIR / "result_tradeoff_scatter")


if __name__ == "__main__":
    main()
