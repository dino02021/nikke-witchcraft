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
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._rate_limited: dict[str, float] = {}
        self._rate_lock = threading.Lock()
        self._write_q: queue.Queue[str | None] = queue.Queue()
        self._closed = threading.Event()
        self._writer = threading.Thread(target=self._write_loop, daemon=True)
        self._writer.start()

    def write(self, line: str) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"{ts} - {line}\n"
        if self._closed.is_set():
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(formatted)
            return
        self._write_q.put(formatted)

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
        now = datetime.datetime.now().timestamp()
        with self._rate_lock:
            last = self._rate_limited.get(key, 0.0)
            if now - last < interval_sec:
                return
            self._rate_limited[key] = now
        self.event(cat, ident, action, detail)

    def flush(self) -> None:
        self._write_q.join()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._write_q.put(None)
        self._writer.join(timeout=2.0)
        self._closed.set()

    def _write_loop(self) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            while True:
                line = self._write_q.get()
                try:
                    if line is None:
                        return
                    f.write(line)
                    f.flush()
                finally:
                    self._write_q.task_done()
