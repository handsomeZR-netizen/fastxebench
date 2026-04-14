"""
Unified figure generation for the AIMER manuscript.
Merges tmp/tmpimg.py (Fig 2 & 3) and tmp/tmpimg_fig3.py (Fig 4).

Usage:
    python visualize_experiments.py          # regenerate all figures
    python plot_all_figures.py               # same, via the wrapper
"""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
import seaborn as sns
import os
from pathlib import Path
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D

# =====================================================================
# Colour palette (superset — covers all three figures)
# =====================================================================
PALETTE = {
    "AIMER":       "#a63d40",
    "Late fusion": "#7e6b8f",
    "PANNs":       "#8da0cb",
    "AST":         "#4e79a7",
    "TSM":         "#a07855",
    "MoViNet":     "#d4b483",
    "MNetV3":      "#d98324",
    "Neutral":     "#95a5a6",
    # aliases used by Fig 4 (robustness / ablation data keys)
    "Naive late fusion": "#7e6b8f",
    "PANNs / CNN14":     "#8da0cb",
}

# =====================================================================
# Data tables
# =====================================================================
MAIN_RESULTS = {
    "AIMER":       {"URMP": (0.84, 0.88), "Solos": (0.81, 0.85)},
    "Late fusion": {"URMP": (0.76, 0.79), "Solos": (0.74, 0.77)},
    "AST":         {"URMP": (0.75, 0.78), "Solos": (0.72, 0.75)},
    "PANNs":       {"URMP": (0.73, 0.76), "Solos": (0.70, 0.73)},
    "TSM":         {"URMP": (0.69, 0.72), "Solos": (0.66, 0.69)},
    "MoViNet":     {"URMP": (0.66, 0.70), "Solos": (0.63, 0.67)},
    "MNetV3":      {"URMP": (0.62, 0.66), "Solos": (0.58, 0.62)},
}

EFFICIENCY = {
    "AIMER":       {"latency": 12.5, "params": 45.2},
    "Late fusion": {"latency": 19.8, "params": 88.0},
    "AST":         {"latency": 22.0, "params": 85.5},
    "PANNs":       {"latency": 15.2, "params": 72.0},
    "TSM":         {"latency": 8.5,  "params": 24.3},
    "MoViNet":     {"latency": 10.2, "params": 15.8},
    "MNetV3":      {"latency": 6.8,  "params": 5.4},
}

ROBUSTNESS_RESULTS = {
    "PANNs / CNN14":     {"A/V offset": 0.01, "Audio corruption": 0.12, "Hand occlusion": None},
    "TSM":               {"A/V offset": None,  "Audio corruption": None,  "Hand occlusion": 0.10},
    "Naive late fusion": {"A/V offset": 0.07, "Audio corruption": 0.09, "Hand occlusion": 0.08},
    "AIMER":             {"A/V offset": 0.03, "Audio corruption": 0.06, "Hand occlusion": 0.05},
}

ABLATION_RESULTS = {
    "w/o audio branch":       {"avg_delta_f1": -0.09},
    "naive late fusion":      {"avg_delta_f1": -0.04},
    "RGB-only visual branch": {"avg_delta_f1": -0.03},
    "w/o phase supervision":  {"avg_delta_f1": -0.02},
    "AIMER":                  {"avg_delta_f1":  0.00},
}

ABLATION_SHORT = {
    "AIMER": "AIMER",
    "w/o phase supervision": "w/o phase",
    "RGB-only visual branch": "RGB-only",
    "naive late fusion": "Late fusion",
    "w/o audio branch": "w/o audio",
}

# =====================================================================
# Label positions (hand-tuned to avoid occlusion)
# =====================================================================
FIG1A_LABEL_POS = {
    "AIMER":       (0.84, 0.94, "center"),
    "Late fusion": (0.72, 0.70, "left"),
    "AST":         (0.75, 0.88, "right"),
    "PANNs":       (0.58, 0.82, "right"),
    "TSM":         (0.78, 0.62, "left"),
    "MoViNet":     (0.50, 0.75, "right"),
    "MNetV3":      (0.48, 0.60, "right"),
}

FIG2C_LABEL_POS = {
    "AIMER":       (12.5, 0.90, "center"),
    "Late fusion": (23.5, 0.78, "left"),
    "AST":         (25.0, 0.73, "left"),
    "PANNs":       (15.2, 0.68, "center"),
    "TSM":         (5.5,  0.73, "right"),
    "MoViNet":     (10.2, 0.60, "center"),
    "MNetV3":      (4.5,  0.64, "right"),
}

# =====================================================================
# Style helpers
# =====================================================================

def setup_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 14,
        "axes.titleweight": "bold",
        "axes.labelweight": "bold",
        "axes.titlesize": 16,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "xtick.color": "#000000",
        "ytick.color": "#000000",
        "axes.labelcolor": "#000000",
        "axes.edgecolor": "#000000",
        "text.color": "#000000",
    })


def _get_short_label(model):
    short_map = {
        "PANNs / CNN14": "PANNs",
        "Naive late fusion": "Late fusion",
    }
    return short_map.get(model, model)


def _add_panel_label(ax, label):
    ax.text(-0.08, 1.06, f"{label}.", transform=ax.transAxes,
            fontsize=17, fontweight="bold", va="bottom", ha="left", color="#000000")


def _apply_halo(text_obj, width=4):
    text_obj.set_path_effects([
        path_effects.withStroke(linewidth=width, foreground="white", alpha=0.9),
    ])


def _draw_connection(ax, start_xy, end_xy, color):
    ax.annotate("", xy=start_xy, xytext=end_xy,
                arrowprops=dict(arrowstyle="-", color=color, lw=0.7, alpha=0.3,
                                shrinkA=5, shrinkB=5))


def _save(fig, name):
    """Save to both project-level and paper-level figures directories."""
    script_dir = Path(__file__).resolve().parent          # submission_code_bundle/paper
    base_dir   = script_dir.parent.parent                 # arxiv6
    targets = [
        base_dir / "figures",
        base_dir / "paper" / "figures",
    ]
    for d in targets:
        d.mkdir(parents=True, exist_ok=True)
        for fmt in ("pdf", "png", "svg"):
            fig.savefig(d / f"{name}.{fmt}", dpi=300, bbox_inches="tight")
    print(f"Saved {name}")


# =====================================================================
# Figure 2 — Cross-dataset generalization
# =====================================================================

def plot_fig1_generalization():
    setup_style()
    fig = plt.figure(figsize=(12, 5.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.2, 1], wspace=0.35)

    # --- Panel A ---
    ax_a = fig.add_subplot(gs[0, 0])
    ax_a.set_title("A. Cross-dataset shift (URMP \u2192 Solos)", loc="left", pad=15)

    for model, data in MAIN_RESULTS.items():
        color = PALETTE[model]
        src, tgt = data["URMP"], data["Solos"]
        is_focus = model == "AIMER"

        arrow = FancyArrowPatch(src, tgt, arrowstyle="-|>", mutation_scale=12,
                                color=color, linewidth=2.5 if is_focus else 1.5,
                                alpha=0.8, zorder=2)
        ax_a.add_patch(arrow)
        ax_a.scatter(*src, marker="D", s=70, color=color, edgecolors="white", zorder=4)
        ax_a.scatter(*tgt, marker="o", s=80, facecolors="white", edgecolors=color,
                     linewidths=2, zorder=5)

        tx, ty, ha = FIG1A_LABEL_POS[model]
        _draw_connection(ax_a, src, (tx, ty), color)
        t = ax_a.text(tx, ty, model, color=color, ha=ha, va="center",
                      fontsize=14 if is_focus else 13,
                      fontweight="bold" if is_focus else "normal", zorder=10)
        _apply_halo(t)

    ax_a.set_xlim(0, 1.0)
    ax_a.set_ylim(0, 1.0)
    ax_a.set_xlabel("Macro-F1")
    ax_a.set_ylabel("Accuracy")
    ax_a.grid(True, linestyle=":", alpha=0.6)

    legend_elements = [
        Line2D([0], [0], marker="D", color="w", label="Source (URMP)",
               markerfacecolor="#555", markersize=7),
        Line2D([0], [0], marker="o", color="w", label="Target (Solos)",
               markeredgecolor="#555", markerfacecolor="w", markersize=7,
               markeredgewidth=1.5),
    ]
    ax_a.legend(handles=legend_elements, loc="upper left",
                bbox_to_anchor=(0.02, 0.98), fontsize=12, framealpha=0.8)

    # --- Panel B ---
    ax_b = fig.add_subplot(gs[0, 1])
    ax_b.set_title("B. Target Retention on Solos", loc="left", pad=15)

    models_sorted = sorted(
        MAIN_RESULTS.keys(),
        key=lambda x: MAIN_RESULTS[x]["Solos"][0] / MAIN_RESULTS[x]["URMP"][0],
        reverse=True,
    )
    y_pos = np.arange(len(models_sorted))

    for i, model in enumerate(models_sorted):
        color = PALETTE[model]
        f1_ret  = (MAIN_RESULTS[model]["Solos"][0] / MAIN_RESULTS[model]["URMP"][0]) * 100
        acc_ret = (MAIN_RESULTS[model]["Solos"][1] / MAIN_RESULTS[model]["URMP"][1]) * 100

        ax_b.hlines(i, 0, 100, color=color, alpha=0.1, linewidth=10, zorder=1)
        ax_b.scatter(f1_ret, i, marker="o", s=60, color=color, edgecolors="white", zorder=3)
        ax_b.scatter(acc_ret, i, marker="s", s=60, facecolors="white",
                     edgecolors=color, linewidths=1.5, zorder=3)

        avg_ret = (f1_ret + acc_ret) / 2
        label_text = ax_b.text(94.0, i, f"{avg_ret:.1f}%", va="center", ha="right",
                               fontsize=12, fontweight="bold", color=color)
        _apply_halo(label_text, width=2)

    ax_b.set_yticks(y_pos)
    ax_b.set_yticklabels(models_sorted)
    ax_b.set_xlim(0, 115)
    ax_b.set_xlabel("Retention (%)")
    ax_b.invert_yaxis()
    ax_b.grid(True, axis="x", linestyle=":", alpha=0.6)

    legend_elements_b = [
        Line2D([0], [0], marker="o", color="w", label="F1 Retention",
               markerfacecolor="#7f8c8d", markersize=8),
        Line2D([0], [0], marker="s", color="w", label="Acc Retention",
               markerfacecolor="none", markeredgecolor="#7f8c8d",
               markeredgewidth=1.5, markersize=8),
    ]
    ax_b.legend(handles=legend_elements_b, loc="lower left",
                bbox_to_anchor=(0.02, 0.02), fontsize=12, framealpha=0.8)

    plt.tight_layout()
    _save(fig, "02_generalization_shift")
    plt.close(fig)


# =====================================================================
# Figure 3 — Efficiency
# =====================================================================

def plot_fig2_efficiency():
    setup_style()
    fig = plt.figure(figsize=(12, 5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.2, 1], wspace=0.3)

    # --- Panel A ---
    ax_c = fig.add_subplot(gs[0, 0])
    ax_c.set_title("A. Latency-Performance Trade-off", loc="left", pad=15)

    points = []
    for model, info in EFFICIENCY.items():
        lat   = info["latency"]
        f1    = MAIN_RESULTS[model]["URMP"][0]
        params = info["params"]
        color = PALETTE[model]
        points.append((lat, f1, model))

        ax_c.scatter(lat, f1, s=params * 2.5 + 40, color=color,
                     edgecolors="white", alpha=0.8, zorder=4)

        tx, ty, ha = FIG2C_LABEL_POS[model]
        _draw_connection(ax_c, (lat, f1), (tx, ty), color)
        t = ax_c.text(tx, ty, model, color=color, ha=ha, va="center",
                      fontsize=11, fontweight="bold" if model == "AIMER" else "normal",
                      zorder=10)
        _apply_halo(t)

    # Pareto frontier
    sorted_pts = sorted(points, key=lambda x: x[0])
    frontier = [sorted_pts[0]]
    for p in sorted_pts[1:]:
        if p[1] > frontier[-1][1]:
            frontier.append(p)
    fx, fy = zip(*[(p[0], p[1]) for p in frontier])
    ax_c.plot(fx, fy, "--", color="#7f8c8d", lw=1.2, alpha=0.5, zorder=1)

    ax_c.set_xlim(0, 30)
    ax_c.set_ylim(0, 1.0)
    ax_c.set_xlabel("Latency (ms/clip)")
    ax_c.set_ylabel("Macro-F1 (URMP)")
    ax_c.grid(True, linestyle=":", alpha=0.6)

    # --- Panel B ---
    ax_d = fig.add_subplot(gs[0, 1])
    ax_d.set_title("B. Parameter Budget", loc="left", pad=15)

    models_p = sorted(EFFICIENCY.keys(),
                      key=lambda x: EFFICIENCY[x]["params"], reverse=True)
    y_p  = np.arange(len(models_p))
    vals = [EFFICIENCY[m]["params"] for m in models_p]

    ax_d.barh(y_p, vals, color=[PALETTE[m] for m in models_p],
              height=0.6, alpha=0.85, edgecolor="none")
    for i, v in enumerate(vals):
        ax_d.text(v + 2, i, f"{v:.1f}M", va="center", fontweight="bold",
                  color=PALETTE[models_p[i]], fontsize=13)

    ax_d.set_yticks(y_p)
    ax_d.set_yticklabels(models_p)
    ax_d.set_xlim(0, 120)
    ax_d.set_xlabel("Parameters (Millions)")
    ax_d.invert_yaxis()
    ax_d.grid(True, axis="x", linestyle=":", alpha=0.5)

    plt.tight_layout()
    _save(fig, "03_efficiency_tradeoff")
    plt.close(fig)


# =====================================================================
# Figure 4 — Composite diagnostics (heatmap + ablation + radar)
# =====================================================================

def plot_fig3_diagnostics():
    setup_style()
    fig = plt.figure(figsize=(10, 7.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.1, 1.0], hspace=1.0, wspace=0.55)

    # --- Panel A: robustness heatmap ---
    ax_heat = fig.add_subplot(gs[0, 0])
    models = list(ROBUSTNESS_RESULTS.keys())
    disturbances = ["A/V offset", "Audio corruption", "Hand occlusion"]
    dist_labels  = ["A/V lag", "Audio noise", "Hand occ."]

    rows = []
    for m in models:
        row = []
        for d in disturbances:
            val = ROBUSTNESS_RESULTS[m].get(d)
            row.append(val if val is not None else 0.0)
        rows.append(row)
    data = np.array(rows)
    mask = data == 0

    sns.heatmap(data, annot=True, fmt=".2f",
                annot_kws={"size": 13, "weight": "bold"},
                cmap="Reds", ax=ax_heat, cbar=False,
                xticklabels=dist_labels,
                yticklabels=[_get_short_label(m) for m in models],
                mask=mask)

    for r in range(data.shape[0]):
        for c in range(data.shape[1]):
            if mask[r, c]:
                ax_heat.text(c + 0.5, r + 0.5, "N/A", ha="center", va="center",
                             color="#000000", fontsize=12, fontweight="bold")
    for text in ax_heat.texts:
        try:
            val = float(text.get_text())
            text.set_color("white" if val > 0.08 else "#000000")
            text.set_weight("bold")
        except ValueError:
            pass

    ax_heat.set_xticklabels(dist_labels, rotation=30, ha="right")
    ax_heat.set_title("Robustness drop", pad=14, fontsize=16)
    _add_panel_label(ax_heat, "A")

    # --- Panel B: ablation bar chart ---
    ax_abl = fig.add_subplot(gs[1, 0])
    ablation_models = list(ABLATION_RESULTS.keys())
    deltas = [ABLATION_RESULTS[m]["avg_delta_f1"] for m in ablation_models]
    bar_colors = [PALETTE["Neutral"]] * len(ablation_models)
    bar_colors[ablation_models.index("AIMER")] = PALETTE["AIMER"]
    ax_abl.barh(np.arange(len(ablation_models)), deltas, color=bar_colors, height=0.6)
    ax_abl.axvline(0, color="#66615B", linestyle="--", alpha=0.5, zorder=1)
    ax_abl.set_yticks(np.arange(len(ablation_models)))
    ax_abl.set_yticklabels([ABLATION_SHORT.get(m, m) for m in ablation_models])
    ax_abl.set_xlabel(r"Average $\Delta$ Macro-F1", fontsize=14)
    ax_abl.set_title("Ablation impact", pad=14, fontsize=16)
    _add_panel_label(ax_abl, "B")
    ax_abl.set_xlim(-0.11, 0.03)
    ax_abl.grid(True, axis="x")
    ax_abl.grid(False, axis="y")

    # --- Panel C: radar chart ---
    ax_radar = fig.add_subplot(gs[:, 1], polar=True)
    metrics = ["Accuracy", "F1", "Latency*", "Memory*", "Robustness"]
    angles  = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    angles += angles[:1]

    aimer_vals  = [0.87, 0.84, 0.78, 0.86, 0.92]
    fusion_vals = [0.84, 0.81, 0.62, 0.71, 0.80]
    for values, label, color in [
        (aimer_vals,  "AIMER",       PALETTE["AIMER"]),
        (fusion_vals, "Late fusion", PALETTE["Late fusion"]),
    ]:
        vals = values + values[:1]
        ax_radar.plot(angles, vals, color=color, linewidth=2.2, label=label)
        ax_radar.fill(angles, vals, color=color, alpha=0.12)

    ax_radar.set_theta_offset(np.pi / 2)
    ax_radar.set_theta_direction(-1)
    ax_radar.set_xticks(angles[:-1])
    radar_ticklabels = ["Accuracy", "F1", "Latency", "Memory", "Robustness"]
    ax_radar.set_xticklabels(radar_ticklabels, fontsize=13, fontweight="bold",
                             color="#000000")
    ax_radar.tick_params(pad=35, colors="#000000")
    ax_radar.set_ylim(0, 1.10)
    ax_radar.set_yticks([0.25, 0.50, 0.75])
    ax_radar.set_yticklabels(["0.25", "0.50", "0.75"], fontsize=9, color="#000000")
    ax_radar.set_rlabel_position(205)
    ax_radar.set_title("Unified profile", pad=40, fontsize=16, color="#000000")
    ax_radar.legend(loc="upper right", bbox_to_anchor=(1.50, 1.18), fontsize=11)
    _add_panel_label(ax_radar, "C")

    plt.tight_layout()
    _save(fig, "04_composite_diagnostics")
    plt.close(fig)


# =====================================================================
if __name__ == "__main__":
    plot_fig1_generalization()
    plot_fig2_efficiency()
    plot_fig3_diagnostics()
    print("All figures generated.")
