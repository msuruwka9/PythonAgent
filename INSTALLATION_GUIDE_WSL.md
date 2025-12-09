# 📘 Przewodnik instalacji PythonAgent na WSL 2

## 🎯 Co robi install.sh?

Skrypt `install.sh` automatycznie:
1. ✅ Sprawdza czy system to Ubuntu (wymagane uprawnienia root)
2. ✅ Instaluje zależności systemowe (Python3, pip, Suricata, itp.)
3. ✅ Tworzy użytkownika systemowego `logmaster-agent`
4. ✅ Pobiera pliki agenta z GitHub
5. ✅ Konfiguruje Suricatę do logowania w formacie EVE JSON
6. ✅ Tworzy usługę systemd i uruchamia agenta

## 🚀 Instalacja na WSL 2 - Krok po kroku

### Metoda 1: Instalacja jedną komendą (ZALECANA)

1. **Otwórz WSL Ubuntu:**
   ```powershell
   wsl
   ```

2. **Uruchom instalator bezpośrednio z GitHub:**
   ```bash
   curl -sfL https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh | \
     sudo bash -s -- <SERVER_GUID> <API_URL>
   ```

   **Przykład z rzeczywistymi danymi:**
   ```bash
   curl -sfL https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh | \
     sudo bash -s -- 550e8400-e29b-41d4-a716-446655440000 https://logmaster.example.com
   ```

### Metoda 2: Instalacja manualna (więcej kontroli)

1. **Otwórz WSL Ubuntu:**
   ```powershell
   wsl
   ```

2. **Utwórz katalog tymczasowy:**
   ```bash
   mkdir -p ~/logmaster-install
   cd ~/logmaster-install
   ```

3. **Pobierz skrypt instalacyjny:**
   ```bash
   wget https://raw.githubusercontent.com/msuruwka9/PythonAgent/main/install.sh
   chmod +x install.sh
   ```

4. **Uruchom instalator z parametrami:**
   ```bash
   sudo ./install.sh <SERVER_GUID> <API_URL>
   ```

   **Przykład:**
   ```bash
   sudo ./install.sh 550e8400-e29b-41d4-a716-446655440000 https://logmaster.example.com
   ```

## 📋 Wymagane parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `SERVER_GUID` | Unikalny identyfikator serwera (UUID) | `550e8400-e29b-41d4-a716-446655440000` |
| `API_URL` | URL do API LogMaster (bez końcowego `/`) | `https://logmaster.example.com` |
| `AgentSourceBase` (opcjonalny) | Własny URL do plików agenta | `https://raw.githubusercontent.com/user/repo/main` |

## 🔍 Sprawdzanie stanu instalacji

```bash
# Status usługi
sudo systemctl status logmaster-agent

# Logi agenta
sudo tail -f /var/log/logmaster-agent/agent.log

# Błędy
sudo tail -f /var/log/logmaster-agent/agent.err.log

# Status Suricata
sudo systemctl status suricata
```

## 📂 Lokalizacje plików po instalacji

```
/opt/logmaster-agent/          # Pliki aplikacji
├── agent.py
├── suricata_installer.py
├── log_shipper.py
├── config.json                # Wygenerowana konfiguracja
└── requirements.txt

/var/lib/logmaster-agent/      # Stan aplikacji
└── offset.json                # Offset logów Suricata

/var/log/logmaster-agent/      # Logi agenta
├── agent.log
└── agent.err.log

/var/log/suricata/             # Logi Suricata
└── eve.json                   # Logi w formacie EVE JSON
```

## ⚙️ Zarządzanie usługą

```bash
# Start
sudo systemctl start logmaster-agent

# Stop
sudo systemctl stop logmaster-agent

# Restart
sudo systemctl restart logmaster-agent

# Włącz autostart
sudo systemctl enable logmaster-agent

# Wyłącz autostart
sudo systemctl disable logmaster-agent

# Zobacz logi systemd
sudo journalctl -u logmaster-agent -f
```

## 🗑️ Odinstalowanie

```bash
# Zatrzymaj i usuń usługę
sudo systemctl disable --now logmaster-agent

# Usuń pliki
sudo rm -rf /opt/logmaster-agent
sudo rm -rf /var/lib/logmaster-agent
sudo rm -rf /var/log/logmaster-agent
sudo rm /etc/systemd/system/logmaster-agent.service

# Przeładuj systemd
sudo systemctl daemon-reload

# Opcjonalnie: usuń użytkownika
sudo userdel logmaster-agent
```

## ⚠️ Wymagania systemowe

- **OS:** Ubuntu (sprawdzane przez instalator)
- **Uprawnienia:** root/sudo
- **Połączenie:** dostęp do internetu (GitHub, apt repositories)
- **Python:** 3.x (instalowane automatycznie)
- **Suricata:** instalowana automatycznie

## 🐛 Rozwiązywanie problemów

### Problem: "Only Ubuntu is supported"
**Rozwiązanie:** Upewnij się, że używasz dystrybucji Ubuntu w WSL:
```bash
cat /etc/os-release
```

### Problem: Agent nie startuje
**Rozwiązanie:** Sprawdź logi błędów:
```bash
sudo journalctl -u logmaster-agent -n 50
cat /var/log/logmaster-agent/agent.err.log
```

### Problem: Brak połączenia z API
**Rozwiązanie:** Sprawdź czy API URL jest poprawny w konfiguracji:
```bash
cat /opt/logmaster-agent/config.json
```

### Problem: Suricata nie działa
**Rozwiązanie:**
```bash
sudo systemctl status suricata
sudo journalctl -u suricata -n 50
```

## 🔧 Konfiguracja zaawansowana

Edytuj `/opt/logmaster-agent/config.json`:

```json
{
  "server_guid": "twoj-guid",
  "api_url": "https://twoje-api.com",
  "heartbeat_interval_seconds": 60,    // Częstotliwość heartbeat
  "log_shipper": {
    "batch_size": 100,                 // Rozmiar paczki logów
    "flush_interval_seconds": 30,      // Częstotliwość wysyłania
    "max_retry_attempts": 3,           // Próby ponowienia
    "retry_backoff_seconds": 5         // Opóźnienie między próbami
  }
}
```

Po zmianach:
```bash
sudo systemctl restart logmaster-agent
```

## 📝 Jak uzyskać SERVER_GUID?

SERVER_GUID to unikalny identyfikator serwera w systemie LogMaster. Powinieneś go otrzymać:
1. Z panelu administracyjnego LogMaster
2. Od administratora systemu
3. Lub wygenerować nowy UUID:
   ```bash
   uuidgen
   ```

## 🌐 Testowanie z lokalnym API

Jeśli testujesz lokalnie na WSL:
```bash
# Użyj adresu IP hosta Windows
sudo ./install.sh <GUID> http://$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):5000
```

## ✅ Weryfikacja instalacji

Po instalacji sprawdź:

```bash
# 1. Czy usługa działa
sudo systemctl is-active logmaster-agent
# Powinno wyświetlić: active

# 2. Czy Suricata działa
sudo systemctl is-active suricata
# Powinno wyświetlić: active

# 3. Czy logi są generowane
ls -lh /var/log/suricata/eve.json
ls -lh /var/log/logmaster-agent/agent.log

# 4. Czy agent wysyła heartbeaty (sprawdź w logach)
sudo tail -20 /var/log/logmaster-agent/agent.log | grep -i heartbeat
```

## 📞 Wsparcie

W razie problemów:
1. Sprawdź logi: `/var/log/logmaster-agent/agent.log`
2. Sprawdź błędy: `/var/log/logmaster-agent/agent.err.log`
3. Sprawdź status: `sudo systemctl status logmaster-agent`
4. Sprawdź konfigurację: `cat /opt/logmaster-agent/config.json`

