param(
    [string]$TargetPath = (Get-Location).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$patterns = @(
    "*.aux",
    "*.bbl",
    "*.bcf",
    "*.blg",
    "*.fdb_latexmk",
    "*.fls",
    "*.fmt",
    "*.lof",
    "*.log",
    "*.lot",
    "*.nav",
    "*.out",
    "*.pdf",
    "*.run.xml",
    "*.snm",
    "*.synctex.gz",
    "*.toc",
    "*.xdv"
)

foreach ($pattern in $patterns) {
    Get-ChildItem -LiteralPath $TargetPath -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

$directories = @(
    "_minted",
    "_minted-main",
    ".tectonic",
    "tikz-cache"
)

foreach ($name in $directories) {
    Get-ChildItem -LiteralPath $TargetPath -Recurse -Directory -Filter $name -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
