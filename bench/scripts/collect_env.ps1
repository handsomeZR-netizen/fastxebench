param(
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "artifact")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

$outputDir = Ensure-Directory -Path $OutputDir
$records = @()

$commands = @(
    "xelatex",
    "xetex",
    "latexmk",
    "bibtex",
    "kpsewhich",
    "latexminted",
    "pdftoppm",
    "tectonic",
    "hyperfine",
    "conda"
)

foreach ($command in $commands) {
    if (Test-CommandAvailable -Name $command) {
        try {
            $versionArgs = switch ($command) {
                "xelatex" { @("--version") }
                "xetex" { @("--version") }
                "latexmk" { @("-v") }
                "bibtex" { @("--version") }
                "kpsewhich" { @("--version") }
                "latexminted" { @("--version") }
                "pdftoppm" { @("-v") }
                default { @("--version") }
            }

            $tempStem = Join-Path $env:TEMP ("fxenv-" + [Guid]::NewGuid().ToString("N"))
            $stdoutPath = "$tempStem.stdout.txt"
            $stderrPath = "$tempStem.stderr.txt"
            $result = Invoke-ExternalProcess `
                -FilePath $command `
                -ArgumentList $versionArgs `
                -WorkingDirectory $repoRoot `
                -StdOutPath $stdoutPath `
                -StdErrPath $stderrPath

            $stdout = if (Test-Path -LiteralPath $stdoutPath) {
                Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue
            }
            else {
                ""
            }
            $stderr = if (Test-Path -LiteralPath $stderrPath) {
                Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
            }
            else {
                ""
            }
            $version = (($stdout, $stderr) -join "`n").Trim()
            if ($version) {
                $version = (($version -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 6) -join "`n"
            }

            Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
        }
        catch {
            $version = $_.Exception.Message
        }

        $records += [pscustomobject]@{
            command = $command
            available = $true
            version = $version.Trim()
        }
    }
    else {
        $records += [pscustomobject]@{
            command = $command
            available = $false
            version = ""
        }
    }
}

$pythonPath = Get-PreferredPythonPath
$repoRoot = Get-RepoRoot
$storageMetadata = Get-StorageMetadata -Path $repoRoot
$osInfo = Get-CimInstance Win32_OperatingSystem
$computerSystem = Get-CimInstance Win32_ComputerSystem
$processor = Get-CimInstance Win32_Processor | Select-Object -First 1
$powerPlan = $null
if (Test-CommandAvailable -Name "powercfg") {
    try {
        $powerPlan = (& powercfg /GETACTIVESCHEME 2>&1 | Out-String).Trim()
    }
    catch {
        $powerPlan = $_.Exception.Message
    }
}
$payload = [pscustomobject]@{
    collected_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    repo_root = $repoRoot
    python = $pythonPath
    os_caption = $osInfo.Caption
    os_version = $osInfo.Version
    os_build_number = $osInfo.BuildNumber
    last_boot_time = ([DateTimeOffset]$osInfo.LastBootUpTime).ToString("o")
    system_model = $computerSystem.Model
    system_manufacturer = $computerSystem.Manufacturer
    processor_name = $processor.Name
    processor_cores = $processor.NumberOfCores
    processor_logical_processors = $processor.NumberOfLogicalProcessors
    total_physical_memory_bytes = [int64]$computerSystem.TotalPhysicalMemory
    power_plan = $powerPlan
    path = $env:PATH
    storage_metadata = $storageMetadata
    commands = $records
}

Write-JsonFile -Path (Join-Path $outputDir "env.json") -Value $payload

$lines = @(
    "Collected at: $($payload.collected_at_utc)",
    "Repo root: $($payload.repo_root)",
    "Python: $($payload.python)",
    "OS: $($payload.os_caption) $($payload.os_version) build $($payload.os_build_number)",
    "CPU: $($payload.processor_name) ($($payload.processor_cores)C/$($payload.processor_logical_processors)T)",
    "Memory (bytes): $($payload.total_physical_memory_bytes)",
    "Power plan: $($payload.power_plan)",
    ""
)

foreach ($record in $records) {
    $lines += "[$($record.command)] available=$($record.available)"
    if ($record.version) {
        $lines += $record.version
    }
    $lines += ""
}

Set-Content -LiteralPath (Join-Path $outputDir "versions.txt") -Value $lines -Encoding utf8
$payload | ConvertTo-Json -Depth 6
