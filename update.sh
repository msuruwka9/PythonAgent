#!/usr/bin/env bash
# LogMaster Agent Update Script - Add ServerId Support
# This script updates existing agent installations to support ServerId validation

set -euo pipefail

AGENT_DIR="/opt/logmaster-agent"
CONFIG_FILE="${AGENT_DIR}/config.json"
BACKUP_DIR="/var/lib/logmaster-agent/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

log() {
  echo "[logmaster-updater $(date +'%Y-%m-%d %H:%M:%S')] $1"
}

error() {
  echo "[ERROR $(date +'%Y-%m-%d %H:%M:%S')] $1" >&2
}

# Check if running as root
if [[ "${EUID}" -ne 0 ]]; then
  error "This update script must be run with sudo/root privileges."
  exit 1
fi

# Check if agent is installed
if [[ ! -d "${AGENT_DIR}" ]]; then
  error "LogMaster agent is not installed in ${AGENT_DIR}"
  error "Please run the full installation script first."
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  error "Configuration file not found: ${CONFIG_FILE}"
  exit 1
fi

log "Starting LogMaster agent update..."
log "This update adds ServerId validation support"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Backup current configuration
log "Backing up current configuration..."
cp "${CONFIG_FILE}" "${BACKUP_DIR}/config.json.${TIMESTAMP}.bak"
log "Backup saved to: ${BACKUP_DIR}/config.json.${TIMESTAMP}.bak"

# Backup current Python files
for file in agent.py log_shipper.py suricata_installer.py; do
  if [[ -f "${AGENT_DIR}/${file}" ]]; then
    cp "${AGENT_DIR}/${file}" "${BACKUP_DIR}/${file}.${TIMESTAMP}.bak"
  fi
done

# Check if server_guid already exists in config
if grep -q '"server_guid"' "${CONFIG_FILE}"; then
  log "✓ Configuration already contains server_guid field"
  CURRENT_SERVER_GUID=$(grep '"server_guid"' "${CONFIG_FILE}" | head -1 | sed 's/.*"server_guid"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
  log "Current ServerId: ${CURRENT_SERVER_GUID}"
  
  # Validate if it's a proper UUID
  if [[ "${CURRENT_SERVER_GUID}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
    log "✓ ServerId is a valid UUID"
    SERVER_GUID="${CURRENT_SERVER_GUID}"
  else
    error "❌ Current server_guid is not a valid UUID: ${CURRENT_SERVER_GUID}"
    log "Please provide a valid ServerId obtained from LogMaster registration:"
    read -p "Enter ServerId (UUID): " SERVER_GUID
    
    # Validate input
    if [[ ! "${SERVER_GUID}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
      error "Invalid UUID format. Aborting update."
      exit 1
    fi
  fi
else
  log "⚠️  Configuration does not contain server_guid field"
  log "You need a valid ServerId from LogMaster registration."
  log ""
  log "To register a new server, use the LogMaster API:"
  log "  curl -X POST http://your-vm-service/api/servers/register \\"
  log "    -H 'Content-Type: application/json' \\"
  log "    -d '{\"ServerName\":\"$(hostname)\",\"Region\":\"your-region\"}'"
  log ""
  read -p "Enter your registered ServerId (UUID): " SERVER_GUID
  
  # Validate UUID format
  if [[ ! "${SERVER_GUID}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
    error "Invalid UUID format. Aborting update."
    exit 1
  fi
  
  log "Adding server_guid to configuration..."
  # Add server_guid field to config.json (after the first opening brace)
  sed -i "1 a \ \ \"server_guid\": \"${SERVER_GUID}\"," "${CONFIG_FILE}"
fi

# Download updated agent files
log "Downloading updated agent files..."
REPO_BASE="https://raw.githubusercontent.com/msuruwka9/PythonAgent/log_upload_refactor_add_serverid"

cd "${AGENT_DIR}"

for file in agent.py log_shipper.py suricata_installer.py; do
  log "Updating ${file}..."
  curl -sfL "${REPO_BASE}/${file}" -o "${file}.new"
  
  if [[ $? -eq 0 ]] && [[ -s "${file}.new" ]]; then
    mv "${file}.new" "${file}"
    chmod 755 "${file}"
    log "✓ ${file} updated successfully"
  else
    error "Failed to download ${file}, keeping old version"
    rm -f "${file}.new"
  fi
done

# Update requirements.txt if available
if curl -sfL "${REPO_BASE}/requirements.txt" -o requirements.txt.new 2>/dev/null; then
  if [[ -s requirements.txt.new ]]; then
    mv requirements.txt.new requirements.txt
    log "✓ requirements.txt updated"
    
    # Install/update dependencies
    if [[ -d "${AGENT_DIR}/venv" ]]; then
      log "Updating Python dependencies..."
      "${AGENT_DIR}/venv/bin/pip" install --upgrade pip -q
      "${AGENT_DIR}/venv/bin/pip" install -r requirements.txt -q
      log "✓ Dependencies updated"
    fi
  fi
fi

# Restart the agent service
log "Restarting logmaster-agent service..."
if systemctl is-active --quiet logmaster-agent; then
  systemctl restart logmaster-agent
  
  # Wait a moment and check if it started successfully
  sleep 2
  
  if systemctl is-active --quiet logmaster-agent; then
    log "✅ Agent service restarted successfully"
  else
    error "❌ Agent service failed to restart. Check logs:"
    error "  journalctl -u logmaster-agent -n 50"
    exit 1
  fi
else
  log "⚠️  Agent service is not running. Starting it..."
  systemctl start logmaster-agent
  
  sleep 2
  
  if systemctl is-active --quiet logmaster-agent; then
    log "✅ Agent service started successfully"
  else
    error "❌ Agent service failed to start. Check logs:"
    error "  journalctl -u logmaster-agent -n 50"
    exit 1
  fi
fi

# Verify the update
log ""
log "========================================="
log "Update completed successfully! 🎉"
log "========================================="
log ""
log "Updated configuration:"
log "  - ServerId: ${SERVER_GUID}"
log "  - Agent files updated with ServerId support"
log "  - Service restarted"
log ""
log "Monitor the agent:"
log "  sudo journalctl -u logmaster-agent -f"
log ""
log "Check agent logs:"
log "  tail -f /var/log/logmaster-agent/agent.log"
log ""
log "Backups saved in: ${BACKUP_DIR}"
log ""
log "The agent will now send X-LogMaster-ServerId header with all log uploads."
log "Ensure this ServerId is registered in LogMaster before sending logs!"
log ""

# Show recent log entries
log "Recent agent logs (last 10 lines):"
if [[ -f /var/log/logmaster-agent/agent.log ]]; then
  tail -10 /var/log/logmaster-agent/agent.log
else
  log "(log file not created yet)"
fi

exit 0

