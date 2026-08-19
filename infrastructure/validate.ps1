[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$required = @(
    'cloud-run-api.yaml',
    'cloud-run-worker.yaml',
    'cloudbuild-api.yaml',
    'cloudbuild-worker.yaml',
    'env.production.example',
    'deploy.ps1',
    'validate.ps1'
)

foreach ($file in $required) {
    $path = Join-Path $PSScriptRoot $file
    if (-not (Test-Path $path)) { throw "Missing infrastructure file: $file" }
    if ((Get-Item $path).Length -eq 0) { throw "Infrastructure file is empty: $file" }
}

foreach ($yaml in @('cloud-run-api.yaml', 'cloud-run-worker.yaml')) {
    $content = Get-Content (Join-Path $PSScriptRoot $yaml) -Raw
    if ($content -notmatch '(?m)^apiVersion:\s+serving\.knative\.dev/v1' -or $content -notmatch '(?m)^kind:\s+Service') {
        throw "Invalid Cloud Run manifest header: $yaml"
    }
    if ($content -match 'GEMINI_API_KEY\s+value:') { throw "Secret value found in $yaml" }
}

if ((Get-Content (Join-Path $root 'frontend/src/App.tsx') -Raw) -notmatch 'VITE_API_URL') {
    throw 'Frontend API URL is not environment-configured.'
}

Write-Output 'Deployment configuration validation passed.'