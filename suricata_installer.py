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


def ensure_suricata_user() -> None:
    """Ensure suricata user and group exist."""
    try:
        # Check if suricata group exists
        result = subprocess.run(
            ["getent", "group", "suricata"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            LOGGER.info("Creating suricata group...")
            run_command(["groupadd", "--system", "suricata"])
        else:
            LOGGER.debug("suricata group already exists")
        
        # Check if suricata user exists
        result = subprocess.run(
            ["getent", "passwd", "suricata"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            LOGGER.info("Creating suricata user...")
            run_command([
                "useradd", "--system", "--no-create-home",
                "--shell", "/usr/sbin/nologin",
                "-g", "suricata", "suricata"
            ])
        else:
            LOGGER.debug("suricata user already exists")
    except Exception as exc:
        LOGGER.warning("Failed to ensure suricata user/group: %s", exc)
        # Don't fail here - we'll try to continue without it


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
    
    # Ensure suricata user/group exist after installation
    ensure_suricata_user()


def configure_suricata(config_path: str = "/etc/suricata/suricata.yaml",
                       eve_path: str = "/var/log/suricata/eve.json") -> None:
    """Configure Suricata using systemd override instead of editing main config."""
    LOGGER.info("Configuring Suricata for LogMaster")
    config_file = Path(config_path)
    
    # Verify config exists (should exist after apt install)
    if not config_file.exists():
        raise RuntimeError(
            f"Suricata config not found at {config_path}. "
            "Ensure 'apt-get install suricata' completed successfully."
        )
    
    LOGGER.info("Suricata config file exists: %s", config_path)

    # Detect network interface
    try:
        interface = detect_network_interface()
        LOGGER.info("Detected primary network interface: %s", interface)
    except Exception as exc:
        LOGGER.warning("Failed to detect network interface: %s. Will use default.", exc)
        interface = "eth0"  # Default fallback
    
    # Ensure log directory exists with correct permissions
    eve_log_dir = Path(eve_path).parent
    run_command(["mkdir", "-p", str(eve_log_dir)])
    
    # Ensure suricata user exists before setting ownership
    ensure_suricata_user()
    
    # Set ownership to suricata user
    try:
        run_command(["chown", "-R", "suricata:suricata", str(eve_log_dir)])
        run_command(["chmod", "755", str(eve_log_dir)])
        LOGGER.info("Ensured EVE log directory exists with correct permissions: %s", eve_log_dir)
    except subprocess.CalledProcessError as exc:
        LOGGER.warning("Failed to set ownership to suricata:suricata: %s. Continuing anyway.", exc)
        # Continue even if chown fails - the directory still exists
    
    # Create systemd override to set interface via command line
    # This is cleaner than editing the main YAML file
    systemd_override_dir = Path("/etc/systemd/system/suricata.service.d")
    run_command(["mkdir", "-p", str(systemd_override_dir)])
    
    override_content = f"""[Service]
# LogMaster Agent: Override interface
ExecStart=
ExecStart=/usr/bin/suricata -c /etc/suricata/suricata.yaml -i {interface} --user suricata --group suricata --pidfile /run/suricata.pid
"""
    
    # Write override file using temporary file and sudo
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp:
        tmp.write(override_content)
        tmp_path = tmp.name
    
    override_file = systemd_override_dir / "logmaster.conf"
    try:
        run_command(["cp", tmp_path, str(override_file)])
        run_command(["chmod", "644", str(override_file)])
        LOGGER.info("Created systemd override: %s", override_file)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    
    # Reload systemd to apply changes
    run_command(["systemctl", "daemon-reload"])
    
    # Verify EVE JSON logging is enabled in default config
    content = config_file.read_text(encoding="utf-8")
    if "eve-log:" in content and "enabled: yes" in content:
        LOGGER.info("EVE JSON logging is already enabled in default config")
    else:
        LOGGER.warning("EVE JSON logging may not be enabled. Check %s manually.", config_path)
    
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
