from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from .util import iter_project_files, utc_now


@dataclass(frozen=True)
class WatchObservation:
    observed_at: str
    paths: list[str]
    created: list[str]
    modified: list[str]
    deleted: list[str]


class PollingSourceWatcher:
    """Portable metadata watcher for an agent workspace.

    The background thread never touches SQLite or parses project code.  It only observes path/size/mtime
    tuples and queues candidates.  The owning HabitatWorkspace hashes and admits those candidates on the
    foreground request thread, keeping storage mutation deterministic and avoiding cross-thread DB access.
    """

    def __init__(self, root: Path, interval_s: float = 0.25, max_queue: int = 256):
        if interval_s < 0.05 or interval_s > 60:
            raise ValueError("watch interval_s must be in [0.05, 60]")
        if max_queue < 1 or max_queue > 10_000:
            raise ValueError("watch max_queue must be in [1, 10000]")
        self.root = root.resolve()
        self.interval_s = float(interval_s)
        self.max_queue = int(max_queue)
        self._cv = threading.Condition()
        self._queue: deque[WatchObservation] = deque(maxlen=max_queue)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = self._scan()
        self._dropped = 0
        self._scan_count = 1

    def _scan(self) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        for p in iter_project_files(self.root):
            try:
                st = p.stat()
            except OSError:
                continue
            out[p.relative_to(self.root).as_posix()] = (st.st_size, st.st_mtime_ns)
        return out

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="nolane-habitat-source-watcher", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            current = self._scan()
            with self._cv:
                previous = self._snapshot
                self._snapshot = current
                self._scan_count += 1
                created = sorted(set(current) - set(previous))
                deleted = sorted(set(previous) - set(current))
                modified = sorted(p for p in set(current) & set(previous) if current[p] != previous[p])
                paths = sorted(set(created) | set(deleted) | set(modified))
                if not paths:
                    continue
                if len(self._queue) == self.max_queue:
                    self._dropped += 1
                self._queue.append(WatchObservation(utc_now(), paths, created, modified, deleted))
                self._cv.notify_all()

    def poll(self, limit: int = 64) -> list[dict]:
        if limit < 1 or limit > 2000:
            raise ValueError("watch poll limit must be in [1, 2000]")
        with self._cv:
            out=[]
            while self._queue and len(out) < limit:
                out.append(asdict(self._queue.popleft()))
            return out

    def wait(self, timeout_s: float = 5.0, limit: int = 64) -> list[dict]:
        if timeout_s < 0 or timeout_s > 300:
            raise ValueError("watch timeout_s must be in [0, 300]")
        with self._cv:
            if not self._queue and timeout_s:
                self._cv.wait(timeout_s)
        return self.poll(limit)

    def status(self) -> dict:
        with self._cv:
            return {
                "running": bool(self._thread and self._thread.is_alive() and not self._stop.is_set()),
                "interval_s": self.interval_s,
                "queued_observations": len(self._queue),
                "dropped_observations": self._dropped,
                "scan_count": self._scan_count,
                "observed_paths": len(self._snapshot),
                "integrity_boundary": "metadata candidate detector only; consequential mutations still deep-hash",
            }

    def close(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(0.2, min(2.0, self.interval_s * 3)))
        self._thread = None
