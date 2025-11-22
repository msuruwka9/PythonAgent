#!/usr/bin/env bash
# Quick test script for development and testing

set -euo pipefail

echo "=========================================="
echo "LogMaster Agent - Quick Test"
echo "=========================================="
echo ""

# Check if required args are provided
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <SERVER_GUID> <API_URL>"
  echo ""
  echo "Example:"
  echo "  $0 12345678-1234-1234-1234-123456789abc https://api.logmaster.com"
  exit 1
fi

SERVER_GUID="$1"
API_URL="$2"

# Test 1: Check Suricata installation
echo "--- Test 1: Suricata Installation ---"
if command -v suricata &>/dev/null; then
  echo "✅ Suricata found: $(suricata --version 2>&1 | head -1)"
else
  echo "❌ Suricata not found"
  exit 1
fi
echo ""

# Test 2: Check configuration
echo "--- Test 2: Suricata Configuration ---"
if [[ -f /etc/suricata/suricata.yaml ]]; then
  echo "✅ Configuration file exists"
  if suricata -T -c /etc/suricata/suricata.yaml &>/dev/null; then
    echo "✅ Configuration is valid"
  else
    echo "⚠️  Configuration test failed"
    suricata -T -c /etc/suricata/suricata.yaml 2>&1 | tail -10
  fi
else
  echo "❌ Configuration file not found"
  exit 1
fi
echo ""

# Test 3: Check interface configuration
echo "--- Test 3: Network Interface ---"
iface=$(grep -A 5 "af-packet:" /etc/suricata/suricata.yaml 2>/dev/null | grep "interface:" | head -1 | awk '{print $3}' | tr -d '"' || echo "")
if [[ -n "$iface" ]]; then
  echo "✅ Interface configured: $iface"
  if ip link show "$iface" &>/dev/null; then
    echo "✅ Interface exists and is $(ip link show "$iface" | grep -o 'state [A-Z]*' | cut -d' ' -f2)"
  else
    echo "⚠️  Configured interface $iface does not exist!"
  fi
else
  echo "⚠️  No interface configured in af-packet section"
fi
echo ""

# Test 4: Check service status
echo "--- Test 4: Service Status ---"
if systemctl is-active --quiet suricata; then
  echo "✅ Suricata service is running"
else
  echo "❌ Suricata service is not running"
  echo "Recent logs:"
  journalctl -u suricata -n 10 --no-pager 2>/dev/null || true
fi
echo ""

# Test 5: Check EVE JSON logging
echo "--- Test 5: EVE JSON Logging ---"
if [[ -f /var/log/suricata/eve.json ]]; then
  size=$(stat -c%s /var/log/suricata/eve.json 2>/dev/null || echo "0")
  echo "✅ EVE JSON file exists (${size} bytes)"
  if [[ $size -gt 0 ]]; then
    echo "Recent events:"
    tail -3 /var/log/suricata/eve.json | jq -r '.event_type' 2>/dev/null || tail -3 /var/log/suricata/eve.json
  else
    echo "⚠️  File is empty (service may have just started)"
  fi
else
  echo "❌ EVE JSON file not found"
fi
echo ""

# Test 6: Check Python environment
echo "--- Test 6: Python Environment ---"
if command -v python3 &>/dev/null; then
  echo "✅ Python3: $(python3 --version)"
  
  missing_deps=()
  for pkg in requests watchdog; do
    if ! python3 -c "import $pkg" 2>/dev/null; then
      missing_deps+=("$pkg")
    fi
  done
  
  if [[ ${#missing_deps[@]} -eq 0 ]]; then
    echo "✅ All required Python packages installed"
  else
    echo "⚠️  Missing packages: ${missing_deps[*]}"
  fi
else
  echo "❌ Python3 not found"
fi
echo ""

# Test 7: API connectivity
echo "--- Test 7: API Connectivity ---"
if command -v curl &>/dev/null; then
  heartbeat_url="${API_URL}/api/agent/heartbeat"
  echo "Testing: $heartbeat_url"
  
  response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$heartbeat_url" 2>/dev/null || echo "000")
  
  if [[ "$response" =~ ^[23] ]]; then
    echo "✅ API endpoint reachable (HTTP $response)"
  elif [[ "$response" == "401" ]] || [[ "$response" == "403" ]]; then
    echo "✅ API endpoint reachable (HTTP $response - auth required, this is normal)"
  elif [[ "$response" == "000" ]]; then
    echo "❌ Cannot reach API (connection timeout or DNS failure)"
  else
    echo "⚠️  API returned HTTP $response"
  fi
else
  echo "⚠️  curl not available for testing"
fi
echo ""

# Test 8: Generate test traffic
echo "--- Test 8: Generate Test Traffic ---"
echo "Generating some DNS queries to test Suricata detection..."
for domain in example.com google.com github.com; do
  nslookup "$domain" &>/dev/null || true
done

sleep 2

echo "Checking for new events in EVE JSON..."
if [[ -f /var/log/suricata/eve.json ]]; then
  new_events=$(tail -20 /var/log/suricata/eve.json 2>/dev/null | wc -l)
  echo "Found $new_events recent log lines"
  
  if [[ $new_events -gt 0 ]]; then
    echo "Event types in last 20 entries:"
    tail -20 /var/log/suricata/eve.json 2>/dev/null | jq -r '.event_type' 2>/dev/null | sort | uniq -c || echo "Unable to parse JSON"
  fi
fi
echo ""

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "Configuration Summary:"
echo "  Server GUID: $SERVER_GUID"
echo "  API URL: $API_URL"
echo "  Suricata Interface: ${iface:-not configured}"
echo ""
echo "Next steps:"
echo "  1. If Suricata is not running: sudo systemctl start suricata"
echo "  2. Check logs: journalctl -u suricata -f"
echo "  3. Run full diagnostics: sudo bash diagnose.sh"
echo "  4. Install agent: sudo bash install.sh $SERVER_GUID $API_URL"
echo ""

