"""Suricata installation helper module."""

from __future__ import annotations

import logging
import os
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


def detect_network_interface() -> str:
    """Detect the primary network interface for Suricata to monitor."""
    try:
        # Try to find default route interface
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        # Parse output like: "default via 192.168.1.1 dev eth0 ..."
        for line in result.stdout.split('\n'):
            if 'default' in line and 'dev' in line:
                parts = line.split()
                if 'dev' in parts:
                    dev_idx = parts.index('dev')
                    if dev_idx + 1 < len(parts):
                        interface = parts[dev_idx + 1]
                        LOGGER.info("Detected primary network interface: %s", interface)
                        return interface
    except Exception as exc:
        LOGGER.warning("Failed to detect interface via ip route: %s", exc)
    
    # Fallback: try common interface names
    try:
        result = subprocess.run(
            ["ip", "link", "show"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        # Look for UP interfaces that are not loopback
        for line in result.stdout.split('\n'):
            if 'state UP' in line or 'state UNKNOWN' in line:
                # Parse line like: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> ..."
                match = re.search(r'\d+:\s+(\S+):', line)
                if match:
                    interface = match.group(1)
                    if interface != 'lo' and not interface.startswith('docker'):
                        LOGGER.info("Found active interface: %s", interface)
                        return interface
    except Exception as exc:
        LOGGER.warning("Failed to detect interface via ip link: %s", exc)
    
    # Last resort: try common names
    common_interfaces = ['eth0', 'ens33', 'ens3', 'enp0s3', 'eno1']
    for iface in common_interfaces:
        try:
            result = subprocess.run(
                ["ip", "link", "show", iface],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            if result.returncode == 0:
                LOGGER.info("Using fallback interface: %s", iface)
                return iface
        except Exception:
            continue
    
    raise RuntimeError(
        "Could not detect any network interface. "
        "Please configure Suricata manually with 'af-packet.interface' setting."
    )


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
    """Execute a shell command with optional sudo."""
    # Don't use sudo if we're already root (UID 0)
    needs_sudo = sudo and os.geteuid() != 0 and command[0] != "sudo"
    full_cmd = ["sudo"] + command if needs_sudo else command
    LOGGER.debug("Executing: %s", " ".join(full_cmd))
    
    try:
        result = subprocess.run(
            full_cmd, 
            check=True, 
            capture_output=True, 
            text=True
        )
        if result.stdout:
            LOGGER.debug("Command stdout: %s", result.stdout.strip())
        if result.stderr:
            LOGGER.debug("Command stderr: %s", result.stderr.strip())
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Command failed: %s", " ".join(full_cmd))
        if exc.stdout:
            LOGGER.error("stdout: %s", exc.stdout.strip())
        if exc.stderr:
            LOGGER.error("stderr: %s", exc.stderr.strip())
        raise


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
    LOGGER.info("Configuring Suricata logging and network interface (%s)", config_path)
    config_file = Path(config_path)
    
    # Verify config exists (should exist after apt install)
    if not config_file.exists():
        raise RuntimeError(
            f"Suricata config not found at {config_path}. "
            "Ensure 'apt-get install suricata' completed successfully."
        )

    content = config_file.read_text(encoding="utf-8")
    
    # Detect network interface
    try:
        interface = detect_network_interface()
        LOGGER.info("Configuring Suricata to monitor interface: %s", interface)
    except Exception as exc:
        LOGGER.error("Failed to detect network interface: %s", exc)
        raise

    # Configure af-packet interface
    # Look for af-packet section and update interface
    af_packet_pattern = r'(af-packet:\s*\n(?:\s+-\s+interface:)[^\n]*)'
    if re.search(r'af-packet:', content):
        # Replace existing af-packet interface configuration
        content = re.sub(
            r'(\s+interface:\s+)\S+',
            rf'\1{interface}',
            content,
            count=1
        )
        LOGGER.info("Updated af-packet interface to %s", interface)
    else:
        # If no af-packet section exists, add basic configuration
        af_packet_config = f"""
# LogMaster Agent: AF_PACKET configuration
af-packet:
  - interface: {interface}
    cluster-id: 99
    cluster-type: cluster_flow
    defrag: yes
    use-mmap: yes
    tpacket-v3: yes
"""
        content += af_packet_config
        LOGGER.info("Added af-packet configuration for %s", interface)
    
    # Update default-rule-path to use suricata-update managed rules
    if "default-rule-path:" in content:
        content = re.sub(
            r'default-rule-path:\s*.*',
            'default-rule-path: /var/lib/suricata/rules',
            content
        )
        LOGGER.info("Updated rule path to /var/lib/suricata/rules")
    
    # Ensure EVE JSON logging is enabled
    # Look for eve-log section and ensure it's enabled
    if re.search(r'eve-log:', content):
        # Make sure enabled is set to yes
        content = re.sub(
            r'(eve-log:.*?enabled:\s*)\S+',
            r'\1yes',
            content,
            flags=re.DOTALL
        )
        # Update filetype to regular if not set
        if 'filetype:' not in content or re.search(r'filetype:\s*regular', content):
            pass  # Already correct
        else:
            content = re.sub(
                r'(eve-log:.*?filetype:\s*)\S+',
                r'\1regular',
                content,
                flags=re.DOTALL
            )
        LOGGER.info("Enabled EVE JSON logging")
    
    # Ensure log directory exists
    eve_log_dir = Path(eve_path).parent
    eve_log_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Ensured EVE log directory exists: %s", eve_log_dir)
    
    # Write updated configuration
    config_file.write_text(content, encoding="utf-8")
    
    # Set proper permissions for Suricata
    try:
        subprocess.run(
            ["chmod", "644", str(config_file)],
            check=True,
            capture_output=True
        )
        # Ensure log directory is writable by suricata
        subprocess.run(
            ["chown", "-R", "root:root", str(eve_log_dir)],
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["chmod", "-R", "755", str(eve_log_dir)],
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as exc:
        LOGGER.warning("Failed to set permissions: %s", exc)
    
    LOGGER.info("Suricata configuration completed successfully")


def enable_community_rules() -> None:
    """Enable ET/Open ruleset and update Suricata rules."""
    LOGGER.info("Updating Suricata community rules and enabling ET Open")
    try:
        # Update sources list
        LOGGER.info("Running suricata-update update-sources...")
        run_command(["suricata-update", "update-sources"])
        
        # Enable ET/Open ruleset explicitly
        LOGGER.info("Enabling et/open source...")
        run_command(["suricata-update", "enable-source", "et/open"])
        
        # Update and download rules
        LOGGER.info("Downloading rules with suricata-update...")
        run_command(["suricata-update"])
        
        LOGGER.info("ET Open rules successfully installed and enabled")
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Failed to enable ET Open rules: %s", exc)
        LOGGER.error("Command output: %s", exc.output if hasattr(exc, 'output') else 'N/A')
        raise
    except Exception as exc:
        LOGGER.error("Unexpected error during rule update: %s", exc)
        raise


def start_suricata(service_name: str = "suricata") -> None:
    LOGGER.info("Starting Suricata service")
    
    # First, validate configuration
    try:
        LOGGER.info("Validating Suricata configuration...")
        result = subprocess.run(
            ["suricata", "-T", "-c", "/etc/suricata/suricata.yaml"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30
        )
        if result.returncode != 0:
            LOGGER.error("Suricata configuration validation failed:")
            LOGGER.error("STDOUT: %s", result.stdout)
            LOGGER.error("STDERR: %s", result.stderr)
            raise RuntimeError(f"Suricata configuration is invalid: {result.stderr}")
        LOGGER.info("Suricata configuration is valid")
    except subprocess.TimeoutExpired:
        LOGGER.warning("Configuration validation timed out, continuing anyway...")
    except FileNotFoundError:
        LOGGER.warning("suricata binary not found in PATH, skipping validation")
    
    # Stop service if running
    try:
        subprocess.run(
            ["systemctl", "stop", service_name],
            capture_output=True,
            check=False,
            timeout=30
        )
    except Exception as exc:
        LOGGER.debug("Error stopping service (may not be running): %s", exc)
    
    # Enable and start
    run_command(["systemctl", "enable", service_name])
    run_command(["systemctl", "start", service_name])
    
    # Wait a moment and verify it's running
    import time
    time.sleep(2)
    
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        if result.returncode == 0 and "active" in result.stdout:
            LOGGER.info("Suricata service started successfully")
        else:
            # Get status details
            status_result = subprocess.run(
                ["systemctl", "status", service_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            LOGGER.error("Suricata service failed to start properly:")
            LOGGER.error("Status: %s", status_result.stdout)
            raise RuntimeError(f"Suricata service is not active: {status_result.stdout}")
    except subprocess.TimeoutExpired:
        LOGGER.warning("Service status check timed out")
    except Exception as exc:
        LOGGER.error("Failed to verify service status: %s", exc)
        raise
