$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$ApiUrl = "http://127.0.0.1:8765"
$StartedProcess = $null

if (Test-Path -LiteralPath $BundledPython) {
    $PythonCommand = $BundledPython
    $PythonArgs = @()
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
    $PythonArgs = @("-3")
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
    $PythonArgs = @()
}
else {
    throw "Python 3.10 or newer is required."
}

$ApiAlreadyRunning = $false
try {
    $Health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 1
    $ApiAlreadyRunning = $Health.status -eq "ok"
}
catch {
    $ApiAlreadyRunning = $false
}

if (-not $ApiAlreadyRunning) {
    $env:PYTHONPATH = Join-Path $ProjectRoot "app"
    $Arguments = @($PythonArgs) + @(
        "-m", "activity_compass.main", "--no-ui", "--port", "8765"
    )
    $StartedProcess = Start-Process `
        -FilePath $PythonCommand `
        -ArgumentList $Arguments `
        -WindowStyle Hidden `
        -PassThru

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 40; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 1
            if ($Health.status -eq "ok") {
                $Ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 200
        }
    }
    if (-not $Ready) {
        Stop-Process -Id $StartedProcess.Id -Force -ErrorAction SilentlyContinue
        throw "Activity Compass API could not start."
    }
}

try {
    Start-Process -FilePath "mshta.exe" -ArgumentList "`"$(Join-Path $ProjectRoot 'desktop.hta')`"" -Wait
}
finally {
    if ($null -ne $StartedProcess) {
        Stop-Process -Id $StartedProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
