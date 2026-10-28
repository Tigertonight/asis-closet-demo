# Pure XML helpers: retain vendor paper identifiers that System.Printing's
# standard PageMediaSizeCapability collection omits. No printer writes here.
$script:DSFramework = 'http://schemas.microsoft.com/windows/2003/08/printing/printschemaframework'
$script:DSKeywords = 'http://schemas.microsoft.com/windows/2003/08/printing/printschemakeywords'

function Get-DSNamespaces($Document) {
    $ns = New-Object System.Xml.XmlNamespaceManager($Document.NameTable)
    $ns.AddNamespace('f', $script:DSFramework)
    return ,$ns
}

function Get-DSQName($Node) {
    $parts = $Node.GetAttribute('name').Split(':', 2)
    if ($parts.Count -ne 2) { return '' }
    return $Node.GetNamespaceOfPrefix($parts[0]) + '|' + $parts[1]
}

function Test-DSPhotoDimensions($WidthMicrons, $HeightMicrons) {
    $short = [Math]::Min([double]$WidthMicrons, [double]$HeightMicrons)
    $long = [Math]::Max([double]$WidthMicrons, [double]$HeightMicrons)
    # Nominal 4x6 and DNP's documented 6x4 print area including bleed.
    # Separate narrow tolerances: never accept 6x4.5, 6x8 or 2x6 strips.
    return (([Math]::Abs($short - 101600) -le 800 -and [Math]::Abs($long - 152400) -le 800) -or
        ([Math]::Abs($short - 105000) -le 800 -and [Math]::Abs($long - 156100) -le 800))
}

function Get-DSMediaOptions($Document) {
    $ns = Get-DSNamespaces $Document
    foreach ($feature in $Document.DocumentElement.SelectNodes('f:Feature', $ns)) {
        if ((Get-DSQName $feature) -ne ($script:DSKeywords + '|PageMediaSize')) { continue }
        foreach ($option in $feature.SelectNodes('f:Option', $ns)) {
            $width = 0; $height = 0; $label = ''
            foreach ($property in $option.SelectNodes('f:ScoredProperty | f:Property', $ns)) {
                $key = Get-DSQName $property
                $value = $property.SelectSingleNode('f:Value', $ns)
                if ($null -eq $value) { continue }
                if ($key -eq ($script:DSKeywords + '|MediaSizeWidth')) {
                    [void][int]::TryParse($value.InnerText, [ref]$width)
                } elseif ($key -eq ($script:DSKeywords + '|MediaSizeHeight')) {
                    [void][int]::TryParse($value.InnerText, [ref]$height)
                } elseif ($key -eq ($script:DSKeywords + '|DisplayName')) {
                    $label = $value.InnerText
                }
            }
            $key = Get-DSQName $option
            $localName = ($key -split '\|', 2)[-1]
            # Some DNP multiple-layout modes share a nominal sheet size.
            $multi = ($label + ' ' + $localName) -match '(?i)(?:[46]\s*[x*\u00d7]\s*[46]\s*\)?\s*[x*\u00d7]\s*(?:n|[2-9][0-9]*)|[2-9]\s*[-_]?\s*up|strip|cut)'
            [pscustomobject]@{
                Key = $key; Name = $option.GetAttribute('name'); Label = $label
                WidthMicrons = $width; HeightMicrons = $height
                Eligible = ($key -ne '' -and !$multi -and (Test-DSPhotoDimensions $width $height))
                Feature = $feature; Option = $option
            }
        }
    }
}

function Select-DSPhotoMedia($Options, $CurrentOptions) {
    $candidates = @($Options | Where-Object { $_.Eligible })
    foreach ($current in $CurrentOptions) {
        # Prefer the current valid form (ordinary 6x4 or its PR rotation).
        $same = @($candidates | Where-Object { $_.Key -eq $current.Key })
        if ($same.Count -eq 1) { return $same[0] }
    }
    if ($candidates.Count -eq 1) { return $candidates[0] }
    # DNP exposes (6x4) and PR(4x6). Prefer its ordinary form deterministically.
    $ordinary = @($candidates | Where-Object { ($_.Label -replace '\s', '') -match '^\(?(6x4|4x6)\)?$' })
    if ($ordinary.Count -eq 1) { return $ordinary[0] }
    throw "Found $($candidates.Count) usable 4x6 forms. See paper-sizes.txt in the diagnostic folder. Select the normal (6x4) or PR(4x6) form in DS620 Printing Preferences and rerun."
}

function Set-DSMediaXml($TicketDocument, $Media) {
    $doc = $TicketDocument.CloneNode($true)
    $ns = Get-DSNamespaces $doc
    foreach ($old in @($doc.DocumentElement.SelectNodes('f:Feature', $ns))) {
        if ((Get-DSQName $old) -eq ($script:DSKeywords + '|PageMediaSize')) {
            [void]$old.ParentNode.RemoveChild($old)
        }
    }
    $feature = $doc.CreateElement('selfitpsf', 'Feature', $script:DSFramework)
    # Names used in attribute values need explicit in-scope namespace bindings.
    $bindings = $Media.Option.CreateNavigator().GetNamespacesInScope([System.Xml.XmlNamespaceScope]::All)
    foreach ($prefix in $bindings.Keys) {
        if ($prefix -eq 'xml') { continue }
        $attribute = 'xmlns'
        if ($prefix) { $attribute += ':' + $prefix }
        $feature.SetAttribute($attribute, $bindings[$prefix])
    }
    $feature.SetAttribute('xmlns:selfitpsf', $script:DSFramework)
    $feature.SetAttribute('name', $Media.Feature.GetAttribute('name'))
    $option = $doc.CreateElement('selfitpsf', 'Option', $script:DSFramework)
    $option.SetAttribute('name', $Media.Name)
    $sourceNs = Get-DSNamespaces $Media.Option.OwnerDocument
    foreach ($property in $Media.Option.SelectNodes('f:ScoredProperty', $sourceNs)) {
        [void]$option.AppendChild($doc.ImportNode($property, $true))
    }
    [void]$feature.AppendChild($option)
    [void]$doc.DocumentElement.AppendChild($feature)
    return ,$doc
}

function Assert-DSSelectedMedia($Document, $Media) {
    $actual = @(Get-DSMediaOptions $Document)
    if ($actual.Count -ne 1 -or $actual[0].Key -ne $Media.Key) {
        throw 'The driver changed the selected paper identifier. Preferences were not accepted.'
    }
    # Preserve orientation as well as the size; no silent 6x8 or rotated fallback.
    # Some drivers omit dimensions from a ticket and return only the exact
    # vendor identifier. That identifier was already verified in capabilities.
    if (($actual[0].WidthMicrons -ne 0 -or $actual[0].HeightMicrons -ne 0) -and
        ([Math]::Abs($actual[0].WidthMicrons - $Media.WidthMicrons) -gt 800 -or
        [Math]::Abs($actual[0].HeightMicrons - $Media.HeightMicrons) -gt 800)) {
        throw 'The driver changed the selected paper dimensions. Preferences were not accepted.'
    }
}
