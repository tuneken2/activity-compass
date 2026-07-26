$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectRoot "launcher.pyw"
$BundledPythonw = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"

if (Test-Path -LiteralPath $BundledPythonw) {
    $PythonCommand = $BundledPythonw
    $PythonArgs = @()
}
elseif (Get-Command pyw -ErrorAction SilentlyContinue) {
    $PythonCommand = "pyw"
    $PythonArgs = @("-3")
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
    $PythonArgs = @("-3")
}
elseif (Get-Command pythonw -ErrorAction SilentlyContinue) {
    $PythonCommand = "pythonw"
    $PythonArgs = @()
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
    $PythonArgs = @()
}
else {
    throw "Python 3.10 or newer is required."
}

$Arguments = @($PythonArgs) + @("`"$Launcher`"")
Start-Process `
    -FilePath $PythonCommand `
    -ArgumentList $Arguments `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

Write-Host "Activity Compass started in the background."
