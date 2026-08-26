[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PointDwg,

    [Parameter(Mandatory = $true)]
    [string]$BaseDwg,

    [Parameter(Mandatory = $true)]
    [string]$OutputDwg,

    [string]$LabelPrefix = "HD",

    [string]$LabelSuffix = "#",

    [ValidateRange(0.0, [double]::MaxValue)]
    [double]$MatchTolerance = 0.5,

    [switch]$AllowTextOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FullExistingPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
}

function Assert-DwgPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ([System.IO.Path]::GetExtension($Path) -ine ".dwg") {
        throw "$Name must be a DWG file: $Path"
    }
}

function Get-Coordinate {
    param([Parameter(Mandatory = $true)]$Value)

    $values = @($Value)
    return [pscustomobject]@{
        X = [double]$values[0]
        Y = [double]$values[1]
        Z = if ($values.Count -ge 3) { [double]$values[2] } else { 0.0 }
    }
}

function Get-TextId {
    param([Parameter(Mandatory = $true)][string]$Text)

    $trimmed = $Text.Trim()
    if ($trimmed -match '^\d+$') {
        return [int]$trimmed
    }
    if ($trimmed -match '(?i)HD\s*(\d+)\s*#') {
        return [int]$Matches[1]
    }
    return $null
}

function Get-RunningAutoCAD {
    if (-not ("RunningObjectTable" -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class RunningObjectTable
{
    [DllImport("ole32.dll")]
    public static extern int CLSIDFromProgID(string progId, out Guid clsid);

    [DllImport("oleaut32.dll", PreserveSig = false)]
    [return: MarshalAs(UnmanagedType.Interface)]
    public static extern object GetActiveObject(ref Guid clsid, IntPtr reserved, [MarshalAs(UnmanagedType.IUnknown)] object reserved2);
}
'@
    }

    $progIds = New-Object System.Collections.Generic.List[string]
    try {
        $currentVersion = (Get-ItemProperty -LiteralPath "Registry::HKEY_CLASSES_ROOT/AutoCAD.Application/CurVer" -ErrorAction Stop).'(default)'
        if (-not [string]::IsNullOrWhiteSpace([string]$currentVersion)) {
            $progIds.Add([string]$currentVersion)
        }
    }
    catch {
        # Fall back to versioned ProgIDs below.
    }

    $progIds.Add("AutoCAD.Application")
    foreach ($version in 30..18) {
        $progIds.Add("AutoCAD.Application.$version")
    }

    foreach ($progId in ($progIds | Select-Object -Unique)) {
        try {
            $application = [Runtime.InteropServices.Marshal]::GetActiveObject($progId)
            if ($null -ne $application) {
                return [pscustomobject]@{ Application = $application; ProgId = $progId }
            }
        }
        catch {
            # PowerShell 7 does not expose Marshal.GetActiveObject; use the native fallback below.
        }

        $classId = [Guid]::Empty
        if ([RunningObjectTable]::CLSIDFromProgID($progId, [ref]$classId) -ne 0) {
            continue
        }
        try {
            $application = [RunningObjectTable]::GetActiveObject([ref]$classId, [IntPtr]::Zero, $null)
            if ($null -ne $application) {
                return [pscustomobject]@{ Application = $application; ProgId = $progId }
            }
        }
        catch {
            # Try the next registered AutoCAD version.
        }
    }

    throw "No running AutoCAD instance was found. Open AutoCAD and retry."
}

function Get-OrOpenDocument {
    param(
        [Parameter(Mandatory = $true)]$Application,
        [Parameter(Mandatory = $true)][string]$Path
    )

    foreach ($document in $Application.Documents) {
        try {
            $documentPath = [System.IO.Path]::GetFullPath([string]$document.FullName)
            if ([string]::Equals($documentPath, $Path, [System.StringComparison]::OrdinalIgnoreCase)) {
                return [pscustomobject]@{ Document = $document; OpenedByScript = $false }
            }
        }
        catch {
            # Ignore unsaved documents without a usable FullName.
        }
    }

    $openedDocument = $Application.Documents.Open($Path, $false)
    Start-Sleep -Milliseconds 350
    return [pscustomobject]@{ Document = $openedDocument; OpenedByScript = $true }
}

function Get-Placements {
    param(
        [Parameter(Mandatory = $true)]$Document,
        [Parameter(Mandatory = $true)][double]$Tolerance,
        [Parameter(Mandatory = $true)][bool]$UseTextOnly
    )

    $points = New-Object System.Collections.Generic.List[object]
    $texts = New-Object System.Collections.Generic.List[object]

    foreach ($entity in $Document.ModelSpace) {
        if ([string]$entity.ObjectName -eq "AcDbPoint") {
            $points.Add((Get-Coordinate -Value $entity.Coordinates))
            continue
        }

        if (([string]$entity.ObjectName -eq "AcDbText") -or ([string]$entity.ObjectName -eq "AcDbMText")) {
            $id = Get-TextId -Text ([string]$entity.TextString)
            if ($null -ne $id) {
                $texts.Add([pscustomobject]@{
                    Id = [int]$id
                    Position = Get-Coordinate -Value $entity.InsertionPoint
                })
            }
        }
    }

    if ($texts.Count -eq 0) {
        throw "No numeric point labels were found in the coordinate DWG."
    }

    $duplicateIds = @($texts | Group-Object Id | Where-Object Count -gt 1 | ForEach-Object Name)
    if ($duplicateIds.Count -gt 0) {
        throw "Duplicate point labels were found: $($duplicateIds -join ', ')"
    }

    if ($points.Count -eq 0) {
        if (-not $UseTextOnly) {
            throw "No POINT entities were found. Use -AllowTextOnly only after confirming the text insertion points are the intended coordinates."
        }

        return @($texts | Sort-Object Id | ForEach-Object {
            [pscustomobject]@{ Id = $_.Id; X = $_.Position.X; Y = $_.Position.Y; Z = $_.Position.Z }
        })
    }

    if ($points.Count -ne $texts.Count) {
        throw "POINT count ($($points.Count)) does not match numeric label count ($($texts.Count))."
    }

    $usedTextIndexes = New-Object System.Collections.Generic.HashSet[int]
    $placements = New-Object System.Collections.Generic.List[object]

    foreach ($point in $points) {
        $matches = New-Object System.Collections.Generic.List[object]
        for ($index = 0; $index -lt $texts.Count; $index++) {
            if ($usedTextIndexes.Contains($index)) {
                continue
            }

            $text = $texts[$index]
            $dx = [double]$text.Position.X - [double]$point.X
            $dy = [double]$text.Position.Y - [double]$point.Y
            $distance = [Math]::Sqrt(($dx * $dx) + ($dy * $dy))
            if ($distance -le $Tolerance) {
                $matches.Add([pscustomobject]@{ Index = $index; Text = $text })
            }
        }

        if ($matches.Count -ne 1) {
            throw "Expected exactly one numeric label within $Tolerance units of point ($($point.X), $($point.Y)); found $($matches.Count)."
        }

        $match = $matches[0]
        $null = $usedTextIndexes.Add([int]$match.Index)
        $placements.Add([pscustomobject]@{
            Id = [int]$match.Text.Id
            X = [double]$point.X
            Y = [double]$point.Y
            Z = [double]$point.Z
        })
    }

    return @($placements | Sort-Object Id)
}

function Import-TemplateEntities {
    param(
        [Parameter(Mandatory = $true)]$Document,
        [Parameter(Mandatory = $true)][string]$TemplatePath
    )

    $origin = [double[]]@(0.0, 0.0, 0.0)
    $outerReference = $Document.ModelSpace.InsertBlock($origin, $TemplatePath, 1.0, 1.0, 1.0, 0.0)
    $entities = @($outerReference.Explode())
    $outerReference.Delete()
    return $entities
}

function Test-NearlyEqual {
    param(
        [Parameter(Mandatory = $true)][double]$Left,
        [Parameter(Mandatory = $true)][double]$Right,
        [double]$Tolerance = 0.000001
    )

    return [Math]::Abs($Left - $Right) -le $Tolerance
}

$pointPath = Get-FullExistingPath -Path $PointDwg
$basePath = Get-FullExistingPath -Path $BaseDwg
$outputPath = [System.IO.Path]::GetFullPath($OutputDwg)

Assert-DwgPath -Path $pointPath -Name "PointDwg"
Assert-DwgPath -Path $basePath -Name "BaseDwg"
Assert-DwgPath -Path $outputPath -Name "OutputDwg"

if ([string]::Equals($outputPath, $pointPath, [System.StringComparison]::OrdinalIgnoreCase) -or
    [string]::Equals($outputPath, $basePath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDwg must be different from both input files."
}
if (Test-Path -LiteralPath $outputPath) {
    throw "OutputDwg already exists: $outputPath"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptRoot
$stylePath = Join-Path $skillRoot "assets/ib-style.json"
$fjTemplatePath = Join-Path $skillRoot "assets/ib-fj-template.dwg"
$labelTemplatePath = Join-Path $skillRoot "assets/ib-label-template.dwg"

foreach ($requiredPath in @($stylePath, $fjTemplatePath, $labelTemplatePath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required skill asset is missing: $requiredPath"
    }
}

$style = Get-Content -LiteralPath $stylePath -Raw -Encoding UTF8 | ConvertFrom-Json
$baseHashBefore = (Get-FileHash -LiteralPath $basePath -Algorithm SHA256).Hash
$pointHashBefore = (Get-FileHash -LiteralPath $pointPath -Algorithm SHA256).Hash
$outputCreated = $false
$sourceDocument = $null
$sourceOpenedByScript = $false
$targetDocument = $null
$success = $false

try {
    $autoCAD = Get-RunningAutoCAD
    $application = $autoCAD.Application

    $sourceResult = Get-OrOpenDocument -Application $application -Path $pointPath
    $sourceDocument = $sourceResult.Document
    $sourceOpenedByScript = [bool]$sourceResult.OpenedByScript
    $sourceDocument.Activate()
    Start-Sleep -Milliseconds 350
    $placements = @(Get-Placements -Document $sourceDocument -Tolerance $MatchTolerance -UseTextOnly ([bool]$AllowTextOnly))

    $outputDirectory = Split-Path -Parent $outputPath
    if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $outputDirectory
    }
    Copy-Item -LiteralPath $basePath -Destination $outputPath
    $outputCreated = $true

    $targetResult = Get-OrOpenDocument -Application $application -Path $outputPath
    $targetDocument = $targetResult.Document
    $targetDocument.Activate()
    Start-Sleep -Milliseconds 350

    $existingFjDefinition = $null
    try {
        $existingFjDefinition = $targetDocument.Blocks.Item([string]$style.fj.blockName)
    }
    catch {
        # The template import below will create the missing block definition.
    }
    if (($null -ne $existingFjDefinition) -and ([int]$existingFjDefinition.Count -ne [int]$style.fj.entityCount)) {
        throw "The base DWG already contains an incompatible '$($style.fj.blockName)' block definition."
    }

    $fjImported = @(Import-TemplateEntities -Document $targetDocument -TemplatePath $fjTemplatePath)
    $labelImported = @(Import-TemplateEntities -Document $targetDocument -TemplatePath $labelTemplatePath)

    $fjTemplateCandidates = @($fjImported | Where-Object {
        ([string]$_.ObjectName -eq "AcDbBlockReference") -and ([string]$_.Name -ieq [string]$style.fj.blockName)
    } | Select-Object -First 1)
    if ($fjTemplateCandidates.Count -ne 1) {
        throw "The wind-turbine template did not yield exactly one '$($style.fj.blockName)' block reference."
    }
    $fjTemplate = $fjTemplateCandidates[0]

    $labelTemplateCandidates = @($labelImported | Where-Object { [string]$_.ObjectName -eq "AcDbMText" } | Select-Object -First 1)
    if ($labelTemplateCandidates.Count -ne 1) {
        throw "The label template did not yield exactly one MText entity."
    }
    $labelTemplate = $labelTemplateCandidates[0]

    $createdFj = New-Object System.Collections.Generic.List[object]
    $createdSquares = New-Object System.Collections.Generic.List[object]
    $createdLabels = New-Object System.Collections.Generic.List[object]

    foreach ($placement in $placements) {
        $insertion = [double[]]@([double]$placement.X, [double]$placement.Y, [double]$placement.Z)
        $fj = $targetDocument.ModelSpace.InsertBlock(
            $insertion,
            [string]$style.fj.blockName,
            [double]$fjTemplate.XScaleFactor,
            [double]$fjTemplate.YScaleFactor,
            [double]$fjTemplate.ZScaleFactor,
            [double]$fjTemplate.Rotation
        )
        $fj.Layer = [string]$style.fj.layer
        $createdFj.Add($fj)

        $squareSize = [double]$style.square.size
        $halfSize = $squareSize / 2.0
        $centerX = [double]$placement.X + [double]$style.square.centerOffset[0]
        $centerY = [double]$placement.Y + [double]$style.square.centerOffset[1]
        $minimumX = [double]$centerX - [double]$halfSize
        $maximumX = [double]$centerX + [double]$halfSize
        $minimumY = [double]$centerY - [double]$halfSize
        $maximumY = [double]$centerY + [double]$halfSize
        $vertices = [double[]]@(
            $minimumX, $minimumY,
            $maximumX, $minimumY,
            $maximumX, $maximumY,
            $minimumX, $maximumY,
            $minimumX, $minimumY
        )
        $square = $targetDocument.ModelSpace.AddLightWeightPolyline($vertices)
        $square.Layer = [string]$style.square.layer
        $square.Elevation = [double]$style.square.elevation
        $square.Color = [int]$style.square.colorIndex
        $square.Lineweight = [int]$style.square.lineweight
        $square.Linetype = [string]$style.square.linetype
        $square.Closed = [bool]$style.square.closed
        $createdSquares.Add($square)

        $labelX = [double]$placement.X + [double]$style.label.offset[0]
        $labelY = [double]$placement.Y + [double]$style.label.offset[1]
        $labelZ = [double]$placement.Z + [double]$style.label.offset[2]
        $label = $labelTemplate.Copy()
        $label.InsertionPoint = [double[]]@($labelX, $labelY, $labelZ)
        $replacement = "$LabelPrefix$($placement.Id)$LabelSuffix"
        $replacementEvaluator = [System.Text.RegularExpressions.MatchEvaluator]{
            param($match)
            return $replacement
        }
        $label.TextString = [regex]::Replace(
            [string]$labelTemplate.TextString,
            [string]$style.label.templatePattern,
            $replacementEvaluator
        )
        $label.Layer = [string]$style.label.layer
        $createdLabels.Add($label)
    }

    foreach ($temporaryEntity in @($fjImported) + @($labelImported)) {
        try {
            $temporaryEntity.Delete()
        }
        catch {
            # A nested temporary object may already have been erased with its owner.
        }
    }

    if (($createdFj.Count -ne $placements.Count) -or
        ($createdSquares.Count -ne $placements.Count) -or
        ($createdLabels.Count -ne $placements.Count)) {
        throw "Created object counts do not match the placement count."
    }

    for ($index = 0; $index -lt $placements.Count; $index++) {
        $placement = $placements[$index]
        $fjPosition = Get-Coordinate -Value $createdFj[$index].InsertionPoint
        if (-not ((Test-NearlyEqual -Left $fjPosition.X -Right $placement.X) -and
                  (Test-NearlyEqual -Left $fjPosition.Y -Right $placement.Y) -and
                  (Test-NearlyEqual -Left $fjPosition.Z -Right $placement.Z))) {
            throw "Wind-turbine insertion point validation failed for ID $($placement.Id)."
        }

        $squareCoordinates = @($createdSquares[$index].Coordinates)
        $squareXs = New-Object System.Collections.Generic.List[double]
        $squareYs = New-Object System.Collections.Generic.List[double]
        for ($coordinateIndex = 0; $coordinateIndex -lt $squareCoordinates.Count; $coordinateIndex += 2) {
            $squareXs.Add([double]$squareCoordinates[$coordinateIndex])
            $squareYs.Add([double]$squareCoordinates[$coordinateIndex + 1])
        }
        $squareWidth = [double](($squareXs | Measure-Object -Maximum).Maximum) - [double](($squareXs | Measure-Object -Minimum).Minimum)
        $squareHeight = [double](($squareYs | Measure-Object -Maximum).Maximum) - [double](($squareYs | Measure-Object -Minimum).Minimum)
        if (-not ((Test-NearlyEqual -Left $squareWidth -Right ([double]$style.square.size)) -and
                  (Test-NearlyEqual -Left $squareHeight -Right ([double]$style.square.size)))) {
            throw "Square size validation failed for ID $($placement.Id)."
        }

        $expectedLabel = "$LabelPrefix$($placement.Id)$LabelSuffix"
        if ([string]$createdLabels[$index].TextString -notmatch [regex]::Escape($expectedLabel)) {
            throw "Label validation failed for ID $($placement.Id)."
        }
    }

    foreach ($layerName in @([string]$style.fj.layer, [string]$style.square.layer, [string]$style.label.layer) | Select-Object -Unique) {
        $layer = $targetDocument.Layers.Item($layerName)
        $layer.LayerOn = $true
        $layer.Freeze = $false
    }

    $targetDocument.Regen(1)
    $application.ZoomExtents()
    $targetDocument.Save()

    if ($sourceOpenedByScript -and ($null -ne $sourceDocument)) {
        $sourceDocument.Close($false)
        Start-Sleep -Milliseconds 350
        $sourceDocument = $null
        $sourceOpenedByScript = $false
    }

    $baseHashAfter = (Get-FileHash -LiteralPath $basePath -Algorithm SHA256).Hash
    $pointHashAfter = (Get-FileHash -LiteralPath $pointPath -Algorithm SHA256).Hash
    if (($baseHashBefore -ne $baseHashAfter) -or ($pointHashBefore -ne $pointHashAfter)) {
        throw "An input DWG hash changed during processing."
    }

    $success = $true
    [pscustomobject]@{
        status = "validated"
        outputDwg = $outputPath
        pointCount = $placements.Count
        fjCount = $createdFj.Count
        squareCount = $createdSquares.Count
        labelCount = $createdLabels.Count
        labels = @($placements | ForEach-Object { "$LabelPrefix$($_.Id)$LabelSuffix" })
        inputHashesUnchanged = $true
        pointDwgSha256 = $pointHashAfter
        baseDwgSha256 = $baseHashAfter
        autoCADProgId = $autoCAD.ProgId
    } | ConvertTo-Json -Depth 4
}
finally {
    if ($sourceOpenedByScript -and ($null -ne $sourceDocument)) {
        try {
            $sourceDocument.Close($false)
        }
        catch {
            # Do not mask the primary result with a source-document close error.
        }
    }

    if (-not $success) {
        if ($null -ne $targetDocument) {
            try {
                $targetDocument.Close($false)
                Start-Sleep -Milliseconds 350
            }
            catch {
                # Continue with scoped cleanup when the document is already closed.
            }
        }
        if ($outputCreated -and (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
            Remove-Item -LiteralPath $outputPath -Force
        }
    }
}
