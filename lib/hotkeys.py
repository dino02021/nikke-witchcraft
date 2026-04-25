from __future__ import annotations

import threading
import queue
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .timing import wait_ms_cancel
from .log import Logger
from .winhook import start_hooks, stop_hooks


@dataclass
class HotkeyDef:
    id: str
    key_name: str
    is_enabled: bool
    on_start: Callable[[threading.Event], None]
    pass_through: bool = False
    on_event: Optional[Callable[[bool], None]] = None


class HotkeyManager:
    def __init__(
        self,
        is_context_enabled: Callable[[], bool],
        logger: Logger,
        context_info: Optional[Callable[[], str]] = None,
    ):
        self.is_context_enabled = is_context_enabled
        self.log = logger
        self.context_info = context_info
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._stop_flags: dict[str, threading.Event] = {}
        self._pressed: dict[str, bool] = {}
        self._key_down: dict[str, bool] = {}
        self._pressed_lock = threading.Lock()
        self._event_q: queue.Queue[tuple[str, bool]] = queue.Queue()
        self._event_stop = threading.Event()
        self._event_thread: threading.Thread | None = None
        self._defs: dict[str, HotkeyDef] = {}
        self._binding_cb: Optional[Callable[[str], None]] = None
        self._suppress = False
        self._force_pass_through = False
        self._hook_state = None
        self._bound_keys_cache: set[str] = set()
        self._blocking_keys_cache: set[str] = set()

    _GENERIC_VARIANTS: dict[str, tuple[str, ...]] = {
        # Keep old config values working, while allowing left/right bindings.
        "shift": ("lshift", "rshift"),
        "ctrl": ("lctrl", "rctrl"),
        "alt": ("lalt", "ralt"),
        "cmd": ("lcmd", "rcmd"),
    }

    def start(self) -> None:
        self._event_stop.clear()
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()
        self._hook_state = start_hooks(
            self._on_hook_key,
            self._on_hook_mouse,
            on_log=self.log.event,
            on_auto_fail_open=self._on_hook_auto_fail_open,
        )
        self.log.event("HK", "-", "listeners", "started")

    def stop(self) -> None:
        self._event_stop.set()
        if self._hook_state:
            stop_hooks(self._hook_state)
            self._hook_state = None

    def set_suppress(self, enable: bool) -> None:
        with self._lock:
            if self._suppress == enable:
                return
            self._suppress = enable

    def _bound_keys(self) -> set[str]:
        return set(self._bound_keys_cache)

    def set_key_blocking(self, enable: bool) -> None:
        if self._force_pass_through:
            self._suppress = False
            return
        self._suppress = enable

    def set_binding_callback(self, cb: Optional[Callable[[str], None]]) -> None:
        self._binding_cb = cb

    def define(self, hk: HotkeyDef) -> None:
        self._defs[hk.id] = hk
        self._refresh_bound_keys()
        self.log.event(
            "HK",
            hk.id,
            "define",
            f"key={hk.key_name} enabled={int(hk.is_enabled)} pass={int(hk.pass_through)}",
        )

    def update_key(self, hotkey_id: str, key_name: str) -> None:
        if hotkey_id in self._defs:
            self._defs[hotkey_id].key_name = key_name
            self._refresh_bound_keys()
            self.log.event("HK", hotkey_id, "updateKey", f"key={key_name}")
            self.set_key_blocking(self.is_context_enabled())

    def update_enabled(self, hotkey_id: str, enabled: bool) -> None:
        if hotkey_id in self._defs:
            self._defs[hotkey_id].is_enabled = enabled
            self._refresh_bound_keys()
            self.log.event("HK", hotkey_id, "updateEnabled", f"enabled={int(enabled)}")
            self.set_key_blocking(self.is_context_enabled())

    def is_pressed(self, key_name: str) -> bool:
        with self._pressed_lock:
            norm = self._norm(key_name)
            if norm in ("left", "right"):
                return self._pressed.get(norm, False)
            if norm in self._GENERIC_VARIANTS:
                if self._key_down.get(norm, False):
                    return True
                return any(self._key_down.get(v, False) for v in self._GENERIC_VARIANTS[norm])
            return self._key_down.get(norm, False)

    def spawn_if_needed(self, hotkey_id: str, run_fn: Callable[[threading.Event], None]) -> None:
        with self._lock:
            if hotkey_id in self._threads and self._threads[hotkey_id].is_alive():
                return
            stop_ev = threading.Event()
            th = threading.Thread(target=run_fn, args=(stop_ev,), daemon=True)
            self._stop_flags[hotkey_id] = stop_ev
            self._threads[hotkey_id] = th
            th.start()

    def stop_hotkey(self, hotkey_id: str) -> None:
        with self._lock:
            ev = self._stop_flags.get(hotkey_id)
            if ev:
                ev.set()

    def stop_all_hotkeys(self, hotkey_ids: Iterable[str] | None = None) -> None:
        with self._lock:
            ids = set(hotkey_ids) if hotkey_ids is not None else set(self._stop_flags)
            for hotkey_id in ids:
                ev = self._stop_flags.get(hotkey_id)
                if ev:
                    ev.set()

    def should_run(self, key_name: str, stop_ev: threading.Event) -> bool:
        if stop_ev.is_set():
            return False
        if not self.is_pressed(key_name):
            return False
        if not self.is_context_enabled():
            return False
        return True

    def wait_ms_cancel(self, ms: int, key_name: str, stop_ev: threading.Event) -> bool:
        return wait_ms_cancel(ms, lambda: stop_ev.is_set() or (not self.is_pressed(key_name)) or (not self.is_context_enabled()))

    def _norm(self, key_name: str) -> str:
        norm = key_name.strip().lower()
        # Shifted glyph for the same physical OEM_3 key
        if norm == "~":
            return "`"
        return norm

    def _expand_bound_key(self, norm: str) -> set[str]:
        keys = {norm}
        variants = self._GENERIC_VARIANTS.get(norm)
        if variants:
            keys.update(variants)
        return keys

    def _match_key(self, binding_norm: str, event_norm: str) -> bool:
        if binding_norm == event_norm:
            return True
        variants = self._GENERIC_VARIANTS.get(binding_norm)
        if variants and event_norm in variants:
            return True
        return False

    def _set_pressed(self, key_name: str, down: bool) -> None:
        with self._pressed_lock:
            self._pressed[self._norm(key_name)] = down

    def _set_key_down(self, key_name: str, down: bool) -> None:
        with self._pressed_lock:
            self._key_down[self._norm(key_name)] = down

    def _maybe_bind(self, name: str) -> bool:
        if self._binding_cb:
            self._binding_cb(name)
            return True
        return False

    def _maybe_trigger(self, name: str, is_down: bool) -> None:
        event_norm = self._norm(name)
        for hk in self._defs.values():
            if not hk.is_enabled:
                continue
            binding_norm = self._norm(hk.key_name)
            if not self._match_key(binding_norm, event_norm):
                continue
            if hk.on_event:
                hk.on_event(is_down)
                continue
            if not is_down:
                continue
            ctx = self.is_context_enabled()
            if not ctx:
                extra = self.context_info() if self.context_info else ""
                detail = f"ctx=0 key={hk.key_name} name={name}"
                if extra:
                    detail = detail + " " + extra
                continue
            self.spawn_if_needed(hk.id, hk.on_start)

    def _event_loop(self) -> None:
        while not self._event_stop.is_set():
            try:
                name, is_down = self._event_q.get(timeout=0.1)
            except Exception:
                continue
            if is_down and self._maybe_bind(name):
                continue
            self._maybe_trigger(name, is_down)

    def _refresh_bound_keys(self) -> None:
        keys: set[str] = set()
        blocking_keys: set[str] = set()
        for hk in self._defs.values():
            if not hk.is_enabled:
                continue
            expanded = self._expand_bound_key(self._norm(hk.key_name))
            keys.update(expanded)
            if not hk.pass_through:
                blocking_keys.update(expanded)
        self._bound_keys_cache = keys
        self._blocking_keys_cache = blocking_keys

    def _should_block(self, name: str) -> bool:
        if self._binding_cb:
            return False
        return self._norm(name) in self._blocking_keys_cache

    def _should_listen(self, name: str) -> bool:
        if self._binding_cb:
            return False
        return self._norm(name) in self._bound_keys_cache

    def _on_hook_key(self, name: str, is_down: bool) -> bool:
        if self._force_pass_through:
            return False
        if self._binding_cb and is_down:
            self._binding_cb(name)
            return False
        if self._should_listen(name):
            self._set_key_down(name, is_down)
            self._event_q.put((name, is_down))
            if self._suppress and self._should_block(name):
                return True
        return False

    def _on_hook_mouse(self, name: str, is_down: bool) -> bool:
        if self._force_pass_through:
            return False
        if name in ("left", "right"):
            self._set_pressed(name, is_down)
        if self._binding_cb and is_down:
            self._binding_cb(name)
            return False
        if self._should_block(name):
            # Track mouse-bound hotkeys (x1/x2/middle) via key_down state.
            self._set_key_down(name, is_down)
            if is_down:
                self._event_q.put((name, True))
                if self._suppress:
                    return True
            if self._suppress:
                return True
        return False

    def _on_hook_auto_fail_open(self) -> None:
        with self._lock:
            self._suppress = False
        self.log.event("SYS", "HookError", "autoFailOpen", "suppress=0")
