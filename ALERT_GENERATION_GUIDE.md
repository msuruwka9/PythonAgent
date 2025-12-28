# Generowanie Alertów Suricata - Przewodnik

## 📋 Dostępne skrypty

### 1. `trigger_suricata_alerts.sh` - Kompleksowy generator
Generuje 20 różnych typów podejrzanej aktywności sieciowej.

### 2. `generate_alerts_simple.sh` - Prosty generator
Szybki skrypt do podstawowego generowania alertów.

### 3. `send_test_alerts.sh` - Bezpośrednie wysyłanie
Generuje i wysyła alerty bezpośrednio do WebService (bez Suricata).

---

## 🚀 Jak używać (na maszynie z agentem)

### Krok 1: Skopiuj skrypt na maszynę z agentem

```bash
# Z Twojego komputera
scp trigger_suricata_alerts.sh user@your-vm:/tmp/

# Lub pobierz bezpośrednio na VM
ssh user@your-vm
curl -O https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/trigger_suricata_alerts.sh
chmod +x trigger_suricata_alerts.sh
```

### Krok 2: Uruchom skrypt

```bash
sudo bash trigger_suricata_alerts.sh
```

Skrypt wykona:
- ✅ Skanowanie portów (MySQL, PostgreSQL, SSH, MSSQL, RDP)
- ✅ Podejrzane requesty HTTP (SQL injection, XSS, admin paths)
- ✅ Próby połączeń z TOR exit nodes
- ✅ Skanowanie z podejrzanymi User-Agent (sqlmap, Nikto)
- ✅ DNS queries do złośliwych domen
- ✅ Próby połączeń FTP/Telnet
- ✅ ICMP flood pattern
- ✅ Rapid connection patterns

### Krok 3: Poczekaj 30-60 sekund

Agent batchuje logi co 30 sekund. Poczekaj chwilę, aż zebrane alerty zostaną wysłane.

### Krok 4: Sprawdź logi

```bash
# Sprawdź czy Suricata wykrył alerty
sudo tail -50 /var/log/suricata/eve.json | grep '"event_type":"alert"'

# Sprawdź czy agent wysłał alerty
tail -30 /var/log/logmaster-agent/agent.log | grep "Uploaded"

# Sprawdź logi systemd
sudo journalctl -u logmaster-agent -n 30
```

---

## 🎯 Najskuteczniejsze metody generowania alertów

### Metoda 1: Port Scanning (najniezawodniejsza)
```bash
# MySQL port scan
nc -zv -w1 scanme.nmap.org 3306

# PostgreSQL scan
nc -zv -w1 scanme.nmap.org 5432

# SSH scan burst (5x w ciągu sekundy)
for i in {1..5}; do nc -zv -w1 scanme.nmap.org 22; done
```

**Triggery reguły:**
- `ET POLICY Suspicious inbound to mySQL port 3306`
- `ET POLICY Suspicious inbound to PostgreSQL port 5432`
- `ET SCAN Potential SSH Scan`

### Metoda 2: Suspicious User-Agent
```bash
curl -A "sqlmap/1.0" http://testphp.vulnweb.com/
curl -A "Nikto/2.1.6" http://testphp.vulnweb.com/
curl -A "Nmap Scripting Engine" http://testphp.vulnweb.com/
```

**Triggery reguły:**
- `ET POLICY SQL DB Scanner User-Agent`
- `ET POLICY Vulnerability Scanner User-Agent`

### Metoda 3: SQL Injection Patterns
```bash
curl "http://testphp.vulnweb.com/artists.php?artist=1' OR '1'='1"
curl "http://testphp.vulnweb.com/artists.php?artist=1 UNION SELECT"
```

**Triggery reguły:**
- `ET WEB_SPECIFIC_APPS SQL Injection Attempt`

### Metoda 4: XSS Patterns
```bash
curl "http://testphp.vulnweb.com/search.php?q=<script>alert('xss')</script>"
curl "http://testphp.vulnweb.com/search.php?q=<iframe src='javascript:alert(1)'>"
```

**Triggery reguły:**
- `ET WEB_SPECIFIC_APPS XSS Attempt`

### Metoda 5: Rapid Connections (DoS pattern)
```bash
for i in {1..50}; do curl -s http://testphp.vulnweb.com/ & done
wait
```

**Triggery reguły:**
- `SURICATA STREAM excessive retransmissions`
- Potencjalnie `ET DOS` rules

---

## 🔍 Weryfikacja alertów

### Na maszynie z agentem:

```bash
# 1. Sprawdź Suricata EVE log
sudo tail -100 /var/log/suricata/eve.json | jq 'select(.event_type=="alert")'

# 2. Policz alerty
sudo grep '"event_type":"alert"' /var/log/suricata/eve.json | wc -l

# 3. Zobacz typy alertów
sudo grep '"event_type":"alert"' /var/log/suricata/eve.json | jq -r '.alert.signature' | sort | uniq -c

# 4. Sprawdź agent logs
tail -50 /var/log/logmaster-agent/agent.log | grep -E "Uploaded|Shipping"

# 5. Zobacz szczegóły ostatnich wysyłek
grep "Uploaded.*events" /var/log/logmaster-agent/agent.log | tail -5
```

### Na serwerze (WebService):

```bash
# Sprawdź czy WebService otrzymał logi
docker logs webservice --tail 100 | grep "LOG UPLOAD AUTHORIZED"

# Sprawdź walidację ServerId
docker logs webservice --tail 100 | grep "VALIDATION SUCCESS"

# Sprawdź LogService
docker logs logservice --tail 50 | grep "Processing"
```

---

## 🛠️ Troubleshooting

### Problem: Brak alertów w eve.json

**Sprawdź czy Suricata działa:**
```bash
sudo systemctl status suricata
sudo journalctl -u suricata -n 50
```

**Sprawdź konfigurację:**
```bash
# Sprawdź czy EVE JSON jest włączony
sudo grep -A5 "eve-log:" /etc/suricata/suricata.yaml

# Sprawdź czy reguły są załadowane
sudo suricata-update list-enabled-sources
```

**Restart Suricata:**
```bash
sudo systemctl restart suricata
sudo systemctl status suricata
```

### Problem: Agent nie wysyła alertów

**Sprawdź offset:**
```bash
cat /var/lib/logmaster-agent/offset.json
```

**Sprawdź czy agent działa:**
```bash
sudo systemctl status logmaster-agent
sudo journalctl -u logmaster-agent -f
```

**Restart agenta:**
```bash
sudo systemctl restart logmaster-agent
```

### Problem: Alerty odrzucane przez WebService (400)

**Sprawdź czy ServerId jest zarejestrowany:**
```bash
curl http://your-vm-service:8084/api/servers
```

**Sprawdź config.json agenta:**
```bash
grep server_guid /opt/logmaster-agent/config.json
```

---

## 📊 Oczekiwane wyniki

Po uruchomieniu `trigger_suricata_alerts.sh` powinieneś zobaczyć:

### W Suricata eve.json:
```json
{
  "timestamp": "2025-12-09T21:00:00.000000+0000",
  "event_type": "alert",
  "alert": {
    "signature": "ET POLICY Suspicious inbound to mySQL port 3306",
    "severity": 2,
    ...
  }
}
```

### W agent.log:
```
[INFO] Uploaded 85 events (0.01 MB compressed) for server 3b4f8b96-80c4-4479-8778-8013dfe81081
```

### W WebService logs:
```
✅ LOG UPLOAD AUTHORIZED: ServerId 3b4f8b96-80c4-4479-8778-8013dfe81081 (VirutalMachineWithLogger3, Status: Active)
Agent batch received and validated in 45 ms, size: 71148 bytes
```

---

## 🎓 Dodatkowe testy

### Test 1: Generuj alerty przez 5 minut
```bash
for i in {1..10}; do 
    bash trigger_suricata_alerts.sh
    sleep 30
done
```

### Test 2: Monitoruj w czasie rzeczywistym
```bash
# Terminal 1: Uruchom generator
bash trigger_suricata_alerts.sh

# Terminal 2: Monitoruj Suricata
sudo tail -f /var/log/suricata/eve.json | grep --line-buffered '"event_type":"alert"'

# Terminal 3: Monitoruj agenta
tail -f /var/log/logmaster-agent/agent.log
```

### Test 3: Weryfikuj w WebService
```bash
# Na serwerze z Dockerem
docker logs -f webservice | grep "LOG UPLOAD"
```

---

## ✅ Sukces!

Jeśli widzisz:
1. ✅ Alerty w `/var/log/suricata/eve.json`
2. ✅ `Uploaded X events` w `/var/log/logmaster-agent/agent.log`
3. ✅ `LOG UPLOAD AUTHORIZED` w logach WebService
4. ✅ Dane w MongoDB (sprawdź przez LogService API)

**Wszystko działa poprawnie! 🎉**

