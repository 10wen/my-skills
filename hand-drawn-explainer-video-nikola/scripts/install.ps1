[CmdletBinding()]
param(
    [string]$Destination,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $codexBase = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $Destination = Join-Path $codexBase 'skills/hand-drawn-explainer-video-nikola'
}
$target = [System.IO.Path]::GetFullPath($Destination)

if (Test-Path -LiteralPath $target) {
    if (-not $Force) { throw "Destination already exists: $target. Use -Force only after backing it up." }
    throw "For safety this installer never deletes an existing Skill. Rename or remove it manually, then run again."
}

New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Recurse
Write-Host "Installed to $target"
Write-Host "Next: python `"$target/scripts/setup_check.py`""
