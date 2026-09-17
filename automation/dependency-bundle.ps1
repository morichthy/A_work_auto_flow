# ASCII only: runs on stock Windows PowerShell 5.1 before Python is available.
# Verify the ZIP and every payload before executing its interpreter. The caller
# trusts the publisher; hashes detect corruption, they are not a digital signature.
param([string]$Archive, [string]$SourceRoot, [switch]$Preview)
$ErrorActionPreference = 'Stop'
function Get-Sha256([string]$Path) {
    # .NET works even when PowerShell module autoloading is disabled by the host.
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLower() }
    finally { $hasher.Dispose(); $stream.Dispose() }
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { throw 'Only Windows x64 is supported.' }
$zipPath = (Resolve-Path -LiteralPath $Archive).Path
Write-Host 'Checking dependency ZIP integrity...'
$checksumPath = $zipPath + '.sha256'
if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) { throw 'Download the matching .zip.sha256 file beside the dependency ZIP.' }
$expectedZip = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0]
if ($expectedZip -notmatch '^[a-fA-F0-9]{64}$' -or (Get-Sha256 $zipPath) -ne $expectedZip) { throw 'Dependency ZIP SHA-256 mismatch.' }
function Assert-PayloadName([string]$Name) {
    if ($Name -match '[\\:\x00]' -or $Name -match '(^|/)(\.|\.\.|)(/|$)' -or $Name -match '[ .](/|$)' -or $Name -match '(?i)(^|/)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.[^/]*)?(/|$)') { throw "Invalid ZIP path: $Name" }
    if ($Name -cnotmatch '^(services/qdrant/runtime/.+|services/qdrant/models/multilingual-minilm/.+|services/qdrant/model-manifest.json|services/qdrant/requirements.lock.txt|services/reranker/model-manifest.json|services/reranker/model/(model_quint8_avx2\.onnx|tokenizer\.json|config\.json|tokenizer_config\.json|special_tokens_map\.json|README\.md)|THIRD_PARTY.md)$') { throw "Unexpected payload: $Name" }
}
function Assert-NoRedirect([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        # Use .NET attributes rather than thousands of PowerShell provider calls.
        if ([IO.File]::Exists($current) -or [IO.Directory]::Exists($current)) {
            if ([IO.File]::GetAttributes($current) -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point is not allowed: $current" }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}
$package = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $manifestEntry = $package.GetEntry('dependency-manifest.json')
    if ($null -eq $manifestEntry -or $manifestEntry.Length -gt 16777216) { throw 'Dependency manifest missing or too large.' }
    $reader = [IO.StreamReader]::new($manifestEntry.Open())
    try { $manifestText = $reader.ReadToEnd() } finally { $reader.Dispose() }
    $manifest = $manifestText | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.platform -ne 'windows-x64' -or $manifest.python -ne '3.12.10') { throw 'Incompatible dependency bundle.' }
    $locks = @{}
    foreach ($line in Get-Content -LiteralPath (Join-Path $SourceRoot 'services\qdrant\requirements.lock.txt')) {
        if (-not $line.Trim() -or $line.Trim().StartsWith('#')) { continue }
        if ($line.Trim() -notmatch '^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)$') { throw 'Framework requires an exact dependency lock.' }
        $locks[($Matches[1] -replace '[-_.]+', '-').ToLower()] = $Matches[2]
    }
    $bundled = @($manifest.packages.PSObject.Properties)
    if ($bundled.Count -ne $locks.Count) { throw 'Bundle does not match the source dependency lock.' }
    foreach ($property in $bundled) {
        if ($locks[$property.Name] -ne $property.Value) { throw "Dependency version mismatch: $($property.Name)" }
    }
    $expected = @{}
    foreach ($property in $manifest.files.PSObject.Properties) {
        Assert-PayloadName $property.Name
        if ($expected.ContainsKey($property.Name) -or $property.Value -notmatch '^[a-f0-9]{64}$') { throw 'Duplicate file or invalid SHA-256.' }
        $expected[$property.Name] = $property.Value
    }
    if (-not $expected.ContainsKey('services/qdrant/runtime/python.exe')) { throw 'Bundle has no Python interpreter.' }
    Write-Host "Checking $($expected.Count) dependency files; first extraction can take a few minutes..."
    $seen = @{}
    $total = [long]0
    foreach ($entry in $package.Entries) {
        $name = $entry.FullName
        if ($seen.ContainsKey($name)) { throw "Duplicate ZIP entry: $name" }
        $seen[$name] = $true
        if ($name -ne 'dependency-manifest.json') { Assert-PayloadName $name; if (-not $expected.ContainsKey($name)) { throw "Unlisted ZIP entry: $name" } }
        # A release of this schema is a ~600 MB runtime/model bundle, never a data archive.
        $total += $entry.Length
        if ($total -gt 6GB) { throw 'Dependency bundle exceeds 6 GiB unpacked limit.' }
    }
    if ($seen.Count -ne $expected.Count + 1) { throw 'ZIP is missing manifest payloads.' }
    # CPython can read long paths, but some third-party DLL loaders still cannot.
    # A content-addressed user temp cache avoids adding depth to an extracted repo.
    $stage = Join-Path ([IO.Path]::GetTempPath()) ('rdwork-deps\' + $expectedZip.Substring(0, 16).ToLower())
    Assert-NoRedirect $stage
    if (-not $Preview) { New-Item -ItemType Directory -Force -Path $stage | Out-Null }
    foreach ($entry in $package.Entries) {
        $name = $entry.FullName
        $stream = $entry.Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLower() }
        finally { $hasher.Dispose(); $stream.Dispose() }
        if ($name -ne 'dependency-manifest.json' -and $actual -ne $expected[$name]) { throw "Payload SHA-256 mismatch: $name" }
        if (-not $Preview) {
            $destination = Join-Path $stage $name.Replace('/', '\')
            Assert-NoRedirect $destination
            if (Test-Path -LiteralPath $destination -PathType Leaf) {
                if ((Get-Sha256 $destination) -ne $actual) { throw "Cached dependency changed: $name" }
            } else {
                New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $false)
                if ((Get-Sha256 $destination) -ne $actual) { throw "Extracted payload mismatch: $name" }
            }
        }
    }
    if ($Preview) { Write-Host "Verified dependency ZIP: $($expected.Count) files; no files written."; return }
    # Reject injected extras before starting Python (not only later in Python).
    foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -Force -File) {
        Assert-NoRedirect $file.FullName
        $relative = $file.FullName.Substring($stage.Length + 1).Replace('\', '/')
        if ($relative -ne 'dependency-manifest.json' -and -not $expected.ContainsKey($relative)) { throw "Unlisted cached file: $relative" }
    }
    Write-Host 'Dependency payload verified. Starting the local installer...'
    return $stage
} finally { $package.Dispose() }
