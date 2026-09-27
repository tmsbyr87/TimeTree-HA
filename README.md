<h1 align="center" style="border-bottom: none">
  <img alt="TimeTree for Home Assistant" src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/custom_components/timetree/brand/logo@2x.png" width="420" />
</h1>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=tmsbyr87&repository=TimeTree-HA&category=integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge" alt="HACS Custom"></a>
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Ftmsbyr87%2FTimeTree-HA%2Fmain%2Fcustom_components%2Ftimetree%2Fmanifest.json&query=%24.version&label=Version&style=for-the-badge&color=purple" alt="Version">
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.6%2B-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white" alt="Home Assistant 2024.6+">
  <a href="https://github.com/tmsbyr87/TimeTree-HA/stargazers"><img src="https://img.shields.io/github/stars/tmsbyr87/TimeTree-HA?style=for-the-badge&label=Stars&color=yellow" alt="Stars"></a>
  <a href="https://github.com/tmsbyr87/TimeTree-HA/commits/main"><img src="https://img.shields.io/github/last-commit/tmsbyr87/TimeTree-HA?style=for-the-badge&label=Updated" alt="Last commit"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/tmsbyr87/TimeTree-HA?style=for-the-badge&color=green" alt="License"></a>
</p>

<p align="center">
  Bring your shared <a href="https://timetreeapp.com">TimeTree</a> calendar into <a href="https://www.home-assistant.io">Home Assistant</a> — sign in once, and every family event shows up as a native <code>calendar</code> entity you can put on dashboards and use in automations.
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/device.png" alt="TimeTree device page in Home Assistant" width="760" />
</p>

## Why this exists

TimeTree retired its public API on 22 December 2023, and there is no official Home Assistant integration. This project talks to the same web endpoints the TimeTree web app uses, so your shared calendar keeps working inside Home Assistant — no ICS exports, no cron jobs, no third-party sync services.

> **Heads-up:** this is an *unofficial* integration built on TimeTree's internal web API. If TimeTree changes those endpoints, the integration can stop working until it is updated. It has been stable in daily use, but treat it as community software, not a supported product.

## How it works

- **Sign in once** — e-mail and password go into the config flow; the resulting session cookie is reused for every refresh and renewed automatically when it expires. If renewal fails, Home Assistant opens a re-authentication dialog.
- **Incremental sync** — after the first full load only *changes* are fetched (`since` cursor), so a short refresh interval costs almost nothing.
- **Real recurrence handling** — `RRULE` / `EXDATE` series are expanded with the same [`ical`](https://github.com/allenporter/ical) library Home Assistant's own Local Calendar uses. Modified single occurrences and cancelled dates render correctly.
- **Time zones done right** — timed events keep their TimeTree time zone; all-day events become proper date-only events with an exclusive end, exactly as the Calendar entity expects.
- **Resilient** — one malformed event is logged and skipped; it never takes the whole calendar down.
- **Branded** — the calendar entity carries the TimeTree icon, served by the integration itself (no `www/` copying).

| TimeTree | Home Assistant |
| --- | --- |
| Timed event | `calendar` event in the event's time zone |
| All-day / multi-day event | Date-only event, exclusive end (RFC 5545) |
| Recurring series (`RRULE`) | Expanded, including `EXDATE` exceptions |
| Edited single occurrence | Shown as its own event |
| Note · Location | `description` · `location` |
| Deleted event | Removed on next refresh |
| Memo · Birthday entries | Not imported (same as the reference exporter) |

## Prerequisites

- **Home Assistant 2024.6** or later
- A TimeTree account with **e-mail/password login** (social logins are not supported by the web endpoints this integration uses)
- [HACS](https://hacs.xyz) for one-click installation *(optional — manual install works too)*

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and add this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tmsbyr87&repository=TimeTree-HA&category=integration)

Or manually: **HACS → Integrations → ⋮ → Custom repositories** → add `https://github.com/tmsbyr87/TimeTree-HA` with category **Integration**, then download **TimeTree** and restart Home Assistant.

### Manual

1. Download this repository as ZIP
2. Copy `custom_components/timetree/` into your `config/custom_components/` folder
3. Restart Home Assistant

## Setup

1. **Settings → Devices & Services → Add Integration**
2. Search for **TimeTree**
3. Enter your TimeTree e-mail and password
4. Pick the calendar you want to import — one entry per calendar, add more if you like

You get a device named after the calendar with a `calendar.<name>` entity.

## Configuration

Open the entry's **Configure** dialog to set the refresh interval (5–120 minutes, default 15). Because syncing is incremental, a short interval is cheap.

Credentials are stored in the config entry, like any other cloud integration in Home Assistant, so the session can be renewed without you. Change your TimeTree password? Home Assistant will prompt you to re-authenticate.

## Using it

The entity behaves like every other Home Assistant calendar:

- Drop it on a **Calendar card** or use it with community cards such as `atomic-calendar-revive`
- Trigger automations with the **calendar event trigger** (“5 minutes before an event starts”)
- Read the next event from the entity's `message`, `start_time`, `end_time`, `description` and `location` attributes in templates

```yaml
# Example: announce the first event of the day at 07:00
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: notify.mobile_app_phone
    data:
      message: >
        Today: {{ state_attr('calendar.family', 'message') }}
        ({{ state_attr('calendar.family', 'start_time') }})
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| *E-mail or password is wrong* during setup | Log in on [timetreeapp.com](https://timetreeapp.com) with the same credentials; social-login accounts need a password set first |
| *TimeTree is rate-limiting login attempts* | Wait a few minutes — TimeTree throttles repeated sign-ins |
| Entity turns `unavailable` | Check **Settings → System → Logs** for `timetree`; a re-auth prompt appears if the session could not be renewed |
| An event is missing | Memos and birthday entries are intentionally skipped; anything else, open an issue with the log line `Skipping TimeTree event …` |

<details>
<summary><strong>🇩🇪 Kurzanleitung auf Deutsch</strong></summary>

**Installation:** HACS → Integrationen → ⋮ → *Custom repositories* → `https://github.com/tmsbyr87/TimeTree-HA` (Kategorie *Integration*) → herunterladen → Home Assistant neu starten.

**Einrichtung:** Einstellungen → Geräte & Dienste → Integration hinzufügen → **TimeTree** → E-Mail und Passwort eingeben → Kalender auswählen. Es entsteht eine `calendar.*`-Entität, die sich wie jeder andere HA-Kalender verwenden lässt.

**Wichtig:** Die Integration nutzt die interne Web-Schnittstelle von TimeTree, weil die offizielle API 2023 abgeschaltet wurde. Ändert TimeTree diese Schnittstelle, kann die Integration bis zu einem Update ausfallen. Memos und Geburtstage werden nicht übernommen.

</details>

## Contributing

Issues and pull requests are welcome. The API client, event conversion and sync store are plain Python without Home Assistant imports and are covered by `pytest`:

```bash
python -m venv .venv && .venv/bin/pip install ical pytest pytest-asyncio "aiohttp<3.13" aioresponses
.venv/bin/python -m pytest tests -p asyncio --asyncio-mode=auto
```

## Acknowledgements

Endpoint behaviour is based on the excellent [eoleedi/TimeTree-Exporter](https://github.com/eoleedi/TimeTree-Exporter). TimeTree and the TimeTree logo are trademarks of TimeTree, Inc.; this project is not affiliated with or endorsed by TimeTree.

## License

[MIT](LICENSE)
