param(
    [string]$SqlSource = "deploy\mysql\original-export.sql",
    [string]$SqlTarget = "deploy\mysql\01-init.sql",
    [string]$FontsSource = "F:\fonts",
    [string]$MediaSource = "F:\shanbei_videos\deduped_media",
    [string]$FontsTarget = "runtime\calligraphy_fonts",
    [string]$MediaTarget = "runtime\media"
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectPath {
    param([string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path (Get-Location) $PathValue
}

function Ensure-Directory {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue)) {
        New-Item -ItemType Directory -Path $PathValue | Out-Null
    }
}

function Copy-DirectoryContents {
    param(
        [string]$Source,
        [string]$Target
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Source directory does not exist: $Source"
    }

    Ensure-Directory $Target

    $robocopyArgs = @(
        $Source,
        $Target,
        "/E",
        "/COPY:DAT",
        "/DCOPY:DAT",
        "/R:2",
        "/W:2",
        "/NFL",
        "/NDL",
        "/NP"
    )

    & robocopy @robocopyArgs | Out-Host
    $exitCode = $LASTEXITCODE

    # Robocopy uses 0-7 for success or non-fatal copy differences.
    if ($exitCode -ge 8) {
        throw "Robocopy failed from $Source to $Target with exit code $exitCode"
    }
}

$sqlSourcePath = Resolve-ProjectPath $SqlSource
$sqlTargetPath = Resolve-ProjectPath $SqlTarget
$fontsTargetPath = Resolve-ProjectPath $FontsTarget
$mediaTargetPath = Resolve-ProjectPath $MediaTarget

if (-not (Test-Path -LiteralPath $sqlSourcePath)) {
    throw "SQL source file does not exist: $sqlSourcePath"
}

Ensure-Directory (Split-Path -Parent $sqlTargetPath)
Ensure-Directory $fontsTargetPath
Ensure-Directory $mediaTargetPath

Write-Host "Processing SQL:"
Write-Host "  Source: $sqlSourcePath"
Write-Host "  Target: $sqlTargetPath"

$sql = Get-Content -LiteralPath $sqlSourcePath -Raw -Encoding UTF8

$sql = $sql.Replace("F:\\fonts\\", "")
$sql = $sql.Replace("F:/fonts/", "")
$sql = $sql.Replace("F:\\shanbei_videos\\deduped_media\\", "")
$sql = $sql.Replace("F:/shanbei_videos/deduped_media/", "")
$sql = $sql.Replace("F:\\shanbei_videos\\", "")
$sql = $sql.Replace("F:/shanbei_videos/", "")

# Navicat exports Windows paths with escaped backslashes. After removing
# fixed roots, normalize remaining SQL path literals to portable slash paths.
$sql = $sql.Replace("\\", "/")

Set-Content -LiteralPath $sqlTargetPath -Value $sql -Encoding UTF8 -NoNewline

Write-Host "Copying calligraphy assets:"
Write-Host "  Source: $FontsSource"
Write-Host "  Target: $fontsTargetPath"
Copy-DirectoryContents -Source $FontsSource -Target $fontsTargetPath

Write-Host "Copying media assets:"
Write-Host "  Source: $MediaSource"
Write-Host "  Target: $mediaTargetPath"
Copy-DirectoryContents -Source $MediaSource -Target $mediaTargetPath

Write-Host "Done."
Write-Host "SQL file now uses relative paths in: $sqlTargetPath"
Write-Host "Calligraphy assets copied to: $fontsTargetPath"
Write-Host "Media assets copied to: $mediaTargetPath"

