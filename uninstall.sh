#!/bin/bash
set -e

echo "=========================================="
echo "LogMaster Agent Uninstaller"
echo "=========================================="

# Stop services
echo "Stopping services..."
sudo systemctl stop logmaster-agent 2>/dev/null || true
sudo systemctl disable logmaster-agent 2>/dev/null || true
sudo systemctl stop suricata 2>/dev/null || true
sudo systemctl disable suricata 2>/dev/null || true

# Remove systemd service
echo "Removing systemd service..."
sudo rm -f /etc/systemd/system/logmaster-agent.service
sudo systemctl daemon-reload

# Remove agent files
echo "Removing agent files..."
sudo rm -rf /opt/logmaster-agent

# Remove state and logs
echo "Removing state and log files..."
sudo rm -rf /var/lib/logmaster-agent
sudo rm -rf /var/log/logmaster-agent

# Remove user
echo "Removing logmaster-agent user..."
sudo userdel -r logmaster-agent 2>/dev/null || true

# Remove sudoers file
echo "Removing sudoers configuration..."
sudo rm -f /etc/sudoers.d/logmaster-agent

# Uninstall Suricata (optional)
echo "Removing Suricata..."
sudo systemctl stop suricata 2>/dev/null || true
sudo apt-get remove -y suricata suricata-update 2>/dev/null || true
sudo apt-get autoremove -y 2>/dev/null || true
sudo rm -rf /etc/suricata
sudo rm -rf /var/log/suricata
sudo rm -rf /var/lib/suricata

echo ""
echo "=========================================="
echo "✅ Uninstallation complete!"
echo "=========================================="
echo "All LogMaster Agent and Suricata components have been removed."
echo ""
echo "To reinstall, run:"
echo "  curl -sfL https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh | sudo bash -s -- <SERVER_GUID> <API_URL>"
echo ""

