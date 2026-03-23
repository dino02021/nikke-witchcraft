from __future__ import annotations

import threading

from .config import Settings
from .hotkeys import HotkeyManager
from . import winapi


class Actions:
    def __init__(self, settings: Settings, hotkeys: HotkeyManager):
        self.s = settings
        self.hk = hotkeys

    def is_context_enabled(self) -> bool:
        return self.s.is_global_hotkeys or winapi.is_foreground_exe("nikke.exe")

    def run_single_map(self, trigger_key: str, output_key: str, stop_ev: threading.Event) -> None:
        self._press_key(output_key)
        # Keep the worker alive until release so a held trigger does not retrigger.
        while self.hk.should_run(trigger_key, stop_ev):
            if not self.hk.wait_ms_cancel(10, trigger_key, stop_ev):
                break

    def run_spam(self, trigger_key: str, output_key: str, stop_ev: threading.Event) -> None:
        while self.hk.should_run(trigger_key, stop_ev):
            self._press_key(output_key)
            if not self.hk.wait_ms_cancel(self.s.key_spam_delay_ms, trigger_key, stop_ev):
                break

    def run_click(self, key_name: str, btn_name: str, hold_ms: int, gap_ms: int, stop_ev: threading.Event) -> None:
        released_any = False
        if self.hk.is_pressed("left"):
            self._release_click("LButton")
            released_any = True
        if self.hk.is_pressed("right"):
            self._release_click("RButton")
            released_any = True
        if released_any:
            if not self.hk.wait_ms_cancel(gap_ms, key_name, stop_ev):
                return
        try:
            while self.hk.should_run(key_name, stop_ev):
                self._hold_click(btn_name)
                if not self.hk.wait_ms_cancel(hold_ms, key_name, stop_ev):
                    break
                self._release_click(btn_name)
                if not self.hk.wait_ms_cancel(gap_ms, key_name, stop_ev):
                    break
        finally:
            self._release_click(btn_name)

    def run_jitter(self, trigger_key: str, stop_ev: threading.Event) -> None:
        while self.hk.should_run(trigger_key, stop_ev):
            seq = []
            if self.s.jitter_z:
                seq.append("z")
            if self.s.jitter_x:
                seq.append("x")
            if self.s.jitter_c:
                seq.append("c")
            if self.s.jitter_v:
                seq.append("v")
            if self.s.jitter_b:
                seq.append("b")
            if not seq:
                if not self.hk.wait_ms_cancel(self.s.key_spam_delay_ms, trigger_key, stop_ev):
                    break
                continue
            for key in seq:
                if not self.hk.should_run(trigger_key, stop_ev):
                    return
                self._press_key(key)
                if not self.hk.wait_ms_cancel(self.s.key_spam_delay_ms, trigger_key, stop_ev):
                    return

    def _key_from_name(self, name: str):
        n = name.strip().lower()
        if len(n) == 1:
            return n
        return n

    def _press_key(self, name: str) -> None:
        key = self._key_from_name(name)
        if not key:
            return
        winapi.send_key_tap(key)

    def _click(self, btn_name: str) -> None:
        winapi.send_mouse_click(btn_name)

    def _hold_click(self, btn_name: str) -> None:
        winapi.send_mouse_down(btn_name)

    def _release_click(self, btn_name: str) -> None:
        winapi.send_mouse_up(btn_name)
