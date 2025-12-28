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
        self._check_file_rotation()
        self._process_existing_lines()

    def _load_offset(self) -> None:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.offset = data.get("offset", 0)
            except json.JSONDecodeError:
                self.offset = 0

    def _check_file_rotation(self) -> None:
        """Check if log file was rotated (offset > file size) and reset if needed."""
        if not self.file_path.exists():
            return
        file_size = self.file_path.stat().st_size
        if self.offset > file_size:
            LOGGER.warning(
                "Detected log rotation: offset (%d) > file size (%d). Resetting offset to 0.",
                self.offset, file_size
            )
            self.offset = 0
            self._save_offset()

    def _save_offset(self) -> None:
        STATE_FILE.write_text(json.dumps({"offset": self.offset}), encoding="utf-8")

    def _process_existing_lines(self) -> None:
        if not self.file_path.exists():
            LOGGER.warning("EVE log file does not exist: %s", self.file_path)
            return
        
        # Get file size BEFORE opening to ensure accurate measurement
        file_size = self.file_path.stat().st_size
        
        # Ensure offset doesn't exceed file size BEFORE seeking
        if self.offset > file_size:
            LOGGER.warning("Offset %d exceeds file size %d, resetting to 0", self.offset, file_size)
            self.offset = 0
            self._save_offset()
        
        LOGGER.info("Processing existing lines from offset %d, file size %d", self.offset, file_size)
        lines_processed = 0
        with self.file_path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            for line in handle:
                self._enqueue_line(line)
                lines_processed += 1
        
        # After processing, set offset to current file size (not handle.tell() which can be wrong)
        new_file_size = self.file_path.stat().st_size
        self.offset = new_file_size
        self._save_offset()
        LOGGER.info("Processed %d existing lines, new offset: %d", lines_processed, self.offset)

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
        # Check for file rotation before processing
        self._check_file_rotation()
        
        file_size = self.file_path.stat().st_size
        
        # Safety check
        if self.offset > file_size:
            LOGGER.warning("Offset %d > file size %d in process_new_lines, resetting", self.offset, file_size)
            self.offset = 0
            self._save_offset()
        
        with self.file_path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            for line in handle:
                self._enqueue_line(line)
        
        # Use file stat for new offset, not handle.tell()
        new_file_size = self.file_path.stat().st_size
        self.offset = new_file_size
        self._save_offset()

    def on_modified(self, event):  # type: ignore[override]
        LOGGER.debug("File modified event: %s", event.src_path)
        if Path(event.src_path) == self.file_path:
            LOGGER.debug("Processing new lines for %s", self.file_path)
            self.process_new_lines()


def ship_batch(events: list[dict[str, Any]], endpoint: str, server_guid: str, retries: int = 3, max_size_mb: int = 200) -> bool:
    """Ship batch with size limit and automatic splitting if needed. Returns True if successful."""
    if not events:
        return True
    
    # Validate server_guid is present
    if not server_guid or server_guid == "":
        LOGGER.error("Cannot ship batch: server_guid is missing or empty")
        return False

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
        result1 = ship_batch(events[:mid], endpoint, server_guid, retries, max_size_mb)
        time.sleep(0.5)  # Rate limit between split batches
        result2 = ship_batch(events[mid:], endpoint, server_guid, retries, max_size_mb)
        return result1 and result2

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
                    "X-LogMaster-ServerId": server_guid,
                },
                timeout=60,  # Increased timeout for large batches
            )
            response.raise_for_status()
            LOGGER.info("Uploaded %s events (%.2f MB compressed) for server %s", len(events), compressed_size_mb, server_guid)
            return True
        except requests.HTTPError as exc:
            if exc.response.status_code == 400:
                LOGGER.error("Server rejected batch: Invalid or unregistered ServerId %s - %s", server_guid, exc.response.text)
                return False  # Don't retry 400 errors - ServerId validation failed
            LOGGER.warning("Failed to upload events (attempt %s/%s): HTTP %s - %s", attempt, retries, exc.response.status_code, exc)
            time.sleep(attempt * 5)
        except requests.RequestException as exc:
            LOGGER.warning("Failed to upload events (attempt %s/%s): %s", attempt, retries, exc)
            time.sleep(attempt * 5)

    LOGGER.error("Giving up after %s attempts uploading %s events for server %s", retries, len(events), server_guid)
    return False


def worker_loop(event_queue: "queue.Queue[dict[str, Any]]",
                endpoint: str,
                server_guid: str,
                batch_size: int,
                flush_interval: int,
                stop_event: threading.Event) -> None:
    buffer: list[dict[str, Any]] = []
    last_flush = time.monotonic()
    estimated_buffer_size = 0  # Track approximate size in bytes
    max_buffer_size_mb = 150  # Start flushing earlier to avoid 200MB limit
    
    # Use larger batch size for catching up with backlog (10x normal)
    catchup_batch_size = batch_size * 10  # e.g., 1000 instead of 100
    min_delay_between_uploads = 0.2  # 200ms minimum between uploads to avoid rate limiting

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
        queue_size = event_queue.qsize()
        
        # Use larger batch size when queue is large (catching up with backlog)
        effective_batch_size = catchup_batch_size if queue_size > 1000 else batch_size
        
        # Flush if: count limit OR size limit OR time limit
        should_flush = (
            len(buffer) >= effective_batch_size
            or buffer_size_mb >= max_buffer_size_mb
            or (buffer and time_since_flush >= flush_interval)
        )
        
        if should_flush:
            if queue_size > 1000:
                LOGGER.info("Catching up: queue has %d items, using batch size %d", queue_size, effective_batch_size)
            if buffer_size_mb >= max_buffer_size_mb:
                LOGGER.debug("Flushing early due to size: %.2f MB estimated", buffer_size_mb)
            
            ship_batch(buffer, endpoint, server_guid)
            buffer.clear()
            estimated_buffer_size = 0
            last_flush = time.monotonic()
            
            # Rate limit: wait between uploads to avoid overwhelming ngrok/server
            time.sleep(min_delay_between_uploads)

    if buffer:
        ship_batch(buffer, endpoint, server_guid)


def start_log_shipper(eve_log: str,
                      endpoint: str,
                      server_guid: str,
                      batch_size: int,
                      flush_interval: int) -> None:
    LOGGER.info("Starting log shipper: eve_log=%s, endpoint=%s, server_guid=%s, batch_size=%d, flush_interval=%d",
                eve_log, endpoint, server_guid, batch_size, flush_interval)
    
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
        args=(event_queue, endpoint, server_guid, batch_size, flush_interval, stop_event),
        daemon=True,
    )
    worker.start()

    LOGGER.info("Log shipper started for server %s", server_guid)

    return stop_event, observer
