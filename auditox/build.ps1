param(
  [string]$NodeHome = $(if ($env:DSH_NODE_HOME) { $env:DSH_NODE_HOME } else { 'D:\编程\AIAuditOx\.tmp\node-v26.13.1-win-x64' })
)

$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $NodeHome) {
  $env:PATH = "$NodeHome;$env:PATH"
}
$env:DSH_CLIENT_TITLE = '审小牛 AuditOx Harness'
Write-Host "Node: $(& node --version)"
Write-Host "pnpm: $(& npx --yes pnpm@11.28.5 --version)"
& npx --yes pnpm@11.28.5 install --frozen-lockfile
& npx --yes pnpm@11.28.5 run build