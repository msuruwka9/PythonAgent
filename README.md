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
7. Rejestrację usługi `logmaster-agent.service` i start

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

