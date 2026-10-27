# Run with Windows PowerShell 5.1 on the computer connected to the printer.
# This script changes current-user preferences only; it does not print anything.
[CmdletBinding()]
param([string]$PrinterName = 'DS620', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Printing
Add-Type -AssemblyName ReachFramework

function Test-SixInch($Media) {
    if ($null -eq $Media -or $null -eq $Media.Width -or $null -eq $Media.Height) { return $false }
    # PrintTicket dimensions are in 1/96 inch. Tolerance: < 0.8 mm.
    $short = [Math]::Min([double]$Media.Width, [double]$Media.Height)
    $long = [Math]::Max([double]$Media.Width, [double]$Media.Height)
    return ([Math]::Abs($short - 384) -lt 3 -and [Math]::Abs($long - 576) -lt 3)
}

$server = New-Object System.Printing.LocalPrintServer
$queue = $null
$previousTicket = $null
$changedTicket = $false
$previousDefault = $null
try {
    $queues = @($server.GetPrintQueues())
    $matchedQueues = @($queues | Where-Object { $_.Name -eq $PrinterName -or $_.FullName -eq $PrinterName })
    if ($matchedQueues.Count -ne 1) {
        $names = ($queues | ForEach-Object { $_.Name }) -join ', '
        throw "Printer '$PrinterName' was not found uniquely. Installed printers: $names. Install the official DS620 driver first, or specify -PrinterName with its exact queue name."
    }
    $queue = $matchedQueues[0]
    $previousTicket = $queue.UserPrintTicket
    if ($null -eq $previousTicket) { $previousTicket = $queue.DefaultPrintTicket }
    if ($null -eq $previousTicket) { throw 'The driver did not provide a valid PrintTicket.' }
    try { $previousDefault = $server.DefaultPrintQueue.FullName } catch { $previousDefault = $null }

    $media = @($queue.GetPrintCapabilities().PageMediaSizeCapability | Where-Object { Test-SixInch $_ })
    if ($media.Count -ne 1) {
        throw "The driver reports $($media.Count) matching 4x6 forms. No settings were changed. Select the normal 4x6 form in DS620 Printing Preferences; do not select 2x6 strips, 2-up, or 6x8."
    }
    $orientation = [System.Printing.PageOrientation]::Portrait
    if ($media[0].Width -gt $media[0].Height) { $orientation = [System.Printing.PageOrientation]::Landscape }
    $delta = New-Object System.Printing.PrintTicket
    $delta.PageMediaSize = $media[0]
    $delta.PageOrientation = $orientation
    $delta.CopyCount = 1
    $validated = $queue.MergeAndValidatePrintTicket($previousTicket, $delta).ValidatedPrintTicket
    if (!(Test-SixInch $validated.PageMediaSize) -or $validated.PageOrientation -ne $orientation -or $validated.CopyCount -ne 1) {
        throw 'The driver rejected the requested 4x6 / portrait / one-copy configuration. No settings were changed.'
    }
    Write-Host "Validated printer: $($queue.FullName)"
    Write-Host "Driver paper: $($media[0].PageMediaSizeName), $($media[0].Width / 96) x $($media[0].Height / 96) inches"
    if ($CheckOnly) { Write-Host 'Check complete. No settings changed.'; return }

    $backup = Join-Path $env:LOCALAPPDATA ('Selfit\Printing\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    $stream = [IO.File]::Create((Join-Path $backup 'previous-print-ticket.xml'))
    try { $previousTicket.SaveTo($stream) } finally { $stream.Dispose() }
    @{ Printer = $queue.FullName; PreviousDefault = $previousDefault } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $backup 'previous-settings.json')
    Write-Host "Previous settings saved to: $backup"

    $changedTicket = $true
    $queue.UserPrintTicket = $validated
    $queue.Commit()
    $queue.Refresh()
    $saved = $queue.UserPrintTicket
    if (!(Test-SixInch $saved.PageMediaSize) -or $saved.PageOrientation -ne $orientation -or $saved.CopyCount -ne 1) {
        throw 'The saved driver preferences did not match the request.'
    }
    $network = New-Object -ComObject WScript.Network
    $network.SetDefaultPrinter($queue.FullName)
    $server.Refresh()
    if ($server.DefaultPrintQueue.FullName -ne $queue.FullName) { throw 'Windows did not retain DS620 as the default printer.' }
    Write-Host "READY: $($queue.FullName) is the current-user default; 4x6 photo paper, portrait output, one copy." -ForegroundColor Green
    Write-Host 'Use start-stamp.cmd for the dedicated silent-printing window, or select DS620 in a normal browser print dialog.'
    Write-Host 'The printer must contain the correct 4x6 media. A physical test print is still required.'
} catch {
    if ($changedTicket) {
        try {
            $queue.UserPrintTicket = $previousTicket
            $queue.Commit()
            if ($previousDefault) { (New-Object -ComObject WScript.Network).SetDefaultPrinter($previousDefault) }
            Write-Warning 'Configuration failed; previous printer preferences were restored.'
        } catch { Write-Warning "Automatic restoration failed. Use the backup: $backup" }
    }
    throw
} finally {
    if ($queue) { $queue.Dispose() }
    $server.Dispose()
}
