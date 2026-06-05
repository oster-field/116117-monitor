# Termin-Wächter · 116117

Automatische Benachrichtigung bei freien Terminen beim Psychiater / Nervenarzt über den offiziellen
116117 Terminservice. Das Tool prüft alle 10 Minuten, ob neue Termine verfügbar sind, und sendet
bei Erfolg eine E-Mail-Benachrichtigung via EmailJS.

> © 2026 Andrei Tregubov — persönliches Werkzeug, nicht mit KBV oder 116117 assoziiert.

---

## Projektstruktur

```
project/
├── main.py          # FastAPI-App, Routen, APScheduler
├── scraper.py       # Playwright-Scraper für 116117-termine.de
├── database.py      # SQLite-Helfer mit Fernet-Verschlüsselung
├── requirements.txt
├── .env.example     # Vorlage für Umgebungsvariablen
└── static/
    └── index.html   # Frontend (kein Build-Schritt nötig)
```

---

## Lokale Entwicklung (Schritt für Schritt)

### 1. Voraussetzungen

- Python 3.11 oder neuer
- pip

### 2. Repository klonen und Abhängigkeiten installieren

```bash
git clone <dein-repo>
cd project
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. Umgebungsvariablen einrichten

```bash
cp .env.example .env
```

Öffne `.env` und ersetze `PASTE_YOUR_GENERATED_KEY_HERE` mit einem frischen Schlüssel:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Für lokale Tests: `PLAYWRIGHT_HEADLESS=false` lassen (öffnet ein echtes Browser-Fenster).

### 4. Server starten

```bash
uvicorn main:app --reload --port 8000
```

Dann im Browser öffnen: [http://localhost:8000](http://localhost:8000)

---

## EmailJS einrichten (einmalig, kostenlos)

1. Konto erstellen auf [emailjs.com](https://www.emailjs.com) (Free Tier: 200 E-Mails/Monat)
2. **Email Service** hinzufügen (z. B. Gmail, Outlook) → `Service ID` notieren
3. **Email Template** erstellen mit diesen Variablen:
   ```
   An: {{to_email}}
   Betreff: ✓ Freier Psychiater-Termin gefunden!
   
   Hallo,
   
   ein freier Termin wurde gefunden: {{appointment_info}}
   
   Direkt buchen: {{booking_url}}
   ```
   → `Template ID` notieren
4. Unter **Account → General** den `Public Key` kopieren
5. Alle drei Werte im Webformular unter „E-Mail-Einstellungen" eintragen

---

## VPS-Deployment (z. B. Hetzner CX22)

### Einmalige Server-Vorbereitung

```bash
apt update && apt install -y python3.11 python3-pip chromium chromium-driver
pip install -r requirements.txt
python -m playwright install chromium
```

### `.env` auf dem Server anpassen

```
PLAYWRIGHT_HEADLESS=true     # kein Display auf VPS
POLL_INTERVAL_MINUTES=10
ENCRYPTION_KEY=<dein-schlüssel>
```

### Als systemd-Dienst betreiben

Datei `/etc/systemd/system/terminwaechter.service` erstellen:

```ini
[Unit]
Description=Termin-Wächter 116117
After=network.target

[Service]
WorkingDirectory=/opt/terminwaechter
EnvironmentFile=/opt/terminwaechter/.env
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable terminwaechter
systemctl start terminwaechter
systemctl status terminwaechter
```

### Logs beobachten

```bash
journalctl -u terminwaechter -f
```

---

## Hinweis zu headless / Akamai

Die Seite `116117-termine.de` wird durch **Akamai Bot Manager** geschützt.

| Modus | Lokal | VPS |
|---|---|---|
| `PLAYWRIGHT_HEADLESS=false` | ✅ funktioniert zuverlässig | ❌ kein Display |
| `PLAYWRIGHT_HEADLESS=true`  | ⚠️ kann geblockt werden | ✅ bevorzugt |

Das Skript setzt bereits Stealth-Maßnahmen ein (WebDriver-Flag entfernen, realistische
User-Agent-/Locale-/Timezone-Header). Falls es dennoch zu Access-Denied-Fehlern kommt,
kann eine Xvfb-Lösung auf dem VPS helfen:

```bash
apt install -y xvfb
# ExecStart in systemd anpassen:
ExecStart=/usr/bin/xvfb-run python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
# und PLAYWRIGHT_HEADLESS=false setzen
```

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/monitor/start` | Monitoring-Job anlegen |
| `GET` | `/api/monitor/status/{job_id}` | Status abfragen |
| `DELETE` | `/api/monitor/{job_id}` | Job stoppen und löschen |
| `GET` | `/health` | Liveness-Check |

---

## Datenschutz & Sicherheit

- E-Mail-Adressen werden mit **Fernet-Symmetricverschlüsselung** (AES-128-CBC) in SQLite gespeichert
- Der Schlüssel liegt ausschließlich in der `.env`-Datei auf deinem Server
- Keine Weitergabe von Daten an Dritte
- EmailJS-Zugangsdaten werden **nicht** in der Datenbank gespeichert — nur in der Browser-Session
