$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourcePlugin = Join-Path $ProjectRoot "plugins\activity-sync"
$PluginRoot = Join-Path $env:USERPROFILE "plugins"
$TargetPlugin = Join-Path $PluginRoot "activity-sync"
$MarketplacePath = Join-Path $env:USERPROFILE ".agents\plugins\marketplace.json"

New-Item -ItemType Directory -Force -Path $PluginRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $MarketplacePath) | Out-Null

if (Test-Path -LiteralPath $TargetPlugin) {
    throw "An activity-sync plugin already exists. It will not be overwritten automatically."
}

Copy-Item -LiteralPath $SourcePlugin -Destination $TargetPlugin -Recurse

if (Test-Path -LiteralPath $MarketplacePath) {
    $Marketplace = Get-Content -Raw -LiteralPath $MarketplacePath | ConvertFrom-Json
}
else {
    $Marketplace = [pscustomobject]@{
        name = "personal"
        interface = [pscustomobject]@{ displayName = "Personal" }
        plugins = @()
    }
}

$Exists = @($Marketplace.plugins | Where-Object { $_.name -eq "activity-sync" }).Count -gt 0
if (-not $Exists) {
    $Entry = [pscustomobject]@{
        name = "activity-sync"
        source = [pscustomobject]@{
            source = "local"
            path = "./plugins/activity-sync"
        }
        policy = [pscustomobject]@{
            installation = "AVAILABLE"
            authentication = "ON_INSTALL"
        }
        category = "Productivity"
    }
    $Marketplace.plugins = @($Marketplace.plugins) + $Entry
    $Marketplace | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $MarketplacePath -Encoding UTF8
}

Write-Host "Installed activity-sync in the personal marketplace. Restart Codex and use it in a new task."

