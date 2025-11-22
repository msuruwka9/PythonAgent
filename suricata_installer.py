"""Suricata installation helper module."""

from __future__ import annotations

import logging
import platform
import re
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
    
    # If config doesn't exist, download the default template
    if not config_file.exists():
        LOGGER.warning("Suricata config not found, downloading default template...")
        try:
            import urllib.request
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Try to download from official Suricata repository
            template_url = "https://raw.githubusercontent.com/OISF/suricata/suricata-6.0.4/suricata.yaml.in"
            LOGGER.info("Downloading config template from %s", template_url)
            
            with urllib.request.urlopen(template_url, timeout=30) as response:
                template_content = response.read().decode('utf-8')
            
            # Replace template variables with actual values
            template_content = template_content.replace("@e_enable_evelog@", "yes")
            template_content = template_content.replace("@e_default_log_dir@", "/var/log/suricata")
            template_content = template_content.replace("@e_runmode@", "autofp")
            
            config_file.write_text(template_content, encoding="utf-8")
            LOGGER.info("Config template downloaded and saved successfully")
            
        except Exception as exc:
            LOGGER.error("Failed to download config template: %s", exc)
            raise RuntimeError(f"Cannot create Suricata config: {exc}") from exc

    content = config_file.read_text(encoding="utf-8")
    
    # Update default-rule-path to use suricata-update managed rules
    if "default-rule-path:" in content:
        # Replace any existing rule path with the suricata-update managed path
        import re
        content = re.sub(
            r'default-rule-path:\s*.*',
            'default-rule-path: /var/lib/suricata/rules',
            content
        )
        LOGGER.info("Updated rule path to /var/lib/suricata/rules")
    
    # Enable EVE JSON logging if not already configured
    if "enabled: yes" not in content or "eve-log:" not in content:
        # Replace template variables that might still exist
        content = content.replace("@e_enable_evelog@", "yes")
        content = content.replace("enabled: @e_enable_evelog@", "enabled: yes")
        LOGGER.info("Enabled EVE JSON logging")
    
    # Ensure output file path is correct
    if eve_path not in content:
        content = re.sub(
            r'filename:\s*eve\.json',
            f'filename: {eve_path}',
            content
        )
        LOGGER.info("Set EVE log path to %s", eve_path)
    
    config_file.write_text(content, encoding="utf-8")
    LOGGER.info("Suricata configuration completed successfully")


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
