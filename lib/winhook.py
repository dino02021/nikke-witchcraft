from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time
from typing import Callable

from . import winapi

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_QUIT = 0x0012
HC_ACTION = 0
LLKHF_INJECTED = 0x00000010
LLMHF_INJECTED = 0x00000001


ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
LRESULT = ctypes.c_ssize_t
WPARAM = wintypes.WPARAM
LPARAM = wintypes.LPARAM


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


LowLevelProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelProc, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, WPARAM, LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL


class HookState:
    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.tid: int | None = None
        self.h_kb = None
        self.h_ms = None
        self.kb_cb = None
        self.ms_cb = None
        self.hook_error_count = 0
        self.fail_open_enabled = False
        self._stop = threading.Event()


VK_NAME_MAP: dict[int, str] = {
    # 1) System / control
    0x03: "cancel",
    0x08: "backspace",
    0x09: "tab",
    0x0C: "clear",
    0x0D: "enter",
    0x10: "shift",
    0x11: "ctrl",
    0x12: "alt",
    0x13: "pause",
    0x14: "capslock",
    0x15: "ime_kana",
    0x17: "ime_junja",
    0x18: "ime_final",
    0x19: "ime_hanja",
    0x1B: "esc",
    0x1C: "ime_convert",
    0x1D: "ime_nonconvert",
    0x1E: "ime_accept",
    0x1F: "ime_modechange",
    0x20: "space",
    0x29: "select",
    0x2A: "print",
    0x2B: "execute",
    0x2F: "help",
    # Left/right modifiers (distinct names)
    0xA0: "lshift",  # VK_LSHIFT
    0xA1: "rshift",  # VK_RSHIFT
    0xA2: "lctrl",   # VK_LCONTROL
    0xA3: "rctrl",   # VK_RCONTROL
    0xA4: "lalt",    # VK_LMENU
    0xA5: "ralt",    # VK_RMENU
    # 2) Navigation / edit
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2C: "printscreen",
    0x2D: "insert",
    0x2E: "delete",
    # 4) Windows keys / apps
    0x5B: "lcmd",
    0x5C: "rcmd",
    0x5D: "apps",
    0x5F: "sleep",
    # 5) Numpad operators
    0x6A: "num*",
    0x6B: "num+",
    0x6C: "numsep",  # VK_SEPARATOR
    0x6D: "num-",
    0x6E: "num.",
    0x6F: "num/",
    # 7) Lock keys
    0x90: "numlock",
    0x91: "scrolllock",
    # 9) Browser / media / launch
    0xA6: "browser_back",
    0xA7: "browser_forward",
    0xA8: "browser_refresh",
    0xA9: "browser_stop",
    0xAA: "browser_search",
    0xAB: "browser_favorites",
    0xAC: "browser_home",
    0xAD: "volume_mute",
    0xAE: "volume_down",
    0xAF: "volume_up",
    0xB0: "media_next",
    0xB1: "media_prev",
    0xB2: "media_stop",
    0xB3: "media_play_pause",
    0xB4: "launch_mail",
    0xB5: "launch_media",
    0xB6: "launch_app1",
    0xB7: "launch_app2",
    # 8) OEM symbols (US layout names)
    0xBA: ";",   # VK_OEM_1
    0xBB: "=",   # VK_OEM_PLUS
    0xBC: ",",   # VK_OEM_COMMA
    0xBD: "-",   # VK_OEM_MINUS
    0xBE: ".",   # VK_OEM_PERIOD
    0xBF: "/",   # VK_OEM_2
    0xC0: "`",   # VK_OEM_3 (`~ key)
    0xDB: "[",   # VK_OEM_4
    0xDC: "\\",  # VK_OEM_5
    0xDD: "]",   # VK_OEM_6
    0xDE: "'",   # VK_OEM_7
    0xDF: "oem_8",
    0xE1: "oem_ax",
    0xE2: "oem_102",
    0xE5: "processkey",
    0xE7: "packet",
    0xE9: "oem_reset",
    0xEA: "oem_jump",
    0xEB: "oem_pa1",
    0xEC: "oem_pa2",
    0xED: "oem_pa3",
    0xEE: "oem_wsctrl",
    0xEF: "oem_cusel",
    0xF0: "oem_attn",
    0xF1: "oem_finish",
    0xF2: "oem_copy",
    0xF3: "oem_auto",
    0xF4: "oem_enlw",
    0xF5: "oem_backtab",
    0xF6: "attn",
    0xF7: "crsel",
    0xF8: "exsel",
    0xF9: "ereof",
    0xFA: "play",
    0xFB: "zoom",
    0xFD: "pa1",
    0xFE: "oem_clear",
}

# 3) Main alnum area
VK_NAME_MAP.update({vk: chr(vk) for vk in range(0x30, 0x3A)})
VK_NAME_MAP.update({vk: chr(vk + 32) for vk in range(0x41, 0x5B)})

# 5) Numpad digits
VK_NAME_MAP.update({vk: f"num{vk - 0x60}" for vk in range(0x60, 0x6A)})

# 6) Function keys
VK_NAME_MAP.update({vk: f"f{vk - 0x6F}" for vk in range(0x70, 0x88)})


def _vk_to_name(vk: int) -> str | None:
    # Unknown VK still returns a stable name so it can be bound.
    return VK_NAME_MAP.get(vk) or f"vk_{vk:02x}"


def _mouse_name(msg: int, mouseData: int) -> str | None:
    if msg in (WM_LBUTTONDOWN, WM_LBUTTONUP):
        return "left"
    if msg in (WM_RBUTTONDOWN, WM_RBUTTONUP):
        return "right"
    if msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
        return "middle"
    if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
        xbtn = (mouseData >> 16) & 0xFFFF
        if xbtn == 1:
            return "x1"
        if xbtn == 2:
            return "x2"
    return None


def start_hooks(
    on_key: Callable[[str, bool], bool],
    on_mouse: Callable[[str, bool], bool],
    on_log: Callable[[str, str, str, str], None] | None = None,
    on_auto_fail_open: Callable[[], None] | None = None,
    enable_mouse: bool = True,
    mouse_filter: Callable[[str], bool] | None = None,
) -> HookState:
    state = HookState()
    err_lock = threading.Lock()
    last_err_log_ts = 0.0
    err_log_interval_sec = 1.0
    err_threshold = 10

    def _safe_next(nCode, wParam, lParam):
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _log_error(kind: str, exc: Exception):
        nonlocal last_err_log_ts
        state.hook_error_count += 1
        now = time.monotonic()
        with err_lock:
            if on_log and (now - last_err_log_ts >= err_log_interval_sec):
                last_err_log_ts = now
                on_log("SYS", "HookError", kind, f"count={state.hook_error_count} err={exc}")
        if state.hook_error_count >= err_threshold and not state.fail_open_enabled:
            state.fail_open_enabled = True
            if on_auto_fail_open:
                on_auto_fail_open()
            if on_log:
                on_log("SYS", "HookError", "autoFailOpen", f"count={state.hook_error_count}")

    def kb_proc(nCode, wParam, lParam):
        try:
            if state.fail_open_enabled:
                return _safe_next(nCode, wParam, lParam)
            if nCode == HC_ACTION:
                data = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if data.flags & LLKHF_INJECTED:
                    return _safe_next(nCode, wParam, lParam)
                name = _vk_to_name(data.vkCode)
                if name:
                    is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if on_key(name, is_down):
                        return 1
        except Exception as exc:
            _log_error("keyboard", exc)
        return _safe_next(nCode, wParam, lParam)

    def ms_proc(nCode, wParam, lParam):
        try:
            if state.fail_open_enabled:
                return _safe_next(nCode, wParam, lParam)
            if nCode == HC_ACTION:
                data = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if data.flags & LLMHF_INJECTED:
                    return _safe_next(nCode, wParam, lParam)
                name = _mouse_name(wParam, data.mouseData)
                if name and (mouse_filter is None or mouse_filter(name)):
                    is_down = wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN)
                    if on_mouse(name, is_down):
                        return 1
        except Exception as exc:
            _log_error("mouse", exc)
        return _safe_next(nCode, wParam, lParam)

    def run():
        state.tid = kernel32.GetCurrentThreadId()
        state.kb_cb = LowLevelProc(kb_proc)
        state.h_kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, state.kb_cb, 0, 0)
        if enable_mouse:
            state.ms_cb = LowLevelProc(ms_proc)
            state.h_ms = user32.SetWindowsHookExW(WH_MOUSE_LL, state.ms_cb, 0, 0)
        if on_log:
            if not state.h_kb or (enable_mouse and not state.h_ms):
                err = ctypes.get_last_error()
                on_log("SYS", "Hook", "initFail", f"hkb={int(bool(state.h_kb))} hms={int(bool(state.h_ms))} mouse={int(enable_mouse)} err={err}")
                state.fail_open_enabled = True
                if on_auto_fail_open:
                    on_auto_fail_open()
            on_log("SYS", "Hook", "init", f"tid={state.tid} hkb={int(bool(state.h_kb))} hms={int(bool(state.h_ms))} mouse={int(enable_mouse)}")
        msg = wintypes.MSG()
        while not state._stop.is_set() and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if state.h_kb:
            user32.UnhookWindowsHookEx(state.h_kb)
        if state.h_ms:
            user32.UnhookWindowsHookEx(state.h_ms)

    t = threading.Thread(target=run, daemon=True)
    state.thread = t
    t.start()
    return state


def stop_hooks(state: HookState) -> None:
    if not state:
        return
    state._stop.set()
    if state.tid:
        user32.PostThreadMessageW(state.tid, WM_QUIT, 0, 0)
    if state.thread and state.thread.is_alive():
        state.thread.join(timeout=2.0)
