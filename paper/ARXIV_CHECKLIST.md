# arXiv Submission Checklist

## Metadata

- Confirm the public artifact URL is correct in the paper and README:
  - `https://github.com/handsomeZR-netizen/fastxebench`
- Confirm the author block matches the submission metadata:
  - `Zirui Xu`
  - `Nanjing Normal University`
  - `19230444@njnu.edu.cn`
- Suggested arXiv categories for this manuscript:
  - primary: `cs.PF`
  - cross-list: `cs.SE`
- Submit the paper as an English-first manuscript. If a multilingual version is added later, keep the English version first.

## Source Bundle

- Run the local dry-run bundle script:

```powershell
.\paper\scripts\build_arxiv_bundle.ps1
```

- Verify the generated bundle directory contains:
  - `main.tex`
  - `main.bbl`
  - `refs.bib`
  - `figures/*.pdf`
  - `tables/*.tex`
- Confirm the isolated bundle compiles with `latexmk -xelatex`.
- Check that no figure, table, or bibliography dependency points outside the bundle directory.

## XeLaTeX / arXiv Constraints

- Keep the manuscript on `xelatex`.
- Do not add `cleveref` on the TeX Live 2025 path.
- If non-default fonts are added later, prefer filename-based loading rather than system font-name lookup.
- The current paper does not use `minted`; if that changes, generate `_minted` locally with the same TeX Live version and include the cache in the bundle.

## Final Validation

- Review the locally compiled bundle PDF.
- After upload, inspect the arXiv processed PDF rather than assuming the local PDF is authoritative.
- Confirm that the artifact statement still points to the public repository before final submission.
