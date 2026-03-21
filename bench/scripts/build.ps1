param(
    [ValidateSet("B0_baseline_xelatex", "B1_latexmk", "B2_latexmk_mylatexformat", "B3_latexmk_tikz_externalize", "B4_minted_cache", "B6_tectonic", "B7_windows_storage_mode")]
    [string]$Config,
    [ValidateSet("W1_text_math", "W2_cjk_font", "W4_tikz", "W5_minted", "R1_fontspec_example", "R2_pgfplots_example")]
    [string]$Workload,
    [ValidateSet("S0_clean_build", "S1_text_edit", "S2_bib_edit", "S3_figure_edit", "S4_preamble_edit")]
    [string]$Scenario,
    [string]$RunId,
    [string]$OutputRoot,
    [string]$ProtocolVersion = "v0.2-prime-measure",
    [string]$StorageMode,
    [switch]$NoRecord,
    [switch]$FailWithExitCode,
    [switch]$RefreshReference
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

$preferredPython = Get-PreferredPythonPath
$preferredPythonDir = Split-Path -Path $preferredPython -Parent
if ($preferredPythonDir -and -not (($env:PATH -split ';') -contains $preferredPythonDir)) {
    $env:PATH = "$preferredPythonDir;$env:PATH"
}

function Get-ScenarioMetadata {
    param([Parameter(Mandatory = $true)][string]$Scenario)
    switch ($Scenario) {
        "S0_clean_build" { [pscustomobject]@{ prime_required = $false; edit_applied = $false; edit_target = "none" } }
        "S1_text_edit" { [pscustomobject]@{ prime_required = $true; edit_applied = $true; edit_target = "text" } }
        "S2_bib_edit" { [pscustomobject]@{ prime_required = $true; edit_applied = $true; edit_target = "bibliography" } }
        "S3_figure_edit" { [pscustomobject]@{ prime_required = $true; edit_applied = $true; edit_target = "figure" } }
        "S4_preamble_edit" { [pscustomobject]@{ prime_required = $true; edit_applied = $true; edit_target = "preamble" } }
        default { throw "Unsupported scenario: $Scenario" }
    }
}

function Test-ConfigAppliesToWorkload {
    param([Parameter(Mandatory = $true)]$ConfigDefinition, [Parameter(Mandatory = $true)][string]$Workload)
    if (-not ($ConfigDefinition.PSObject.Properties.Name -contains "applicable_workloads")) { return $true }
    return $ConfigDefinition.applicable_workloads -contains $Workload
}

function Test-MintedWorkload {
    param([Parameter(Mandatory = $true)][string]$Workload)
    return $Workload -eq "W5_minted"
}

function Get-MissingRequiredCommands {
    param([Parameter(Mandatory = $true)]$ConfigDefinition)
    $missing = @()
    foreach ($required in $ConfigDefinition.requires) {
        if (-not (Test-CommandAvailable -Name $required)) { $missing += $required }
    }
    return @($missing)
}

function Get-RequiresShellEscape {
    param([Parameter(Mandatory = $true)][string]$Config, [Parameter(Mandatory = $true)][string]$Workload)
    if ($Config -in @("B3_latexmk_tikz_externalize", "B4_minted_cache")) { return $true }
    if ((Test-MintedWorkload -Workload $Workload) -and $Config -in @("B0_baseline_xelatex", "B1_latexmk", "B2_latexmk_mylatexformat", "B7_windows_storage_mode")) { return $true }
    return $false
}

function Apply-ScenarioMutation {
    param([Parameter(Mandatory = $true)][string]$Scenario, [Parameter(Mandatory = $true)][string]$MainTexPath)
    if ($Scenario -eq "S0_clean_build") { return }
    $content = Get-Content -LiteralPath $MainTexPath -Raw
    switch ($Scenario) {
        "S1_text_edit" { $content = $content -replace '\\newcommand\{\\benchtexttoken\}\{[^}]+\}', '\newcommand{\benchtexttoken}{BETA}' }
        "S2_bib_edit" { $content = $content -replace '\\cite\{refalpha\}', '\cite{refalpha,refbeta}' }
        "S3_figure_edit" { $content = $content -replace '\\newcommand\{\\benchfiguretoken\}\{[^}]+\}', '\newcommand{\benchfiguretoken}{1.25}' }
        "S4_preamble_edit" { $content = $content -replace '\\newcommand\{\\benchpreambletoken\}\{[^}]+\}', '\newcommand{\benchpreambletoken}{P1}' }
        default { throw "Unsupported scenario: $Scenario" }
    }
    Set-Content -LiteralPath $MainTexPath -Value $content -Encoding utf8
}

function Remove-PrimaryOutputs {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory)
    foreach ($name in @("main.pdf", "main.xdv", "main.dvi")) {
        $path = Join-Path $WorkingDirectory $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    }
}

function Invoke-BibtexIfNeeded {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory, [Parameter(Mandatory = $true)][string]$PhaseLogDirectory)
    $auxPath = Join-Path $WorkingDirectory "main.aux"
    if (-not (Test-Path -LiteralPath $auxPath)) { return [pscustomobject]@{ ran = $false; success = $true; exit_code = 0; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); status = "ok" } }
    if ((Get-Content -LiteralPath $auxPath -Raw) -notmatch '\\bibdata\{') { return [pscustomobject]@{ ran = $false; success = $true; exit_code = 0; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); status = "ok" } }
    if (-not (Test-CommandAvailable -Name "bibtex")) { return [pscustomobject]@{ ran = $true; success = $false; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); status = "missing_bibtex" } }
    $stdout = Join-Path $PhaseLogDirectory "bibtex.stdout.log"
    $stderr = Join-Path $PhaseLogDirectory "bibtex.stderr.log"
    $process = Invoke-ExternalProcess -FilePath "bibtex" -ArgumentList @("main") -WorkingDirectory $WorkingDirectory -StdOutPath $stdout -StdErrPath $stderr
    return [pscustomobject]@{ ran = $true; success = ($process.exit_code -eq 0); exit_code = $process.exit_code; elapsed_ms = $process.elapsed_ms; stdout_paths = @($stdout); stderr_paths = @($stderr); status = $(if ($process.exit_code -eq 0) { "ok" } else { "bibtex_failed" }) }
}

function Invoke-XeLaTeXBuild {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory, [Parameter(Mandatory = $true)][string]$PhaseLogDirectory, [Parameter(Mandatory = $true)][string]$Config, [Parameter(Mandatory = $true)][string]$Workload, [string]$FormatPath)
    if (-not (Test-CommandAvailable -Name "xelatex")) { return [pscustomobject]@{ success = $false; status = "missing_command"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Missing required command: xelatex" } }
    $shellEscape = Get-RequiresShellEscape -Config $Config -Workload $Workload
    $totalElapsed = 0.0
    $stdoutPaths = @()
    $stderrPaths = @()
    for ($pass = 1; $pass -le 3; $pass++) {
        $stdout = Join-Path $PhaseLogDirectory ("xelatex-pass{0}.stdout.log" -f $pass)
        $stderr = Join-Path $PhaseLogDirectory ("xelatex-pass{0}.stderr.log" -f $pass)
        $args = @("-interaction=nonstopmode", "-halt-on-error", "-file-line-error")
        if ($shellEscape) { $args += "-shell-escape" }
        if ($FormatPath) { $args += "-fmt=$FormatPath" }
        $args += "main.tex"
        $process = Invoke-ExternalProcess -FilePath "xelatex" -ArgumentList $args -WorkingDirectory $WorkingDirectory -StdOutPath $stdout -StdErrPath $stderr
        $stdoutPaths += $stdout
        $stderrPaths += $stderr
        $totalElapsed += $process.elapsed_ms
        if ($process.exit_code -ne 0) { return [pscustomobject]@{ success = $false; status = "build_failed"; exit_code = $process.exit_code; elapsed_ms = [math]::Round($totalElapsed, 3); stdout_paths = $stdoutPaths; stderr_paths = $stderrPaths; detail = "XeLaTeX pass $pass failed." } }
        if ($pass -eq 1) {
            $bibtexResult = Invoke-BibtexIfNeeded -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory
            $totalElapsed += $bibtexResult.elapsed_ms
            $stdoutPaths += $bibtexResult.stdout_paths
            $stderrPaths += $bibtexResult.stderr_paths
            if (-not $bibtexResult.success) { return [pscustomobject]@{ success = $false; status = $bibtexResult.status; exit_code = $bibtexResult.exit_code; elapsed_ms = [math]::Round($totalElapsed, 3); stdout_paths = $stdoutPaths; stderr_paths = $stderrPaths; detail = "BibTeX failed or was unavailable." } }
        }
    }
    $pdfPath = Join-Path $WorkingDirectory "main.pdf"
    $pdfExists = Test-Path -LiteralPath $pdfPath
    return [pscustomobject]@{ success = $pdfExists; status = $(if ($pdfExists) { "ok" } else { "missing_pdf" }); exit_code = $(if ($pdfExists) { 0 } else { -1 }); elapsed_ms = [math]::Round($totalElapsed, 3); stdout_paths = $stdoutPaths; stderr_paths = $stderrPaths; detail = $(if ($pdfExists) { $null } else { "XeLaTeX completed without producing main.pdf." }) }
}

function Invoke-LatexmkBuild {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory, [Parameter(Mandatory = $true)][string]$PhaseLogDirectory, [Parameter(Mandatory = $true)][string]$Config, [Parameter(Mandatory = $true)][string]$Workload)
    if (-not (Test-CommandAvailable -Name "latexmk")) { return [pscustomobject]@{ success = $false; status = "missing_command"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Missing required command: latexmk" } }
    if ($Config -eq "B3_latexmk_tikz_externalize") { $null = Ensure-Directory -Path (Join-Path $WorkingDirectory "tikz-cache") }
    $stdout = Join-Path $PhaseLogDirectory "latexmk.stdout.log"
    $stderr = Join-Path $PhaseLogDirectory "latexmk.stderr.log"
    $xelatexCommand = if (Get-RequiresShellEscape -Config $Config -Workload $Workload) { 'xelatex -shell-escape -interaction=nonstopmode -halt-on-error -file-line-error %O %S' } else { 'xelatex -interaction=nonstopmode -halt-on-error -file-line-error %O %S' }
    $args = @("-pdfxe", "-pdfxelatex=`"$xelatexCommand`"", "main.tex")
    $process = Invoke-ExternalProcess -FilePath "latexmk" -ArgumentList $args -WorkingDirectory $WorkingDirectory -StdOutPath $stdout -StdErrPath $stderr
    $pdfPath = Join-Path $WorkingDirectory "main.pdf"
    $pdfExists = Test-Path -LiteralPath $pdfPath
    return [pscustomobject]@{ success = ($process.exit_code -eq 0 -and $pdfExists); status = $(if ($process.exit_code -eq 0 -and $pdfExists) { "ok" } elseif ($process.exit_code -eq 0) { "missing_pdf" } else { "build_failed" }); exit_code = $(if ($pdfExists -or $process.exit_code -ne 0) { $process.exit_code } else { -1 }); elapsed_ms = $process.elapsed_ms; stdout_paths = @($stdout); stderr_paths = @($stderr); detail = $(if ($process.exit_code -eq 0 -or -not $pdfExists) { $null } else { "latexmk returned a non-zero exit code." }) }
}

function Invoke-TectonicBuild {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory, [Parameter(Mandatory = $true)][string]$PhaseLogDirectory, [switch]$AllowBundleFetch)
    if (-not (Test-CommandAvailable -Name "tectonic")) { return [pscustomobject]@{ success = $false; status = "missing_command"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Missing required command: tectonic" } }
    $stdout = Join-Path $PhaseLogDirectory "tectonic.stdout.log"
    $stderr = Join-Path $PhaseLogDirectory "tectonic.stderr.log"
    $args = @("-X", "compile", "main.tex", "--keep-logs", "--keep-intermediates")
    if (-not $AllowBundleFetch) { $args += "--only-cached" }
    $process = Invoke-ExternalProcess -FilePath "tectonic" -ArgumentList $args -WorkingDirectory $WorkingDirectory -StdOutPath $stdout -StdErrPath $stderr
    $pdfPath = Join-Path $WorkingDirectory "main.pdf"
    $pdfExists = Test-Path -LiteralPath $pdfPath
    $status = if ($process.exit_code -eq 0 -and $pdfExists) { "ok" } elseif ($process.exit_code -eq 0) { "missing_pdf" } elseif ($AllowBundleFetch) { "build_failed" } else { "build_failed_cached_only" }
    return [pscustomobject]@{ success = ($process.exit_code -eq 0 -and $pdfExists); status = $status; exit_code = $(if ($pdfExists -or $process.exit_code -ne 0) { $process.exit_code } else { -1 }); elapsed_ms = $process.elapsed_ms; stdout_paths = @($stdout); stderr_paths = @($stderr); detail = $(if ($AllowBundleFetch) { "tectonic build allowed bundle fetches." } else { "tectonic build ran in cached-only mode." }) }
}

function Invoke-MylatexformatBuild {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory, [Parameter(Mandatory = $true)][string]$PhaseLogDirectory, [Parameter(Mandatory = $true)][string]$Workload, [Parameter(Mandatory = $true)][string]$Config)
    if (-not (Test-CommandAvailable -Name "kpsewhich")) { return [pscustomobject]@{ success = $false; status = "missing_command"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Missing required command: kpsewhich" } }
    $mylatexformatPath = (& kpsewhich "mylatexformat.ltx" 2>$null | Select-Object -First 1)
    if (-not $mylatexformatPath) { return [pscustomobject]@{ success = $false; status = "missing_dependency"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Could not locate mylatexformat.ltx." } }
    $cacheRoot = Join-Path (Join-Path (Get-RepoRoot) "results\\cache\\mylatexformat") $Workload
    $fmtSourceRoot = Join-Path $cacheRoot "fmt-src"
    if (Test-Path -LiteralPath $fmtSourceRoot) { Remove-Item -LiteralPath $fmtSourceRoot -Recurse -Force -ErrorAction SilentlyContinue }
    $null = Ensure-Directory -Path $fmtSourceRoot
    Copy-DirectoryContents -Source $WorkingDirectory -Destination $fmtSourceRoot
    $stdout = Join-Path $cacheRoot "mylatexformat-build.stdout.log"
    $stderr = Join-Path $cacheRoot "mylatexformat-build.stderr.log"
    $args = @("-ini", "-jobname=benchfmt", "&xelatex", $mylatexformatPath.Trim(), "main.tex")
    $process = Invoke-ExternalProcess -FilePath "xelatex" -ArgumentList $args -WorkingDirectory $fmtSourceRoot -StdOutPath $stdout -StdErrPath $stderr
    $fmtPath = Join-Path $fmtSourceRoot "benchfmt.fmt"
    if ($process.exit_code -ne 0 -or -not (Test-Path -LiteralPath $fmtPath)) {
        return [pscustomobject]@{ success = $false; status = "mylatexformat_cache_generation_failed"; exit_code = $(if ($process.exit_code -ne 0) { $process.exit_code } else { -1 }); elapsed_ms = $process.elapsed_ms; stdout_paths = @($stdout); stderr_paths = @($stderr); detail = "mylatexformat cache generation failed. See $stderr" }
    }
    $buildResult = Invoke-XeLaTeXBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -Config $Config -Workload $Workload -FormatPath $fmtPath
    $buildResult.elapsed_ms = [math]::Round(($process.elapsed_ms + $buildResult.elapsed_ms), 3)
    $buildResult.stdout_paths = @($stdout) + $buildResult.stdout_paths
    $buildResult.stderr_paths = @($stderr) + $buildResult.stderr_paths
    if ($buildResult.success) { $buildResult.detail = "mylatexformat cache built from $fmtPath" }
    return $buildResult
}

function Invoke-ConfiguredBuild {
    param([Parameter(Mandatory = $true)]$ConfigDefinition, [Parameter(Mandatory = $true)][string]$Config, [Parameter(Mandatory = $true)][string]$Workload, [Parameter(Mandatory = $true)][string]$WorkingDirectory, [Parameter(Mandatory = $true)][string]$PhaseLogDirectory, [switch]$IsPrimePhase)
    switch ($ConfigDefinition.build_strategy) {
        "baseline_xelatex" { return Invoke-XeLaTeXBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -Config $Config -Workload $Workload }
        "latexmk_xelatex" { return Invoke-LatexmkBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -Config $Config -Workload $Workload }
        "latexmk_tikz_externalize" { return Invoke-LatexmkBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -Config $Config -Workload $Workload }
        "latexmk_minted_cache" { return Invoke-LatexmkBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -Config $Config -Workload $Workload }
        "mylatexformat_xelatex" { return Invoke-MylatexformatBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -Workload $Workload -Config $Config }
        "tectonic" { return Invoke-TectonicBuild -WorkingDirectory $WorkingDirectory -PhaseLogDirectory $PhaseLogDirectory -AllowBundleFetch:$IsPrimePhase }
        default { return [pscustomobject]@{ success = $false; status = "unknown_strategy"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Unknown build strategy: $($ConfigDefinition.build_strategy)" } }
    }
}

function Invoke-PdfFidelity {
    param([Parameter(Mandatory = $true)][string]$ReferencePdf, [Parameter(Mandatory = $true)][string]$CandidatePdf, [Parameter(Mandatory = $true)][string]$FidelityDirectory)
    if (-not (Test-CommandAvailable -Name "pdftoppm")) {
        return [pscustomobject]@{
            status = "missing_pdftoppm"
            binary_equal = $null
            visual_equal = $null
            visual_diff_pages = @()
            changed_pages_count = $null
            reference_page_count = $null
            candidate_page_count = $null
            detail = "Missing required command: pdftoppm"
            json_path = $null
            artifacts = $null
        }
    }
    $pythonPath = Get-PreferredPythonPath
    $scriptPath = Join-Path $PSScriptRoot "pdf_diff.py"
    $stdout = Join-Path $FidelityDirectory "pdf-diff.stdout.log"
    $stderr = Join-Path $FidelityDirectory "pdf-diff.stderr.log"
    $jsonOut = Join-Path $FidelityDirectory "pdf-diff.json"
    $args = @($scriptPath, "--left", $ReferencePdf, "--right", $CandidatePdf, "--output-dir", $FidelityDirectory, "--json-out", $jsonOut)
    $null = Invoke-ExternalProcess -FilePath $pythonPath -ArgumentList $args -WorkingDirectory $FidelityDirectory -StdOutPath $stdout -StdErrPath $stderr
    if (-not (Test-Path -LiteralPath $jsonOut)) {
        return [pscustomobject]@{
            status = "fidelity_failed"
            binary_equal = $null
            visual_equal = $null
            visual_diff_pages = @()
            changed_pages_count = $null
            reference_page_count = $null
            candidate_page_count = $null
            detail = "pdf_diff.py did not produce $jsonOut"
            json_path = $null
            artifacts = $null
        }
    }
    $payload = Get-Content -LiteralPath $jsonOut -Raw | ConvertFrom-Json
    $artifacts = [pscustomobject]@{
        left_pdf_hash = $payload.left_hash
        right_pdf_hash = $payload.right_hash
        left_render_dir = $payload.left_render_dir
        right_render_dir = $payload.right_render_dir
        diff_render_dir = $payload.diff_render_dir
        left_pages = @($payload.left_pages)
        right_pages = @($payload.right_pages)
        visual_diff_images = @($payload.visual_diff_images)
        stdout_log = $stdout
        stderr_log = $stderr
    }
    return [pscustomobject]@{
        status = $payload.status
        binary_equal = $payload.binary_equal
        visual_equal = $payload.visual_equal
        visual_diff_pages = @($payload.visual_diff_pages)
        changed_pages_count = @($payload.visual_diff_pages).Count
        reference_page_count = $payload.left_page_count
        candidate_page_count = $payload.right_page_count
        detail = $payload.error
        json_path = $jsonOut
        artifacts = $artifacts
    }
}

function Invoke-WithDirectoryLock {
    param([Parameter(Mandatory = $true)][string]$LockDirectory, [Parameter(Mandatory = $true)][scriptblock]$ScriptBlock, [int]$TimeoutSeconds = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ($true) {
        try {
            $null = New-Item -ItemType Directory -Path $LockDirectory -ErrorAction Stop
            break
        }
        catch {
            if (Test-Path -LiteralPath $LockDirectory) {
                $lockItem = Get-Item -LiteralPath $LockDirectory -ErrorAction SilentlyContinue
                if ($lockItem -and $lockItem.LastWriteTime -lt (Get-Date).AddSeconds(-$TimeoutSeconds)) {
                    Remove-Item -LiteralPath $LockDirectory -Recurse -Force -ErrorAction SilentlyContinue
                    continue
                }
            }
            if ((Get-Date) -ge $deadline) { throw "Timed out acquiring lock: $LockDirectory" }
            Start-Sleep -Milliseconds 500
        }
    }
    try { return & $ScriptBlock } finally { if (Test-Path -LiteralPath $LockDirectory) { Remove-Item -LiteralPath $LockDirectory -Recurse -Force -ErrorAction SilentlyContinue } }
}

function Write-ProtocolArtifact {
    param([Parameter(Mandatory = $true)][string]$OutputRoot, [Parameter(Mandatory = $true)][string]$ProtocolVersion)
    $artifactRoot = Ensure-Directory -Path (Join-Path $OutputRoot "artifact")
    $protocolPath = Join-Path $artifactRoot "protocol.json"
    if (Test-Path -LiteralPath $protocolPath) { return }
    $payload = [pscustomobject]@{
        protocol_version = $ProtocolVersion
        main_matrix = [pscustomobject]@{
            workloads = @("W1_text_math", "W2_cjk_font", "W4_tikz", "W5_minted")
            scenarios = @("S0_clean_build", "S1_text_edit", "S2_bib_edit", "S3_figure_edit", "S4_preamble_edit")
            configs = @("B0_baseline_xelatex", "B1_latexmk", "B4_minted_cache")
        }
        appendix_configs = @("B2_latexmk_mylatexformat", "B3_latexmk_tikz_externalize", "B6_tectonic", "B7_windows_storage_mode")
        generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    }
    Write-JsonFile -Path $protocolPath -Value $payload
}

function Complete-TopLevelResult {
    param([Parameter(Mandatory = $true)]$Result)
    if ($FailWithExitCode -and -not $Result.success) {
        if ($Result.detail) { throw $Result.detail }
        throw "Benchmark build failed with status $($Result.status)."
    }
    return $Result
}

function Invoke-BenchmarkRunCore {
    param([Parameter(Mandatory = $true)][string]$Config, [Parameter(Mandatory = $true)]$ConfigDefinition, [Parameter(Mandatory = $true)][string]$Workload, [Parameter(Mandatory = $true)][string]$Scenario, [Parameter(Mandatory = $true)][string]$ProtocolVersion, [Parameter(Mandatory = $true)][string]$RunDirectory, [Parameter(Mandatory = $true)][string]$RunId, [switch]$ReferenceMode, [string]$StorageMode, [string]$OutputRoot)
    $scenarioMeta = Get-ScenarioMetadata -Scenario $Scenario
    $sourceDirectory = Ensure-Directory -Path (Join-Path $RunDirectory "source")
    $logsDirectory = Ensure-Directory -Path (Join-Path $RunDirectory "logs")
    $fidelityDirectory = Ensure-Directory -Path (Join-Path $RunDirectory "fidelity")
    $resultPath = Join-Path $RunDirectory "result.json"
    Copy-DirectoryContents -Source (Get-WorkloadPath -Workload $Workload) -Destination $sourceDirectory
    Set-Content -LiteralPath (Join-Path $sourceDirectory "bench-config.tex") -Value (Get-BenchConfigContent -Config $Config -Workload $Workload) -Encoding utf8
    $storageMetadata = Get-StorageMetadata -Path $sourceDirectory
    $storageMetadata | Add-Member -NotePropertyName "requested_storage_mode" -NotePropertyValue $StorageMode -Force
    $mainTexPath = Join-Path $sourceDirectory "main.tex"
    if (-not (Test-Path -LiteralPath $mainTexPath)) {
        $result = [pscustomobject]@{ timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o"); protocol_version = $ProtocolVersion; config = $Config; workload = $Workload; scenario = $Scenario; run_id = $RunId; reference_mode = [bool]$ReferenceMode; success = $false; status = "missing_main_tex"; exit_code = -1; elapsed_ms = 0.0; prime_required = $scenarioMeta.prime_required; prime_success = $null; prime_elapsed_ms = 0.0; measure_elapsed_ms = 0.0; total_wall_clock_ms = 0.0; scenario_edit_applied = $scenarioMeta.edit_applied; scenario_edit_target = $scenarioMeta.edit_target; pdf_exists = $false; pdf_path = (Join-Path $sourceDirectory "main.pdf"); pdf_hash = $null; stdout_logs = @(); stderr_logs = @(); phase_records = @{}; development_only = $ConfigDefinition.development_only; strong_fidelity_expected = $ConfigDefinition.strong_fidelity_expected; reference_pdf = $null; reference_page_count = $null; candidate_page_count = $null; fidelity_status = $null; fidelity_binary_equal = $null; fidelity_visual_equal = $null; visual_diff_pages = @(); changed_pages_count = $null; fidelity_json = $null; missing_tool = @(); preamble_signature_before = $null; preamble_signature_after_prime = $null; preamble_signature_after_edit = $null; storage_metadata = $storageMetadata; detail = "Missing source\\main.tex in copied workload." }
        Write-JsonFile -Path $resultPath -Value $result
        return $result
    }
    $preambleBefore = Get-PreambleSignature -MainTexPath $mainTexPath
    $preambleAfterPrime = $preambleBefore
    $preambleAfterEdit = $preambleBefore
    $phaseRecords = [ordered]@{}
    $stdoutLogs = @()
    $stderrLogs = @()
    $primeElapsed = 0.0
    $measureElapsed = 0.0
    $primeSuccess = $null
    $status = "ok"
    $exitCode = 0
    $detail = $null
    if ($scenarioMeta.prime_required) {
        $primeResult = Invoke-ConfiguredBuild -ConfigDefinition $ConfigDefinition -Config $Config -Workload $Workload -WorkingDirectory $sourceDirectory -PhaseLogDirectory (Ensure-Directory -Path (Join-Path $logsDirectory "prime")) -IsPrimePhase
        $phaseRecords["prime"] = $primeResult
        $stdoutLogs += $primeResult.stdout_paths
        $stderrLogs += $primeResult.stderr_paths
        $primeElapsed = $primeResult.elapsed_ms
        $primeSuccess = $primeResult.success
        $preambleAfterPrime = Get-PreambleSignature -MainTexPath $mainTexPath
        if (-not $primeResult.success) {
            $status = $primeResult.status
            $exitCode = $primeResult.exit_code
            $detail = $primeResult.detail
        } else {
            Remove-PrimaryOutputs -WorkingDirectory $sourceDirectory
            Apply-ScenarioMutation -Scenario $Scenario -MainTexPath $mainTexPath
            $preambleAfterEdit = Get-PreambleSignature -MainTexPath $mainTexPath
        }
    }
    elseif ($ConfigDefinition.build_strategy -eq "tectonic") {
        $setupResult = Invoke-ConfiguredBuild -ConfigDefinition $ConfigDefinition -Config $Config -Workload $Workload -WorkingDirectory $sourceDirectory -PhaseLogDirectory (Ensure-Directory -Path (Join-Path $logsDirectory "setup")) -IsPrimePhase
        $phaseRecords["setup"] = $setupResult
        $stdoutLogs += $setupResult.stdout_paths
        $stderrLogs += $setupResult.stderr_paths
        if (-not $setupResult.success) {
            $status = $setupResult.status
            $exitCode = $setupResult.exit_code
            $detail = $setupResult.detail
        } else {
            Remove-PrimaryOutputs -WorkingDirectory $sourceDirectory
        }
    }
    if ($status -eq "ok") {
        $measureResult = Invoke-ConfiguredBuild -ConfigDefinition $ConfigDefinition -Config $Config -Workload $Workload -WorkingDirectory $sourceDirectory -PhaseLogDirectory (Ensure-Directory -Path (Join-Path $logsDirectory "measure"))
        $phaseRecords["measure"] = $measureResult
        $stdoutLogs += $measureResult.stdout_paths
        $stderrLogs += $measureResult.stderr_paths
        $measureElapsed = $measureResult.elapsed_ms
        if (-not $measureResult.success) { $status = $measureResult.status; $exitCode = $measureResult.exit_code; $detail = $measureResult.detail }
    } else {
        $phaseRecords["measure"] = [pscustomobject]@{ success = $false; status = "skipped_due_to_prime_failure"; exit_code = -1; elapsed_ms = 0.0; stdout_paths = @(); stderr_paths = @(); detail = "Measure phase skipped because prime phase failed." }
    }
    $pdfPath = Join-Path $sourceDirectory "main.pdf"
    $pdfExists = (($status -eq "ok") -and (Test-Path -LiteralPath $pdfPath))
    if ($status -eq "ok" -and -not $pdfExists) { $status = "missing_pdf"; $exitCode = -1; $detail = "Build completed without producing main.pdf." }
    $referencePdf = $null
    $referencePageCount = $null
    $candidatePageCount = $null
    $fidelityStatus = $null
    $fidelityBinary = $null
    $fidelityVisual = $null
    $visualDiffPages = @()
    $changedPagesCount = $null
    $fidelityJson = $null
    $fidelityArtifacts = $null
    if ($ReferenceMode) {
        if ($pdfExists) {
            $referencePdf = $pdfPath
            $fidelityStatus = "self_reference"
            $fidelityBinary = $true
            $fidelityVisual = $true
            $changedPagesCount = 0
            $fidelityArtifacts = [pscustomobject]@{
                left_pdf_hash = Get-Sha256Hash -Path $pdfPath
                right_pdf_hash = Get-Sha256Hash -Path $pdfPath
                left_render_dir = $null
                right_render_dir = $null
                diff_render_dir = $null
                left_pages = @()
                right_pages = @()
                visual_diff_images = @()
                stdout_log = $null
                stderr_log = $null
            }
        }
    } elseif ($pdfExists) {
        $referenceResult = Ensure-ReferenceRun -OutputRoot $OutputRoot -Workload $Workload -Scenario $Scenario -ProtocolVersion $ProtocolVersion -RefreshReference:$RefreshReference
        if ($referenceResult.success -and $referenceResult.pdf_exists -and $referenceResult.pdf_path) {
            $referencePdf = $referenceResult.pdf_path
            $fidelityResult = Invoke-PdfFidelity -ReferencePdf $referencePdf -CandidatePdf $pdfPath -FidelityDirectory $fidelityDirectory
            $fidelityStatus = $fidelityResult.status
            $fidelityBinary = $fidelityResult.binary_equal
            $fidelityVisual = $fidelityResult.visual_equal
            $visualDiffPages = $fidelityResult.visual_diff_pages
            $changedPagesCount = $fidelityResult.changed_pages_count
            $referencePageCount = $fidelityResult.reference_page_count
            $candidatePageCount = $fidelityResult.candidate_page_count
            $fidelityJson = $fidelityResult.json_path
            $fidelityArtifacts = $fidelityResult.artifacts
        } else {
            $fidelityStatus = "reference_unavailable"
            if (-not $detail) { $detail = "Reference build was unavailable for fidelity comparison." }
        }
    }
    $result = [pscustomobject]@{
        timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o")
        protocol_version = $ProtocolVersion
        config = $Config
        workload = $Workload
        scenario = $Scenario
        run_id = $RunId
        requested_storage_mode = $StorageMode
        reference_mode = [bool]$ReferenceMode
        success = ($status -eq "ok" -and $pdfExists)
        status = $status
        exit_code = $exitCode
        elapsed_ms = $measureElapsed
        prime_required = $scenarioMeta.prime_required
        prime_success = $primeSuccess
        prime_elapsed_ms = $primeElapsed
        measure_elapsed_ms = $measureElapsed
        total_wall_clock_ms = [math]::Round(($primeElapsed + $measureElapsed), 3)
        scenario_edit_applied = $scenarioMeta.edit_applied
        scenario_edit_target = $scenarioMeta.edit_target
        pdf_exists = $pdfExists
        pdf_path = $pdfPath
        pdf_hash = Get-Sha256Hash -Path $pdfPath
        stdout_logs = $stdoutLogs
        stderr_logs = $stderrLogs
        phase_records = $phaseRecords
        development_only = $ConfigDefinition.development_only
        strong_fidelity_expected = $ConfigDefinition.strong_fidelity_expected
        reference_pdf = $referencePdf
        reference_page_count = $referencePageCount
        candidate_page_count = $candidatePageCount
        fidelity_status = $fidelityStatus
        fidelity_binary_equal = $fidelityBinary
        fidelity_visual_equal = $fidelityVisual
        visual_diff_pages = $visualDiffPages
        changed_pages_count = $changedPagesCount
        fidelity_json = $fidelityJson
        fidelity_artifacts = $fidelityArtifacts
        missing_tool = @()
        preamble_signature_before = $preambleBefore
        preamble_signature_after_prime = $preambleAfterPrime
        preamble_signature_after_edit = $preambleAfterEdit
        storage_metadata = $storageMetadata
        detail = $detail
    }
    Write-JsonFile -Path $resultPath -Value $result
    return $result
}

function Ensure-ReferenceRun {
    param([Parameter(Mandatory = $true)][string]$OutputRoot, [Parameter(Mandatory = $true)][string]$Workload, [Parameter(Mandatory = $true)][string]$Scenario, [Parameter(Mandatory = $true)][string]$ProtocolVersion, [switch]$RefreshReference)
    $referenceRoot = Get-ReferenceDirectory -OutputRoot $OutputRoot -Workload $Workload -Scenario $Scenario
    $referenceResultPath = Join-Path $referenceRoot "result.json"
    $referenceLock = "$referenceRoot.lock"
    return Invoke-WithDirectoryLock -LockDirectory $referenceLock -ScriptBlock {
        if (-not $RefreshReference -and (Test-Path -LiteralPath $referenceResultPath)) { return (Get-Content -LiteralPath $referenceResultPath -Raw | ConvertFrom-Json) }
        if (Test-Path -LiteralPath $referenceRoot) { Remove-Item -LiteralPath $referenceRoot -Recurse -Force -ErrorAction SilentlyContinue }
        $null = Ensure-Directory -Path $referenceRoot
        return Invoke-BenchmarkRunCore -Config "B0_baseline_xelatex" -ConfigDefinition (Get-ConfigDefinition -Config "B0_baseline_xelatex") -Workload $Workload -Scenario $Scenario -ProtocolVersion $ProtocolVersion -RunDirectory $referenceRoot -RunId "reference" -ReferenceMode -OutputRoot $OutputRoot
    }
}

$outputRoot = Get-ResultsRoot -OutputRoot $OutputRoot
Write-ProtocolArtifact -OutputRoot $outputRoot -ProtocolVersion $ProtocolVersion
$configDefinition = Get-ConfigDefinition -Config $Config
$scenarioMetadata = Get-ScenarioMetadata -Scenario $Scenario
$runId = if ($RunId) { $RunId } else { New-RunId }
$bucket = if ($NoRecord) { "raw\\_scratch" } else { "raw" }
$runDirectory = Get-RunDirectory -OutputRoot $outputRoot -Bucket $bucket -Workload $Workload -Scenario $Scenario -Config $Config -RunId $runId
if (-not (Test-ConfigAppliesToWorkload -ConfigDefinition $configDefinition -Workload $Workload)) {
    $null = Ensure-Directory -Path $runDirectory
    $invalidResult = [pscustomobject]@{ timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o"); protocol_version = $ProtocolVersion; config = $Config; workload = $Workload; scenario = $Scenario; run_id = $runId; requested_storage_mode = $StorageMode; reference_mode = $false; success = $false; status = "invalid_combination"; exit_code = -1; elapsed_ms = 0.0; prime_required = $scenarioMetadata.prime_required; prime_success = $null; prime_elapsed_ms = 0.0; measure_elapsed_ms = 0.0; total_wall_clock_ms = 0.0; scenario_edit_applied = $scenarioMetadata.edit_applied; scenario_edit_target = $scenarioMetadata.edit_target; pdf_exists = $false; pdf_path = (Join-Path (Join-Path $runDirectory "source") "main.pdf"); pdf_hash = $null; stdout_logs = @(); stderr_logs = @(); phase_records = @{}; development_only = $configDefinition.development_only; strong_fidelity_expected = $configDefinition.strong_fidelity_expected; reference_pdf = $null; reference_page_count = $null; candidate_page_count = $null; fidelity_status = $null; fidelity_binary_equal = $null; fidelity_visual_equal = $null; visual_diff_pages = @(); changed_pages_count = $null; fidelity_json = $null; missing_tool = @(); preamble_signature_before = $null; preamble_signature_after_prime = $null; preamble_signature_after_edit = $null; storage_metadata = $null; detail = "Config $Config does not apply to workload $Workload." }
    Write-JsonFile -Path (Join-Path $runDirectory "result.json") -Value $invalidResult
    return (Complete-TopLevelResult -Result $invalidResult)
}
$missingCommands = @(Get-MissingRequiredCommands -ConfigDefinition $configDefinition)
if ($missingCommands.Count -gt 0) {
    $null = Ensure-Directory -Path $runDirectory
    $storageMetadata = Get-StorageMetadata -Path $outputRoot
    $storageMetadata | Add-Member -NotePropertyName "requested_storage_mode" -NotePropertyValue $StorageMode -Force
    $missingResult = [pscustomobject]@{ timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o"); protocol_version = $ProtocolVersion; config = $Config; workload = $Workload; scenario = $Scenario; run_id = $runId; requested_storage_mode = $StorageMode; reference_mode = $false; success = $false; status = "missing_command"; exit_code = -1; elapsed_ms = 0.0; prime_required = $scenarioMetadata.prime_required; prime_success = $null; prime_elapsed_ms = 0.0; measure_elapsed_ms = 0.0; total_wall_clock_ms = 0.0; scenario_edit_applied = $scenarioMetadata.edit_applied; scenario_edit_target = $scenarioMetadata.edit_target; pdf_exists = $false; pdf_path = (Join-Path (Join-Path $runDirectory "source") "main.pdf"); pdf_hash = $null; stdout_logs = @(); stderr_logs = @(); phase_records = @{}; development_only = $configDefinition.development_only; strong_fidelity_expected = $configDefinition.strong_fidelity_expected; reference_pdf = $null; reference_page_count = $null; candidate_page_count = $null; fidelity_status = $null; fidelity_binary_equal = $null; fidelity_visual_equal = $null; visual_diff_pages = @(); changed_pages_count = $null; fidelity_json = $null; missing_tool = $missingCommands; preamble_signature_before = $null; preamble_signature_after_prime = $null; preamble_signature_after_edit = $null; storage_metadata = $storageMetadata; detail = "Missing required command(s): $($missingCommands -join ', ')" }
    Write-JsonFile -Path (Join-Path $runDirectory "result.json") -Value $missingResult
    return (Complete-TopLevelResult -Result $missingResult)
}
return (Complete-TopLevelResult -Result (Invoke-BenchmarkRunCore -Config $Config -ConfigDefinition $configDefinition -Workload $Workload -Scenario $Scenario -ProtocolVersion $ProtocolVersion -RunDirectory $runDirectory -RunId $runId -StorageMode $StorageMode -OutputRoot $outputRoot))
