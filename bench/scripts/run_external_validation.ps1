param(
    [string[]]$Workloads = @("R1_fontspec_example", "R2_pgfplots_example"),
    [string[]]$Scenarios = @("S0_clean_build", "S1_text_edit", "S2_bib_edit", "S3_figure_edit", "S4_preamble_edit"),
    [string[]]$Configs = @("B0_baseline_xelatex", "B1_latexmk"),
    [int]$Runs = 3,
    [int]$WarmupRuns = 1,
    [string]$DatasetName = "external_validation_r1_20260321"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

$repoRoot = Get-RepoRoot
$datasetRoot = Ensure-Directory -Path (Join-Path $repoRoot (Join-Path "results\datasets" $DatasetName))
$benchmarkScript = Join-Path $PSScriptRoot "benchmark.ps1"
$summarizeScript = Join-Path $PSScriptRoot "summarize_external_validation.py"
$pythonPath = Get-PreferredPythonPath

& $benchmarkScript `
    -Configs $Configs `
    -Workloads $Workloads `
    -Scenarios $Scenarios `
    -Runs $Runs `
    -WarmupRuns $WarmupRuns `
    -OutputRoot $datasetRoot

& $pythonPath $summarizeScript --dataset-root $datasetRoot
