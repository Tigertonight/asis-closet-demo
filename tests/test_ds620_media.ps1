# Cross-platform regression checks. No Windows printer or print job is used.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'deploy/ds620-windows/ds620-media.ps1')
$script:passed = 0

function Check($Name, [scriptblock]$Body) {
    & $Body
    $script:passed++
    Write-Host "PASS: $Name"
}
function Require($Condition) {
    if (!$Condition) { throw 'Assertion failed.' }
}
function Require-Throws([scriptblock]$Body) {
    $failed = $false
    try { & $Body | Out-Null } catch { $failed = $true }
    Require $failed
}
function Fixture($Forms, $Kind = 'PrintCapabilities') {
    if ($Forms[0] -is [string]) { $Forms = ,$Forms }
    $items = foreach ($form in $Forms) {
        $w = $form[1]; $h = $form[2]; $label = $form[3]
        @"
<f:Option name="v:$($form[0])">
 <f:Property name="k:DisplayName"><f:Value>$label</f:Value></f:Property>
 <f:ScoredProperty name="k:MediaSizeWidth"><f:Value xsi:type="xsd:integer">$w</f:Value></f:ScoredProperty>
 <f:ScoredProperty name="k:MediaSizeHeight"><f:Value xsi:type="xsd:integer">$h</f:Value></f:ScoredProperty>
</f:Option>
"@
    }
    return [xml]@"
<f:$Kind xmlns:f="$script:DSFramework" xmlns:k="$script:DSKeywords" xmlns:v="urn:fixture:dnp"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" version="1">
 <f:Feature name="k:PageMediaSize">$($items -join '')</f:Feature>
</f:$Kind>
"@
}

Check 'All shipped PowerShell scripts parse' {
    foreach ($file in Get-ChildItem (Join-Path $root 'deploy/ds620-windows') -Filter '*.ps1') {
        $tokens = $null; $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
        if ($errors.Count) { throw ($errors | Out-String) }
    }
}
Check 'Nominal 4x6 and both orientations' {
    Require (Test-DSPhotoDimensions 101600 152400)
    Require (Test-DSPhotoDimensions 152400 101600)
}
Check 'DNP documented 105 x 156.1 mm bleed area and rounding' {
    Require (Test-DSPhotoDimensions 105000 156100)
    Require (Test-DSPhotoDimensions 156100 105000)
    Require (Test-DSPhotoDimensions 104902 155956)
}
Check 'Wrong sizes, strip, square, missing dimensions rejected' {
    foreach ($size in @(@(117300,156100), @(105000,206200), @(50800,152400), @(156100,155400), @(0,0), @(104000,153000))) {
        Require (!(Test-DSPhotoDimensions $size[0] $size[1]))
    }
}
$cap = Fixture @(@('DNP6x4',156100,105000,'(6x4)'), @('DNPR4x6',105000,156100,'PR(4x6)'), @('DNP6x8',206200,105000,'(6x8)'))
$options = @(Get-DSMediaOptions $cap)
Check 'Custom vendor options survive enumeration' {
    Require ($options.Count -eq 3)
    Require ($options[0].Key -eq 'urn:fixture:dnp|DNP6x4')
    Require ($options[0].Eligible -and $options[1].Eligible -and !$options[2].Eligible)
}
Check 'Ordinary DNP form chosen when PR rotation also exists' {
    $selected = Select-DSPhotoMedia $options @()
    Require ($selected.Key -eq $options[0].Key)
}
Check 'Current valid PR form retained' {
    $selected = Select-DSPhotoMedia $options @($options[1])
    Require ($selected.Key -eq $options[1].Key)
}
Check 'Current 6x8 does not override correct six-inch selection' {
    Require ((Select-DSPhotoMedia $options @($options[2])).Key -eq $options[0].Key)
}
Check 'Multi-layout modes with identical dimensions rejected' {
    $multiple = Fixture @(@('DNP6x4xN',156100,105000,'(6x4)xN'), @('DNP6x4x2',156100,105000,'(6x4)x2'), @('strip2up',156100,105000,'2-up'))
    $multipleOptions = @(Get-DSMediaOptions $multiple)
    Require (@($multipleOptions | Where-Object { $_.Eligible }).Count -eq 0)
    Require-Throws { Select-DSPhotoMedia $multipleOptions @() }
}
Check 'Ambiguous unknown forms stop rather than guess' {
    $ambiguous = @(Get-DSMediaOptions (Fixture @(@('a',101600,152400,'A'), @('b',101600,152400,'B'))))
    Require-Throws { Select-DSPhotoMedia $ambiguous @() }
}
Check 'Missing dimensions never inferred from label alone' {
    $missing = @(Get-DSMediaOptions (Fixture @(@('DNP6x4',0,0,'(6x4)'))))
    Require-Throws { Select-DSPhotoMedia $missing @() }
}
$ticket = Fixture @(@('DNP6x8',206200,105000,'(6x8)')) 'PrintTicket'
$oldXml = $ticket.OuterXml
$changed = Set-DSMediaXml $ticket $options[0]
Check 'Ticket replacement preserves vendor ID and namespace through XML roundtrip' {
    $roundtrip = [xml]$changed.OuterXml
    $roundOptions = @(Get-DSMediaOptions $roundtrip)
    Require ($roundOptions.Count -eq 1)
    Require ($roundOptions[0].Key -eq $options[0].Key)
    Require ($roundOptions[0].WidthMicrons -eq 156100)
    Require ($roundOptions[0].HeightMicrons -eq 105000)
    Assert-DSSelectedMedia $roundtrip $options[0]
}
Check 'Original ticket is untouched for rollback' {
    Require ($ticket.OuterXml -eq $oldXml)
}
Check 'Capability-only DisplayName is not written into the print ticket' {
    $ns = Get-DSNamespaces $changed
    Require ($changed.SelectNodes('//f:Property', $ns).Count -eq 0)
}
Check 'Conflicting namespace prefixes in original ticket are handled' {
    $conflicting = [xml]$oldXml.Replace('urn:fixture:dnp', 'urn:different-driver')
    $result = Set-DSMediaXml $conflicting $options[0]
    Assert-DSSelectedMedia ([xml]$result.OuterXml) $options[0]
}
Check 'Read-back must retain vendor paper identifier, even at same dimensions' {
    Require-Throws { Assert-DSSelectedMedia (Fixture @(@('other',156100,105000,'(6x4)')) 'PrintTicket') $options[0] }
}
Check 'Read-back rejects wrong size or unexpected rotation' {
    Require-Throws { Assert-DSSelectedMedia (Fixture @(@('DNP6x4',206200,105000,'(6x8)')) 'PrintTicket') $options[0] }
    Require-Throws { Assert-DSSelectedMedia (Fixture @(@('DNP6x4',105000,156100,'(6x4)')) 'PrintTicket') $options[0] }
}
Check 'Driver ticket may omit dimensions when exact verified vendor ID remains' {
    Assert-DSSelectedMedia (Fixture @(@('DNP6x4',0,0,'(6x4)')) 'PrintTicket') $options[0]
}
Write-Host "$script:passed DS620 paper regression checks passed. Physical Windows driver validation is still required."
