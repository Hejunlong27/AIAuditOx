param(
  [string]$NodeHome = $(if ($env:DSH_NODE_HOME) { $env:DSH_NODE_HOME } else { 'D:\编程\AIAuditOx\.tmp\node-v26.13.1-win-x64' }),
  [int]$Port = 3080,
  [int]$AuditOxPort = 8765,
  [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $repo
$runtimeRoot = Join-Path $workspace 'agent-runtime'
$python = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $NodeHome) {
  $env:PATH = "$NodeHome;$env:PATH"
}
$env:DSH_HOME = Join-Path $repo '.tmp\dsh-home-auditox'

$runtimeProcess = $null
$listener = Get-NetTCPConnection -LocalPort $AuditOxPort -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
  if (-not (Test-Path -LiteralPath $python)) {
    throw "AuditOx Python Runtime not found: $python"
  }
  $tmp = Join-Path $repo '.tmp'
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $runtimeProcess = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'api.main', '--port', "$AuditOxPort") `
    -WorkingDirectory $runtimeRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $tmp 'auditox-runtime.out.log') `
    -RedirectStandardError (Join-Path $tmp 'auditox-runtime.err.log') `
    -PassThru
  Start-Sleep -Seconds 2
  Write-Host "Started AuditOx Runtime: http://127.0.0.1:$AuditOxPort"
} else {
  Write-Host "Using existing AuditOx Runtime on port $AuditOxPort"
}

try {
  $dshArgs = @('--yes', 'pnpm@11.28.5', 'dsh', '--profile', 'web', '--patch', './auditox/cordis.patch.yml', '--port', "$Port")
  if ($NoOpen) { $dshArgs += '--no-open' }
  Push-Location $repo
  try { & npx @dshArgs } finally { Pop-Location }
} finally {
  if ($runtimeProcess -and -not $runtimeProcess.HasExited) {
    Stop-Process -Id $runtimeProcess.Id -Force -ErrorAction SilentlyContinue
    Write-Host 'Stopped the AuditOx Runtime started by this script.'
  }
}
