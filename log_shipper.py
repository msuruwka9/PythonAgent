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


def ship_batch(events: list[dict[str, Any]], endpoint: str, retries: int = 3, max_size_mb: int = 200) -> None:
    """Ship batch with size limit and automatic splitting if needed."""
    if not events:
        return

    # Check uncompressed size first
    payload = json.dumps(events).encode("utf-8")
    uncompressed_size_mb = len(payload) / (1024 * 1024)
    
    # If batch is too large, split it recursively
    if uncompressed_size_mb > max_size_mb:
        mid = len(events) // 2
        LOGGER.warning(
            "Batch too large (%.2f MB uncompressed), splitting %s events into two batches",
            uncompressed_size_mb,
            len(events),
        )
        ship_batch(events[:mid], endpoint, retries, max_size_mb)
        ship_batch(events[mid:], endpoint, retries, max_size_mb)
        return

    compressed = gzip.compress(payload)
    compressed_size_mb = len(compressed) / (1024 * 1024)
    
    LOGGER.debug(
        "Shipping batch: %s events, %.2f MB uncompressed, %.2f MB compressed (%.1f%% ratio)",
        len(events),
        uncompressed_size_mb,
        compressed_size_mb,
        (compressed_size_mb / uncompressed_size_mb * 100) if uncompressed_size_mb > 0 else 0,
    )

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                endpoint,
                data=compressed,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
                timeout=60,  # Increased timeout for large batches
            )
            response.raise_for_status()
            LOGGER.info("Uploaded %s events (%.2f MB compressed)", len(events), compressed_size_mb)
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
    estimated_buffer_size = 0  # Track approximate size in bytes
    max_buffer_size_mb = 150  # Start flushing earlier to avoid 200MB limit

    while not stop_event.is_set():
        try:
            item = event_queue.get(timeout=1)
            buffer.append(item)
            # Rough estimate: JSON serialized size
            estimated_buffer_size += len(json.dumps(item))
        except queue.Empty:
            pass

        buffer_size_mb = estimated_buffer_size / (1024 * 1024)
        time_since_flush = time.monotonic() - last_flush
        
        # Flush if: count limit OR size limit OR time limit
        should_flush = (
            len(buffer) >= batch_size
            or buffer_size_mb >= max_buffer_size_mb
            or (buffer and time_since_flush >= flush_interval)
        )
        
        if should_flush:
            if buffer_size_mb >= max_buffer_size_mb:
                LOGGER.debug("Flushing early due to size: %.2f MB estimated", buffer_size_mb)
            ship_batch(buffer, endpoint)
            buffer.clear()
            estimated_buffer_size = 0
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
