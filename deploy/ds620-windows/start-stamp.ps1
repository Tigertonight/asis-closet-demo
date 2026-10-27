# Dedicated onsite Chrome window. This script does not create a print job.
# Printing from this window skips the preview confirmation; use it only for Selfit.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$chromeCandidates = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe')
    $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe' })
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (!$chrome) { throw 'Google Chrome is not installed. Install Chrome from Google before starting the stamp station.' }

# A separate data directory prevents an already-running personal Chrome process
# from swallowing the launch flags. No browser-wide policy is changed.
$profileDir = Join-Path $env:LOCALAPPDATA 'Selfit\DS620\Chrome'
$existing = @(Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profileDir) })
if ($existing.Count -gt 0) {
    throw 'The dedicated stamp browser is already running. Use that window, or close it before starting again.'
}

# Stop on a missing printer, unsupported paper or failed read-back. Never start
# silent printing with an unverified default (for example, Save as PDF).
& (Join-Path $PSScriptRoot 'configure-ds620.ps1') -PrinterName 'DS620'
New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
$launchArguments = @(
    ('--user-data-dir="' + $profileDir + '"')
    '--no-first-run'
    '--kiosk-printing'
    '--use-system-default-printer'
    '--app=https://selfit.com.cn/selfit/stamp'
)
Start-Process -FilePath $chrome -ArgumentList $launchArguments -ErrorAction Stop | Out-Null
Write-Host 'Opened the dedicated stamp window. The Print Photo button sends to the Windows default printer without confirmation.' -ForegroundColor Green
Write-Host 'Keep DS620 as the default while this window is open. Run one physical test before the event.'
