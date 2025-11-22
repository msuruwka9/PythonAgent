"""Suricata installation helper module."""

from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("logmaster.suricata")
SUPPORTED_DISTROS = {"ubuntu", "debian", "centos", "rhel", "rocky", "alma", "fedora"}


class SuricataInstallationStatus:
    CONFIGURING = "SuricataConfiguring"
    CONFIGURED = "SuricataConfigured"
    FAILED = "SuricataFailed"


def detect_distro() -> str:
    """Return distro ID parsed from /etc/os-release."""
    if platform.system().lower() != "linux":
        raise RuntimeError("Suricata installer works only on Linux")

    try:
        with open("/etc/os-release", encoding="utf-8") as release_file:
            for line in release_file:
                if line.startswith("ID="):
                    distro_id = line.split("=", 1)[1].strip().strip('"').lower()
                    if distro_id in SUPPORTED_DISTROS:
                        return distro_id
                    raise RuntimeError(f"Unsupported distro {distro_id}")
    except FileNotFoundError as exc:
        raise RuntimeError("Cannot detect distro (missing /etc/os-release)") from exc

    raise RuntimeError("Unable to determine distro ID")


def run_command(command: list[str], sudo: bool = True) -> None:
    full_cmd = ["sudo"] + command if sudo and command[0] != "sudo" else command
    LOGGER.debug("Executing: %s", " ".join(full_cmd))
    subprocess.run(full_cmd, check=True, capture_output=True, text=True)


def install_suricata(distro: str) -> None:
    LOGGER.info("Installing Suricata packages (%s)", distro)
    if distro in {"ubuntu", "debian"}:
        run_command(["apt-get", "update"])
        run_command(["apt-get", "install", "-y", "suricata", "suricata-update"])
    elif distro in {"centos", "rhel", "rocky", "alma"}:
        run_command(["yum", "install", "-y", "epel-release"])
        run_command(["yum", "install", "-y", "suricata", "suricata-update"])
    elif distro == "fedora":
        run_command(["dnf", "install", "-y", "suricata", "suricata-update"])
    else:
        raise RuntimeError(f"Unsupported distro {distro}")


def get_default_interface() -> str:
    """Detect the default network interface."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Parse output like: "default via 192.168.1.1 dev eth0 ..."
        for line in result.stdout.split("\n"):
            if "default" in line and "dev" in line:
                parts = line.split()
                dev_idx = parts.index("dev") + 1
                if dev_idx < len(parts):
                    return parts[dev_idx]
    except Exception as exc:
        LOGGER.warning("Failed to detect default interface: %s", exc)
    
    # Fallback to common interface names
    for iface in ["eth0", "ens33", "enp0s3", "ens160"]:
        try:
            result = subprocess.run(
                ["ip", "link", "show", iface],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                LOGGER.info("Using fallback interface: %s", iface)
                return iface
        except Exception:
            continue
    
    raise RuntimeError("Cannot detect network interface for Suricata")


def configure_suricata(config_path: str = "/etc/suricata/suricata.yaml",
                       eve_path: str = "/var/log/suricata/eve.json") -> None:
    LOGGER.info("Configuring Suricata logging (%s)", config_path)
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(config_path)

    content = config_file.read_text(encoding="utf-8")
    
    # Detect and configure default interface
    try:
        interface = get_default_interface()
        LOGGER.info("Detected network interface: %s", interface)
        
        # Update af-packet interface section
        if "af-packet:" not in content or f"interface: {interface}" not in content:
            # Simple append - in production consider proper YAML parsing
            content += f"\naf-packet:\n  - interface: {interface}\n    cluster-id: 99\n    cluster-type: cluster_flow\n"
    except Exception as exc:
        LOGGER.warning("Could not configure interface: %s", exc)
    
    if "eve-log" not in content:
        content += (
            "\noutputs:\n"
            "  - eve-log:\n"
            "      enabled: yes\n"
            "      filetype: regular\n"
            f"      filename: {eve_path}\n"
            "      types:\n"
            "        - alert\n"
            "        - http\n"
            "        - dns\n"
            "        - tls\n"
            "        - files\n"
            "        - flow\n"
        )
    config_file.write_text(content, encoding="utf-8")


def enable_community_rules() -> None:
    LOGGER.info("Updating Suricata community rules")
    run_command(["suricata-update", "update-sources"])
    run_command(["suricata-update"])


def start_suricata(service_name: str = "suricata") -> None:
    LOGGER.info("Starting Suricata service")
    
    # Test configuration before starting
    try:
        LOGGER.debug("Testing Suricata configuration...")
        result = subprocess.run(
            ["suricata", "-T", "-c", "/etc/suricata/suricata.yaml"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            LOGGER.warning("Suricata configuration test failed: %s", result.stderr)
            # Continue anyway, as the agent's configure_suricata might fix it
    except Exception as exc:
        LOGGER.warning("Could not test Suricata configuration: %s", exc)
    
    # Ensure log directory exists with correct permissions
    try:
        run_command(["mkdir", "-p", "/var/log/suricata"], sudo=True)
        run_command(["chmod", "755", "/var/log/suricata"], sudo=True)
    except Exception as exc:
        LOGGER.warning("Could not set log directory permissions: %s", exc)
    
    # Enable and restart service
    try:
        run_command(["systemctl", "enable", service_name])
        run_command(["systemctl", "restart", service_name])
        
        # Wait a moment and check if it's running
        import time
        time.sleep(2)
        
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode != 0:
            # Try to get error details
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", "20", "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            LOGGER.error("Suricata failed to start. Recent logs:\n%s", result.stdout)
            raise RuntimeError(f"Suricata service failed to start. Check: journalctl -u {service_name} -xe")
        
        LOGGER.info("Suricata service started successfully")
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Failed to start Suricata: %s", exc)
        raise
