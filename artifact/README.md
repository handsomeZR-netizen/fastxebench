# Artifact Notes

This directory stores reproducibility metadata for the current FastXeBench protocol.

- `env.json`: machine-readable environment snapshot, including OS, power plan, storage metadata, and tool availability.
- `versions.txt`: human-readable version snapshot.

The public repository keeps sanitized snapshots. Local absolute paths and user-specific PATH contents are removed from the public-facing copies before release.

Generate them with:

```powershell
.\bench\scripts\collect_env.ps1
```

Sanitize the public release copies with:

```powershell
. .\bench\scripts\common.ps1
& (Get-PreferredPythonPath) .\bench\scripts\sanitize_public_artifacts.py
```

## arXiv-first submission checklist

- Processor: keep the manuscript on `xelatex`.
- Preamble: keep the current conservative paper preamble; do not add `cleveref` on the TL2025 path.
- Fonts: if non-default fonts are added later, prefer filename-based `fontspec` loading.
- `minted`: the current paper does not use it; if it is introduced later, generate `_minted` locally with the same TeX Live version and include the cache in the submission bundle.
- Bundle contents: include `paper/main.tex`, `paper/refs.bib`, `paper/figures/`, and `paper/tables/`.
- Public artifact link: `https://github.com/handsomeZR-netizen/fastxebench`
- Multilingual submissions: if a Chinese+English version is prepared later, put the English version first.

Run the local isolated bundle dry-run with:

```powershell
.\paper\scripts\build_arxiv_bundle.ps1
```

The paper-specific checklist is also tracked in `paper/ARXIV_CHECKLIST.md`.
