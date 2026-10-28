# Run with Windows PowerShell 5.1 on the computer connected to the printer.
# This script changes current-user preferences only; it does not print anything.
[CmdletBinding()]
param([string]$PrinterName = 'DS620', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Printing
Add-Type -AssemblyName ReachFramework
. (Join-Path $PSScriptRoot 'ds620-media.ps1')

function Read-DSXml($Stream) {
    try {
        $doc = New-Object System.Xml.XmlDocument
        $doc.XmlResolver = $null
        $doc.Load($Stream)
        return ,$doc
    } finally { $Stream.Dispose() }
}

function New-DSPrintTicket($Document) {
    $stream = New-Object System.IO.MemoryStream
    try {
        $Document.Save($stream)
        $stream.Position = 0
        return [System.Printing.PrintTicket]::new($stream)
    } finally { $stream.Dispose() }
}

function Assert-PhotoLayout($Ticket, $Media, $Orientation, $Settings) {
    if ($null -eq $Ticket -or $Ticket.PageOrientation -ne $Orientation -or $Ticket.CopyCount -ne 1) {
        throw 'The driver did not retain 4x6 paper / portrait output / one copy.'
    }
    Assert-DSSelectedMedia (Read-DSXml $Ticket.GetXmlStream()) $Media
    foreach ($name in $Settings.Keys) {
        if ($Ticket.$name -ne $Settings[$name]) {
            throw "The driver did not retain $name = $($Settings[$name]). Check DS620 Printing Preferences."
        }
    }
    # Do not silently inherit an incompatible value even when the driver does
    # not advertise that setting through the standard PrintCapabilities API.
    if ($Ticket.PageBorderless -eq [System.Printing.PageBorderless]::None) {
        throw 'The driver still has borders enabled. Set DS620 Option > Border to Disable, then run again.'
    }
    if ($null -ne $Ticket.PageScalingFactor -and $Ticket.PageScalingFactor -ne 100) {
        throw 'The driver still has non-100% scaling. Set scaling to 100%, then run again.'
    }
    if ($null -ne $Ticket.PagesPerSheet -and $Ticket.PagesPerSheet -ne 1) {
        throw 'The driver still has multiple pages per sheet. Select one page per sheet, then run again.'
    }
}

$server = New-Object System.Printing.LocalPrintServer
$queue = $null
$previousTicket = $null
$changedTicket = $false
$previousDefault = $null
$backup = $null
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

    $backup = Join-Path $env:LOCALAPPDATA ('Selfit\Printing\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Write-Host "Diagnostic folder: $backup"
    $previousXml = Read-DSXml $previousTicket.GetXmlStream()
    $previousXml.Save((Join-Path $backup 'previous-print-ticket.xml'))
    @{ Printer = $queue.FullName; PreviousDefault = $previousDefault } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $backup 'previous-settings.json')
    $capabilityXml = Read-DSXml $queue.GetPrintCapabilitiesAsXml()
    $capabilityXml.Save((Join-Path $backup 'print-capabilities.xml'))
    $options = @(Get-DSMediaOptions $capabilityXml)
    $inventory = @($options | ForEach-Object {
        "Name=$($_.Name); label=$($_.Label); size=$($_.WidthMicrons / 1000) x $($_.HeightMicrons / 1000) mm; usable=$($_.Eligible)"
    })
    $inventory | Set-Content -Encoding UTF8 (Join-Path $backup 'paper-sizes.txt')
    $inventory | ForEach-Object { Write-Host $_ }
    $media = Select-DSPhotoMedia $options @(Get-DSMediaOptions $previousXml)
    $orientation = [System.Printing.PageOrientation]::Portrait
    if ($media.WidthMicrons -gt $media.HeightMicrons) { $orientation = [System.Printing.PageOrientation]::Landscape }
    # Do not assign PageMediaSize: it discards custom vendor option identifiers.
    $delta = New-DSPrintTicket (Set-DSMediaXml $previousXml $media)
    $delta.PageOrientation = $orientation
    $delta.CopyCount = 1
    # Query capabilities for the chosen paper, not an unrelated previous size.
    $paperTicket = $queue.MergeAndValidatePrintTicket($previousTicket, $delta).ValidatedPrintTicket
    Assert-DSSelectedMedia (Read-DSXml $paperTicket.GetXmlStream()) $media
    $capabilities = $queue.GetPrintCapabilities($paperTicket)
    $layoutSettings = @{}
    if (@($capabilities.PageBorderlessCapability) -contains [System.Printing.PageBorderless]::Borderless) {
        $layoutSettings['PageBorderless'] = [System.Printing.PageBorderless]::Borderless
    } else {
        Write-Warning 'Automatic borderless setup is unavailable. In DS620 Printing Preferences, confirm Option > Border = Disable. This setting has NOT been verified.'
    }
    $scaleRange = $capabilities.PageScalingFactorRange
    if ($null -ne $scaleRange -and $scaleRange.MinimumScale -le 100 -and $scaleRange.MaximumScale -ge 100) {
        $layoutSettings['PageScalingFactor'] = 100
    } else {
        Write-Warning 'Automatic scaling setup is unavailable. Confirm 100% scaling in the driver/browser. This setting has NOT been verified.'
    }
    if (@($capabilities.PagesPerSheetCapability) -contains 1) {
        $layoutSettings['PagesPerSheet'] = 1
    } else {
        Write-Warning 'Automatic page-layout setup is unavailable. Confirm one page per sheet in Printing Preferences. This setting has NOT been verified.'
    }
    foreach ($name in $layoutSettings.Keys) { $delta.$name = $layoutSettings[$name] }
    $validated = $queue.MergeAndValidatePrintTicket($previousTicket, $delta).ValidatedPrintTicket
    Assert-PhotoLayout $validated $media $orientation $layoutSettings
    (Read-DSXml $validated.GetXmlStream()).Save((Join-Path $backup 'validated-print-ticket.xml'))
    Write-Host "Validated printer: $($queue.FullName)"
    Write-Host "Driver paper: $($media.Label) [$($media.Name)], $($media.WidthMicrons / 1000) x $($media.HeightMicrons / 1000) mm"
    Write-Host 'Paper: 4 x 6 inches. Web print area: 105 x 156.1 mm including bleed, 1240 x 1844 pixels; background covers all four edges.'
    if ($CheckOnly) { Write-Host 'Check complete. No settings changed.'; return }

    Write-Host "Previous settings saved to: $backup"

    $changedTicket = $true
    $queue.UserPrintTicket = $validated
    $queue.Commit()
    $queue.Refresh()
    $saved = $queue.UserPrintTicket
    (Read-DSXml $saved.GetXmlStream()).Save((Join-Path $backup 'saved-print-ticket.xml'))
    Assert-PhotoLayout $saved $media $orientation $layoutSettings
    $network = New-Object -ComObject WScript.Network
    $network.SetDefaultPrinter($queue.FullName)
    $server.Refresh()
    if ($server.DefaultPrintQueue.FullName -ne $queue.FullName) { throw 'Windows did not retain DS620 as the default printer.' }
    Write-Host "READY: $($queue.FullName) is the current-user default; 4x6 photo paper, portrait output, one copy." -ForegroundColor Green
    foreach ($name in ($layoutSettings.Keys | Sort-Object)) {
        Write-Host "Verified saved preference: $name = $($saved.$name)"
    }
    if ($layoutSettings.Count -lt 3) {
        Write-Warning 'Some layout settings require manual confirmation (see warnings above). READY does not confirm edge-to-edge output.'
    }
    Write-Host 'Use start-stamp.cmd for the dedicated silent-printing window, or select DS620 in a normal browser print dialog.'
    Write-Host 'The printer must contain the correct 4x6 media. A physical test print is still required.'
} catch {
    if ($backup) { Write-Warning "For diagnosis, send paper-sizes.txt from: $backup" }
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
