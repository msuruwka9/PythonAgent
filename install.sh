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
Usage: install.sh <ServerGuid> <WebServiceUrl> <VMIntegrationUrl> [AgentSourceBase]

Arguments:
  ServerGuid         - Unique GUID for this VM/server
  WebServiceUrl      - URL for file uploads (e.g., https://webservice-xxx.ngrok.app)
  VMIntegrationUrl   - URL for heartbeat/registration (e.g., https://vm-service-xxx.ngrok.app)
  AgentSourceBase    - (Optional) Base URL for agent files

Example:
  curl -sfL https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh | \
    sudo bash -s -- \
      00000000-0000-0000-0000-000000000000 \
      https://webservice-xxx.ngrok.app \
      https://vm-service-xxx.ngrok.app
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

install_suricata() {
  log "Configuring Suricata"
  if systemctl is-active --quiet suricata; then
    log "Suricata already running, skipping configuration"
    return
  fi
  
  # Enable and start Suricata
  systemctl enable suricata
  systemctl start suricata
  
  log "Suricata installed and started"
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
  local webservice_url="$2"
  local vm_integration_url="$3"
  log "Generating config.json"
  sed "s#__SERVER_GUID__#${server_guid}#g" "${INSTALL_DIR}/config.json.template" | \
    sed "s#__WEBSERVICE_URL__#${webservice_url}#g" | \
    sed "s#__VM_INTEGRATION_URL__#${vm_integration_url}#g" > "${INSTALL_DIR}/config.json"
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
  if [[ $# -lt 3 ]]; then
    usage
    exit 1
  fi

  require_root
  assert_ubuntu

  local server_guid="$1"
  local webservice_url="${2%/}"
  local vm_integration_url="${3%/}"
  local agent_base="${4:-$DEFAULT_AGENT_BASE}"

  install_dependencies
  create_user_and_dirs
  install_suricata
  setup_sudoers
  fetch_agent_files "${agent_base}"
  render_config "${server_guid}" "${webservice_url}" "${vm_integration_url}"
  install_python_dependencies
  install_service "${vm_integration_url}"

  log "Installation finished. Check status with: systemctl status logmaster-agent"
}

main "$@"
