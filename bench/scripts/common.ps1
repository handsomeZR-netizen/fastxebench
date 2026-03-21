Set-StrictMode -Version Latest

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:DefaultDatasetName = "protocol_v0_2_core_formal_20x3"

function Add-DirectoryToPath {
    param([string]$PathToAdd)

    if (-not $PathToAdd -or -not (Test-Path -LiteralPath $PathToAdd)) {
        return
    }

    if (($env:PATH -split ";") -contains $PathToAdd) {
        return
    }

    $env:PATH = "$PathToAdd;$env:PATH"
}

Add-DirectoryToPath -PathToAdd (Join-Path $HOME "miniconda3")
Add-DirectoryToPath -PathToAdd (Join-Path $HOME "miniconda3\Scripts")
Add-DirectoryToPath -PathToAdd (Join-Path $HOME "miniconda3\Library\bin")

$wingetPackagesRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
if (Test-Path -LiteralPath $wingetPackagesRoot) {
    Get-ChildItem -LiteralPath $wingetPackagesRoot -Directory -Filter "sharkdp.hyperfine_*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Directory -Filter "hyperfine-*" -ErrorAction SilentlyContinue |
                Select-Object -First 1 |
                ForEach-Object { Add-DirectoryToPath -PathToAdd $_.FullName }
        }
}

function Get-RepoRoot {
    return $script:RepoRoot
}

function Get-DefaultDatasetName {
    return $script:DefaultDatasetName
}

function Get-DefaultDatasetRoot {
    param([string]$DatasetName = $script:DefaultDatasetName)

    return (Join-Path $script:RepoRoot (Join-Path "results\datasets" $DatasetName))
}

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        $null = New-Item -ItemType Directory -Path $Path -Force
    }

    return (Resolve-Path -LiteralPath $Path).Path
}

function Test-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Name)

    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PreferredPythonPath {
    if ($env:BENCH_PYTHON -and (Test-Path -LiteralPath $env:BENCH_PYTHON)) {
        return (Resolve-Path -LiteralPath $env:BENCH_PYTHON).Path
    }

    $commonCandidates = @(
        (Join-Path $HOME "miniconda3\python.exe"),
        (Join-Path $HOME "anaconda3\python.exe")
    )

    foreach ($candidate in $commonCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($conda) {
        $condaBase = (& conda info --base 2>$null | Select-Object -First 1)
        if ($condaBase) {
            $candidate = Join-Path $condaBase.Trim() "python.exe"
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike "*WindowsApps*") {
        return $python.Source
    }

    throw "No usable Python interpreter was found. Set BENCH_PYTHON or install Miniconda/Python."
}

function Get-ConfigDefinition {
    param([Parameter(Mandatory = $true)][string]$Config)

    $path = Join-Path $script:RepoRoot "bench\configs\$Config\config.json"
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Unknown config: $Config"
    }

    return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Get-WorkloadPath {
    param([Parameter(Mandatory = $true)][string]$Workload)

    $path = Join-Path $script:RepoRoot "bench\workloads\$Workload"
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Unknown workload: $Workload"
    }

    return $path
}

function New-RunId {
    $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd-HHmmss-fff")
    $suffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    return "$stamp-$suffix"
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $null = Ensure-Directory -Path $Destination
    Get-ChildItem -LiteralPath $Source -Force | Copy-Item -Destination $Destination -Recurse -Force
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    $parent = Split-Path -Path $Path -Parent
    if ($parent) {
        $null = Ensure-Directory -Path $parent
    }

    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding utf8
}

function Get-Sha256Hash {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-ExternalProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$StdOutPath,
        [Parameter(Mandatory = $true)][string]$StdErrPath
    )

    $null = Ensure-Directory -Path (Split-Path -Path $StdOutPath -Parent)
    $null = Ensure-Directory -Path (Split-Path -Path $StdErrPath -Parent)

    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $process = Start-Process -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $StdOutPath `
            -RedirectStandardError $StdErrPath `
            -Wait `
            -PassThru `
            -NoNewWindow
        $stopwatch.Stop()

        return [pscustomobject]@{
            exit_code = $process.ExitCode
            elapsed_ms = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 3)
            stdout_path = $StdOutPath
            stderr_path = $StdErrPath
        }
    }
    catch {
        Set-Content -LiteralPath $StdErrPath -Value $_.Exception.ToString() -Encoding utf8
        return [pscustomobject]@{
            exit_code = -1
            elapsed_ms = 0.0
            stdout_path = $StdOutPath
            stderr_path = $StdErrPath
        }
    }
}

function Get-ResultsRoot {
    param([string]$OutputRoot)

    if ($OutputRoot) {
        return (Ensure-Directory -Path $OutputRoot)
    }

    return (Ensure-Directory -Path (Get-DefaultDatasetRoot))
}

function Get-RunDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][string]$Bucket,
        [Parameter(Mandatory = $true)][string]$Workload,
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$Config,
        [Parameter(Mandatory = $true)][string]$RunId
    )

    return (Join-Path $OutputRoot (Join-Path $Bucket (Join-Path $Workload (Join-Path $Scenario (Join-Path $Config $RunId)))))
}

function Get-ReferenceDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][string]$Workload,
        [Parameter(Mandatory = $true)][string]$Scenario
    )

    return (Join-Path $OutputRoot (Join-Path "raw" (Join-Path "_references" (Join-Path $Workload $Scenario))))
}

function Get-BenchConfigContent {
    param(
        [Parameter(Mandatory = $true)][string]$Config,
        [Parameter(Mandatory = $true)][string]$Workload
    )

    $lines = @("% generated bench-config")

    if ($Config -eq "B3_latexmk_tikz_externalize") {
        $lines += "\BenchTikzExternalizetrue"
    }

    if ($Workload -eq "W5_minted") {
        if ($Config -eq "B4_minted_cache") {
            $lines += "\BenchMintedCachetrue"
        }
        else {
            $lines += "\BenchMintedCachefalse"
        }
    }

    return (($lines -join "`n") + "`n")
}

function Get-PreambleSignature {
    param([Parameter(Mandatory = $true)][string]$MainTexPath)

    $lines = Get-Content -LiteralPath $MainTexPath
    $builder = [System.Text.StringBuilder]::new()
    foreach ($line in $lines) {
        [void]$builder.AppendLine($line)
        if ($line -match "\\begin\{document\}") {
            break
        }
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($builder.ToString())
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-StorageMetadata {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolvedRoot = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $Path).Path)
    $driveLetter = $resolvedRoot.TrimEnd('\').TrimEnd(':')
    $volume = $null
    if ($driveLetter) {
        $volume = Get-Volume -DriveLetter $driveLetter -ErrorAction SilentlyContinue
    }

    $mpPreference = $null
    if (Get-Command Get-MpPreference -ErrorAction SilentlyContinue) {
        $mpPreference = Get-MpPreference
    }

    $devDriveStatus = "unknown"
    $devDriveRaw = $null
    if (Test-CommandAvailable -Name "fsutil") {
        try {
            $devDriveOutput = & fsutil devdrv query "$driveLetter`:" 2>&1
            if ($LASTEXITCODE -eq 0) {
                $devDriveStatus = "query_ok"
            }
            else {
                $devDriveStatus = "query_failed"
            }
            $devDriveRaw = ($devDriveOutput | Out-String).Trim()
        }
        catch {
            $devDriveStatus = "query_exception"
            $devDriveRaw = $_.Exception.Message
        }
    }

    return [pscustomobject]@{
        drive_letter = $driveLetter
        path_root = $resolvedRoot
        file_system = $(if ($volume) { $volume.FileSystem } else { $null })
        drive_type = $(if ($volume) { $volume.DriveType } else { $null })
        defender_performance_mode_status = $(if ($mpPreference) { $mpPreference.PerformanceModeStatus } else { $null })
        defender_realtime_disabled = $(if ($mpPreference) { $mpPreference.DisableRealtimeMonitoring } else { $null })
        defender_exclusion_paths = $(if ($mpPreference) { $mpPreference.ExclusionPath } else { $null })
        dev_drive_query_status = $devDriveStatus
        dev_drive_query_output = $devDriveRaw
    }
}
