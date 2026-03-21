param(
    [ValidateSet("B3_latexmk_tikz_externalize", "B6_tectonic")]
    [string]$Config,
    [ValidateSet("W1_text_math", "W2_cjk_font", "W4_tikz")]
    [string]$Workload,
    [ValidateSet("S0_clean_build", "S1_text_edit", "S2_bib_edit", "S3_figure_edit", "S4_preamble_edit")]
    [string]$Scenario,
    [string]$OutputRoot,
    [switch]$RefreshReference
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

function Get-ClassificationDecision {
    param([Parameter(Mandatory = $true)]$Result)

    if (-not $Result.success) {
        return [pscustomobject]@{
            classification = "unknown"
            reason = "build_not_successful"
        }
    }

    if ($Result.fidelity_status -ne "ok") {
        return [pscustomobject]@{
            classification = "unknown"
            reason = "fidelity_status_not_ok"
        }
    }

    if ($Result.fidelity_visual_equal -eq $true) {
        return [pscustomobject]@{
            classification = "main_matrix_safe"
            reason = "visual_equal"
        }
    }

    switch ($Result.config) {
        "B6_tectonic" {
            return [pscustomobject]@{
                classification = "dev_only"
                reason = "visual_diff_under_tectonic"
            }
        }
        "B3_latexmk_tikz_externalize" {
            return [pscustomobject]@{
                classification = "appendix_negative"
                reason = "visual_diff_under_externalization"
            }
        }
        default {
            return [pscustomobject]@{
                classification = "unknown"
                reason = "unhandled_config"
            }
        }
    }
}

function Write-TriageIndex {
    param([Parameter(Mandatory = $true)][string]$OutputRoot)

    $artifactRoot = Ensure-Directory -Path (Join-Path $OutputRoot "artifact")
    $summaryJsonOut = Join-Path $artifactRoot "triage-summary.json"
    $summaryCsvOut = Join-Path $artifactRoot "triage-summary.csv"
    $rows = @()

    Get-ChildItem -LiteralPath (Join-Path $OutputRoot "raw") -Recurse -Filter "summary.json" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\triage\\" } |
        ForEach-Object {
            $payload = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            $rows += [pscustomobject]@{
                config = $payload.case.config
                workload = $payload.case.workload
                scenario = $payload.case.scenario
                success = $payload.result.success
                status = $payload.result.status
                fidelity_status = $payload.result.fidelity_status
                fidelity_visual_equal = $payload.result.fidelity_visual_equal
                fidelity_binary_equal = $payload.result.fidelity_binary_equal
                changed_pages_count = $payload.result.changed_pages_count
                visual_diff_pages = (($payload.result.visual_diff_pages | ForEach-Object { $_.ToString() }) -join ";")
                classification = $payload.classification.classification
                reason = $payload.classification.reason
                run_directory = $payload.paths.run_directory
                summary_json = $_.FullName
            }
        }

    $rows = @($rows | Sort-Object workload, scenario, config)
    Write-JsonFile -Path $summaryJsonOut -Value $rows
    $rows | Export-Csv -LiteralPath $summaryCsvOut -NoTypeInformation -Encoding utf8
}

$outputRoot = Get-ResultsRoot -OutputRoot $OutputRoot
$buildScript = Join-Path $PSScriptRoot "build.ps1"
$result = & $buildScript -Config $Config -Workload $Workload -Scenario $Scenario -OutputRoot $outputRoot -RefreshReference:$RefreshReference
$runDirectory = Get-RunDirectory -OutputRoot $outputRoot -Bucket "raw" -Workload $Workload -Scenario $Scenario -Config $Config -RunId $result.run_id
$referenceDirectory = Get-ReferenceDirectory -OutputRoot $outputRoot -Workload $Workload -Scenario $Scenario
$triageDirectory = Ensure-Directory -Path (Join-Path $runDirectory "triage")

$referencePdfCopy = $null
$candidatePdfCopy = $null
$referenceResultCopy = $null

if ($result.reference_pdf -and (Test-Path -LiteralPath $result.reference_pdf)) {
    $referencePdfCopy = Join-Path $triageDirectory "reference.pdf"
    Copy-Item -LiteralPath $result.reference_pdf -Destination $referencePdfCopy -Force
}

if ($result.pdf_path -and (Test-Path -LiteralPath $result.pdf_path)) {
    $candidatePdfCopy = Join-Path $triageDirectory "candidate.pdf"
    Copy-Item -LiteralPath $result.pdf_path -Destination $candidatePdfCopy -Force
}

$referenceResultPath = Join-Path $referenceDirectory "result.json"
if (Test-Path -LiteralPath $referenceResultPath) {
    $referenceResultCopy = Join-Path $triageDirectory "reference.result.json"
    Copy-Item -LiteralPath $referenceResultPath -Destination $referenceResultCopy -Force
}

$classification = Get-ClassificationDecision -Result $result
$summary = [pscustomobject]@{
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    case = [pscustomobject]@{
        config = $Config
        workload = $Workload
        scenario = $Scenario
    }
    classification = $classification
    result = [pscustomobject]@{
        run_id = $result.run_id
        success = $result.success
        status = $result.status
        fidelity_status = $result.fidelity_status
        fidelity_visual_equal = $result.fidelity_visual_equal
        fidelity_binary_equal = $result.fidelity_binary_equal
        visual_diff_pages = @($result.visual_diff_pages)
        changed_pages_count = $result.changed_pages_count
        reference_page_count = $result.reference_page_count
        candidate_page_count = $result.candidate_page_count
        measure_elapsed_ms = $result.measure_elapsed_ms
        prime_elapsed_ms = $result.prime_elapsed_ms
    }
    paths = [pscustomobject]@{
        output_root = $outputRoot
        run_directory = $runDirectory
        reference_directory = $referenceDirectory
        result_json = (Join-Path $runDirectory "result.json")
        fidelity_json = $result.fidelity_json
        reference_pdf = $result.reference_pdf
        candidate_pdf = $result.pdf_path
        triage_reference_pdf = $referencePdfCopy
        triage_candidate_pdf = $candidatePdfCopy
        triage_reference_result = $referenceResultCopy
    }
    fidelity_artifacts = $result.fidelity_artifacts
    stdout_logs = @($result.stdout_logs)
    stderr_logs = @($result.stderr_logs)
}

$summaryPath = Join-Path $triageDirectory "summary.json"
Write-JsonFile -Path $summaryPath -Value $summary
Write-TriageIndex -OutputRoot $outputRoot

$summary | ConvertTo-Json -Depth 12
