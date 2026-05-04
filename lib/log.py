from __future__ import annotations

import datetime
import os
import queue
import threading
from pathlib import Path


def default_log_dir(app_name: str) -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / app_name / "Logs"
    return Path.home() / "Documents" / f"{app_name}Settings" / "Logs"


def session_log_path(app_name: str) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return default_log_dir(app_name) / f"{app_name}_{ts}_{os.getpid()}.log"


class Logger:
    def __init__(self, log_path: Path, enabled: bool = True) -> None:
        self.log_path = log_path
        self._rate_limited: dict[str, float] = {}
        self._rate_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._write_q: queue.Queue[str | None] | None = None
        self._writer: threading.Thread | None = None
        self._enabled = False
        if enabled:
            self.set_enabled(True)

    def is_enabled(self) -> bool:
        with self._state_lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        q: queue.Queue[str | None] | None = None
        writer: threading.Thread | None = None
        with self._state_lock:
            if enabled == self._enabled:
                return
            if enabled:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_q = queue.Queue()
                self._writer = threading.Thread(target=self._write_loop, args=(self._write_q,), daemon=True)
                self._enabled = True
                self._writer.start()
                return
            q = self._write_q
            writer = self._writer
            self._write_q = None
            self._writer = None
            self._enabled = False
        if q:
            q.put(None)
        if writer:
            writer.join(timeout=2.0)

    def write(self, line: str) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"{ts} - {line}\n"
        with self._state_lock:
            if not self._enabled or self._write_q is None:
                return
            self._write_q.put(formatted)
            return

    def event(self, cat: str, ident: str, action: str, detail: str = "") -> None:
        if detail:
            self.write(f"LOG | {cat} | {ident} | {action} | {detail}")
        else:
            self.write(f"LOG | {cat} | {ident} | {action}")

    def event_rate_limited(
        self,
        key: str,
        interval_sec: float,
        cat: str,
        ident: str,
        action: str,
        detail: str = "",
    ) -> None:
        if not self.is_enabled():
            return
        now = datetime.datetime.now().timestamp()
        with self._rate_lock:
            last = self._rate_limited.get(key, 0.0)
            if now - last < interval_sec:
                return
            self._rate_limited[key] = now
        self.event(cat, ident, action, detail)

    def flush(self) -> None:
        with self._state_lock:
            q = self._write_q
        if q:
            q.join()

    def close(self) -> None:
        self.set_enabled(False)

    def _write_loop(self, q: queue.Queue[str | None]) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            while True:
                line = q.get()
                try:
                    if line is None:
                        return
                    f.write(line)
                    f.flush()
                finally:
                    q.task_done()
