param(
    [string[]]$Configs = @("B0_baseline_xelatex", "B1_latexmk", "B4_minted_cache"),
    [string[]]$Workloads = @("W1_text_math", "W2_cjk_font", "W4_tikz", "W5_minted"),
    [string[]]$Scenarios = @("S0_clean_build", "S1_text_edit", "S2_bib_edit", "S3_figure_edit", "S4_preamble_edit"),
    [int]$Runs = 20,
    [int]$WarmupRuns = 3,
    [string]$OutputRoot,
    [string]$StorageMode,
    [switch]$UseHyperfine
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

function Normalize-List {
    param([string[]]$Values)
    if ($null -eq $Values) { return @() }
    $normalized = @()
    foreach ($value in $Values) {
        if ($null -eq $value) { continue }
        foreach ($part in ($value -split ",")) {
            $trimmed = $part.Trim()
            if ($trimmed) { $normalized += $trimmed }
        }
    }
    return @($normalized)
}

function Get-ExecutionPlan {
    param([string[]]$Configs, [string[]]$Workloads, [string[]]$Scenarios)
    $plan = @()
    foreach ($config in $Configs) {
        $definition = Get-ConfigDefinition -Config $config
        foreach ($workload in $Workloads) {
            if ($definition.PSObject.Properties.Name -contains "applicable_workloads" -and $definition.applicable_workloads -notcontains $workload) { continue }
            foreach ($scenario in $Scenarios) {
                $plan += [pscustomobject]@{ config = $config; workload = $workload; scenario = $scenario }
            }
        }
    }
    return @($plan)
}

function Shuffle-Items {
    param([object[]]$Items)
    if (-not $Items -or $Items.Count -le 1) { return @($Items) }
    return @(Get-Random -InputObject $Items -Count $Items.Count)
}

function New-ProgressTracker {
    param(
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][int]$PlanCount,
        [Parameter(Mandatory = $true)][int]$WarmupRuns,
        [Parameter(Mandatory = $true)][int]$Runs
    )

    $artifactRoot = Ensure-Directory -Path (Join-Path $OutputRoot "artifact")
    $progressPath = Join-Path $artifactRoot "benchmark-progress.json"
    $logPath = Join-Path $artifactRoot "benchmark-progress.log"
    $startedAt = (Get-Date).ToString("o")
    $state = [ordered]@{
        status = "running"
        output_root = $OutputRoot
        started_at = $startedAt
        updated_at = $startedAt
        plan_count = $PlanCount
        warmup_runs_per_item = $WarmupRuns
        recorded_runs_per_item = $Runs
        totals = [ordered]@{
            warmup_ops = $PlanCount * $WarmupRuns
            recorded_ops = $PlanCount * $Runs
            total_ops = $PlanCount * ($WarmupRuns + $Runs)
        }
        completed = [ordered]@{
            warmup_ops = 0
            recorded_ops = 0
            total_ops = 0
            items_with_first_recorded_run = 0
        }
        remaining_ops = $PlanCount * ($WarmupRuns + $Runs)
        percent_complete = 0.0
        current = $null
        last_completed = $null
        postprocess_status = "not_started"
        postprocess_started_at = $null
        postprocess_completed_at = $null
        postprocess_error = $null
    }

    Write-JsonFile -Path $progressPath -Value $state
    Set-Content -LiteralPath $logPath -Value "$startedAt`tSTART benchmark run" -Encoding utf8

    return [pscustomobject]@{
        path = $progressPath
        log_path = $logPath
        state = $state
    }
}

function Save-ProgressTracker {
    param([Parameter(Mandatory = $true)]$Tracker)

    $Tracker.state.updated_at = (Get-Date).ToString("o")
    $totalOps = [double]$Tracker.state.totals.total_ops
    $completedOps = [double]$Tracker.state.completed.total_ops
    $Tracker.state.remaining_ops = [Math]::Max(0, [int]($Tracker.state.totals.total_ops - $Tracker.state.completed.total_ops))
    $Tracker.state.percent_complete = if ($totalOps -le 0) { 100.0 } else { [math]::Round((100.0 * $completedOps) / $totalOps, 2) }
    Write-JsonFile -Path $Tracker.path -Value $Tracker.state
}

function Add-ProgressLog {
    param(
        [Parameter(Mandatory = $true)]$Tracker,
        [Parameter(Mandatory = $true)][string]$Message
    )

    $timestamp = (Get-Date).ToString("o")
    Add-Content -LiteralPath $Tracker.log_path -Value "$timestamp`t$Message" -Encoding utf8
}

function Get-ResultElapsedMs {
    param($Result)

    if ($null -eq $Result) { return 0.0 }
    if ($Result.PSObject.Properties["measure_elapsed_ms"] -and $null -ne $Result.measure_elapsed_ms) {
        return [double]$Result.measure_elapsed_ms
    }
    if ($Result.PSObject.Properties["elapsed_ms"] -and $null -ne $Result.elapsed_ms) {
        return [double]$Result.elapsed_ms
    }
    return 0.0
}

function Get-ResultStatus {
    param($Result)

    if ($null -eq $Result) { return "unknown" }
    if ($Result.PSObject.Properties["status"] -and $Result.status) {
        return [string]$Result.status
    }
    return "unknown"
}

function Invoke-PlanStep {
    param(
        [Parameter(Mandatory = $true)]$Item,
        [Parameter(Mandatory = $true)][string]$Phase,
        [Parameter(Mandatory = $true)][int]$PhaseIndex,
        [Parameter(Mandatory = $true)][int]$PhaseCount,
        [Parameter(Mandatory = $true)]$Tracker,
        [Parameter(Mandatory = $true)][string]$BuildScript,
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [string]$StorageMode,
        [switch]$NoRecord
    )

    $phaseLabel = if ($NoRecord) { "Warmup $PhaseIndex/$PhaseCount" } else { "Run $PhaseIndex/$PhaseCount" }
    $message = "$phaseLabel :: $($Item.workload) :: $($Item.scenario) :: $($Item.config)"
    $Tracker.state.current = [ordered]@{
        phase = $Phase
        phase_index = $PhaseIndex
        phase_count = $PhaseCount
        workload = $Item.workload
        scenario = $Item.scenario
        config = $Item.config
        global_step = $Tracker.state.completed.total_ops + 1
        total_ops = $Tracker.state.totals.total_ops
        label = $message
    }
    Save-ProgressTracker -Tracker $Tracker
    Add-ProgressLog -Tracker $Tracker -Message "START`t$message"
    Write-Host $message

    try {
        if ($NoRecord) {
            if ($StorageMode) {
                $result = & $BuildScript -Config $Item.config -Workload $Item.workload -Scenario $Item.scenario -OutputRoot $OutputRoot -StorageMode $StorageMode -NoRecord
            }
            else {
                $result = & $BuildScript -Config $Item.config -Workload $Item.workload -Scenario $Item.scenario -OutputRoot $OutputRoot -NoRecord
            }
        }
        else {
            if ($StorageMode) {
                $result = & $BuildScript -Config $Item.config -Workload $Item.workload -Scenario $Item.scenario -OutputRoot $OutputRoot -StorageMode $StorageMode
            }
            else {
                $result = & $BuildScript -Config $Item.config -Workload $Item.workload -Scenario $Item.scenario -OutputRoot $OutputRoot
            }
        }

        if ($NoRecord) {
            $Tracker.state.completed.warmup_ops += 1
        }
        else {
            $Tracker.state.completed.recorded_ops += 1
            if ($PhaseIndex -eq 1) {
                $Tracker.state.completed.items_with_first_recorded_run += 1
            }
        }

        $Tracker.state.completed.total_ops += 1
        $Tracker.state.last_completed = [ordered]@{
            finished_at = (Get-Date).ToString("o")
            phase = $Phase
            phase_index = $PhaseIndex
            phase_count = $PhaseCount
            workload = $Item.workload
            scenario = $Item.scenario
            config = $Item.config
            status = (Get-ResultStatus -Result $result)
            elapsed_ms = (Get-ResultElapsedMs -Result $result)
            global_step = $Tracker.state.completed.total_ops
        }
        $Tracker.state.current = $null
        Save-ProgressTracker -Tracker $Tracker
        Add-ProgressLog -Tracker $Tracker -Message ("DONE`t{0}`tstatus={1}`telapsed_ms={2}" -f $message, $Tracker.state.last_completed.status, $Tracker.state.last_completed.elapsed_ms)

        return $result
    }
    catch {
        $Tracker.state.status = "failed"
        $Tracker.state.last_completed = [ordered]@{
            finished_at = (Get-Date).ToString("o")
            phase = $Phase
            phase_index = $PhaseIndex
            phase_count = $PhaseCount
            workload = $Item.workload
            scenario = $Item.scenario
            config = $Item.config
            status = "exception"
            error = $_.Exception.Message
            global_step = $Tracker.state.completed.total_ops
        }
        Save-ProgressTracker -Tracker $Tracker
        Add-ProgressLog -Tracker $Tracker -Message ("ERROR`t{0}`terror={1}" -f $message, $_.Exception.Message)
        throw
    }
}

function Invoke-BenchmarkPostprocess {
    param(
        [Parameter(Mandatory = $true)]$Tracker,
        [Parameter(Mandatory = $true)][string]$OutputRoot
    )

    $artifactRoot = Ensure-Directory -Path (Join-Path $OutputRoot "artifact")
    $csvRoot = Ensure-Directory -Path (Join-Path $OutputRoot "csv")
    $collectEnvScript = Join-Path $PSScriptRoot "collect_env.ps1"
    $summarizeScript = Join-Path $PSScriptRoot "summarize.py"
    $summaryPath = Join-Path $csvRoot "summary.csv"
    $perRunPath = Join-Path $csvRoot "per_run.csv"
    $inputRoot = Join-Path $OutputRoot "raw"
    $errors = @()

    $Tracker.state.postprocess_status = "running"
    $Tracker.state.postprocess_started_at = (Get-Date).ToString("o")
    $Tracker.state.postprocess_completed_at = $null
    $Tracker.state.postprocess_error = $null
    Save-ProgressTracker -Tracker $Tracker
    Add-ProgressLog -Tracker $Tracker -Message "START`tpostprocess"

    try {
        & $collectEnvScript -OutputDir $artifactRoot | Out-Null
        Add-ProgressLog -Tracker $Tracker -Message "DONE`tcollect_env"
    }
    catch {
        $errors += "collect_env: $($_.Exception.Message)"
        Add-ProgressLog -Tracker $Tracker -Message ("ERROR`tcollect_env`terror={0}" -f $_.Exception.Message)
    }

    try {
        $pythonPath = Get-PreferredPythonPath
        & $pythonPath $summarizeScript --input-root $inputRoot --csv-out $summaryPath --per-run-out $perRunPath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "summarize.py exited with code $LASTEXITCODE"
        }
        Add-ProgressLog -Tracker $Tracker -Message "DONE`tsummarize"
    }
    catch {
        $errors += "summarize: $($_.Exception.Message)"
        Add-ProgressLog -Tracker $Tracker -Message ("ERROR`tsummarize`terror={0}" -f $_.Exception.Message)
    }

    $Tracker.state.postprocess_completed_at = (Get-Date).ToString("o")
    if ($errors.Count -eq 0) {
        $Tracker.state.postprocess_status = "completed"
        $Tracker.state.postprocess_error = $null
        Add-ProgressLog -Tracker $Tracker -Message "DONE`tpostprocess"
    }
    else {
        $Tracker.state.postprocess_status = "failed"
        $Tracker.state.postprocess_error = ($errors -join "; ")
        Add-ProgressLog -Tracker $Tracker -Message ("ERROR`tpostprocess`terror={0}" -f $Tracker.state.postprocess_error)
        Write-Warning "Benchmark postprocess finished with errors: $($Tracker.state.postprocess_error)"
    }

    Save-ProgressTracker -Tracker $Tracker
}

$Configs = Normalize-List -Values $Configs
$Workloads = Normalize-List -Values $Workloads
$Scenarios = Normalize-List -Values $Scenarios
$OutputRoot = Get-ResultsRoot -OutputRoot $OutputRoot
$buildScript = Join-Path $PSScriptRoot "build.ps1"
$plan = Get-ExecutionPlan -Configs $Configs -Workloads $Workloads -Scenarios $Scenarios

if ($UseHyperfine -and (Test-CommandAvailable -Name "hyperfine")) {
    $grouped = $plan | Group-Object -Property workload,scenario
    foreach ($group in $grouped) {
        $commands = @()
        $labelParts = $group.Group[0]
        foreach ($item in $group.Group) {
            if ($StorageMode) {
                $commands += "pwsh -File $buildScript -Config $($item.config) -Workload $($item.workload) -Scenario $($item.scenario) -OutputRoot $OutputRoot -StorageMode $StorageMode -FailWithExitCode"
            }
            else {
                $commands += "pwsh -File $buildScript -Config $($item.config) -Workload $($item.workload) -Scenario $($item.scenario) -OutputRoot $OutputRoot -FailWithExitCode"
            }
        }
        $jsonOut = Join-Path $OutputRoot (Join-Path "raw" (Join-Path "hyperfine" "$($labelParts.workload)-$($labelParts.scenario).json"))
        $null = Ensure-Directory -Path (Split-Path -Path $jsonOut -Parent)
        & hyperfine --warmup $WarmupRuns --runs $Runs --export-json $jsonOut @commands
    }
    return
}

$orderedPlan = Shuffle-Items -Items $plan
$tracker = New-ProgressTracker -OutputRoot $OutputRoot -PlanCount $orderedPlan.Count -WarmupRuns $WarmupRuns -Runs $Runs
Write-Host "Progress artifact: $($tracker.path)"
Write-Host "Progress log: $($tracker.log_path)"

try {
    foreach ($item in $orderedPlan) {
        for ($warmup = 1; $warmup -le $WarmupRuns; $warmup++) {
            $null = Invoke-PlanStep -Item $item -Phase "warmup" -PhaseIndex $warmup -PhaseCount $WarmupRuns -Tracker $tracker -BuildScript $buildScript -OutputRoot $OutputRoot -StorageMode $StorageMode -NoRecord
        }

        if ($Runs -ge 1) {
            $null = Invoke-PlanStep -Item $item -Phase "run" -PhaseIndex 1 -PhaseCount $Runs -Tracker $tracker -BuildScript $buildScript -OutputRoot $OutputRoot -StorageMode $StorageMode
        }
    }

    for ($run = 2; $run -le $Runs; $run++) {
        foreach ($item in (Shuffle-Items -Items $orderedPlan)) {
            $null = Invoke-PlanStep -Item $item -Phase "run" -PhaseIndex $run -PhaseCount $Runs -Tracker $tracker -BuildScript $buildScript -OutputRoot $OutputRoot -StorageMode $StorageMode
        }
    }

    $tracker.state.status = "completed"
    $tracker.state.completed_at = (Get-Date).ToString("o")
    $tracker.state.current = $null
    Save-ProgressTracker -Tracker $tracker
    Add-ProgressLog -Tracker $tracker -Message "COMPLETE`tbenchmark run finished"
    Invoke-BenchmarkPostprocess -Tracker $tracker -OutputRoot $OutputRoot
}
catch {
    $tracker.state.status = "failed"
    $tracker.state.failed_at = (Get-Date).ToString("o")
    $tracker.state.current = $null
    Save-ProgressTracker -Tracker $tracker
    throw
}
