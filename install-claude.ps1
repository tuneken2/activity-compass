[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeCommand = Get-Command "claude" -ErrorAction SilentlyContinue

if ($null -eq $ClaudeCommand) {
    throw "Claude Code was not found. Install and authenticate Claude Code first."
}

$ClaudeRoot = Join-Path $env:USERPROFILE ".claude"
$SkillTarget = Join-Path $ClaudeRoot "skills\sync-activity"
$IntegrationTarget = Join-Path $ClaudeRoot "integrations\activity-compass"
$SkillSource = Join-Path $ProjectRoot "plugins\activity-sync\skills\sync-activity\SKILL.md"
$ServerSource = Join-Path $ProjectRoot "plugins\activity-sync\scripts\mcp-server.ps1"
$ServerTarget = Join-Path $IntegrationTarget "mcp-server.ps1"

if ((Test-Path -LiteralPath $SkillTarget) -or (Test-Path -LiteralPath $IntegrationTarget)) {
    throw "An Activity Compass Claude integration already exists. Review it before updating manually."
}

& $ClaudeCommand.Source mcp get activity-compass *> $null
if ($LASTEXITCODE -eq 0) {
    throw "The activity-compass MCP is already registered. Review the existing configuration first."
}

New-Item -ItemType Directory -Force -Path $SkillTarget | Out-Null
New-Item -ItemType Directory -Force -Path $IntegrationTarget | Out-Null
Copy-Item -LiteralPath $SkillSource -Destination (Join-Path $SkillTarget "SKILL.md")
Copy-Item -LiteralPath $ServerSource -Destination $ServerTarget

& $ClaudeCommand.Source mcp add `
    --transport stdio `
    --scope user `
    activity-compass `
    -- powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ServerTarget

if ($LASTEXITCODE -ne 0) {
    throw "MCP registration failed. Copied files remain in $IntegrationTarget and $SkillTarget."
}

Write-Host "Installed the Claude Code skill and user-scoped activity-compass MCP."
Write-Host "Start Activity Compass, restart Claude Code, and verify the connection with /mcp."
