#!/usr/bin/env python3
"""LogMaster Python agent orchestrating Suricata installation and monitoring."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

from log_shipper import start_log_shipper
from suricata_installer import (
    SuricataInstallationStatus,
    configure_suricata,
    detect_distro,
    enable_community_rules,
    install_suricata,
    start_suricata,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("logmaster.agent")


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def send_heartbeat(config: dict[str, Any], status: str, message: str = "") -> None:
    payload = {
        "ServerGuid": config["server_guid"],
        "AgentVersion": config.get("agent_version", "1.0.0"),
        "Status": status,
        "SuricataInstalled": status == SuricataInstallationStatus.CONFIGURED,
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Message": message,
        "Hostname": socket.gethostname(),
    }
    endpoint = config.get("heartbeat_endpoint") or f"{config['api_url'].rstrip('/')}/api/agent/heartbeat"
    try:
        response = requests.post(endpoint, json=payload, timeout=15)
        response.raise_for_status()
        LOGGER.info("Heartbeat sent: %s", status)
    except requests.RequestException as exc:
        LOGGER.warning("Failed to send heartbeat: %s", exc)


def check_suricata_status() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "suricata"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("Unable to check Suricata status: %s", exc)
        return False


def orchestrate_installation(config: dict[str, Any]) -> str:
    """Install/configure Suricata only if needed, otherwise skip to monitoring."""
    try:
        # Check if Suricata is already running
        if check_suricata_status():
            LOGGER.info("Suricata is already active, skipping installation")
            send_heartbeat(config, SuricataInstallationStatus.CONFIGURED, "Suricata already configured")
            return SuricataInstallationStatus.CONFIGURED

        # Check if auto_install is disabled in config
        if not config.get("suricata", {}).get("auto_install", True):
            LOGGER.warning("Suricata not running and auto_install=false, sending AgentInstalled status")
            send_heartbeat(config, "AgentInstalled", "Suricata auto-install disabled")
            return "AgentInstalled"

        send_heartbeat(config, SuricataInstallationStatus.CONFIGURING, "Starting Suricata installation")
        distro = detect_distro()
        install_suricata(distro)
        configure_suricata(
            config["suricata"].get("config_path", "/etc/suricata/suricata.yaml"),
            config["suricata"].get("eve_log_path", "/var/log/suricata/eve.json"),
        )
        enable_community_rules()
        start_suricata(config["suricata"].get("service_name", "suricata"))
        send_heartbeat(config, SuricataInstallationStatus.CONFIGURED, "Suricata configured successfully")
        return SuricataInstallationStatus.CONFIGURED
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Suricata installation failed: %s", exc)
        send_heartbeat(config, SuricataInstallationStatus.FAILED, str(exc))
        return SuricataInstallationStatus.FAILED


def heartbeat_loop(config: dict[str, Any], stop_event: threading.Event) -> None:
    interval = config.get("heartbeat_interval_seconds", 60)
    while not stop_event.is_set():
        status = SuricataInstallationStatus.CONFIGURED if check_suricata_status() else "AgentInstalled"
        send_heartbeat(config, status)
        stop_event.wait(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="LogMaster Suricata Agent")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        LOGGER.error("Config file %s not found", config_path)
        sys.exit(1)

    config = load_config(config_path)
    install_status = orchestrate_installation(config)

    # Continue monitoring even if installation was skipped or partial
    if install_status == SuricataInstallationStatus.FAILED:
        LOGGER.error("Installation failed, exiting")
        sys.exit(1)

    stop_event = threading.Event()

    def handle_stop(signum: int, _: Any) -> None:  # type: ignore[override]
        LOGGER.info("Received signal %s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    heartbeat_thread = threading.Thread(target=heartbeat_loop, args=(config, stop_event), daemon=True)
    heartbeat_thread.start()

    start_log_shipper(
        config["suricata"].get("eve_log_path", "/var/log/suricata/eve.json"),
        config.get("log_upload_endpoint"),
        config["log_shipper"].get("batch_size", 100),
        config["log_shipper"].get("flush_interval_seconds", 30),
    )

    while not stop_event.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main()

