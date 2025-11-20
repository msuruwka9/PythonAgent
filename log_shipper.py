"""Suricata EVE JSON log shipper."""

from __future__ import annotations

import gzip
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

LOGGER = logging.getLogger("logmaster.logshipper")
STATE_FILE = Path("/var/lib/logmaster-agent/offset.json")


class EveLogHandler(FileSystemEventHandler):
    def __init__(self, file_path: Path, event_queue: "queue.Queue[dict[str, Any]]") -> None:
        self.file_path = file_path
        self.queue = event_queue
        self.offset = 0
        self._load_offset()
        self._process_existing_lines()

    def _load_offset(self) -> None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.offset = data.get("offset", 0)
            except json.JSONDecodeError:
                self.offset = 0

    def _save_offset(self) -> None:
        STATE_FILE.write_text(json.dumps({"offset": self.offset}), encoding="utf-8")

    def _process_existing_lines(self) -> None:
        if not self.file_path.exists():
            return
        with self.file_path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            for line in handle:
                self._enqueue_line(line)
            self.offset = handle.tell()
            self._save_offset()

    def _enqueue_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            payload = json.loads(line)
            self.queue.put(payload)
        except json.JSONDecodeError:
            LOGGER.debug("Skipping invalid JSON line")

    def process_new_lines(self) -> None:
        with self.file_path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            for line in handle:
                self._enqueue_line(line)
            self.offset = handle.tell()
            self._save_offset()

    def on_modified(self, event):  # type: ignore[override]
        if Path(event.src_path) == self.file_path:
            self.process_new_lines()


def ship_batch(events: list[dict[str, Any]], endpoint: str, retries: int = 3) -> None:
    if not events:
        return

    payload = json.dumps(events).encode("utf-8")
    compressed = gzip.compress(payload)

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                endpoint,
                data=compressed,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
                timeout=30,
            )
            response.raise_for_status()
            LOGGER.info("Uploaded %s events", len(events))
            return
        except requests.RequestException as exc:
            LOGGER.warning("Failed to upload events (attempt %s/%s): %s", attempt, retries, exc)
            time.sleep(attempt * 5)

    LOGGER.error("Giving up after %s attempts uploading %s events", retries, len(events))


def worker_loop(event_queue: "queue.Queue[dict[str, Any]]",
                endpoint: str,
                batch_size: int,
                flush_interval: int,
                stop_event: threading.Event) -> None:
    buffer: list[dict[str, Any]] = []
    last_flush = time.monotonic()

    while not stop_event.is_set():
        try:
            item = event_queue.get(timeout=1)
            buffer.append(item)
        except queue.Empty:
            pass

        should_flush = len(buffer) >= batch_size or (buffer and (time.monotonic() - last_flush) >= flush_interval)
        if should_flush:
            ship_batch(buffer, endpoint)
            buffer.clear()
            last_flush = time.monotonic()

    if buffer:
        ship_batch(buffer, endpoint)


def start_log_shipper(eve_log: str,
                      endpoint: str,
                      batch_size: int,
                      flush_interval: int) -> None:
    if not endpoint:
        LOGGER.warning("Log upload endpoint is not configured; skipping log shipper")
        return

    log_path = Path(eve_log)
    if not log_path.exists():
        LOGGER.info("Creating missing EVE log path %s", eve_log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    event_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
    stop_event = threading.Event()

    handler = EveLogHandler(log_path, event_queue)
    observer = Observer()
    observer.schedule(handler, log_path.parent, recursive=False)
    observer.start()

    worker = threading.Thread(
        target=worker_loop,
        args=(event_queue, endpoint, batch_size, flush_interval, stop_event),
        daemon=True,
    )
    worker.start()

    return stop_event, observer
