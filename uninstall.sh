#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[logmaster-uninstaller] $1"
}

echo '=========================================='
echo 'LogMaster Agent Uninstaller'
echo '=========================================='

# Check if running as root
if [[ "${EUID}" -ne 0 ]]; then
  echo "This uninstaller must run with sudo/root privileges."
  exit 1
fi

# Stop services
log 'Stopping services...'
systemctl stop logmaster-agent 2>/dev/null || true
systemctl disable logmaster-agent 2>/dev/null || true
systemctl stop suricata 2>/dev/null || true
systemctl disable suricata 2>/dev/null || true

# Remove systemd service
log 'Removing systemd service...'
rm -f /etc/systemd/system/logmaster-agent.service
systemctl daemon-reload

# Remove agent files
log 'Removing agent files...'
rm -rf /opt/logmaster-agent

# Remove state and logs
log 'Removing state and log files...'
rm -rf /var/lib/logmaster-agent
rm -rf /var/log/logmaster-agent

# Remove user
log 'Removing logmaster-agent user...'
if id -u logmaster-agent >/dev/null 2>&1; then
  userdel logmaster-agent 2>/dev/null || true
  groupdel logmaster-agent 2>/dev/null || true
fi

# Remove sudoers file
log 'Removing sudoers configuration...'
rm -f /etc/sudoers.d/logmaster-agent

# Ask about Suricata removal
read -p "Do you want to completely remove Suricata? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  log 'Removing Suricata...'
  systemctl stop suricata 2>/dev/null || true
  apt-get remove -y suricata suricata-update 2>/dev/null || true
  apt-get autoremove -y 2>/dev/null || true
  
  read -p "Remove Suricata configuration and logs? (y/N): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf /etc/suricata
    rm -rf /var/log/suricata
    rm -rf /var/lib/suricata
    log 'Suricata configuration and data removed'
  else
    log 'Keeping Suricata configuration and logs'
  fi
else
  log 'Keeping Suricata installed'
fi

echo ''
echo '=========================================='
echo '✅ Uninstallation complete!'
echo '=========================================='
echo 'LogMaster Agent components have been removed.'
echo ''
stal