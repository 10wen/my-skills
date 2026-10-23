param(
    [Parameter(Mandatory=$true)][string]$TextFile,
    [Parameter(Mandatory=$true)][string]$OutputFile,
    [string]$Speaker,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
function Get-TextHash([string]$Value) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Get-AudioHash([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $inputStream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant() }
    finally { $inputStream.Dispose(); $sha.Dispose() }
}
try {
    $prefs = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../preferences.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $Speaker) { $Speaker = $prefs.speaker }
    if ([string]::IsNullOrWhiteSpace($Speaker)) { throw 'Missing speaker preference.' }
    $text = (Get-Content -LiteralPath $TextFile -Raw -Encoding UTF8).Trim()
    if (-not $text) { throw 'Narration is empty.' }
    if ($text.Length -gt 1500) { throw 'Local safety limit: 1500 characters. Split at natural paragraph boundaries.' }
    $OutputFile = [IO.Path]::GetFullPath($OutputFile)
    if ([IO.Path]::GetExtension($OutputFile) -ne '.mp3') { throw 'Output must have an .mp3 extension.' }
    $textHash = Get-TextHash $text
    $resource = 'seed-tts-2.0'
    $requestHash = Get-TextHash ($textHash + '|' + $Speaker + '|' + $resource + '|mp3|24000')
    $metaPath = $OutputFile + '.json'
    if (Test-Path -LiteralPath $OutputFile) {
        if (-not (Test-Path -LiteralPath $metaPath)) { throw 'Output exists without cache metadata; choose a new output path.' }
        $old = Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $audioHash = Get-AudioHash $OutputFile
        if ($old.complete -ne $true -or $old.request_sha256 -ne $requestHash -or $old.audio_sha256 -ne $audioHash) {
            throw 'Existing audio does not match the input, voice or checksum. Refusing to overwrite.'
        }
        Write-Output "Cache verified; no API request: $OutputFile"
        exit 0
    }
    if (Test-Path -LiteralPath $metaPath) { throw 'Orphan metadata exists; choose a new output path.' }
    if ($DryRun) {
        @{dry_run=$true;network_request=$false;characters=$text.Length;speaker=$Speaker;resource=$resource;text_sha256=$textHash;output=$OutputFile} | ConvertTo-Json
        exit 0
    }
    $plain = $env:VOLCENGINE_TTS_API_KEY
    if (-not $plain) {
        $secretPath = Join-Path $env:LOCALAPPDATA 'CodexVoice/volcengine-key.dpapi'
        if (-not (Test-Path -LiteralPath $secretPath)) { throw 'No authorized local TTS credential found.' }
        $secure = Get-Content -LiteralPath $secretPath | ConvertTo-SecureString
        $plain = [Net.NetworkCredential]::new('', $secure).Password
    }
    $requestId = [guid]::NewGuid().ToString()
    $headers = @{'X-Api-Key'=$plain;'X-Api-Request-Id'=$requestId;'X-Api-Resource-Id'=$resource}
    $payload = @{user=@{uid='local-video'};req_params=@{text=$text;speaker=$Speaker;audio_params=@{format='mp3';sample_rate=24000}}}
    $body = [Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json -Depth 8 -Compress))
    Write-Output "One paid TTS request, speaker=$Speaker, characters=$($text.Length), request_id=$requestId. No automatic retries."
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'https://openspeech.bytedance.com/api/v3/tts/unidirectional' -Method Post -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 180 -MaximumRedirection 0
    } catch {
        # Never echo raw transport errors: some clients embed headers or request bodies.
        throw "TTS transport failed or timed out. Billing may already have occurred. Check service logs using request_id=$requestId before retrying."
    }
    $content = $response.Content
    if ($content -is [byte[]]) { $content = [Text.Encoding]::UTF8.GetString($content) }
    $stream = New-Object IO.MemoryStream
    $complete = $false
    foreach ($line in ($content -split "`n")) {
        if (-not $line.Trim()) { continue }
        if ($complete) { throw 'Unexpected data after completion; refusing ambiguous response.' }
        try { $entry = $line | ConvertFrom-Json } catch { throw 'Malformed TTS response; not saving partial audio.' }
        if ($null -eq $entry.code -or $entry.code -notin @(0,20000000)) {
            # Service message is untrusted and may contain submitted text. Return only numeric codes.
            $safeCode = if ([string]$entry.code -match '^\d+$') { [string]$entry.code } else { 'unknown' }
            throw "TTS service rejected the request (code=$safeCode); no retry performed."
        }
        if ($entry.data) {
            try { $part = [Convert]::FromBase64String($entry.data) } catch { throw 'Invalid audio encoding in response.' }
            $stream.Write($part,0,$part.Length)
        }
        if ($entry.code -eq 20000000) { $complete = $true }
    }
    if (-not $complete -or $stream.Length -eq 0) { throw 'Incomplete or empty audio response; not saving and not retrying.' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $OutputFile) -Force | Out-Null
    # CreateNew also protects against a second process producing the same output while this request runs.
    $file = [IO.File]::Open($OutputFile,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try { $stream.Position=0; $stream.CopyTo($file) } finally { $file.Dispose() }
    $metadata = @{complete=$true;created_at=(Get-Date -Format o);request_id=$requestId;resource=$resource;speaker=$Speaker;sample_rate=24000;format='mp3';characters=$text.Length;text_sha256=$textHash;request_sha256=$requestHash;audio_sha256=(Get-AudioHash $OutputFile);needs_listening_review=$true}
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $metaPath -Encoding UTF8
    Write-Output "Saved: $OutputFile. Decode and listen for pronunciation, missing words and the ending before aligning captions."
} catch {
    $message = $_.Exception.Message
    if ($plain) { $message = $message.Replace($plain,'[REDACTED]') }
    Write-Output ('TTS failed: ' + $message)
    exit 1
} finally {
    $plain=$null; $headers=$null; $content=$null; $response=$null
    if ($stream) { $stream.Dispose() }
}
