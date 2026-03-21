# FastXeBench

[![Repository](https://img.shields.io/badge/GitHub-handsomeZR--netizen%2Ffastxebench-181717?logo=github&style=for-the-badge)](https://github.com/handsomeZR-netizen/fastxebench)
[![Paper PDF](https://img.shields.io/badge/Paper-PDF-B31B1B?style=for-the-badge)](paper/main.pdf)
[![Protocol](https://img.shields.io/badge/Protocol-v0.2--prime--measure-0F766E?style=for-the-badge)](#reproducing-the-paper-assets)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011-0078D4?style=for-the-badge)](#reproducing-the-paper-assets)

FastXeBench is a benchmark artifact and companion paper about **edit-to-PDF latency** in **Windows-local XeLaTeX workflows**. The project is built around a simple observation: a lot of TeX performance advice is based on clean builds, personal impressions, or tool-specific folklore, while the thing authors actually wait on is the repeated edit-build-inspect loop.

This repository turns that loop into something measurable. It contains the benchmark workloads, orchestration scripts, compact recorded summaries, and the paper assets used to study which XeLaTeX acceleration paths are actually helpful, and which ones stop being acceptable once PDF fidelity is treated as a hard constraint. If you only want the paper, start with [`paper/main.pdf`](paper/main.pdf). If you want to inspect or regenerate the figures and tables, the entry points are under [`paper/scripts/`](paper/scripts/) and [`results/datasets/`](results/datasets/).

![Formal speedup heatmap](paper/figures/formal_speedup_heatmap.png)

## What is in this repository

- A Windows-local XeLaTeX benchmark harness with workload, scenario, and configuration boundaries made explicit.
- A `v0.2-prime-measure` protocol that measures incremental scenarios as post-edit rebuilds rather than as fresh-build proxies.
- A fidelity pipeline that combines PDF SHA-256 hashes with per-page raster comparison.
- A formal core dataset built from `W1/W2/W4/W5 × S0..S4 × B0/B1/B4`, plus external validation workloads and a scoped Windows storage follow-up.
- Paper source, generated tables and figures, and an isolated arXiv-style bundle dry run.

## What the current results suggest

- `latexmk` is a good default for steady incremental editing, but it is not uniformly faster on clean builds or bibliography edits.
- `minted` cache is the strongest safe optimization in the current code-heavy path.
- The retained main matrix keeps `visual_equal_rate = 1.0`, so fidelity is treated as a gate rather than as an afterthought.
- `B3_latexmk_tikz_externalize` and `B6_tectonic` are still useful comparison points, but they are not presented as default recommendations because fidelity triage reproduced persistent visual differences.
- The real-project-derived follow-up workloads reproduce the main `latexmk` pattern, while the `B7` storage study is intentionally scoped to the current machine and Windows state.

## Reproducing the paper assets

The formal paper assets are generated from the compact summaries under [`results/datasets/protocol_v0_2_core_formal_20x3/`](results/datasets/protocol_v0_2_core_formal_20x3/). The environment snapshot used for that dataset is recorded in:

- [`results/datasets/protocol_v0_2_core_formal_20x3/artifact/env.json`](results/datasets/protocol_v0_2_core_formal_20x3/artifact/env.json)
- [`results/datasets/protocol_v0_2_core_formal_20x3/artifact/versions.txt`](results/datasets/protocol_v0_2_core_formal_20x3/artifact/versions.txt)

Run one benchmark case:

```powershell
.\bench\scripts\build.ps1 -Config B1_latexmk -Workload W1_text_math -Scenario S2_bib_edit
```

Regenerate the paper figures, tables, and statistical summaries:

```powershell
. .\bench\scripts\common.ps1
& (Get-PreferredPythonPath) .\paper\scripts\generate_formal_assets.py
```

Build the isolated arXiv-style source bundle locally:

```powershell
.\paper\scripts\build_arxiv_bundle.ps1
```

The full benchmark loop is still available through [`bench/scripts/benchmark.ps1`](bench/scripts/benchmark.ps1), but the public repository intentionally keeps compact summaries and sanitized metadata rather than bulky raw run directories.

## Repository layout

- [`bench/workloads/`](bench/workloads/): synthetic workloads and real-project-derived validation cases
- [`bench/configs/`](bench/configs/): build-strategy metadata
- [`bench/scripts/`](bench/scripts/): PowerShell orchestration and Python helpers
- [`paper/`](paper/): manuscript source, generated figures and tables, and submission tooling
- [`artifact/`](artifact/): reproducibility and release notes
- [`results/datasets/`](results/datasets/): compact summaries, analysis CSVs, and sanitized environment snapshots

## Paper and submission notes

- Paper source: [`paper/main.tex`](paper/main.tex)
- Current PDF: [`paper/main.pdf`](paper/main.pdf)
- arXiv checklist: [`paper/ARXIV_CHECKLIST.md`](paper/ARXIV_CHECKLIST.md)
- Local bundle dry run: [`paper/scripts/build_arxiv_bundle.ps1`](paper/scripts/build_arxiv_bundle.ps1)

The public tree does not include scratch runs, smoke datasets, or machine-specific progress logs. It keeps the parts that are needed to understand the benchmark, inspect the results, and rebuild the paper-facing assets without turning the repository itself into a raw data dump.
