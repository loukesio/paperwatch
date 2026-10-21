"""Watch folders and rename PDFs as soon as a download finishes."""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from paperwatch.config import Config
from paperwatch.core import process

log = logging.getLogger(__name__)

# Partial-download files written by browsers before the final rename.
TEMP_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".tmp", ".opdownload")


def _interesting(path: Path) -> bool:
    name = path.name
    return (
        name.lower().endswith(".pdf")
        and not name.startswith(".")
        and not name.startswith("~$")
        and not any(name.lower().endswith(s) for s in TEMP_SUFFIXES)
    )


def wait_until_stable(path: Path, interval: float = 1.0, checks: int = 2, timeout: float = 300) -> bool:
    """Wait until the file size stops changing (the download has finished)."""
    deadline = time.monotonic() + timeout
    last, stable = -1, 0
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False  # moved away / deleted (e.g. browser renamed it again)
        if size > 0 and size == last:
            stable += 1
            if stable >= checks:
                return True
        else:
            stable = 0
        last = size
        time.sleep(interval)
    return False


class _Handler(FileSystemEventHandler):
    def __init__(self, q: "queue.Queue[Path]"):
        self.q = q

    def _push(self, p: str):
        path = Path(p)
        if _interesting(path):
            self.q.put(path)

    def on_created(self, event):
        if not event.is_directory:
            self._push(event.src_path)

    def on_moved(self, event):  # Chrome/Firefox/Safari rename the temp file when done
        if not event.is_directory:
            self._push(event.dest_path)

    def on_modified(self, event):  # some systems only report the final write
        if not event.is_directory:
            self._push(event.src_path)


class Watcher:
    def __init__(self, cfg: Config, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.q: "queue.Queue[Path]" = queue.Queue()
        self._pending: set[Path] = set()
        self._recent: dict[Path, float] = {}  # paths we produced or already handled
        self._lock = threading.Lock()

    def _should_handle(self, path: Path) -> bool:
        now = time.monotonic()
        with self._lock:
            self._recent = {p: t for p, t in self._recent.items() if now - t < 30}
            if path in self._pending or path in self._recent:
                return False
            self._pending.add(path)
            return True

    def _work(self, path: Path):
        try:
            if not wait_until_stable(path):
                return
            res = process(path, self.cfg, dry_run=self.dry_run)
            if res.renamed:
                verb = "would rename" if self.dry_run else "renamed"
                log.info("%s %s -> %s", verb, path.name, res.target.name)
                with self._lock:
                    self._recent[res.target] = time.monotonic()
            else:
                log.info("skipped %s: %s", path.name, res.reason or "already named")
        except Exception:
            log.exception("error while processing %s", path)
        finally:
            with self._lock:
                self._pending.discard(path)
                self._recent[path] = time.monotonic()

    def _dispatch(self):
        while True:
            path = self.q.get()
            if self._should_handle(path):
                threading.Thread(target=self._work, args=(path,), daemon=True).start()

    def run(self):
        observer = Observer()
        watched = 0
        for folder in self.cfg.folders:
            folder = Path(folder).expanduser()
            if not folder.is_dir():
                log.warning("folder does not exist, skipping: %s", folder)
                continue
            try:
                next(folder.iterdir(), None)
            except PermissionError:
                log.error(
                    "no permission to read %s. On macOS, give the Python/paperwatch binary "
                    "access under System Settings > Privacy & Security > Files and Folders "
                    "(or Full Disk Access).", folder)
                continue
            observer.schedule(_Handler(self.q), str(folder), recursive=False)
            log.info("watching %s", folder)
            watched += 1
        if not watched:
            raise SystemExit("nothing to watch")

        threading.Thread(target=self._dispatch, daemon=True).start()
        observer.start()
        try:
            while observer.is_alive():
                observer.join(1)
        except KeyboardInterrupt:
            log.info("stopping")
        finally:
            observer.stop()
            observer.join()
