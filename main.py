from __future__ import annotations

import sys
import ctypes
from ctypes import wintypes
import tkinter as tk
import os
from pathlib import Path
from functools import partial

from lib.config import Settings, ConfigStore, APP_NAME, APP_TITLE
from lib.log import Logger
from lib.hotkeys import HotkeyManager, HotkeyDef
from lib.actions import Actions
from lib.gui.ui import AppUI
from lib import winapi
from PIL import Image, ImageDraw
import pystray
import threading
import queue
import faulthandler


_fg_pending = {"fg": 0, "exe": "-", "hwnd": 0}
_fg_ui: AppUI | None = None
_fg_log: Logger | None = None
_fg_queue: queue.Queue[tuple[int, str, int, int, int]] = queue.Queue()
_faulthandler_file = None
_app_state = {"hk": None, "icon": None, "log": None, "closing": False}


def ensure_admin(log: Logger) -> None:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.IsUserAnAdmin.argtypes = []
    shell32.IsUserAnAdmin.restype = wintypes.BOOL
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    try:
        is_admin = shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        log.event("SYS", "Admin", "request", "state=0")
        params = " ".join(['"%s"' % arg for arg in sys.argv])
        exe = sys.executable
        if exe.lower().endswith("python.exe"):
            exe = exe[:-10] + "pythonw.exe"
        rc = shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        if rc <= 32:
            log.event("SYS", "Admin", "requestFail", f"rc={rc}")
            return
        sys.exit(0)
    else:
        log.event("SYS", "Admin", "ok", "state=1")


def main() -> None:
    base_dir = Path.home() / "Documents" / f"{APP_NAME}Settings"
    log = Logger(base_dir / f"{APP_NAME}Debug.log")
    _app_state["log"] = log
    _install_exception_logging(log)
    _enable_faulthandler(log.log_path)
    ensure_admin(log)
    _terminate_existing_instances()
    store = ConfigStore(base_dir)
    settings = store.load(Settings())
    winapi.time_begin_period(1)
    log.event("SYS", "timeBeginPeriod", "init", "ok=1")

    hk = HotkeyManager(
        is_context_enabled=partial(_is_context_enabled, settings),
        logger=log,
        context_info=partial(_context_info, settings),
    )
    _app_state["hk"] = hk
    actions = Actions(settings, hk)

    hk.define(HotkeyDef("EscMap", settings.key_esc, settings.is_esc_enabled,
                        lambda stop: actions.run_single_map(settings.key_esc, "esc", stop)))
    hk.define(HotkeyDef("DSpam", settings.key_spam_d, settings.is_spam_d_enabled,
                        lambda stop: actions.run_spam(settings.key_spam_d, "d", stop)))
    hk.define(HotkeyDef("SSpam", settings.key_spam_s, settings.is_spam_s_enabled,
                        lambda stop: actions.run_spam(settings.key_spam_s, "s", stop)))
    hk.define(HotkeyDef("ASpam", settings.key_spam_a, settings.is_spam_a_enabled,
                        lambda stop: actions.run_spam(settings.key_spam_a, "a", stop)))

    hk.define(HotkeyDef("ClickSeq1", settings.key_click1, settings.is_click1_enabled,
                        lambda stop: actions.run_click(settings.key_click1, settings.click_btn1,
                                                       settings.click1_hold_ms, settings.click1_gap_ms, stop)))
    hk.define(HotkeyDef("ClickSeq2", settings.key_click2, settings.is_click2_enabled,
                        lambda stop: actions.run_click(settings.key_click2, settings.click_btn2,
                                                       settings.click2_hold_ms, settings.click2_gap_ms, stop)))
    hk.define(HotkeyDef("ClickSeq3", settings.key_click3, settings.is_click3_enabled,
                        lambda stop: actions.run_click(settings.key_click3, settings.click_btn3,
                                                       settings.click3_hold_ms, settings.click3_gap_ms, stop)))

    hk.define(HotkeyDef("Jitter", settings.key_jitter, settings.is_jitter_enabled,
                        lambda stop: actions.run_jitter(settings.key_jitter, stop)))
    for key in ("a", "s", ";", "'"):
        hk.define(HotkeyDef(
            f"RhythmPreset2_{key}",
            key,
            settings.is_rhythm_preset2_enabled,
            lambda stop: None,
            pass_through=True,
            on_event=lambda is_down, trigger=key: actions.handle_rhythm_preset2_key(trigger, is_down),
        ))

    hk.start()

    root, ui = _init_ui(settings, store, hk, actions, log)
    _install_foreground_hook(root, ui, log, hk, settings)

    tray = pystray.Icon(
        APP_TITLE,
        _build_tray_icon(),
        APP_TITLE,
        menu=pystray.Menu(
            pystray.MenuItem("開啟面板", lambda: root.after(0, partial(_show_ui, root)), default=True),
            pystray.MenuItem("結束", partial(_quit_app, root)),
        ),
    )
    tray.on_activate = lambda icon, item=None: root.after(0, partial(_show_ui, root))
    _app_state["icon"] = tray

    root.protocol("WM_DELETE_WINDOW", partial(_close_ui, root))
    tray.run_detached()
    root.after(200, lambda: _cursor_lock_tick(root, settings))
    root.mainloop()


def _is_context_enabled(settings: Settings) -> bool:
    return settings.is_global_hotkeys or winapi.is_foreground_exe("nikke.exe")


def _context_info(settings: Settings) -> str:
    fg = 1 if winapi.is_foreground_exe("nikke.exe") else 0
    g = 1 if settings.is_global_hotkeys else 0
    exe = winapi.get_foreground_exe_name() or "-"
    return f"global={g} fg={fg} exe={exe}"


def _init_ui(settings: Settings, store: ConfigStore, hk: HotkeyManager, actions: Actions, log: Logger) -> tuple[tk.Tk, AppUI]:
    try:
        root = tk.Tk()
        root.report_callback_exception = lambda exc, val, tb: log.event("SYS", "UI", "exception", f"err={val}")
        ui = AppUI(root, settings, store, hk, actions, log)
        log.event("SYS", "UI", "init", "ok=1")
        root.update_idletasks()
        _show_ui(root)
        return root, ui
    except Exception as exc:
        log.event("SYS", "UI", "initFail", f"err={exc}")
        raise


def _install_foreground_hook(root: tk.Tk, ui: AppUI, log: Logger, hk: HotkeyManager, settings: Settings) -> None:
    state = {"last": None}
    _install_foreground_pending(root, ui, log, hk, settings)

    def on_foreground(hook, event, hwnd, obj_id, child_id, thread_id, time_ms):
        try:
            if not hwnd:
                return
            path = winapi.get_process_image(hwnd)
            exe = os.path.basename(path).lower() if path else "-"
            fg = 1 if exe == "nikke.exe" else 0
            current = (fg, exe)
            if state["last"] != current:
                state["last"] = current
                is_primary = 1 if winapi.is_window_on_primary_monitor(hwnd) else 0
                _queue_foreground_update(fg, exe, hwnd, is_primary, 1 if settings.is_global_hotkeys else 0)
        except Exception as exc:
            log.event("SYS", "ForegroundHook", "error", f"err={exc}")

    hook, proc = winapi.set_foreground_event_hook(on_foreground)
    if not hook:
        err = winapi.get_last_error()
        log.event("SYS", "ForegroundHook", "initFail", f"err={err}")
    else:
        log.event("SYS", "ForegroundHook", "init", "ok=1")
    setattr(root, "_fg_hook", hook)
    setattr(root, "_fg_proc", proc)
    hwnd = winapi.get_foreground_hwnd()
    on_foreground(0, 0, hwnd, 0, 0, 0, 0)


def _cursor_lock_tick(root: tk.Tk, settings: Settings) -> None:
    if settings.is_cursor_lock and winapi.is_foreground_exe("nikke.exe"):
        rect = winapi.get_client_rect_screen(winapi.get_foreground_hwnd())
        if rect and rect.width > 0 and rect.height > 0:
            winapi.clip_cursor(rect)
        else:
            winapi.clip_cursor(None)
    else:
        winapi.clip_cursor(None)
    root.after(200, lambda: _cursor_lock_tick(root, settings))


def _show_ui(root: tk.Tk) -> None:
    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))


def _close_ui(root: tk.Tk) -> None:
    log: Logger | None = _app_state.get("log")
    if log:
        log.event("SYS", "App", "close", "start")
    winapi.clip_cursor(None)
    root.withdraw()
    if log:
        log.event("SYS", "App", "close", "done")


def _quit_app(root: tk.Tk, icon, item=None) -> None:
    _shutdown_app(root, "quit", icon)


def _build_tray_icon() -> Image.Image:
    try:
        icon_path = Path(__file__).resolve().parent / "assets" / "app.png"
        return Image.open(icon_path).convert("RGBA")
    except Exception:
        img = Image.new("RGB", (64, 64), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        draw.rectangle((8, 8, 56, 56), outline=(255, 255, 255), width=3)
        draw.text((18, 18), "NW", fill=(255, 255, 255))
        return img


def _shutdown_app(root: tk.Tk, reason: str, icon=None) -> None:
    if _app_state.get("closing"):
        return
    _app_state["closing"] = True
    log: Logger | None = _app_state.get("log")
    try:
        if log:
            log.event("SYS", "App", "shutdown", f"reason={reason} step=start")
        winapi.clip_cursor(None)
        hk: HotkeyManager | None = _app_state.get("hk")
        if hk:
            if log:
                log.event("SYS", "App", "shutdown", "step=hotkeys_stop")
            hk.stop()
        actions = getattr(_fg_ui, "actions", None)
        if actions:
            actions.release_rhythm_preset2()
        fg_hook = getattr(root, "_fg_hook", None)
        if fg_hook:
            if log:
                log.event("SYS", "App", "shutdown", "step=fg_unhook")
            winapi.unhook_win_event(fg_hook)
        if log:
            log.event("SYS", "App", "shutdown", "step=destroy")
        root.after(0, root.destroy)
        icon = icon or _app_state.get("icon")
        if icon:
            if log:
                log.event("SYS", "App", "shutdown", "step=tray_stop")
            icon.stop()
        if log:
            log.event("SYS", "App", "shutdown", "step=done")
    except Exception as exc:
        if log:
            log.event("SYS", "App", "shutdownFail", f"err={exc}")


def _install_foreground_pending(root: tk.Tk, ui: AppUI, log: Logger, hk: HotkeyManager, settings: Settings) -> None:
    global _fg_ui, _fg_log
    _fg_ui = ui
    _fg_log = log

    def _drain_queue():
        try:
            last = None
            while True:
                try:
                    last = _fg_queue.get_nowait()
                except Exception:
                    break
            if last and _fg_ui and _fg_log:
                fg, exe, _hwnd, is_primary, is_global = last
                suppress = 1 if (is_global or (fg == 1 and is_primary == 1)) else 0
                hk.set_key_blocking(bool(suppress))
                if not suppress:
                    _fg_ui.actions.release_rhythm_preset2()
                _fg_ui.set_game_state(fg, exe)
        except Exception as exc:
            if _fg_log:
                _fg_log.event("SYS", "ForegroundHook", "pendingError", f"err={exc}")
        finally:
            root.after(500, _drain_queue)

    root.after(500, _drain_queue)


def _queue_foreground_update(fg: int, exe: str, hwnd: int, is_primary: int, is_global: int) -> None:
    _fg_pending["fg"] = fg
    _fg_pending["exe"] = exe
    _fg_pending["hwnd"] = hwnd
    _fg_queue.put((fg, exe, hwnd, is_primary, is_global))


def _install_exception_logging(log: Logger) -> None:
    def _hook(exc_type, exc, tb):
        log.event("SYS", "App", "crash", f"err={exc}")
    sys.excepthook = _hook
    if hasattr(threading, "excepthook"):
        def _thread_hook(args):
            log.event("SYS", "Thread", "crash", f"err={args.exc_value}")
        threading.excepthook = _thread_hook


def _enable_faulthandler(log_path: Path) -> None:
    global _faulthandler_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _faulthandler_file = open(log_path, "a", encoding="utf-8")
    faulthandler.enable(_faulthandler_file)


def _terminate_existing_instances() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    current_pid = os.getpid()
    current_exe = os.path.normcase(os.path.abspath(sys.executable))

    def _get_process_image(pid: int) -> str | None:
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            buf_len = wintypes.DWORD(4096)
            buf = ctypes.create_unicode_buffer(buf_len.value)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len))
            if not ok:
                return None
            return buf.value
        finally:
            kernel32.CloseHandle(handle)

    def enum_proc(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return 1
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if not buf.value.startswith(APP_NAME):
            return 1
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value and pid.value != current_pid:
            img = _get_process_image(pid.value)
            if not img:
                return 1
            if os.path.normcase(os.path.abspath(img)) != current_exe:
                return 1
            handle = kernel32.OpenProcess(0x0001, False, pid.value)
            if handle:
                kernel32.TerminateProcess(handle, 0)
                kernel32.CloseHandle(handle)
        return 1

    cb = EnumWindowsProc(enum_proc)
    user32.EnumWindows(cb, 0)






if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        base_dir = Path.home() / "Documents" / f"{APP_NAME}Settings"
        log = Logger(base_dir / f"{APP_NAME}Debug.log")
        log.event("SYS", "App", "fatal", f"err={exc}")
        raise
