param(
    [string]$PaperRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist\arxiv_bundle_preview"),
    [switch]$SkipCompile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\..\bench\scripts\common.ps1")

function Copy-RequiredFiles {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$DestinationRoot
    )

    $null = Ensure-Directory -Path $DestinationRoot
    $targets = @(
        @{ Source = "main.tex"; Destination = "main.tex" },
        @{ Source = "refs.bib"; Destination = "refs.bib" }
    )

    foreach ($target in $targets) {
        Copy-Item -LiteralPath (Join-Path $SourceRoot $target.Source) -Destination (Join-Path $DestinationRoot $target.Destination) -Force
    }

    foreach ($subdir in @("figures", "tables")) {
        $sourceDir = Join-Path $SourceRoot $subdir
        $destDir = Ensure-Directory -Path (Join-Path $DestinationRoot $subdir)
        Get-ChildItem -LiteralPath $sourceDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destDir $_.Name) -Force
        }
    }
}


$paperRootResolved = (Resolve-Path -LiteralPath $PaperRoot).Path
$outputRoot = Ensure-Directory -Path $OutputDir

Get-ChildItem -LiteralPath $outputRoot -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
$outputRoot = Ensure-Directory -Path $outputRoot

Copy-RequiredFiles -SourceRoot $paperRootResolved -DestinationRoot $outputRoot

$manifest = @(
    "FastXeBench arXiv bundle preview",
    "Generated at: $([DateTimeOffset]::Now.ToString('o'))",
    "Source root: $paperRootResolved",
    "Output root: $outputRoot",
    "",
    "Required follow-up before submission:",
    "- Review the generated PDF and compare it with the repository-local paper PDF.",
    "- Keep main.bbl in the upload bundle together with main.tex and refs.bib.",
    "- Check the arXiv processed PDF after upload."
)
Set-Content -LiteralPath (Join-Path $outputRoot "bundle_manifest.txt") -Value $manifest -Encoding utf8

if (-not $SkipCompile) {
    Push-Location $outputRoot
    try {
        & latexmk -xelatex -bibtex -interaction=nonstopmode -halt-on-error main.tex
    }
    finally {
        Pop-Location
    }
}

Write-Output $outputRoot
