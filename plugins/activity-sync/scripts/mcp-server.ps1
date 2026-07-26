$ErrorActionPreference = "Stop"
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$ApiBase = if ($env:ACTIVITY_COMPASS_URL) {
    $env:ACTIVITY_COMPASS_URL.TrimEnd("/")
}
else {
    "http://127.0.0.1:8765"
}

function Write-JsonRpc {
    param([object]$Value)
    $json = $Value | ConvertTo-Json -Depth 30 -Compress
    [Console]::Out.WriteLine($json)
    [Console]::Out.Flush()
}

function New-Result {
    param([object]$Id, [object]$Result)
    return [ordered]@{
        jsonrpc = "2.0"
        id = $Id
        result = $Result
    }
}

function Assert-TextEncoding {
    param([object]$Value)

    if ($Value -is [string]) {
        if ($Value.Contains([char]0xFFFD) -or $Value -match '\?{3,}') {
            throw "Text appears corrupted. Send JSON as UTF-8; Windows PowerShell 5.1 native pipelines default to ASCII."
        }
        return
    }
    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($nested in $Value.Values) {
            Assert-TextEncoding $nested
        }
        return
    }
    if ($Value -is [pscustomobject]) {
        foreach ($property in $Value.PSObject.Properties) {
            Assert-TextEncoding $property.Value
        }
        return
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        foreach ($nested in $Value) {
            Assert-TextEncoding $nested
        }
    }
}

while ($null -ne ($line = [Console]::In.ReadLine())) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }
    try {
        $request = $line | ConvertFrom-Json
        $method = [string]$request.method

        if ($method -eq "initialize") {
            Write-JsonRpc (New-Result $request.id ([ordered]@{
                protocolVersion = "2025-03-26"
                capabilities = [ordered]@{ tools = [ordered]@{} }
                serverInfo = [ordered]@{
                    name = "activity-compass"
                    version = "0.1.0"
                }
            }))
            continue
        }

        if ($method -eq "notifications/initialized") {
            continue
        }

        if ($method -eq "ping") {
            Write-JsonRpc (New-Result $request.id ([ordered]@{}))
            continue
        }

        if ($method -eq "tools/list") {
            $tools = @(
                [ordered]@{
                    name = "sync_activity"
                    description = "Send created or changed activities from the current conversation to Activity Compass."
                    inputSchema = [ordered]@{
                        type = "object"
                        properties = [ordered]@{
                            source = [ordered]@{ type = "string"; default = "chatgpt" }
                            source_summary = [ordered]@{ type = "string" }
                            idempotency_key = [ordered]@{ type = "string" }
                            events = [ordered]@{
                                type = "array"
                                items = [ordered]@{
                                    type = "object"
                                    properties = [ordered]@{
                                        action = [ordered]@{
                                            type = "string"
                                            enum = @("create", "update", "complete", "cancel", "defer", "note")
                                        }
                                        entity_type = [ordered]@{
                                            type = "string"
                                            enum = @("task", "schedule", "idea", "waiting", "decision", "project")
                                        }
                                        title = [ordered]@{ type = "string" }
                                        details = [ordered]@{ type = "string" }
                                        status = [ordered]@{
                                            type = "string"
                                            enum = @("inbox", "today", "next", "in_progress", "waiting", "someday", "done", "cancelled")
                                        }
                                        due_at = [ordered]@{ type = "string" }
                                        scheduled_at = [ordered]@{ type = "string" }
                                        priority = [ordered]@{ type = "integer"; minimum = 0; maximum = 3 }
                                        project_id = [ordered]@{ type = "string" }
                                        project_title = [ordered]@{ type = "string" }
                                        parent_project_id = [ordered]@{ type = "string" }
                                        category = [ordered]@{ type = "string"; maxLength = 50 }
                                        category_color = [ordered]@{
                                            type = "string"
                                            pattern = "^#[0-9A-Fa-f]{6}$"
                                        }
                                        effort = [ordered]@{ type = "integer"; minimum = 1; maximum = 5 }
                                        target_id = [ordered]@{ type = "string" }
                                        confidence = [ordered]@{ type = "number"; minimum = 0; maximum = 1 }
                                        source_excerpt = [ordered]@{ type = "string" }
                                    }
                                    required = @("action", "entity_type", "title", "confidence")
                                }
                            }
                        }
                        required = @("events")
                    }
                },
                [ordered]@{
                    name = "search_activities"
                    description = "Search existing Activity Compass items before deciding whether an event is new or an update."
                    inputSchema = [ordered]@{
                        type = "object"
                        properties = [ordered]@{
                            query = [ordered]@{ type = "string" }
                        }
                        required = @("query")
                    }
                },
                [ordered]@{
                    name = "get_sync_status"
                    description = "Check whether Activity Compass is running and return current dashboard counts."
                    inputSchema = [ordered]@{
                        type = "object"
                        properties = [ordered]@{}
                    }
                }
            )
            Write-JsonRpc (New-Result $request.id ([ordered]@{ tools = $tools }))
            continue
        }

        if ($method -eq "tools/call") {
            $toolName = [string]$request.params.name
            if ($toolName -eq "sync_activity") {
                Assert-TextEncoding $request.params.arguments
                $payload = $request.params.arguments | ConvertTo-Json -Depth 30 -Compress
                $response = Invoke-RestMethod `
                    -Uri "$ApiBase/v1/sync" `
                    -Method Post `
                    -ContentType "application/json; charset=utf-8" `
                    -Body ([Text.Encoding]::UTF8.GetBytes($payload)) `
                    -TimeoutSec 10
            }
            elseif ($toolName -eq "search_activities") {
                $query = [uri]::EscapeDataString([string]$request.params.arguments.query)
                $response = Invoke-RestMethod `
                    -Uri "$ApiBase/v1/items?q=$query" `
                    -Method Get `
                    -TimeoutSec 10
            }
            elseif ($toolName -eq "get_sync_status") {
                $health = Invoke-RestMethod -Uri "$ApiBase/health" -Method Get -TimeoutSec 10
                $dashboard = Invoke-RestMethod -Uri "$ApiBase/v1/items?view=today" -Method Get -TimeoutSec 10
                $response = [ordered]@{
                    status = $health.status
                    counts = $dashboard.counts
                }
            }
            else {
                throw "Unknown tool: $toolName"
            }
            $responseText = $response | ConvertTo-Json -Depth 20 -Compress
            Write-JsonRpc (New-Result $request.id ([ordered]@{
                content = @([ordered]@{ type = "text"; text = $responseText })
                structuredContent = $response
                isError = $false
            }))
            continue
        }

        if ($null -ne $request.id) {
            Write-JsonRpc ([ordered]@{
                jsonrpc = "2.0"
                id = $request.id
                error = [ordered]@{ code = -32601; message = "Method not found" }
            })
        }
    }
    catch {
        $message = $_.Exception.Message
        if ($null -ne $request -and $null -ne $request.id) {
            Write-JsonRpc ([ordered]@{
                jsonrpc = "2.0"
                id = $request.id
                result = [ordered]@{
                    content = @([ordered]@{
                        type = "text"
                        text = "Cannot connect to Activity Compass. Start the app and try again. Details: $message"
                    })
                    isError = $true
                }
            })
        }
    }
}
