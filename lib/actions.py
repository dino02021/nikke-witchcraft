from __future__ import annotations

import threading

from .config import Settings
from .hotkeys import HotkeyManager
from . import winapi


class Actions:
    def __init__(self, settings: Settings, hotkeys: HotkeyManager):
        self.s = settings
        self.hk = hotkeys
        self._rhythm_lock = threading.Lock()
        self._rhythm_triggers_down: set[str] = set()
        self._rhythm_outputs_down: set[str] = set()
        self._rhythm_latch_keys: dict[str, set[str]] = {
            "lshift": set(),
            "rshift": set(),
            "space": set(),
        }

    def is_context_enabled(self) -> bool:
        return self.hk.is_context_enabled()

    def run_single_map(self, trigger_key: str, output_key: str, stop_ev: threading.Event) -> None:
        self.hk.log.event("ACT", "SingleMap", "start", f"trigger={trigger_key} output={output_key}")
        self._press_key(output_key)
        # Keep the worker alive until release so a held trigger does not retrigger.
        reason = "released"
        try:
            while self.hk.should_run(trigger_key, stop_ev):
                if not self.hk.wait_ms_cancel(10, trigger_key, stop_ev):
                    reason = self._stop_reason(trigger_key, stop_ev)
                    break
        finally:
            self.hk.log.event("ACT", "SingleMap", "stop", f"trigger={trigger_key} output={output_key} reason={reason}")

    def run_spam(self, trigger_key: str, output_key: str, stop_ev: threading.Event) -> None:
        count = 0
        reason = "released"
        self.hk.log.event("ACT", "KeySpam", "start", f"trigger={trigger_key} output={output_key}")
        try:
            while self.hk.should_run(trigger_key, stop_ev):
                self._press_key(output_key)
                count += 1
                if not self.hk.wait_ms_cancel(self.s.key_spam_delay_ms, trigger_key, stop_ev):
                    reason = self._stop_reason(trigger_key, stop_ev)
                    break
        finally:
            self.hk.log.event("ACT", "KeySpam", "stop", f"trigger={trigger_key} output={output_key} count={count} reason={reason}")

    def run_click(self, key_name: str, btn_name: str, hold_ms: int, gap_ms: int, stop_ev: threading.Event) -> None:
        released_any = False
        released_names = []
        if winapi.is_mouse_button_down("LButton"):
            self._release_click("LButton")
            released_any = True
            released_names.append("left")
        if winapi.is_mouse_button_down("RButton"):
            self._release_click("RButton")
            released_any = True
            released_names.append("right")
        self.hk.log.event(
            "ACT",
            "ClickSeq",
            "start",
            f"trigger={key_name} output={btn_name} released={','.join(released_names) or '-'}",
        )
        count = 0
        reason = "released"
        if released_any:
            if not self.hk.wait_ms_cancel(gap_ms, key_name, stop_ev):
                reason = self._stop_reason(key_name, stop_ev)
                self.hk.log.event("ACT", "ClickSeq", "stop", f"trigger={key_name} output={btn_name} count=0 reason={reason}_after_pre_release")
                return
        try:
            while self.hk.should_run(key_name, stop_ev):
                self._hold_click(btn_name)
                count += 1
                if not self.hk.wait_ms_cancel(hold_ms, key_name, stop_ev):
                    reason = self._stop_reason(key_name, stop_ev)
                    break
                self._release_click(btn_name)
                if not self.hk.wait_ms_cancel(gap_ms, key_name, stop_ev):
                    reason = self._stop_reason(key_name, stop_ev)
                    break
        finally:
            self._release_click(btn_name)
            self.hk.log.event("ACT", "ClickSeq", "stop", f"trigger={key_name} output={btn_name} count={count} reason={reason}")

    def run_jitter(self, trigger_key: str, stop_ev: threading.Event) -> None:
        count = 0
        reason = "released"
        self.hk.log.event("ACT", "Jitter", "start", f"trigger={trigger_key}")
        try:
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
                        reason = self._stop_reason(trigger_key, stop_ev)
                        break
                    continue
                for key in seq:
                    if not self.hk.should_run(trigger_key, stop_ev):
                        reason = self._stop_reason(trigger_key, stop_ev)
                        return
                    self._press_key(key)
                    count += 1
                    if not self.hk.wait_ms_cancel(self.s.key_spam_delay_ms, trigger_key, stop_ev):
                        reason = self._stop_reason(trigger_key, stop_ev)
                        return
        finally:
            self.hk.log.event("ACT", "Jitter", "stop", f"trigger={trigger_key} count={count} reason={reason}")

    def handle_rhythm_preset2_key(self, trigger_key: str, is_down: bool) -> None:
        trigger = trigger_key.strip().lower()
        if not self.s.is_rhythm_preset2_enabled or not self.is_context_enabled():
            self.release_rhythm_preset2()
            return

        if trigger not in {"a", "s", ";", "'"}:
            return

        with self._rhythm_lock:
            if is_down:
                self._rhythm_triggers_down.add(trigger)
            else:
                self._rhythm_triggers_down.discard(trigger)
                for latch_keys in self._rhythm_latch_keys.values():
                    latch_keys.discard(trigger)
            self._sync_rhythm_preset2_outputs()

    def release_rhythm_preset2(self) -> None:
        with self._rhythm_lock:
            if self._rhythm_outputs_down or self._rhythm_triggers_down:
                self.hk.log.event(
                    "ACT",
                    "RhythmPreset2",
                    "releaseAll",
                    f"triggers={','.join(sorted(self._rhythm_triggers_down)) or '-'} outputs={','.join(sorted(self._rhythm_outputs_down)) or '-'}",
                )
            for output_key in ("space", "lshift", "rshift"):
                if output_key in self._rhythm_outputs_down:
                    winapi.send_key_up(output_key)
            self._rhythm_outputs_down.clear()
            self._rhythm_triggers_down.clear()
            for latch_keys in self._rhythm_latch_keys.values():
                latch_keys.clear()

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

    def _sync_rhythm_preset2_outputs(self) -> None:
        down = self._rhythm_triggers_down
        self._sync_rhythm_latch("lshift", {"a", "s"}, down)
        self._sync_rhythm_latch("rshift", {";", "'"}, down)
        self._sync_rhythm_latch("space", {"a", "s", ";", "'"}, down)

    def _sync_rhythm_latch(self, output_key: str, trigger_keys: set[str], down: set[str]) -> None:
        latch_keys = self._rhythm_latch_keys[output_key]
        if trigger_keys.issubset(down) and output_key not in self._rhythm_outputs_down:
            latch_keys.clear()
            latch_keys.update(trigger_keys)
            self._set_rhythm_output(output_key, True)
            return
        if output_key in self._rhythm_outputs_down and not latch_keys:
            self._set_rhythm_output(output_key, False)

    def _set_rhythm_output(self, output_key: str, should_hold: bool) -> None:
        if should_hold:
            if output_key not in self._rhythm_outputs_down:
                winapi.send_key_down(output_key)
                self._rhythm_outputs_down.add(output_key)
                self.hk.log.event("ACT", "RhythmPreset2", "outputDown", f"key={output_key}")
            return
        if output_key in self._rhythm_outputs_down:
            winapi.send_key_up(output_key)
            self._rhythm_outputs_down.discard(output_key)
            self.hk.log.event("ACT", "RhythmPreset2", "outputUp", f"key={output_key}")

    def _stop_reason(self, trigger_key: str, stop_ev: threading.Event) -> str:
        if stop_ev.is_set():
            return "stop_requested"
        if not self.hk.is_pressed(trigger_key):
            return "released"
        if not self.hk.is_context_enabled():
            return "context_lost"
        return "unknown"

    def _click(self, btn_name: str) -> None:
        winapi.send_mouse_click(btn_name)

    def _hold_click(self, btn_name: str) -> None:
        winapi.send_mouse_down(btn_name)

    def _release_click(self, btn_name: str) -> None:
        winapi.send_mouse_up(btn_name)
