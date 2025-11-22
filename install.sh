#!/usr/bin/env bash
set -euo pipefail

AGENT_USER="logmaster-agent"
AGENT_GROUP="logmaster-agent"
INSTALL_DIR="/opt/logmaster-agent"
STATE_DIR="/var/lib/logmaster-agent"
LOG_DIR="/var/log/logmaster-agent"
SERVICE_FILE="/etc/systemd/system/logmaster-agent.service"
DEFAULT_AGENT_BASE="https://raw.githubusercontent.com/msuruwka9/PythonAgent/main"
PYTHON_BIN="/usr/bin/python3"

log() {
  echo "[logmaster-installer] $1"
}

usage() {
  cat <<'USAGE'
Usage: install.sh <ServerGuid> <ApiUrl> [AgentSourceBase]

Example:
  curl -sfL https://raw.githubusercontent.com/yourusername/log-master-agent/main/PythonAgent/install.sh | \
    sudo bash -s -- 00000000-0000-0000-0000-000000000000 https://logmaster.example.com
USAGE
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This installer must run with sudo/root privileges."
    exit 1
  fi
}

assert_ubuntu() {
  if [[ ! -f /etc/os-release ]]; then
    echo "Cannot detect distribution (missing /etc/os-release)."
    exit 1
  fi
  if ! grep -qi 'ubuntu' /etc/os-release; then
    echo "Only Ubuntu is supported by this installer."
    exit 1
  fi
}

install_dependencies() {
  log "Installing system dependencies"
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl wget ca-certificates gzip tar \
    jq coreutils systemd suricata suricata-update
}

get_default_interface() {
  # Try to detect default network interface
  local iface
  iface=$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')
  
  if [[ -z "$iface" ]]; then
    # Fallback to common interface names
    for candidate in eth0 ens33 enp0s3 ens160 ens192 enp1s0; do
      if ip link show "$candidate" &>/dev/null; then
        iface="$candidate"
        break
      fi
    done
  fi
  
  if [[ -z "$iface" ]]; then
    log "WARNING: Cannot detect network interface, using eth0 as fallback"
    iface="eth0"
  fi
  
  echo "$iface"
}

configure_suricata_yaml() {
  local iface="$1"
  local config_file="/etc/suricata/suricata.yaml"
  
  log "Configuring Suricata for interface: $iface"
  
  # Backup original config if exists
  if [[ -f "$config_file" ]]; then
    cp "$config_file" "${config_file}.backup.$(date +%s)" 2>/dev/null || true
  fi
  
  # The default Ubuntu/Debian Suricata config already has af-packet section
  # We just need to ensure the interface is set correctly
  if grep -q "af-packet:" "$config_file" 2>/dev/null; then
    log "Updating af-packet interface to $iface"
    # Update the first interface: line under af-packet section
    sed -i "/af-packet:/,/interface:/ s/interface: .*/interface: $iface/" "$config_file" 2>/dev/null || {
      log "WARNING: Could not update interface with sed, trying alternative method"
      # Alternative: just ensure there's an interface line
      if ! grep -A 5 "af-packet:" "$config_file" | grep -q "interface:"; then
        # Add interface line after af-packet:
        sed -i "/af-packet:/a\  - interface: $iface" "$config_file" 2>/dev/null || true
      fi
    }
  else
    log "Adding af-packet section with interface $iface"
    cat >> "$config_file" <<YAML

# Added by LogMaster Agent installer
af-packet:
  - interface: $iface
    cluster-id: 99
    cluster-type: cluster_flow
    defrag: yes
YAML
  fi
  
  # Ensure eve-log is enabled (usually it is by default)
  if ! grep -q "eve-log:" "$config_file" 2>/dev/null; then
    log "Enabling EVE JSON logging"
    cat >> "$config_file" <<YAML

# Added by LogMaster Agent installer
outputs:
  - eve-log:
      enabled: yes
      filetype: regular
      filename: /var/log/suricata/eve.json
YAML
  else
    # Just ensure it's enabled
    sed -i '/eve-log:/,/enabled:/ s/enabled: no/enabled: yes/' "$config_file" 2>/dev/null || true
  fi
  
  # Fix permissions
  mkdir -p /var/log/suricata
  chmod 755 /var/log/suricata
}

install_suricata() {
  log "Configuring Suricata"
  
  # Check if Suricata is already running and properly configured
  if systemctl is-active --quiet suricata; then
    log "Suricata is already running"
    # Check if it has proper interface configured
    if grep -A 5 "af-packet:" /etc/suricata/suricata.yaml 2>/dev/null | grep -q "interface:"; then
      log "Suricata appears properly configured, skipping reconfiguration"
      return 0
    else
      log "Suricata is running but may need interface configuration"
      systemctl stop suricata 2>/dev/null || true
    fi
  else
    log "Suricata is not running, will configure and start"
  fi
  
  # Detect network interface
  local iface
  iface=$(get_default_interface)
  log "Detected network interface: $iface"
  
  # Configure Suricata YAML
  configure_suricata_yaml "$iface"
  
  # Test configuration (non-fatal if fails)
  log "Testing Suricata configuration..."
  if suricata -T -c /etc/suricata/suricata.yaml 2>/dev/null; then
    log "✓ Suricata configuration is valid"
  else
    log "⚠ Suricata configuration test failed (may still work)"
    # Show last few lines of error
    suricata -T -c /etc/suricata/suricata.yaml 2>&1 | tail -5 || true
  fi
  
  # Enable service
  systemctl enable suricata 2>/dev/null || true
  
  # Start with retry logic
  local max_attempts=3
  local attempt=1
  while [[ $attempt -le $max_attempts ]]; do
    log "Starting Suricata (attempt $attempt/$max_attempts)..."
    if systemctl start suricata 2>/dev/null; then
      sleep 2
      if systemctl is-active --quiet suricata; then
        log "✓ Suricata started successfully"
        return 0
      fi
    fi
    
    if [[ $attempt -lt $max_attempts ]]; then
      log "Suricata failed to start, retrying..."
      journalctl -u suricata -n 10 --no-pager 2>/dev/null | tail -5 || true
      sleep 2
    fi
    attempt=$((attempt + 1))
  done
  
  log "⚠ Suricata may not have started correctly"
  log "Check status with: systemctl status suricata"
  log "Check logs with: journalctl -u suricata -n 50"
  return 0  # Don't fail the entire installation
}

setup_sudoers() {
  log "Configuring sudoers for agent"
  cat <<'SUDOERS' > /etc/sudoers.d/logmaster-agent
logmaster-agent ALL=(ALL) NOPASSWD:/usr/bin/apt-get,/usr/bin/apt,/usr/bin/systemctl,/usr/bin/suricata-update,/usr/bin/suricata
SUDOERS
  chmod 440 /etc/sudoers.d/logmaster-agent
}

create_user_and_dirs() {
  log "Preparing agent user and directories"
  if ! id -u "${AGENT_USER}" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${AGENT_USER}"
  fi
  install -d -m 755 "${INSTALL_DIR}" "${STATE_DIR}" "${LOG_DIR}"
  chown -R "${AGENT_USER}:${AGENT_GROUP}" "${INSTALL_DIR}" "${STATE_DIR}" "${LOG_DIR}" || true
}

fetch_agent_files() {
  local base_url="$1"
  log "Downloading agent files from ${base_url}"
  curl -sfL "${base_url}/agent.py" -o "${INSTALL_DIR}/agent.py"
  curl -sfL "${base_url}/suricata_installer.py" -o "${INSTALL_DIR}/suricata_installer.py"
  curl -sfL "${base_url}/log_shipper.py" -o "${INSTALL_DIR}/log_shipper.py"
  curl -sfL "${base_url}/requirements.txt" -o "${INSTALL_DIR}/requirements.txt"
  curl -sfL "${base_url}/config.json.template" -o "${INSTALL_DIR}/config.json.template"
  chmod 755 "${INSTALL_DIR}/agent.py"
}

render_config() {
  local server_guid="$1"
  local api_url="$2"
  log "Generating config.json"
  sed "s#__SERVER_GUID__#${server_guid}#g" "${INSTALL_DIR}/config.json.template" | \
    sed "s#__API_URL__#${api_url}#g" > "${INSTALL_DIR}/config.json"
  chmod 640 "${INSTALL_DIR}/config.json"
  chown "${AGENT_USER}:${AGENT_GROUP}" "${INSTALL_DIR}/config.json"
}

install_python_dependencies() {
  log "Installing Python dependencies"
  python3 -m pip install --upgrade pip
  python3 -m pip install --no-cache-dir -r "${INSTALL_DIR}/requirements.txt"
}

install_service() {
  local api_url="$1"
  log "Registering systemd service"
  cat <<SERVICE > "${SERVICE_FILE}"
[Unit]
Description=LogMaster Suricata Agent
After=network-online.target suricata.service
Wants=network-online.target

[Service]
Type=simple
User=${AGENT_USER}
Group=${AGENT_GROUP}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=API_URL=${api_url}
ExecStart=${PYTHON_BIN} ${INSTALL_DIR}/agent.py --config ${INSTALL_DIR}/config.json
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/agent.log
StandardError=append:${LOG_DIR}/agent.err.log

[Install]
WantedBy=multi-user.target
SERVICE

  systemctl daemon-reload
  systemctl enable --now logmaster-agent.service
}

main() {
  if [[ $# -lt 2 ]]; then
    usage
    exit 1
  fi

  require_root
  assert_ubuntu

  local server_guid="$1"
  local api_url="${2%/}"
  local agent_base="${3:-$DEFAULT_AGENT_BASE}"

  install_dependencies
  create_user_and_dirs
  install_suricata
  setup_sudoers
  fetch_agent_files "${agent_base}"
  render_config "${server_guid}" "${api_url}"
  install_python_dependencies
  install_service "${api_url}"

  log "Installation finished. Check status with: systemctl status logmaster-agent"
}

main "$@"
