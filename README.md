<h1 align="center" style="border-bottom: none">
  <img alt="TimeTree for Home Assistant" src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/custom_components/timetree/brand/logo@2x.png" width="420" />
</h1>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=tmsbyr87&repository=TimeTree-HA&category=integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge" alt="HACS Custom"></a>
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Ftmsbyr87%2FTimeTree-HA%2Fmain%2Fcustom_components%2Ftimetree%2Fmanifest.json&query=%24.version&label=Version&style=for-the-badge&color=purple" alt="Version">
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.12%2B-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white" alt="Home Assistant 2024.12+">
  <a href="https://github.com/tmsbyr87/TimeTree-HA/stargazers"><img src="https://img.shields.io/github/stars/tmsbyr87/TimeTree-HA?style=for-the-badge&label=Stars&color=yellow" alt="Stars"></a>
  <a href="https://github.com/tmsbyr87/TimeTree-HA/commits/main"><img src="https://img.shields.io/github/last-commit/tmsbyr87/TimeTree-HA?style=for-the-badge&label=Updated" alt="Last commit"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/tmsbyr87/TimeTree-HA?style=for-the-badge&color=green" alt="License"></a>
</p>

<p align="center">
  <a href="https://buymeacoffee.com/tmsbyr"><img src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me A Coffee"></a>
</p>

<p align="center">
  Bring your shared <a href="https://timetreeapp.com">TimeTree</a> calendar into <a href="https://www.home-assistant.io">Home Assistant</a> — sign in once, and every family event shows up as a native <code>calendar</code> entity you can put on dashboards and use in automations.
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/today-tomorrow-tablet.png" alt="TimeTree card in Home Assistant: today &amp; tomorrow" width="760" />
</p>

## Features at a glance

| | |
| --- | --- |
| 🔐 **Sign in once** | One entry per TimeTree account, pick any number of calendars; the session renews itself |
| 📅 **Native calendars** | A `calendar` entity per TimeTree calendar – recurring series, all-day events and time zones done right |
| 🏷️ **Your labels** | Colours and names from TimeTree; optional calendar per label for automations |
| 📊 **Sensors** | *Events today* and *Next event*, ready for dashboards and templates |
| 🔔 **TimeTree reminders** | The alerts you set in TimeTree fire a `timetree_reminder` event – with a ready-made blueprint for push and voice |
| 💬 **Comments & details** | Event comments in the card's detail sheet and via the `timetree.get_event_details` action |
| 🗓️ **Dashboard card** | Agenda, *Today & tomorrow* and month view, tabs, label chips – responsive, light & dark |
| 🛟 **Built to last** | Diagnostics without personal data, a repair notice if TimeTree changes its API, request limits that protect your account |

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

- **Home Assistant 2024.12** or later (tested with 2026.9)
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
4. Tick the calendars you want to import — all of them are preselected

You get one entry per TimeTree account and, for every selected calendar, a device named after it with its own `calendar.<name>` entity. All calendars share one login.

## Configuration

Open the entry's **Configure** dialog to

- **add or remove calendars** — calendars you joined later show up here; deselected calendars are removed together with their entities
- set the **refresh interval** (5–120 minutes, default 15). Because syncing is incremental, a short interval is cheap.

> **Upgrading from 1.3 or older?** Your existing entry is converted to an account entry automatically. The calendar keeps its entity id, history and dashboard cards; use **Configure** to add further calendars of the same account.

Credentials are stored in the config entry, like any other cloud integration in Home Assistant, so the session can be renewed without you. Change your TimeTree password? Home Assistant will prompt you to re-authenticate.

## Dashboard card

The integration ships its own Lovelace card, **TimeTree Agenda** (`custom:timetree-card`). It is registered automatically — after a restart it simply appears in the card picker. No YAML needed: everything is configurable in the visual editor.

<p align="center">
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/month-desktop.png" alt="Month view with tabs and label chips" width="100%" />
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/today-tomorrow-tablet.png" alt="Today &amp; tomorrow view on a tablet" width="100%" />
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/phone-month-dark.png" alt="Month view on a phone, dark" width="32%" />
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/phone-dialog-comments.png" alt="Event details with comments and photo hint" width="32%" />
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/phone-dark.png" alt="Agenda on a phone, dark" width="32%" />
</p>

- **Responsive** — a list on phones, day columns on tablets in landscape and on desktop. Decided by the card's own width (container queries), so it adapts inside any section or grid.
- **Theme-aware** — uses only Home Assistant theme variables, so light and dark themes just work; pick an accent colour if you like.
- **Works with any calendar** — not just TimeTree. Add several `calendar.*` entities; each gets its own colour.
- **Readable at a glance** — *Today* / *Tomorrow* labels, the running event highlighted with *Now*, all-day events first, locations and (optionally) descriptions.
- **Your TimeTree labels** — colours and names come straight from TimeTree. Show them on each event, filter the card to selected labels in the editor, or switch on the **chip bar** so anyone can toggle labels right on the card (remembered per device).
- **Three views** — *Agenda* (the next days), *Today & tomorrow* (two columns on wide cards, past events dimmed) and *Month* (grid with navigation; tap a day to see its events). Switch on **tabs** and everyone can change the view right on the card; the choice is remembered per device.
- **Event details** — tapping an event opens a clean detail sheet: date, time and duration, location (opens in Maps), label, notes with clickable links, calendar, the event's **TimeTree comments** and a hint when the event has photos. No entity history graphs.
- **Localised** — German and English, date/time formats follow your Home Assistant locale.

<p align="center">
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/phone-labels.png" alt="Label chips" width="24%" />
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/phone-labels-filtered.png" alt="Two labels hidden" width="24%" />
  <img src="https://raw.githubusercontent.com/tmsbyr87/TimeTree-HA/main/assets/screenshots/card/tablet-landscape-light.png" alt="Agenda in day columns on a tablet" width="49%" />
</p>

### Options

| Option | Default | What it does |
| --- | --- | --- |
| `entities` | first `calendar.*` | One or more calendar entities |
| `title` | Family calendar | Header text |
| `icon` | TimeTree logo | Any `mdi:` icon for the header |
| `days` | `7` | How many days ahead to show (1–60) |
| `max_events` | `30` | Cap on listed events; the rest is summarised as “+ n more” |
| `layout` | `auto` | `auto` (list ↔ columns by width), `list`, or `columns` |
| `view` | `agenda` | `agenda`, `today` (today & tomorrow) or `month` |
| `tabs` | `false` | Tab bar to switch views on the card |
| `show_comments` | `true` | Load TimeTree comments in the detail sheet |
| `tap_action` | `dialog` | `dialog` (detail sheet), `more-info` (entity dialog), `none` |
| `accent_color` | theme primary | Any CSS colour, e.g. `#2ecc84` |
| `labels` | all | Only show events with these TimeTree label ids (multi-select in the editor) |
| `label_filter` | `false` | Chip bar on the card to toggle labels; choice is remembered per browser |
| `show_label` | `true` | Label tag under each event |
| `show_header` / `show_icon` | `true` | Header row and icon |
| `show_all_day` | `true` | Include all-day events |
| `show_location` | `true` | Location line under the title |
| `show_description` | `false` | Two-line description preview |
| `relative_days` | `true` | “Today” / “Tomorrow” instead of only the date |
| `compact` | `false` | Tighter spacing and smaller type |
| `empty_text` | — | Custom text when nothing is coming up |
| `colors` | built-in palette | Per-entity colours for calendars without labels, e.g. `["#2ecc84", "#3b82f6"]` |

```yaml
type: custom:timetree-card
entities:
  - calendar.family
title: Family calendar
icon: mdi:calendar-heart
view: agenda        # agenda | today | month
tabs: true          # let everyone switch views on the card
days: 7
label_filter: true
tap_action: dialog
```

> **Privacy:** like Home Assistant's own calendar API, event details and comments are visible to every user who can log in to your Home Assistant – not only administrators. Comments are fetched from TimeTree only when a detail sheet is opened, cached briefly, and rate-limited so a dashboard can never flood your TimeTree account.

Labels are read from the calendar entity's `labels` attribute (TimeTree calendars only); events are fetched from `/api/timetree/events/<entity>` so each one carries its label. Other calendar integrations fall back to Home Assistant's standard calendar API and simply have no labels.

> Running Lovelace in YAML mode? Add `/timetree_card/timetree-card.js` as a *module* resource yourself — the integration logs the exact URL at startup.

## Using it

Every selected calendar becomes a device with these entities (Home Assistant derives the exact entity ids from your calendar and area names):

| Entity | Enabled | What it is |
| --- | --- | --- |
| `calendar.<name>` | ✅ | The whole calendar — works with every calendar card and the calendar trigger |
| `sensor.<name>_events_today` | ✅ | Number of events today; the events (time, location, label) as `events` attribute |
| `sensor.<name>_next_event` | ✅ | Start of the next event (timestamp) with summary, location and label as attributes |
| `calendar.<name>_<label>` | ➖ | One calendar per TimeTree label, e.g. only *Kids* or *Work*. Disabled by default — enable the ones you want to automate on. New labels appear automatically. |

### Reminders from TimeTree

The alerts you set on an event in TimeTree (“15 minutes before”, “1 day before”) fire a `timetree_reminder` event in Home Assistant at exactly that moment — for every occurrence of a series, too.

The bundled **TimeTree reminder** blueprint turns that into a push notification and, optionally, a spoken announcement on your speakers. It is installed automatically to `blueprints/automation/timetree/` — find it under **Settings → Automations & Scenes → Blueprints**. Filter by calendar and by TimeTree label, enter one or more notify actions (e.g. `notify.mobile_app_pixel_9`), done.

Labels are your own – whatever you named them in TimeTree. Pick them from a list (enable the matching label calendars first; each TimeTree label has one) or type their names. Leave both empty to be reminded of every event. An unedited copy of the blueprint is updated automatically with new releases; once you edit it, it is left alone.

<details>
<summary>Event data of <code>timetree_reminder</code></summary>

| Key | Example |
| --- | --- |
| `entity_id` | `calendar.family` |
| `calendar_id`, `calendar_name` | `42`, `Family` |
| `uid` | TimeTree event id |
| `summary`, `description`, `location` | event text |
| `start`, `end` | ISO timestamps (local time) |
| `all_day` | `false` |
| `label_id`, `label` | `3`, `Kids` |
| `label_entity_id` | `calendar.family_kids` (the label's calendar) |
| `minutes_before` | `15` |

```yaml
triggers:
  - trigger: event
    event_type: timetree_reminder
    event_data:
      label: Kids
actions:
  - action: notify.mobile_app_phone
    data:
      title: "{{ trigger.event.data.summary }}"
      message: "in {{ trigger.event.data.minutes_before }} min"
```
</details>

### Action: `timetree.get_event_details`

Returns an event with its **comments** and **photo links** — handy for notifications or voice assistants. Without `uid` it uses the next upcoming event.

```yaml
actions:
  - action: timetree.get_event_details
    data:
      entity_id: calendar.family
      uid: "{{ trigger.event.data.uid }}"   # e.g. from timetree_reminder; omit for the next event
    response_variable: details
  - action: notify.mobile_app_phone
    data:
      title: "{{ details.event.summary }}"
      message: "{{ details.comments | map(attribute='content') | join('\n') or 'No comments' }}"
```

Response: `event` (summary, start, end, location, label, `media_count`), `comments` (`author`, `content`, `created_at`) and `media` (links found in the event's activity). Requests are cached and rate-limited like the card's.

### Automations with the calendar

- Trigger automations with the **calendar event trigger** (“5 minutes before an event starts”) — on the whole calendar or on a label calendar
- Read the next event from the entity's `message`, `start_time`, `end_time`, `description` and `location` attributes in templates

```yaml
# Example: announce the number of today's events at 07:00
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: notify.mobile_app_phone
    data:
      message: >
        Today: {{ states('sensor.family_events_today') }} events,
        next: {{ state_attr('sensor.family_next_event', 'summary') }}
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| *E-mail or password is wrong* during setup | Log in on [timetreeapp.com](https://timetreeapp.com) with the same credentials; social-login accounts need a password set first |
| *TimeTree is rate-limiting login attempts* | Wait a few minutes — TimeTree throttles repeated sign-ins |
| Entity turns `unavailable` | Check **Settings → System → Logs** for `timetree`; a re-auth prompt appears if the session could not be renewed |
| *This TimeTree account is already configured* | Add further calendars via **Configure** on the existing entry instead of adding the integration again |
| An event is missing | Memos and birthday entries are intentionally skipped; anything else, open an issue with the log line `Skipping TimeTree event …` |
| Repair notice *TimeTree changed its web API* | TimeTree answered several times with an unknown format – check HACS for an update; the calendar keeps its last known events meanwhile |
| A label is missing in the blueprint's list | Enable that label's calendar first (**Settings → Devices & services → TimeTree**), or type the label name instead |
| Comments show *Too many requests* | The card protects your TimeTree account with a request limit – wait a minute |

**Reporting a problem:** attach the diagnostics (**Settings → Devices & services → TimeTree → ⋮ → Download diagnostics**). They contain counters and field names only – no credentials, calendar names or event content – and are safe to post publicly.

<details>
<summary><strong>🇩🇪 Kurzanleitung auf Deutsch</strong></summary>

**Installation:** HACS → Integrationen → ⋮ → *Custom repositories* → `https://github.com/tmsbyr87/TimeTree-HA` (Kategorie *Integration*) → herunterladen → Home Assistant neu starten.

**Einrichtung:** Einstellungen → Geräte & Dienste → Integration hinzufügen → **TimeTree** → E-Mail und Passwort eingeben → Kalender ankreuzen (mehrere möglich). Pro Kalender entsteht eine `calendar.*`-Entität, die sich wie jeder andere HA-Kalender verwenden lässt. Dazu kommen die Sensoren „Termine heute“ und „Nächster Termin“ sowie (deaktiviert) je ein Kalender pro TimeTree-Label. In TimeTree gesetzte Erinnerungen lösen das Ereignis `timetree_reminder` aus; der mitgelieferte Blueprint „TimeTree reminder“ macht daraus Push-Nachrichten oder Sprachansagen. Mit der Aktion `timetree.get_event_details` holen Automationen einen Termin samt Kommentaren. Weitere Kalender und das Aktualisierungsintervall lassen sich später über **Konfigurieren** ändern; bestehende Einträge aus Version 1.3 oder älter werden automatisch übernommen, die Entitäts-ID bleibt gleich.

**Karte:** Die mitgelieferte Karte *TimeTree Agenda* erscheint nach dem Neustart automatisch in der Kartenauswahl – mit den Ansichten Agenda, Heute & Morgen und Monat (optional per Reiter umschaltbar), Label-Filter und Detail-Dialog mit Kommentaren. Hell/dunkel, Handy, Tablet und Desktop.

**Erinnerungen:** Labels im Blueprint per Liste auswählen (dazu den Label-Kalender einmal aktivieren) oder den Namen eintippen – es sind immer die eigenen Labels aus TimeTree.

**Hinweis:** Die Integration nutzt die interne Web-Schnittstelle von TimeTree, weil die offizielle API 2023 abgeschaltet wurde. Ändert TimeTree diese Schnittstelle, kann die Integration bis zu einem Update ausfallen. Memos und Geburtstage werden nicht übernommen.

</details>

## Contributing

Issues and pull requests are welcome. The API client, event conversion and sync store are plain Python without Home Assistant imports and are covered by `pytest`:

```bash
python -m venv .venv && .venv/bin/pip install ical pytest pytest-asyncio "aiohttp<3.13" aioresponses
.venv/bin/python -m pytest tests -p asyncio --asyncio-mode=auto
```

Config flow, migration and setup run against a real Home Assistant core (Python 3.14):

```bash
python3.14 -m venv .venv-ha && .venv-ha/bin/pip install -r requirements_test_ha.txt
.venv-ha/bin/python -m pytest tests_ha
```

## Support

If this integration saves you the ICS-export dance, you can [buy me a coffee](https://buymeacoffee.com/tmsbyr) ☕ — it keeps the TimeTree endpoints watched and the project maintained.

## Acknowledgements

Endpoint behaviour is based on the excellent [eoleedi/TimeTree-Exporter](https://github.com/eoleedi/TimeTree-Exporter). TimeTree and the TimeTree logo are trademarks of TimeTree, Inc.; this project is not affiliated with or endorsed by TimeTree.

## License

[MIT](LICENSE)
