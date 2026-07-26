"""Windowless Windows launcher and system-tray host for Activity Compass."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
API_URL = "http://127.0.0.1:8765/health"
CONTROL_URL = "http://127.0.0.1:8766"
CREATE_NO_WINDOW = 0x08000000
ERROR_ALREADY_EXISTS = 183
API_SCHEMA_VERSION = 2


def api_is_ready() -> bool:
    try:
        with urllib.request.urlopen(API_URL, timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return (
                response.status == 200
                and payload.get("status") == "ok"
                and payload.get("api_schema_version") == API_SCHEMA_VERSION
            )
    except Exception:
        return False


def send_control(action: str) -> None:
    try:
        request = urllib.request.Request(
            f"{CONTROL_URL}/{action}", data=b"{}", method="POST"
        )
        urllib.request.urlopen(request, timeout=0.5).close()
    except Exception:
        pass


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, "Activity Compass", 0x10)


def console_python_executable() -> str:
    executable = Path(sys.executable)
    if executable.stem.lower() == "pythonw":
        console_executable = executable.with_name("python.exe")
        if console_executable.exists():
            return str(console_executable)
    return str(executable)


class ControlHandler(BaseHTTPRequestHandler):
    actions: dict[str, threading.Event]

    def log_message(self, format: str, *args: object) -> None:
        return

    def _reply(self, status: int = 200) -> None:
        payload = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self._reply(204)

    def do_POST(self) -> None:
        event = self.actions.get(self.path.strip("/"))
        if event is None:
            self._reply(404)
            return
        event.set()
        self._reply()


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT_VALUE(ctypes.Union):
    _fields_ = [
        ("pwszVal", wintypes.LPWSTR),
        ("uhVal", ctypes.c_ulonglong),
        ("_padding", ctypes.c_byte * 16),
    ]


class PROPVARIANT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("vt", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
        ("wReserved2", wintypes.WORD),
        ("wReserved3", wintypes.WORD),
        ("value", PROPVARIANT_VALUE),
    ]


def make_guid(value: str) -> GUID:
    return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)


APP_USER_MODEL_ID = "Tuneken.ActivityCompass.Desktop"
APP_USER_MODEL_FMTID = make_guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3")
IID_IPROPERTY_STORE = make_guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
PKEY_APP_USER_MODEL_RELAUNCH_COMMAND = PROPERTYKEY(APP_USER_MODEL_FMTID, 2)
PKEY_APP_USER_MODEL_RELAUNCH_ICON_RESOURCE = PROPERTYKEY(APP_USER_MODEL_FMTID, 3)
PKEY_APP_USER_MODEL_ID = PROPERTYKEY(APP_USER_MODEL_FMTID, 5)


LRESULT = ctypes.c_ssize_t
HRESULT = ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class TrayApplication:
    WM_DESTROY = 0x0002
    WM_SETICON = 0x0080
    WM_TIMER = 0x0113
    WM_COMMAND = 0x0111
    WM_APP = 0x8000
    WM_TRAYICON = WM_APP + 1
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_CONTEXTMENU = 0x007B
    SW_HIDE = 0
    SW_RESTORE = 9
    ICON_SMALL = 0
    ICON_BIG = 1
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    LR_DEFAULTSIZE = 0x0040
    SM_CXICON = 11
    SM_CYICON = 12
    SM_CXSMICON = 49
    SM_CYSMICON = 50
    NIF_MESSAGE = 0x0001
    NIF_ICON = 0x0002
    NIF_TIP = 0x0004
    NIM_ADD = 0x0000
    NIM_DELETE = 0x0002
    TPM_RIGHTBUTTON = 0x0002
    TPM_RETURNCMD = 0x0100
    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    CMD_OPEN = 1001
    CMD_EXIT = 1002

    def __init__(
        self,
        exit_event: threading.Event,
        show_event: threading.Event,
        hide_event: threading.Event,
    ) -> None:
        self.exit_event = exit_event
        self.show_event = show_event
        self.hide_event = hide_event
        self.user32 = ctypes.windll.user32
        self.shell32 = ctypes.windll.shell32
        self.kernel32 = ctypes.windll.kernel32
        self.ole32 = ctypes.windll.ole32
        self.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self.user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        self.user32.RegisterClassExW.restype = wintypes.ATOM
        self.user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        self.user32.CreateWindowExW.restype = wintypes.HWND
        self.user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.DefWindowProcW.restype = LRESULT
        self.user32.CreatePopupMenu.restype = wintypes.HMENU
        self.user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user32.LoadImageW.restype = wintypes.HANDLE
        self.user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        self.user32.LoadIconW.restype = wintypes.HICON
        self.user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.SendMessageW.restype = LRESULT
        self.shell32.Shell_NotifyIconW.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(NOTIFYICONDATAW),
        ]
        self.shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        self.shell32.SHGetPropertyStoreForWindow.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.shell32.SHGetPropertyStoreForWindow.restype = HRESULT
        self.ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.ole32.CoInitializeEx.restype = HRESULT
        self.ole32.CoUninitialize.argtypes = []
        self.ole32.CoUninitialize.restype = None
        self._com_initialized = self.ole32.CoInitializeEx(None, 0x2) in (0, 1)
        self.process: subprocess.Popen[bytes] | None = None
        self.app_window: int | None = None
        self.has_launched = False
        self.hwnd: int | None = None
        self.large_icon: int | None = None
        self.small_icon: int | None = None
        self._owned_icons: list[int] = []
        self._iconized_window: int | None = None
        self._taskbar_window: int | None = None
        self.notify_data: NOTIFYICONDATAW | None = None
        self.tray_added = False
        self._last_tray_retry = 0.0
        self._wndproc = WNDPROC(self._window_proc)
        self._enumproc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )(self._enum_window)

    def _launch_ui(self, hidden: bool) -> None:
        startupinfo = None
        if hidden:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = self.SW_HIDE
        self.process = subprocess.Popen(
            ["mshta.exe", str(PROJECT_ROOT / "desktop.hta")],
            cwd=PROJECT_ROOT,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=startupinfo,
        )
        self.app_window = None
        self._iconized_window = None
        self._taskbar_window = None
        self.has_launched = True

    def _enum_window(self, hwnd: int, _: int) -> bool:
        if self.process is None:
            return True
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == self.process.pid:
            self.app_window = hwnd
            return False
        return True

    def _find_app_window(self) -> int | None:
        self.app_window = None
        self.user32.EnumWindows(self._enumproc, 0)
        if self.app_window:
            self._apply_window_icon(self.app_window)
            self._apply_taskbar_properties(self.app_window)
        return self.app_window

    def _apply_window_icon(self, hwnd: int) -> None:
        if hwnd == self._iconized_window:
            return
        if self.large_icon:
            self.user32.SendMessageW(
                hwnd, self.WM_SETICON, self.ICON_BIG, self.large_icon
            )
        if self.small_icon:
            self.user32.SendMessageW(
                hwnd, self.WM_SETICON, self.ICON_SMALL, self.small_icon
            )
        self._iconized_window = hwnd

    def _apply_taskbar_properties(self, hwnd: int) -> None:
        if hwnd == self._taskbar_window:
            return
        store = ctypes.c_void_p()
        result = self.shell32.SHGetPropertyStoreForWindow(
            hwnd, ctypes.byref(IID_IPROPERTY_STORE), ctypes.byref(store)
        )
        if result < 0 or not store.value:
            return

        vtable = ctypes.cast(
            store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
        set_value = ctypes.WINFUNCTYPE(
            HRESULT,
            ctypes.c_void_p,
            ctypes.POINTER(PROPERTYKEY),
            ctypes.POINTER(PROPVARIANT),
        )(vtable[6])
        commit = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p)(vtable[7])

        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        relaunch_command = (
            f'"{windows_dir / "System32" / "wscript.exe"}" '
            f'"{PROJECT_ROOT / "Activity Compass.vbs"}"'
        )
        icon_resource = (
            f"{PROJECT_ROOT / 'assets' / 'activity-compass.ico'},0"
        )
        properties = (
            (PKEY_APP_USER_MODEL_RELAUNCH_COMMAND, relaunch_command),
            (PKEY_APP_USER_MODEL_RELAUNCH_ICON_RESOURCE, icon_resource),
            (PKEY_APP_USER_MODEL_ID, APP_USER_MODEL_ID),
        )

        succeeded = True
        try:
            for key, value in properties:
                buffer = ctypes.create_unicode_buffer(value)
                variant = PROPVARIANT()
                variant.vt = 31  # VT_LPWSTR
                variant.pwszVal = ctypes.cast(buffer, wintypes.LPWSTR)
                if set_value(store, ctypes.byref(key), ctypes.byref(variant)) < 0:
                    succeeded = False
                    break
            if succeeded and commit(store) >= 0:
                self._taskbar_window = hwnd
        finally:
            release(store)

    def show_window(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self._launch_ui(hidden=True)
            return
        hwnd = self._find_app_window()
        if hwnd:
            self.user32.ShowWindow(hwnd, self.SW_RESTORE)
            self.user32.SetForegroundWindow(hwnd)

    def hide_window(self) -> None:
        hwnd = self._find_app_window()
        if hwnd:
            self.user32.ShowWindow(hwnd, self.SW_HIDE)

    def _tick(self) -> None:
        if self.exit_event.is_set():
            if self.hwnd:
                self.user32.DestroyWindow(self.hwnd)
            return
        if (
            not self.tray_added
            and self.notify_data is not None
            and time.monotonic() - self._last_tray_retry >= 2
        ):
            self._last_tray_retry = time.monotonic()
            self.tray_added = bool(
                self.shell32.Shell_NotifyIconW(
                    self.NIM_ADD, ctypes.byref(self.notify_data)
                )
            )
        if self.show_event.is_set():
            self.show_event.clear()
            self.show_window()
        if self.hide_event.is_set():
            self.hide_event.clear()
            self.hide_window()
        if self.process is None:
            self._launch_ui(hidden=self.has_launched)
            return
        if self.process.poll() is not None:
            # Closing the title bar behaves as "hide to tray". Recreate the
            # HTA hidden so it is ready when opened from the tray.
            self.process = None
            self.app_window = None
            self._launch_ui(hidden=True)
            return
        hwnd = self._find_app_window()
        if hwnd and self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, self.SW_HIDE)

    def _show_menu(self) -> None:
        if not self.hwnd:
            return
        menu = self.user32.CreatePopupMenu()
        self.user32.AppendMenuW(menu, self.MF_STRING, self.CMD_OPEN, "開く")
        self.user32.AppendMenuW(menu, self.MF_SEPARATOR, 0, None)
        self.user32.AppendMenuW(menu, self.MF_STRING, self.CMD_EXIT, "終了")
        point = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        self.user32.SetForegroundWindow(self.hwnd)
        command = self.user32.TrackPopupMenu(
            menu,
            self.TPM_RIGHTBUTTON | self.TPM_RETURNCMD,
            point.x,
            point.y,
            0,
            self.hwnd,
            None,
        )
        self.user32.DestroyMenu(menu)
        if command == self.CMD_OPEN:
            self.show_window()
        elif command == self.CMD_EXIT:
            self.exit_event.set()

    def _window_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == self.WM_TIMER:
            self._tick()
            return 0
        if message == self.WM_TRAYICON:
            event = lparam & 0xFFFF
            if event == self.WM_LBUTTONDBLCLK:
                self.show_window()
            elif event in (self.WM_RBUTTONUP, self.WM_CONTEXTMENU):
                self._show_menu()
            return 0
        if message == self.WM_COMMAND:
            command = wparam & 0xFFFF
            if command == self.CMD_OPEN:
                self.show_window()
            elif command == self.CMD_EXIT:
                self.exit_event.set()
            return 0
        if message == self.WM_DESTROY:
            self.user32.PostQuitMessage(0)
            return 0
        return self.user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _create_tray(self) -> None:
        instance = self.kernel32.GetModuleHandleW(None)
        class_name = "ActivityCompassTrayWindow"
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = instance
        window_class.lpszClassName = class_name
        self.user32.RegisterClassExW(ctypes.byref(window_class))
        self.hwnd = self.user32.CreateWindowExW(
            0,
            class_name,
            "Activity Compass Tray",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            instance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError()
        icon_path = str(PROJECT_ROOT / "assets" / "activity-compass.ico")
        self.large_icon = self._load_icon(
            icon_path,
            self.user32.GetSystemMetrics(self.SM_CXICON),
            self.user32.GetSystemMetrics(self.SM_CYICON),
        )
        self.small_icon = self._load_icon(
            icon_path,
            self.user32.GetSystemMetrics(self.SM_CXSMICON),
            self.user32.GetSystemMetrics(self.SM_CYSMICON),
        )
        if not self.large_icon:
            self.large_icon = self.user32.LoadIconW(None, ctypes.c_void_p(32512))
        if not self.small_icon:
            self.small_icon = self.large_icon
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        data.uCallbackMessage = self.WM_TRAYICON
        data.hIcon = self.small_icon
        data.szTip = "Activity Compass"
        self.notify_data = data
        self.tray_added = bool(
            self.shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(data))
        )
        self._last_tray_retry = time.monotonic()
        self.user32.SetTimer(self.hwnd, 1, 150, None)

    def _load_icon(self, path: str, width: int, height: int) -> int | None:
        icon = self.user32.LoadImageW(
            None,
            path,
            self.IMAGE_ICON,
            width,
            height,
            self.LR_LOADFROMFILE,
        )
        if icon:
            self._owned_icons.append(icon)
        return icon or None

    def run(self) -> None:
        self._create_tray()
        self._launch_ui(hidden=False)
        message = wintypes.MSG()
        while self.user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            self.user32.TranslateMessage(ctypes.byref(message))
            self.user32.DispatchMessageW(ctypes.byref(message))

    def close(self) -> None:
        if self.notify_data is not None and self.tray_added:
            self.shell32.Shell_NotifyIconW(
                self.NIM_DELETE, ctypes.byref(self.notify_data)
            )
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        for icon in set(self._owned_icons):
            self.user32.DestroyIcon(icon)
        self._owned_icons.clear()
        if self._com_initialized:
            self.ole32.CoUninitialize()


def main() -> None:
    ctypes.windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
    mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Local\\ActivityCompassLauncher"
    )
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        if api_is_ready():
            send_control("show")
            return
        # The files were updated while an older tray/API process was still
        # running. Stop it so the current schema and migrations can load.
        send_control("exit")
        ctypes.windll.kernel32.CloseHandle(mutex)
        mutex = None
        for _ in range(50):
            time.sleep(0.2)
            candidate = ctypes.windll.kernel32.CreateMutexW(
                None, False, "Local\\ActivityCompassLauncher"
            )
            if ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS:
                mutex = candidate
                break
            ctypes.windll.kernel32.CloseHandle(candidate)
        if mutex is None:
            show_error("更新前のActivity Compassを終了できませんでした。")
            return

    api_process: subprocess.Popen[bytes] | None = None
    control_server: ThreadingHTTPServer | None = None
    tray: TrayApplication | None = None
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
                    console_python_executable(),
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

        actions = {
            "exit": threading.Event(),
            "show": threading.Event(),
            "hide": threading.Event(),
        }
        handler = type(
            "ActivityCompassControlHandler",
            (ControlHandler,),
            {"actions": actions},
        )
        control_server = ThreadingHTTPServer(("127.0.0.1", 8766), handler)
        threading.Thread(
            target=control_server.serve_forever,
            daemon=True,
            name="activity-control",
        ).start()
        tray = TrayApplication(actions["exit"], actions["show"], actions["hide"])
        tray.run()
    except Exception as exc:
        show_error(f"Activity Compass を起動できませんでした。\n\n{exc}")
    finally:
        if tray is not None:
            tray.close()
        if control_server is not None:
            control_server.shutdown()
            control_server.server_close()
        if api_process is not None and api_process.poll() is None:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
