"""Playback logger with timestamped history."""

import json
import threading
import time
from pathlib import Path
from collections import deque


class PlayLog:
    """Thread-safe playback logger. Keeps in-memory ring buffer + optional file."""

    def __init__(self, log_file: str | None = None, maxlen: int = 500):
        self._log = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._log_file = Path(log_file) if log_file else None
        if self._log_file:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def record(self, key: str, sound: str, source: str, ok: bool = True) -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": time.time(),
            "key": key,
            "sound": sound,
            "source": source,  # "keyboard", "esp32", "web", "midi", "serial", "udp"
            "ok": ok,
        }
        with self._lock:
            self._log.append(entry)
        if self._log_file:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._log)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._log.clear()

    def stats(self) -> dict:
        with self._lock:
            total = len(self._log)
            by_sound = {}
            by_source = {}
            for e in self._log:
                by_sound[e["sound"]] = by_sound.get(e["sound"], 0) + 1
                by_source[e["source"]] = by_source.get(e["source"], 0) + 1
            return {
                "total": total,
                "by_sound": by_sound,
                "by_source": by_source,
            }
