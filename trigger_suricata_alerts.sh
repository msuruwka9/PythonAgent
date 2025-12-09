#!/usr/bin/env bash
# Trigger Suricata alerts by simulating suspicious network activity
# This script performs various network actions that should trigger ET/OPEN rules

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}Suricata Alert Generator${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Check if running with sufficient privileges
if [[ $EUID -ne 0 ]]; then
   echo -e "${YELLOW}⚠️  This script should be run with sudo for best results${NC}"
fi

echo "This script will simulate various network activities that trigger Suricata alerts."
echo "Activities include:"
echo "  - Port scanning"
echo "  - Suspicious DNS queries"
echo "  - Known malicious IPs connections"
echo "  - User-Agent spoofing"
echo "  - Various protocol anomalies"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo ""

# Counter for activities
ACTIVITY_COUNT=0

perform_activity() {
    local name="$1"
    local description="$2"
    ACTIVITY_COUNT=$((ACTIVITY_COUNT + 1))
    echo -e "${GREEN}[$ACTIVITY_COUNT]${NC} $name"
    echo "    $description"
}

# 1. Port Scanning (triggers ET SCAN rules)
perform_activity "Port Scan Simulation" "Scanning common ports (triggers ET SCAN alerts)"
for port in 22 80 443 3306 5432 1433 3389; do
    timeout 1 nc -zv -w 1 scanme.nmap.org $port 2>/dev/null || true
done
sleep 1

# 2. SSH Brute Force Pattern (triggers ET SCAN Potential SSH Scan)
perform_activity "SSH Scan Pattern" "Multiple SSH connection attempts"
for i in {1..5}; do
    timeout 1 nc -zv -w 1 scanme.nmap.org 22 2>/dev/null || true
done
sleep 1

# 3. MySQL Port Scan (triggers ET POLICY Suspicious inbound to mySQL port 3306)
perform_activity "MySQL Port Probe" "Connection to MySQL port 3306"
timeout 2 nc -zv -w 1 scanme.nmap.org 3306 2>/dev/null || true
sleep 1

# 4. PostgreSQL Port Scan (triggers ET POLICY Suspicious inbound to PostgreSQL port 5432)
perform_activity "PostgreSQL Port Probe" "Connection to PostgreSQL port 5432"
timeout 2 nc -zv -w 1 scanme.nmap.org 5432 2>/dev/null || true
sleep 1

# 5. MSSQL Port Scan (triggers ET POLICY Suspicious inbound to MSSQL port 1433)
perform_activity "MSSQL Port Probe" "Connection to MSSQL port 1433"
timeout 2 nc -zv -w 1 scanme.nmap.org 1433 2>/dev/null || true
sleep 1

# 6. Suspicious User-Agent (triggers ET POLICY rules)
perform_activity "Suspicious User-Agent" "HTTP request with suspicious User-Agent"
curl -s -A "sqlmap/1.0" http://testphp.vulnweb.com/ > /dev/null 2>&1 || true
curl -s -A "Nmap Scripting Engine" http://testphp.vulnweb.com/ > /dev/null 2>&1 || true
sleep 1

# 7. DNS Queries to suspicious domains
perform_activity "Suspicious DNS Queries" "Querying known malicious domains"
nslookup malware.wicar.org 8.8.8.8 > /dev/null 2>&1 || true
nslookup phishing-test.example.com 8.8.8.8 > /dev/null 2>&1 || true
sleep 1

# 8. Connection to TOR exit nodes (triggers ET DROP rules)
perform_activity "TOR Exit Node Connection" "Attempting connection to known TOR exit node"
timeout 2 curl -s --connect-timeout 1 http://185.220.101.1 > /dev/null 2>&1 || true
sleep 1

# 9. Multiple rapid connections (potential DoS pattern)
perform_activity "Rapid Connection Pattern" "Multiple rapid connections to same host"
for i in {1..10}; do
    timeout 1 curl -s --connect-timeout 1 http://testphp.vulnweb.com/ > /dev/null 2>&1 || true
done
sleep 1

# 10. Dropbox Broadcasting (triggers ET POLICY Dropbox Client Broadcasting)
perform_activity "Dropbox-like Broadcast" "UDP broadcast simulation"
# This is simulated - actual Dropbox would use specific ports
echo "test" | timeout 1 nc -u -b 255.255.255.255 17500 2>/dev/null || true
sleep 1

# 11. ICMP Ping flood pattern
perform_activity "ICMP Activity" "Ping to trigger ICMP rules"
ping -c 5 -i 0.2 8.8.8.8 > /dev/null 2>&1 || true
sleep 1

# 12. FTP Connection attempt (triggers policy violations)
perform_activity "FTP Connection" "Attempting FTP connection"
timeout 2 nc -zv -w 1 ftp.gnu.org 21 2>/dev/null || true
sleep 1

# 13. Telnet Connection attempt (triggers policy violations)
perform_activity "Telnet Connection" "Attempting Telnet connection"
timeout 2 nc -zv -w 1 telnet.example.com 23 2>/dev/null || true
sleep 1

# 14. SMTP Connection patterns
perform_activity "SMTP Activity" "SMTP port scanning"
timeout 2 nc -zv -w 1 scanme.nmap.org 25 2>/dev/null || true
sleep 1

# 15. Web Application Scanning patterns
perform_activity "Web App Scan Pattern" "Accessing common admin paths"
curl -s http://testphp.vulnweb.com/admin > /dev/null 2>&1 || true
curl -s http://testphp.vulnweb.com/phpMyAdmin > /dev/null 2>&1 || true
curl -s http://testphp.vulnweb.com/wp-admin > /dev/null 2>&1 || true
sleep 1

# 16. SQL Injection attempt patterns
perform_activity "SQL Injection Pattern" "HTTP requests with SQL injection signatures"
curl -s "http://testphp.vulnweb.com/artists.php?artist=1' OR '1'='1" > /dev/null 2>&1 || true
curl -s "http://testphp.vulnweb.com/artists.php?artist=1 UNION SELECT" > /dev/null 2>&1 || true
sleep 1

# 17. XSS Pattern
perform_activity "XSS Pattern" "HTTP requests with XSS signatures"
curl -s "http://testphp.vulnweb.com/search.php?search=<script>alert('xss')</script>" > /dev/null 2>&1 || true
sleep 1

# 18. Directory Traversal Pattern
perform_activity "Directory Traversal" "Path traversal attempts"
curl -s "http://testphp.vulnweb.com/../../../../etc/passwd" > /dev/null 2>&1 || true
sleep 1

# 19. Known Bad IP ranges
perform_activity "Suspicious IP Connections" "Connecting to known suspicious IPs"
timeout 2 curl -s --connect-timeout 1 http://45.142.212.1 > /dev/null 2>&1 || true
timeout 2 curl -s --connect-timeout 1 http://89.248.165.1 > /dev/null 2>&1 || true
sleep 1

# 20. Generate some legitimate-looking but suspicious SSL traffic
perform_activity "SSL/TLS Activity" "Various HTTPS connections"
curl -s -k https://self-signed.badssl.com/ > /dev/null 2>&1 || true
curl -s -k https://expired.badssl.com/ > /dev/null 2>&1 || true
sleep 1

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}✅ Activity Generation Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Generated $ACTIVITY_COUNT different types of network activities."
echo ""
echo "Suricata should have detected these activities and logged them to:"
echo "  /var/log/suricata/eve.json"
echo ""
echo "Your LogMaster agent should pick them up and send to the server."
echo ""
echo "To check Suricata logs:"
echo "  sudo tail -100 /var/log/suricata/eve.json | grep 'event_type.*alert'"
echo ""
echo "To check agent logs:"
echo "  sudo journalctl -u logmaster-agent -n 50"
echo "  tail -50 /var/log/logmaster-agent/agent.log"
echo ""
echo "To see if alerts were sent:"
echo "  grep 'Uploaded.*events' /var/log/logmaster-agent/agent.log | tail -10"
echo ""
echo -e "${YELLOW}Note: It may take 30-60 seconds for the agent to batch and send the alerts.${NC}"
echo ""

