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


def configure_suricata(config_path: str = "/etc/suricata/suricata.yaml",
                       eve_path: str = "/var/log/suricata/eve.json") -> None:
    LOGGER.info("Configuring Suricata logging (%s)", config_path)
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(config_path)

    content = config_file.read_text(encoding="utf-8")
    
    # Update default-rule-path to use suricata-update managed rules
    if "default-rule-path:" in content:
        content = content.replace(
            "default-rule-path: /etc/suricata/rules",
            "default-rule-path: /var/lib/suricata/rules"
        )
        LOGGER.info("Updated rule path to /var/lib/suricata/rules")
    
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
            "        - flow\n"
            "        - tls\n"
        )
    config_file.write_text(content, encoding="utf-8")


def enable_community_rules() -> None:
    LOGGER.info("Updating Suricata community rules and enabling ET Open")
    try:
        # Update sources list
        run_command(["suricata-update", "update-sources"])
        # Enable ET/Open ruleset explicitly
        run_command(["suricata-update", "enable-source", "et/open"])
        # Update and download rules
        run_command(["suricata-update"])
        LOGGER.info("ET Open rules successfully installed and enabled")
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Failed to enable ET Open rules: %s", exc)
        raise


def start_suricata(service_name: str = "suricata") -> None:
    LOGGER.info("Starting Suricata service")
    run_command(["systemctl", "enable", service_name])
    run_command(["systemctl", "restart", service_name])
