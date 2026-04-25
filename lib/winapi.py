from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
MONITOR_DEFAULTTONEAREST = 0x00000002
MONITORINFOF_PRIMARY = 0x00000001

WinEventProc = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)

_win_event_procs = []

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
user32.ClipCursor.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.MsgWaitForMultipleObjectsEx.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
user32.MsgWaitForMultipleObjectsEx.restype = wintypes.DWORD
user32.SetWinEventHook.argtypes = [
    wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WinEventProc,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD
]
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.UnhookWinEvent.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

psapi.GetProcessImageFileNameW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD]
psapi.GetProcessImageFileNameW.restype = wintypes.DWORD

@dataclass
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def get_foreground_hwnd() -> int:
    return user32.GetForegroundWindow()


def get_window_rect(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def get_client_rect_screen(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    pt = wintypes.POINT(rect.left, rect.top)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    left, top = pt.x, pt.y
    pt = wintypes.POINT(rect.right, rect.bottom)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    right, bottom = pt.x, pt.y
    return Rect(left, top, right, bottom)


def clip_cursor(rect: Rect | None) -> bool:
    if rect is None:
        return bool(user32.ClipCursor(None))
    r = wintypes.RECT(rect.left, rect.top, rect.right, rect.bottom)
    return bool(user32.ClipCursor(ctypes.byref(r)))


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]


def is_window_on_primary_monitor(hwnd: int) -> bool:
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return False
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    return (info.dwFlags & MONITORINFOF_PRIMARY) != 0


def get_process_image(hwnd: int) -> str | None:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        if psapi.GetProcessImageFileNameW(handle, buf, len(buf)):
            return buf.value
    finally:
        kernel32.CloseHandle(handle)
    return None


def is_foreground_exe(exe_name: str) -> bool:
    hwnd = get_foreground_hwnd()
    if not hwnd:
        return False
    path = get_process_image(hwnd)
    if not path:
        return False
    base = os.path.basename(path).lower()
    target = exe_name.lower()
    return base == target


def get_foreground_exe_name() -> str | None:
    hwnd = get_foreground_hwnd()
    if not hwnd:
        return None
    path = get_process_image(hwnd)
    if not path:
        return None
    return os.path.basename(path)


def msg_wait(timeout_ms: int) -> None:
    # MsgWaitForMultipleObjectsEx with no handles
    MWMO_INPUTAVAILABLE = 0x0004
    QS_ALLINPUT = 0x04FF
    user32.MsgWaitForMultipleObjectsEx(0, None, max(0, int(timeout_ms)), QS_ALLINPUT, MWMO_INPUTAVAILABLE)


def time_begin_period(ms: int) -> bool:
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
    winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
    winmm.timeBeginPeriod.restype = wintypes.UINT
    return winmm.timeBeginPeriod(ms) == 0


def time_end_period(ms: int) -> bool:
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
    winmm.timeEndPeriod.argtypes = [wintypes.UINT]
    winmm.timeEndPeriod.restype = wintypes.UINT
    return winmm.timeEndPeriod(ms) == 0


def set_foreground_event_hook(callback) -> wintypes.HANDLE:
    proc = WinEventProc(callback)
    _win_event_procs.append(proc)
    hook = user32.SetWinEventHook(
        EVENT_SYSTEM_FOREGROUND,
        EVENT_SYSTEM_FOREGROUND,
        0,
        proc,
        0,
        0,
        WINEVENT_OUTOFCONTEXT,
    )
    return hook, proc


def unhook_win_event(hook: wintypes.HANDLE) -> bool:
    if not hook:
        return False
    return bool(user32.UnhookWinEvent(hook))


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008


def _vk_from_name(name: str) -> int | None:
    n = name.strip().lower()
    if len(n) == 1:
        return ord(n.upper())
    if n.startswith("f") and n[1:].isdigit():
        idx = int(n[1:])
        if 1 <= idx <= 24:
            return 0x6F + idx
    vk_map = {
        "esc": 0x1B,
        "escape": 0x1B,
        "tab": 0x09,
        "enter": 0x0D,
        "space": 0x20,
        "backspace": 0x08,
        "shift": 0x10,
        "lshift": 0xA0,
        "rshift": 0xA1,
        "ctrl": 0x11,
        "lctrl": 0xA2,
        "rctrl": 0xA3,
        "alt": 0x12,
        "lalt": 0xA4,
        "ralt": 0xA5,
        "lwin": 0x5B,
        "lcmd": 0x5B,
        "rwin": 0x5C,
        "rcmd": 0x5C,
    }
    return vk_map.get(n)

def _scan_from_vk(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0))

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


def _send_input(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))


def _key_input(vk: int, flags: int) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki = KEYBDINPUT(vk, 0, flags, 0, None)
    return inp


def _mouse_input(flags: int) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
    return inp


def _key_inputs(name: str, flags: int) -> list[INPUT]:
    vk = _vk_from_name(name)
    if vk is None:
        return []
    sc = _scan_from_vk(vk)
    if sc:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT(0, sc, KEYEVENTF_SCANCODE | flags, 0, None)
        return [inp]
    return [_key_input(vk, flags)]


def send_key_down(name: str) -> None:
    _send_input(_key_inputs(name, 0))


def send_key_up(name: str) -> None:
    _send_input(_key_inputs(name, KEYEVENTF_KEYUP))


def send_key_tap(name: str) -> None:
    _send_input(_key_inputs(name, 0) + _key_inputs(name, KEYEVENTF_KEYUP))


def send_mouse_down(btn_name: str) -> None:
    name = btn_name.strip().lower()
    if name == "lbutton":
        _send_input([_mouse_input(MOUSEEVENTF_LEFTDOWN)])
    elif name == "rbutton":
        _send_input([_mouse_input(MOUSEEVENTF_RIGHTDOWN)])


def send_mouse_up(btn_name: str) -> None:
    name = btn_name.strip().lower()
    if name == "lbutton":
        _send_input([_mouse_input(MOUSEEVENTF_LEFTUP)])
    elif name == "rbutton":
        _send_input([_mouse_input(MOUSEEVENTF_RIGHTUP)])


def send_mouse_click(btn_name: str) -> None:
    send_mouse_down(btn_name)
    send_mouse_up(btn_name)


def get_last_error() -> int:
    return ctypes.get_last_error()
