# LogMaster Python Agent

Agent automatyzuje instalację Suricata na serwerach Linux, przesyła heartbeaty do LogMaster i streamuje logi EVE JSON.

> **ℹ️ Uwaga o reinstalacji**: Oryginalny `install.sh` działa poprawnie przy pierwszej instalacji. Poprawki dotyczą głównie **reinstalacji** po użyciu `uninstall.sh`. Zobacz [TROUBLESHOOTING_REINSTALL.md](TROUBLESHOOTING_REINSTALL.md) dla szczegółów.

## Pliki

- `install.sh` – instalator (Ubuntu) przygotowujący środowisko, użytkownika, config i usługę systemd
- `uninstall.sh` – skrypt deinstalacyjny z opcjonalnym usunięciem Suricata
- `diagnose.sh` – narzędzie diagnostyczne do debugowania problemów
- `agent.py` – proces, który orchestruje instalację Suricata, wysyła heartbeaty i startuje log_shipper
- `suricata_installer.py` – wykrywa dystrybucję, instaluje paczki, konfiguruje logowanie EVE, uruchamia usługę
- `log_shipper.py` – monitoruje `/var/log/suricata/eve.json`, batchuje logi i wysyła je do API z kompresją gzip
- `config.json.template` – szablon konfiguracji generowanej przez instalator
- `requirements.txt` – zależności Python

## Szybka instalacja

```bash
curl -sfL https://raw.githubusercontent.com/yourusername/log-master-agent/main/PythonAgent/install.sh | \
  sudo bash -s -- <SERVER_GUID> <API_URL>
```

Instalator wykona:
1. Walidację uprawnień i dystrybucji (Ubuntu)
2. Instalację python3/pip i zależności systemowych
3. Utworzenie użytkownika `logmaster-agent` i katalogów (`/opt`, `/var/lib`, `/var/log`)
4. Pobranie plików agenta + `config.json.template`
5. Wygenerowanie `config.json` z podstawionymi parametrami
6. Instalację zależności `pip`
7. Wykrycie interfejsu sieciowego i konfigurację Suricata
8. Rejestrację usługi `logmaster-agent.service` i start

## Diagnostyka

Jeśli masz problemy z uruchomieniem agenta lub Suricata:

```bash
sudo bash diagnose.sh
```

Ten skrypt sprawdzi:
- Status serwisów systemd
- Konfigurację Suricata i interfejsów sieciowych
- Logi błędów
- Uprawnienia do plików
- Połączenie z API

## Logi i stan

- Logi agenta: `/var/log/logmaster-agent/agent.log`
- Błędy: `/var/log/logmaster-agent/agent.err.log`
- Offset logów Suricata: `/var/lib/logmaster-agent/offset.json`
- Logi Suricata: `journalctl -u suricata -f`
- Logi agenta: `journalctl -u logmaster-agent -f`

## Typowe problemy

### Suricata nie startuje po reinstalacji

**Problem**: Po użyciu `uninstall.sh` i ponownej instalacji Suricata nie uruchamia się.

**Rozwiązanie**: 
1. Sprawdź konfigurację interfejsu: `grep -A 3 "af-packet:" /etc/suricata/suricata.yaml`
2. Zweryfikuj dostępne interfejsy: `ip -br link show`
3. Uruchom diagnostykę: `sudo bash diagnose.sh`
4. Testuj konfigurację: `sudo suricata -T -c /etc/suricata/suricata.yaml`

### Brak logów w eve.json

**Problem**: Plik `/var/log/suricata/eve.json` jest pusty lub nie istnieje.

**Rozwiązanie**:
1. Sprawdź czy Suricata działa: `systemctl status suricata`
2. Sprawdź logi błędów: `journalctl -u suricata -n 50`
3. Sprawdź uprawnienia: `ls -la /var/log/suricata/`

### Agent nie łączy się z API

**Problem**: Agent wysyła heartbeaty, ale serwer ich nie otrzymuje.

**Rozwiązanie**:
1. Sprawdź URL w konfiguracji: `cat /opt/logmaster-agent/config.json | grep api_url`
2. Testuj łączność: `curl -v <API_URL>/api/agent/heartbeat`
3. Sprawdź firewall: `sudo ufw status` lub `sudo iptables -L`

## Odinstalowanie

```bash
sudo bash uninstall.sh
```

Skrypt zapyta czy chcesz również usunąć Suricata i jej konfigurację. Możesz zachować Suricata dla przyszłych reinstalacji.

