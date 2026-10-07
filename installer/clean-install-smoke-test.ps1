param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath
)

$ErrorActionPreference = "Stop"

$installDirectory = Join-Path $env:TEMP "VaultHaven-clean-install-$PID"
$logPath = Join-Path $env:TEMP "VaultHaven-clean-install-$PID.log"

try {
    New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
    $arguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=$installDirectory",
        "/LOG=$logPath"
    )
    $installer = Start-Process -FilePath $InstallerPath -ArgumentList $arguments -Wait -PassThru
    if ($installer.ExitCode -ne 0) {
        throw "Installer exited with code $($installer.ExitCode). See $logPath"
    }

    $applicationPath = Join-Path $installDirectory "VaultHaven.exe"
    if (-not (Test-Path $applicationPath)) {
        throw "Installed application was not found at $applicationPath"
    }

    $application = Start-Process -FilePath $applicationPath -PassThru
    Start-Sleep -Seconds 8
    if ($application.HasExited) {
        throw "Installed application exited during startup with code $($application.ExitCode)."
    }

    Stop-Process -Id $application.Id -Force
    Write-Host "Clean install and application startup smoke test passed."
}
finally {
    Get-Process -Name VaultHaven -ErrorAction SilentlyContinue | Stop-Process -Force
    Remove-Item -LiteralPath $installDirectory -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
}
