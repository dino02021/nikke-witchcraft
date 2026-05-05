from __future__ import annotations

import threading
import queue
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .timing import WaitProfile, wait_ms_cancel
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
    on_release: Optional[Callable[[], None]] = None


class HotkeyManager:
    _CANCEL_WAIT_PROFILE = WaitProfile(long_ms=14, mid_ms=1, short_ms=0)

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
        self._binding_q: queue.Queue[str] = queue.Queue()
        self._suppress = False
        self._force_pass_through = False
        self._hook_state = None
        self._hook_lock = threading.RLock()
        self._running = False
        self._mouse_hook_enabled = False
        self._bound_keys_cache: set[str] = set()
        self._blocking_keys_cache: set[str] = set()

    _GENERIC_VARIANTS: dict[str, tuple[str, ...]] = {
        # Keep old config values working, while allowing left/right bindings.
        "shift": ("lshift", "rshift"),
        "ctrl": ("lctrl", "rctrl"),
        "alt": ("lalt", "ralt"),
        "cmd": ("lcmd", "rcmd"),
    }
    _MOUSE_KEYS = {"left", "right", "middle", "x1", "x2"}

    def start(self) -> None:
        self._event_stop.clear()
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()
        with self._hook_lock:
            self._running = True
            self._restart_hooks_locked()
        self.log.event("HK", "-", "listeners", "started")

    def stop(self) -> None:
        self.stop_all_hotkeys()
        self._event_stop.set()
        with self._hook_lock:
            self._running = False
            if self._hook_state:
                stop_hooks(self._hook_state)
                self._hook_state = None
            self._mouse_hook_enabled = False
        if self._event_thread and self._event_thread.is_alive():
            self._event_thread.join(timeout=1.0)
        self._join_workers(timeout_per_thread=0.5)
        self._clear_all_key_state()

    def set_suppress(self, enable: bool) -> None:
        with self._lock:
            if self._suppress == enable:
                return
            self._suppress = enable
        self.log.event("HK", "-", "suppress", f"enabled={int(enable)}")

    def _bound_keys(self) -> set[str]:
        return set(self._bound_keys_cache)

    def set_key_blocking(self, enable: bool) -> None:
        if self._force_pass_through:
            self._suppress = False
            self.log.event("HK", "-", "blocking", "enabled=0 force_pass=1")
            return
        if self._suppress == enable:
            return
        self._suppress = enable
        blocking = ",".join(sorted(self._blocking_keys_cache)) or "-"
        self.log.event("HK", "-", "blocking", f"enabled={int(enable)} keys={blocking}")

    def set_binding_callback(self, cb: Optional[Callable[[str], None]]) -> None:
        self._binding_cb = cb
        if cb is None:
            self._clear_binding_queue()
        self._sync_hooks()

    def poll_binding_key(self) -> str | None:
        try:
            return self._binding_q.get_nowait()
        except queue.Empty:
            return None

    def define(self, hk: HotkeyDef) -> None:
        self._defs[hk.id] = hk
        self._refresh_bound_keys()
        self._sync_hooks()
        self.log.event(
            "HK",
            hk.id,
            "define",
            f"key={hk.key_name} enabled={int(hk.is_enabled)} pass={int(hk.pass_through)}",
        )

    def update_key(self, hotkey_id: str, key_name: str) -> None:
        if hotkey_id in self._defs:
            if self._defs[hotkey_id].key_name == key_name:
                return
            old_key = self._defs[hotkey_id].key_name
            with self._lock:
                self._request_stop_locked(hotkey_id)
            self._defs[hotkey_id].key_name = key_name
            self._refresh_bound_keys()
            self._clear_key_state(old_key)
            self.log.event("HK", hotkey_id, "updateKey", f"key={key_name}")
            self.set_key_blocking(self.is_context_enabled())
            self._sync_hooks()

    def update_enabled(self, hotkey_id: str, enabled: bool) -> None:
        if hotkey_id in self._defs:
            if self._defs[hotkey_id].is_enabled == enabled:
                return
            old_key = self._defs[hotkey_id].key_name
            if not enabled:
                with self._lock:
                    self._request_stop_locked(hotkey_id)
            self._defs[hotkey_id].is_enabled = enabled
            self._refresh_bound_keys()
            if not enabled:
                self._clear_key_state(old_key)
            self.log.event("HK", hotkey_id, "updateEnabled", f"enabled={int(enabled)}")
            self.set_key_blocking(self.is_context_enabled())
            self._sync_hooks()

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
                self.log.event("HK", hotkey_id, "spawnSkip", "reason=already_running")
                return
            stop_ev = threading.Event()
            th = threading.Thread(target=run_fn, args=(stop_ev,), daemon=True)
            self._stop_flags[hotkey_id] = stop_ev
            self._threads[hotkey_id] = th
            th.start()
        self.log.event("HK", hotkey_id, "spawn", "started=1")

    def stop_hotkey(self, hotkey_id: str) -> None:
        with self._lock:
            self._request_stop_locked(hotkey_id)

    def stop_all_hotkeys(self, hotkey_ids: Iterable[str] | None = None) -> None:
        with self._lock:
            ids = set(hotkey_ids) if hotkey_ids is not None else set(self._stop_flags)
            for hotkey_id in ids:
                ev = self._stop_flags.get(hotkey_id)
                if ev:
                    ev.set()
            self.log.event("HK", "-", "stopRequest", f"scope=all count={len(ids)}")

    def should_run(self, key_name: str, stop_ev: threading.Event) -> bool:
        if stop_ev.is_set():
            return False
        if not self.is_pressed(key_name):
            return False
        if not self.is_context_enabled():
            return False
        return True

    def wait_ms_cancel(self, ms: int, key_name: str, stop_ev: threading.Event) -> bool:
        return wait_ms_cancel(
            ms,
            lambda: stop_ev.is_set() or (not self.is_pressed(key_name)) or (not self.is_context_enabled()),
            self._CANCEL_WAIT_PROFILE,
        )

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

    def _clear_key_state(self, key_name: str) -> None:
        norm = self._norm(key_name)
        if norm in self._bound_keys_cache:
            return
        with self._pressed_lock:
            self._key_down.pop(norm, None)
            self._pressed.pop(norm, None)

    def _clear_all_key_state(self) -> None:
        with self._pressed_lock:
            self._key_down.clear()
            self._pressed.clear()

    def _request_stop_locked(self, hotkey_id: str) -> None:
        ev = self._stop_flags.get(hotkey_id)
        if ev:
            ev.set()
            self.log.event("HK", hotkey_id, "stopRequest", "scope=single")

    def _join_workers(self, timeout_per_thread: float) -> None:
        with self._lock:
            threads = list(self._threads.items())
        for hotkey_id, thread in threads:
            if thread.is_alive():
                thread.join(timeout=timeout_per_thread)
                self.log.event("HK", hotkey_id, "workerJoin", f"alive={int(thread.is_alive())}")

    def _clear_binding_queue(self) -> None:
        while True:
            try:
                self._binding_q.get_nowait()
            except queue.Empty:
                return

    def _maybe_bind(self, name: str) -> bool:
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
                self._log_trigger(hk, name, is_down, "event")
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
                self.log.event("HK", hk.id, "contextSkip", detail)
                continue
            self._log_trigger(hk, name, is_down, "start")
            self.spawn_if_needed(hk.id, hk.on_start)

    def _release_outputs_for_trigger(self, name: str) -> None:
        event_norm = self._norm(name)
        for hk in self._defs.values():
            if not hk.is_enabled or not hk.on_release:
                continue
            binding_norm = self._norm(hk.key_name)
            if self._match_key(binding_norm, event_norm):
                hk.on_release()

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
        with self._pressed_lock:
            for key in list(self._key_down):
                if key not in keys:
                    self._key_down.pop(key, None)
            for mouse_button in ("left", "right"):
                if mouse_button not in keys:
                    self._pressed.pop(mouse_button, None)

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
            self._binding_q.put(name)
            return False
        if self._should_listen(name):
            should_block = self._should_block(name)
            self._set_key_down(name, is_down)
            if not is_down:
                self._release_outputs_for_trigger(name)
            self._event_q.put((name, is_down))
            if is_down:
                self._log_hook_event("key", name, is_down, should_block)
            if self._suppress and should_block:
                self._log_blocked_event("key", name, is_down)
                return True
        return False

    def _on_hook_mouse(self, name: str, is_down: bool) -> bool:
        if self._force_pass_through:
            return False
        if self._binding_cb and is_down:
            self._binding_q.put(name)
            return False
        if not self._should_listen(name):
            return False
        should_block = self._should_block(name)
        self._set_key_down(name, is_down)
        if name in ("left", "right"):
            self._set_pressed(name, is_down)
            if is_down:
                self._log_left_right_mouse_diag(name, should_block)
        if not is_down:
            self._release_outputs_for_trigger(name)
        if name in ("middle", "x1", "x2", "left", "right"):
            self.log.event(
                "HK",
                "MouseTrigger",
                "hook",
                f"button={name} down={int(is_down)} suppress={int(self._suppress)} should_block={int(should_block)}",
            )
        self._event_q.put((name, is_down))
        if self._suppress and should_block:
            self._log_blocked_event("mouse", name, is_down)
            return True
        return False

    def _log_left_right_mouse_diag(self, name: str, should_block: bool) -> None:
        action = "leftRightBlockCandidate" if should_block else "leftRightPass"
        interval = 1.0 if should_block else 10.0
        blocking = ",".join(sorted(self._blocking_keys_cache)) or "-"
        bound = ",".join(sorted(self._bound_keys_cache)) or "-"
        detail = (
            f"button={name} suppress={int(self._suppress)} should_block={int(should_block)} "
            f"blocking={blocking} bound={bound}"
        )
        self.log.event_rate_limited(f"mouse:{name}:{action}", interval, "HK", "MouseDiag", action, detail)

    def _log_hook_event(self, device: str, name: str, is_down: bool, should_block: bool) -> None:
        detail = (
            f"device={device} key={name} down={int(is_down)} suppress={int(self._suppress)} "
            f"should_block={int(should_block)} {self._key_snapshot()}"
        )
        self.log.event_rate_limited(f"hook:{device}:{name}:{int(is_down)}", 1.0, "HK", "HookEvent", "listen", detail)

    def _log_blocked_event(self, device: str, name: str, is_down: bool) -> None:
        detail = f"device={device} key={name} down={int(is_down)} suppress={int(self._suppress)} {self._key_snapshot()}"
        self.log.event_rate_limited(f"block:{device}:{name}:{int(is_down)}", 0.5, "HK", "HookEvent", "blocked", detail)

    def _log_trigger(self, hk: HotkeyDef, name: str, is_down: bool, action: str) -> None:
        detail = (
            f"id={hk.id} bound={hk.key_name} event={name} down={int(is_down)} "
            f"pass={int(hk.pass_through)} {self._context_detail()}"
        )
        self.log.event_rate_limited(f"trigger:{hk.id}:{name}:{action}:{int(is_down)}", 0.5, "HK", hk.id, action, detail)

    def _key_snapshot(self) -> str:
        blocking = ",".join(sorted(self._blocking_keys_cache)) or "-"
        bound = ",".join(sorted(self._bound_keys_cache)) or "-"
        return f"blocking={blocking} bound={bound}"

    def _context_detail(self) -> str:
        extra = self.context_info() if self.context_info else ""
        return extra or "context=-"

    def _on_hook_auto_fail_open(self) -> None:
        with self._lock:
            self._suppress = False
        self.log.event("SYS", "HookError", "autoFailOpen", "suppress=0")

    def _mouse_hook_filter(self, name: str) -> bool:
        if self._binding_cb:
            return True
        return self._norm(name) in self._bound_keys_cache

    def _needs_mouse_hook(self) -> bool:
        if self._binding_cb:
            return True
        return any(key in self._MOUSE_KEYS for key in self._bound_keys_cache)

    def _sync_hooks(self) -> None:
        with self._hook_lock:
            if not self._running:
                return
            needs_mouse = self._needs_mouse_hook()
            if self._hook_state and needs_mouse == self._mouse_hook_enabled:
                return
            self._restart_hooks_locked()

    def _restart_hooks_locked(self) -> None:
        if self._hook_state:
            stop_hooks(self._hook_state)
            self._hook_state = None
        needs_mouse = self._needs_mouse_hook()
        self._mouse_hook_enabled = needs_mouse
        self._hook_state = start_hooks(
            self._on_hook_key,
            self._on_hook_mouse,
            on_log=self.log.event,
            on_auto_fail_open=self._on_hook_auto_fail_open,
            enable_mouse=needs_mouse,
            mouse_filter=self._mouse_hook_filter,
        )
