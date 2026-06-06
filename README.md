# Termin-Wächter · 116117

Ein kostenloses, persönliches Tool zur automatischen Überwachung freier Psychiater-Termine
über den offiziellen [116117 Terminservice](https://www.116117-termine.de) der KBV.

🌐 **Live:** [https://www.116117-monitor.tech](https://www.116117-monitor.tech)

Einfach E-Mail, Vermittlungscode und PLZ eingeben — der Server prüft alle 10 Minuten
ob Termine im Umkreis von 150 km verfügbar sind und schickt sofort eine Benachrichtigung.

**Fachrichtung:** Psychiatrie & Nervenheilkunde  
**Stack:** Python · FastAPI · Playwright · SQLite · Resend

---

## Wie es funktioniert

Der Nutzer gibt drei Felder ein. Der Server öffnet automatisch die 116117-Seite
mit Playwright (Chromium), liest den Seitentext aus und prüft ob Termine verfügbar sind.
Sobald die Anzahl der Termine größer als 0 ist, wird sofort eine E-Mail via Resend verschickt.

Die gesuchte URL wird automatisch zusammengesetzt:
```
https://www.116117-termine.de/termin/suchen/{VERMITTLUNGSCODE}/{PLZ}/W550,W147,W533,W149,W141?suchradius=150
```

---

## Schnellstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
/opt/terminwaechter/.venv/bin/playwright install-deps chromium
cp .env.example .env   # .env ausfüllen
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Voraussetzungen

- Python 3.12
- Resend-Konto mit verifizierter Domain: [resend.com](https://resend.com)
- Auf Linux-Server: `xvfb` für virtuelles Display (`apt install -y xvfb`)

---

## Deployment

Getestet und produktiv auf **DigitalOcean** (Ubuntu 24.04, Frankfurt) mit systemd + Nginx + HTTPS.
Detaillierte Anleitung im Wiki des Repositories.

---

© 2026 Andrei Tregubov · Nicht mit KBV oder 116117 assoziiert · Nur für den persönlichen Gebrauch

---

# Termin-Wächter · 116117 (English)

A free, personal tool for automatic monitoring of available psychiatric appointments
via the official [116117 Terminservice](https://www.116117-termine.de) by KBV (Germany).

🌐 **Live:** [https://www.116117-monitor.tech](https://www.116117-monitor.tech)

Simply enter your email, referral code (Vermittlungscode) and postal code — the server
checks every 10 minutes whether appointments are available within 150 km and sends
an instant email notification.

**Specialty:** Psychiatry & Neurology  
**Stack:** Python · FastAPI · Playwright · SQLite · Resend

---

## How it works

The user fills in three fields. The server automatically opens the 116117 website
using Playwright (headless Chromium), reads the page text and checks whether
appointments are available. As soon as the number of available slots is greater
than 0, an email is sent immediately via Resend.

The target URL is constructed automatically:
```
https://www.116117-termine.de/termin/suchen/{REFERRAL_CODE}/{POSTAL_CODE}/W550,W147,W533,W149,W141?suchradius=150
```

The service codes `W550,W147,W533,W149,W141` correspond to psychiatry and neurology.
The search radius is fixed at 150 km.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
/opt/terminwaechter/.venv/bin/playwright install-deps chromium
cp .env.example .env   # fill in your credentials
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Requirements

- Python 3.12
- Resend account with verified domain: [resend.com](https://resend.com)
- On Linux server: `xvfb` for virtual display (`apt install -y xvfb`)

---

## Deployment

Tested and running in production on **DigitalOcean** (Ubuntu 24.04, Frankfurt region)
with systemd + Nginx + HTTPS (Let's Encrypt).

---

© 2026 Andrei Tregubov · Not affiliated with KBV or 116117 · For personal use only
