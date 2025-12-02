# LogMaster Python Agent

Agent automatyzuje instalację Suricata na serwerach Linux, przesyła heartbeaty do LogMaster i streamuje logi EVE JSON.

## Pliki

- `install.sh` – instalator (Ubuntu) przygotowujący środowisko, użytkownika, config i usługę systemd
- `agent.py` – proces, który orchestruje instalację Suricata, wysyła heartbeaty i startuje log_shipper
- `suricata_installer.py` – wykrywa dystrybucję, instaluje paczki, konfiguruje logowanie EVE, uruchamia usługę
- `log_shipper.py` – monitoruje `/var/log/suricata/eve.json`, batchuje logi i wysyła je do API z kompresją gzip
- `config.json.template` – szablon konfiguracji generowanej przez instalator
- `requirements.txt` – zależności Python

## Szybka instalacja

```bash
curl -sfL https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh | \
  sudo bash -s -- <SERVER_GUID> <WEBSERVICE_URL> <VM_INTEGRATION_URL>
```

**Parametry:**
- `SERVER_GUID` - Unikalny GUID dla tej VM/serwera
- `WEBSERVICE_URL` - URL do WebService dla uploadu logów (np. https://webservice-xxx.ngrok.app)
- `VM_INTEGRATION_URL` - URL do VM Integration Service dla heartbeat (np. https://vm-service-xxx.ngrok.app)

**Przykład:**
```bash
curl -sfL https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh | \
  sudo bash -s -- \
    0a61b4ae-869c-4d2b-9702-1d6f100a63ce \
    https://webservice-3ffb54e7-ef8a-45ed-b484-20054c19875d.ngrok.app \
    https://vm-service-917bdec0-469f-44ac-9450-d008e16cc521.ngrok.app
```

**Co robi agent:**
- Zbiera logi Suricata z `/var/log/suricata/eve.json`
- Batchuje 100 eventów na raz
- Kompresuje za pomocą gzip (6.9KB → 87KB compression ratio)
- Wysyła do `WebService` przez POST `/api/logupload/uploadlogfile` z nagłówkiem `X-Server-Id` (identyfikacja serwera)
- Wysyła heartbeat co 60s do `VM Integration Service`

Instalator wykona:
1. Walidację uprawnień i dystrybucji (Ubuntu)
2. Instalację python3/pip/venv i zależności systemowych
3. Utworzenie użytkownika `logmaster-agent` i katalogów (`/opt`, `/var/lib`, `/var/log`)
4. Instalację Suricata (jeśli jeszcze nie zainstalowana)
5. Pobranie plików agenta + `config.json.template`
6. Wygenerowanie `config.json` z podstawionymi parametrami
7. Utworzenie virtual environment i instalację zależności Python
8. Rejestrację usługi `logmaster-agent.service` i start

## Logi i stan

- Logi agenta: `/var/log/logmaster-agent/agent.log`
- Błędy: `/var/log/logmaster-agent/agent.err.log`
- Offset logów Suricata: `/var/lib/logmaster-agent/offset.json`

## Odinstalowanie

```bash
sudo systemctl disable --now logmaster-agent
sudo rm -rf /opt/logmaster-agent /var/lib/logmaster-agent /var/log/logmaster-agent
sudo rm /etc/systemd/system/logmaster-agent.service
sudo systemctl daemon-reload
```

