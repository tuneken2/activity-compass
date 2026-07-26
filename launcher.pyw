"""Windowless Windows launcher for Activity Compass.

This file is started by ``Activity Compass.vbs``.  It keeps all startup and
shutdown work out of PowerShell and does not create a console window.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
API_URL = "http://127.0.0.1:8765/health"
CREATE_NO_WINDOW = 0x08000000


def api_is_ready() -> bool:
    try:
        with urllib.request.urlopen(API_URL, timeout=0.5) as response:
            return response.status == 200 and b'"status": "ok"' in response.read()
    except Exception:
        return False


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(
        None,
        message,
        "Activity Compass",
        0x10,  # MB_ICONERROR
    )


def main() -> None:
    api_process: subprocess.Popen[bytes] | None = None
    try:
        if not api_is_ready():
            environment = os.environ.copy()
            app_path = str(PROJECT_ROOT / "app")
            environment["PYTHONPATH"] = (
                app_path
                if not environment.get("PYTHONPATH")
                else app_path + os.pathsep + environment["PYTHONPATH"]
            )
            api_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "activity_compass.main",
                    "--no-ui",
                    "--port",
                    "8765",
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for _ in range(50):
                if api_is_ready():
                    break
                if api_process.poll() is not None:
                    raise RuntimeError("バックグラウンド処理を開始できませんでした。")
                time.sleep(0.2)
            else:
                raise RuntimeError("起動がタイムアウトしました。")

        subprocess.run(
            ["mshta.exe", str(PROJECT_ROOT / "desktop.hta")],
            cwd=PROJECT_ROOT,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        show_error(f"Activity Compass を起動できませんでした。\n\n{exc}")
    finally:
        if api_process is not None and api_process.poll() is None:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()


if __name__ == "__main__":
    main()
