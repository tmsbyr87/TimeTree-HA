# TimeTree für Home Assistant

Bindet einen TimeTree-Kalender als `calendar.*`-Entität ein. Einmal im
Einrichtungsdialog anmelden, Kalender wählen – fertig. Die Sitzung wird
wiederverwendet und bei Ablauf automatisch erneuert.

## Wichtig zu wissen

TimeTree hat seine öffentliche API am 22.12.2023 abgeschaltet. Diese
Integration nutzt die **interne Schnittstelle der TimeTree-Web-App** (wie das
Projekt [eoleedi/TimeTree-Exporter](https://github.com/eoleedi/TimeTree-Exporter)).
Ändert TimeTree diese Schnittstelle, kann die Integration ohne Vorwarnung
ausfallen. Für einen Familienkalender ist das in der Praxis unproblematisch,
aber es ist kein offiziell unterstützter Weg.

E-Mail und Passwort werden im Config-Entry gespeichert (HA-Standard für
Cloud-Integrationen), damit die Sitzung ohne Nutzereingriff erneuert werden
kann. Schlägt das fehl, startet HA den Reauth-Dialog.

## Installation über HACS

Repo: [tmsbyr87/TimeTree-HA](https://github.com/tmsbyr87/TimeTree-HA)

1. HACS → Integrationen → ⋮ → **Custom repositories**
2. `https://github.com/tmsbyr87/TimeTree-HA` eintragen, Kategorie **Integration**
3. „TimeTree" herunterladen, Home Assistant neu starten

Ohne HACS: den Ordner `custom_components/timetree/` nach
`<config>/custom_components/timetree/` kopieren und neu starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „TimeTree"**
2. E-Mail und Passwort des TimeTree-Kontos eingeben
3. Kalender aus der Liste wählen

Ergebnis: eine Entität `calendar.<kalendername>` mit Gerät „TimeTree".

## Optionen

Über das Zahnrad des Eintrags lässt sich das Abrufintervall setzen
(5–120 Minuten, Standard 15). TimeTree liefert nur Änderungen seit dem
letzten Abruf, ein kurzes Intervall kostet also wenig.

## Was abgebildet wird

| TimeTree | Home Assistant |
|----------|----------------|
| Termin mit Uhrzeit | Termin in der jeweiligen Zeitzone |
| Ganztägig | Ganztägig (Ende exklusiv, wie iCalendar) |
| Serientermin (RRULE) | aufgelöst, inkl. Ausnahmen (EXDATE) |
| Geänderte Einzelinstanz einer Serie | erscheint als eigener Termin |
| Notiz, Ort | Beschreibung, Ort |
| Gelöschter Termin | wird entfernt |
| Memo, Geburtstag | **nicht** übernommen (wie im Referenzprojekt) |

## Aufbau

```
api.py          – aiohttp-Client (Login, Kalender, Sync) – ohne HA-Abhängigkeit
event.py        – TimeTree-Termin → ical.Event – ohne HA-Abhängigkeit
store.py        – Merge/Löschen/Cursor – ohne HA-Abhängigkeit
coordinator.py  – DataUpdateCoordinator, Re-Login
config_flow.py  – user → calendar, reauth, options
calendar.py     – CalendarEntity, Serienauflösung über ical-Timeline
```

Serien werden mit der Bibliothek `ical` (allenporter) aufgelöst – derselben,
die HAs eigene `local_calendar`-Integration verwendet.

## Branding

`brand/` enthält Icon und Logo im Format des Home-Assistant-Brands-Repos
(`icon.png` 256², `icon@2x.png` 512², `logo.png` Höhe 256, `logo@2x.png` Höhe 512,
jeweils mit Transparenz), erzeugt aus dem offiziellen TimeTree-Logo-Paket.

Home Assistant lädt Integrations-Icons **zentral** von `brands.home-assistant.io`;
für eine Custom Integration erscheint dort ein Platzhalter, bis die Dateien aus
`brand/` im Repo [home-assistant/brands](https://github.com/home-assistant/brands)
unter `custom_integrations/timetree/` eingereicht sind.

Lokal sichtbar ist das Branding trotzdem: Die Integration registriert ihren
`brand/`-Ordner selbst unter `/timetree_static/`, und die Kalender-Entität trägt
`entity_picture: /timetree_static/icon.png`. Es muss nichts nach `www/` kopiert werden.

## Tests

```bash
python -m venv .venv && .venv/bin/pip install ical pytest pytest-asyncio aiohttp aioresponses
.venv/bin/python -m pytest tests/timetree -p asyncio --asyncio-mode=auto
```

Die Tests decken API-Client, Terminumsetzung (inkl. Serien, ganztägig,
Zeitzonen) und die Merge-Logik ab – alles ohne laufendes Home Assistant.
