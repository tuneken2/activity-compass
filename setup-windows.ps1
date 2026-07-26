$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectRoot "Activity Compass.vbs"
$Icon = Join-Path $ProjectRoot "assets\activity-compass.ico"
$WScriptExe = Join-Path ([Environment]::GetFolderPath("System")) "wscript.exe"
$Shell = New-Object -ComObject WScript.Shell

$ShortcutTargets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Activity Compass.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "Activity Compass.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Startup")) "Activity Compass.lnk")
)

foreach ($ShortcutPath in $ShortcutTargets) {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $WScriptExe
    $Shortcut.Arguments = "`"$Launcher`""
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "Activity Compass"
    $Shortcut.IconLocation = "$Icon,0"
    $Shortcut.Save()
}

Write-Host "Created Activity Compass shortcuts on the Desktop, Start menu, and Startup folder."
