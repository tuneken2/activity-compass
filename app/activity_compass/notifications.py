from __future__ import annotations

import os
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "activity-compass.ico"

# Text is passed through environment variables (never interpolated into the
# script itself) so a task title containing quotes, `$`, or backticks can
# never be interpreted as PowerShell syntax.
_NOTIFY_SCRIPT = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notify = New-Object System.Windows.Forms.NotifyIcon
$iconPath = $env:ACTIVITY_COMPASS_NOTIFY_ICON
if ($iconPath -and (Test-Path $iconPath)) {
    $notify.Icon = New-Object System.Drawing.Icon($iconPath)
} else {
    $notify.Icon = [System.Drawing.SystemIcons]::Information
}
$notify.Visible = $true
$notify.BalloonTipTitle = $env:ACTIVITY_COMPASS_NOTIFY_TITLE
$notify.BalloonTipText = $env:ACTIVITY_COMPASS_NOTIFY_MESSAGE
$notify.ShowBalloonTip(10000)
Start-Sleep -Seconds 10
$notify.Dispose()
"""


def show_windows_notification(title: str, message: str) -> None:
    """Show a native Windows notification balloon without blocking the caller."""
    environment = os.environ.copy()
    environment["ACTIVITY_COMPASS_NOTIFY_TITLE"] = title
    environment["ACTIVITY_COMPASS_NOTIFY_MESSAGE"] = message
    environment["ACTIVITY_COMPASS_NOTIFY_ICON"] = str(ICON_PATH)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            _NOTIFY_SCRIPT,
        ],
        creationflags=CREATE_NO_WINDOW,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
