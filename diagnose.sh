#!/usr/bin/env bash
# Diagnostic script for LogMaster Agent and Suricata issues

echo "=========================================="
echo "LogMaster Agent Diagnostic Tool"
echo "=========================================="
echo ""

# Check if running as root
if [[ "${EUID}" -ne 0 ]]; then
  echo "⚠️  This script should run with sudo for full diagnostics"
  echo ""
fi

echo "--- System Information ---"
echo "OS: $(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)"
echo "Kernel: $(uname -r)"
echo ""

echo "--- Network Interfaces ---"
ip -br link show
echo ""
echo "Default route interface:"
ip route show default | awk '{print $5}'
echo ""

echo "--- LogMaster Agent Status ---"
if systemctl list-unit-files | grep -q logmaster-agent; then
  systemctl status logmaster-agent --no-pager || true
  echo ""
  echo "Recent agent logs (last 20 lines):"
  journalctl -u logmaster-agent -n 20 --no-pager || cat /var/log/logmaster-agent/agent.log 2>/dev/null | tail -20 || echo "No logs found"
else
  echo "❌ logmaster-agent service not installed"
fi
echo ""

echo "--- Suricata Status ---"
if command -v suricata &>/dev/null; then
  echo "✅ Suricata is installed: $(suricata --version 2>&1 | head -1)"
  echo ""
  
  if systemctl list-unit-files | grep -q "^suricata.service"; then
    systemctl status suricata --no-pager || true
    echo ""
    
    echo "Recent Suricata logs (last 20 lines):"
    journalctl -u suricata -n 20 --no-pager || true
    echo ""
  else
    echo "⚠️  Suricata service not configured in systemd"
  fi
  
  echo "Configuration test:"
  if [[ -f /etc/suricata/suricata.yaml ]]; then
    suricata -T -c /etc/suricata/suricata.yaml 2>&1 | tail -5
  else
    echo "❌ /etc/suricata/suricata.yaml not found"
  fi
  echo ""
  
  echo "Configured interface in suricata.yaml:"
  grep -A 3 "af-packet:" /etc/suricata/suricata.yaml 2>/dev/null | grep "interface:" || echo "Not configured"
  echo ""
  
  echo "EVE JSON log:"
  if [[ -f /var/log/suricata/eve.json ]]; then
    echo "✅ /var/log/suricata/eve.json exists ($(stat -c%s /var/log/suricata/eve.json) bytes)"
    echo "Last modified: $(stat -c%y /var/log/suricata/eve.json)"
  else
    echo "❌ /var/log/suricata/eve.json not found"
  fi
  echo ""
  
  echo "Suricata stats log:"
  if [[ -f /var/log/suricata/stats.log ]]; then
    tail -5 /var/log/suricata/stats.log
  else
    echo "❌ /var/log/suricata/stats.log not found"
  fi
else
  echo "❌ Suricata is not installed"
fi
echo ""

echo "--- File Permissions ---"
echo "/var/log/suricata:"
ls -ld /var/log/suricata 2>/dev/null || echo "Directory does not exist"
echo ""

echo "/opt/logmaster-agent:"
ls -ld /opt/logmaster-agent 2>/dev/null || echo "Directory does not exist"
echo ""

echo "--- Agent Configuration ---"
if [[ -f /opt/logmaster-agent/config.json ]]; then
  echo "✅ config.json exists"
  echo "API URL: $(grep -o '"api_url": "[^"]*"' /opt/logmaster-agent/config.json | cut -d'"' -f4)"
  echo "Server GUID: $(grep -o '"server_guid": "[^"]*"' /opt/logmaster-agent/config.json | cut -d'"' -f4)"
else
  echo "❌ /opt/logmaster-agent/config.json not found"
fi
echo ""

echo "--- Python Dependencies ---"
if command -v python3 &>/dev/null; then
  echo "Python version: $(python3 --version)"
  echo "Installed packages:"
  python3 -m pip list 2>/dev/null | grep -E "(requests|watchdog)" || echo "Required packages may be missing"
else
  echo "❌ Python3 not found"
fi
echo ""

echo "--- Port Connectivity Test ---"
if [[ -f /opt/logmaster-agent/config.json ]]; then
  api_url=$(grep -o '"api_url": "[^"]*"' /opt/logmaster-agent/config.json | cut -d'"' -f4)
  if [[ -n "$api_url" ]]; then
    echo "Testing connection to: $api_url"
    if command -v curl &>/dev/null; then
      if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$api_url" 2>/dev/null | grep -q "^[23]"; then
        echo "✅ Can reach API endpoint"
      else
        echo "⚠️  Cannot reach API endpoint (may be normal if requires auth)"
      fi
    else
      echo "⚠️  curl not available for testing"
    fi
  fi
fi
echo ""

echo "=========================================="
echo "Diagnostic complete"
echo "=========================================="
echo ""
echo "Common issues and solutions:"
echo "1. Suricata won't start: Check network interface configuration"
echo "   Command: grep -A 3 'af-packet:' /etc/suricata/suricata.yaml"
echo ""
echo "2. No logs in eve.json: Ensure Suricata is running and monitoring correct interface"
echo "   Command: systemctl status suricata"
echo ""
echo "3. Agent can't connect: Check API URL in config.json and firewall rules"
echo "   Command: cat /opt/logmaster-agent/config.json | grep api_url"
echo ""

