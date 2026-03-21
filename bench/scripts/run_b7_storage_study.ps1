param(
    [string[]]$Workloads = @("W1_text_math", "W4_tikz", "W5_minted"),
    [string[]]$Scenarios = @("S0_clean_build", "S1_text_edit", "S3_figure_edit"),
    [int]$Runs = 5,
    [int]$WarmupRuns = 1,
    [string]$DatasetName = "b7_storage_study_r2_20260321"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

$repoRoot = Get-RepoRoot
$studyRoot = Ensure-Directory -Path (Join-Path $repoRoot (Join-Path "results\datasets" $DatasetName))
$benchmarkScript = Join-Path $PSScriptRoot "benchmark.ps1"
$summarizeScript = Join-Path $PSScriptRoot "summarize_b7_storage.py"
$pythonPath = Get-PreferredPythonPath

$modes = @(
    [pscustomobject]@{
        label = "d_repo_ntfs"
        output_root = (Join-Path $studyRoot "modes\d_repo_ntfs")
    },
    [pscustomobject]@{
        label = "c_profile_ntfs"
        output_root = (Join-Path $env:LOCALAPPDATA (Join-Path "FastXeBench\$DatasetName" "c_profile_ntfs"))
    }
)

foreach ($mode in $modes) {
    Write-Host ("Running B7 mode {0} at {1}" -f $mode.label, $mode.output_root)
    & $benchmarkScript `
        -Configs B7_windows_storage_mode `
        -Workloads $Workloads `
        -Scenarios $Scenarios `
        -Runs $Runs `
        -WarmupRuns $WarmupRuns `
        -OutputRoot $mode.output_root `
        -StorageMode $mode.label
}

$modeArgs = @()
foreach ($mode in $modes) {
    $modeArgs += "--mode"
    $modeArgs += ("{0}={1}" -f $mode.label, $mode.output_root)
}

& $pythonPath $summarizeScript --study-root $studyRoot @modeArgs
