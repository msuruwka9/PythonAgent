#!/bin/bash
# Script to manually enable ET/Open rules for Suricata

set -e  # Exit on error

echo "=== Enabling ET/Open rules for Suricata ==="

# Update sources list
echo "[1/4] Updating suricata-update sources..."
sudo suricata-update update-sources

# Enable ET/Open source
echo "[2/4] Enabling et/open source..."
sudo suricata-update enable-source et/open

# Download and update rules
echo "[3/4] Downloading rules..."
sudo suricata-update

# Verify enabled sources
echo "[4/4] Verifying enabled sources..."
suricata-update list-enabled-sources

# Update suricata.yaml to use correct rules path
echo ""
echo "Updating Suricata configuration..."
SURICATA_CONFIG="/etc/suricata/suricata.yaml"
if [ -f "$SURICATA_CONFIG" ]; then
    sudo sed -i 's|default-rule-path: /etc/suricata/rules|default-rule-path: /var/lib/suricata/rules|g' "$SURICATA_CONFIG"
    echo "✓ Updated rule path to /var/lib/suricata/rules"
else
    echo "⚠ Warning: $SURICATA_CONFIG not found"
fi

# Restart Suricata
echo ""
echo "Restarting Suricata service..."
sudo systemctl restart suricata
sudo systemctl status suricata --no-pager

echo ""
echo "=== ET/Open rules enabled successfully! ==="
echo ""
echo "To verify rules are loaded, run:"
echo "  suricata-update list-enabled-sources"
echo "  sudo suricatasc -c 'ruleset-stats' | head -20"

