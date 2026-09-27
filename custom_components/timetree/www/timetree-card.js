/*
 * TimeTree Agenda Card — a responsive, theme-aware agenda for Home Assistant.
 *
 * Shipped by the TimeTree integration, but works with ANY calendar.* entity:
 * it reads events through Home Assistant's own REST calendar API.
 *
 * No build step, no framework: a single vanilla Web Component plus a visual
 * editor based on <ha-form>, so the card can be configured without YAML.
 */

const CARD_VERSION = "1.1.0";
const CARD_TAG = "timetree-card";
const EDITOR_TAG = "timetree-card-editor";
const REFRESH_MS = 15 * 60 * 1000;

const PALETTE = [
  "#2ecc84", // TimeTree green
  "#3b82f6",
  "#f59e0b",
  "#ec4899",
  "#8b5cf6",
  "#14b8a6",
];

const STRINGS = {
  de: {
    today: "Heute",
    tomorrow: "Morgen",
    yesterday: "Gestern",
    allDay: "Ganztägig",
    noEvents: "Keine Termine",
    loading: "Lade Termine …",
    error: "Kalender nicht erreichbar",
    missing: "Keine Kalender-Entität konfiguriert",
    now: "Jetzt",
    until: "bis",
    more: (n) => `+ ${n} weitere`,
    title: "Familienkalender",
  },
  en: {
    today: "Today",
    tomorrow: "Tomorrow",
    yesterday: "Yesterday",
    allDay: "All day",
    noEvents: "No upcoming events",
    loading: "Loading events …",
    error: "Calendar unavailable",
    missing: "No calendar entity configured",
    now: "Now",
    until: "until",
    more: (n) => `+ ${n} more`,
    title: "Family calendar",
  },
};

const DEFAULTS = {
  title: "",
  entities: [],
  days: 7,
  max_events: 30,
  show_all_day: true,
  show_location: true,
  show_description: false,
  show_header: true,
  show_icon: true,
  compact: false,
  group_by_day: true,
  relative_days: true,
  layout: "auto", // auto | list | columns
  accent_color: "",
  empty_text: "",
  colors: [],
};

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; /* required: only block-level boxes can be size containers */
    container-type: inline-size;
    container-name: card;
    overflow: hidden;
    border-radius: var(--ha-card-border-radius, 12px);
    background: var(--ha-card-background, var(--card-background-color, #fff));
    color: var(--primary-text-color);
    --tt-accent: var(--timetree-accent, var(--primary-color, #2ecc84));
    --tt-muted: var(--secondary-text-color);
    --tt-divider: var(--divider-color, rgba(127,127,127,.25));
    --tt-radius: 12px;
    --tt-pad: 16px;
    --tt-row-pad: 10px;
    --tt-time-w: 92px;
    --tt-font: var(--ha-card-font-size, 15px);
  }
  ha-card.compact { --tt-pad: 12px; --tt-row-pad: 6px; --tt-time-w: 76px; --tt-font: 14px; }

  .header {
    display: flex; align-items: center; gap: 12px;
    padding: var(--tt-pad) var(--tt-pad) 6px;
  }
  .header .icon {
    width: 36px; height: 36px; border-radius: 50%; flex: none;
    display: grid; place-items: center;
    background: color-mix(in srgb, var(--tt-accent) 18%, transparent);
    color: var(--tt-accent);
  }
  .header .icon img { width: 22px; height: 22px; display: block; }
  .header .icon ha-icon { --mdc-icon-size: 22px; }
  .header .title { font-size: 1.05em; font-weight: 600; line-height: 1.2; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .header .sub { font-size: .85em; color: var(--tt-muted); }
  .header .spacer { flex: 1; }
  .header .count { font-size: .8em; color: var(--tt-muted); flex: none; }

  .body { padding: 0 var(--tt-pad) var(--tt-pad); }
  .state { padding: 14px 0 6px; color: var(--tt-muted); font-size: .95em; display: flex; align-items: center; gap: 10px; }
  .state.error { color: var(--error-color, #db4437); }

  .days { display: grid; grid-template-columns: 1fr; gap: 8px; }
  .day { min-width: 0; }
  .day-head {
    display: flex; align-items: baseline; gap: 8px;
    padding: 10px 0 4px; border-bottom: 1px solid var(--tt-divider);
    font-size: .82em; text-transform: uppercase; letter-spacing: .04em; color: var(--tt-muted);
  }
  .day-head .rel { font-weight: 700; color: var(--primary-text-color); text-transform: none; letter-spacing: 0; font-size: 1.05em; }
  .day.today .day-head { border-bottom-color: var(--tt-accent); }
  .day.today .day-head .rel { color: var(--tt-accent); }

  .event {
    display: grid; grid-template-columns: var(--tt-time-w) 10px 1fr; column-gap: 10px; align-items: start;
    padding: var(--tt-row-pad) 0; border-bottom: 1px solid var(--tt-divider);
    cursor: pointer; border-radius: 8px; transition: background 120ms ease;
    font-size: var(--tt-font);
  }
  .event:last-child { border-bottom: none; }
  .event:hover { background: color-mix(in srgb, var(--tt-accent) 6%, transparent); }
  .event.running { background: color-mix(in srgb, var(--tt-accent) 10%, transparent); }
  .event.running .time { color: var(--tt-accent); font-weight: 700; }
  .event.past { opacity: .55; }
  .time { font-variant-numeric: tabular-nums; color: var(--tt-muted); font-size: .92em; line-height: 1.35; white-space: nowrap; }
  .time .end { display: block; font-size: .85em; opacity: .8; }
  .dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; background: var(--dot, var(--tt-accent)); }
  .main { min-width: 0; }
  .summary { font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
  .meta { color: var(--tt-muted); font-size: .88em; margin-top: 2px; display: flex; gap: 6px; align-items: center; min-width: 0; }
  .meta ha-icon { --mdc-icon-size: 14px; flex: none; }
  .meta span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .desc { color: var(--tt-muted); font-size: .86em; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
  .more { color: var(--tt-muted); font-size: .85em; padding-top: 8px; }

  /* Wide containers (tablet landscape, desktop): day columns */
  ha-card.layout-columns .days,
  ha-card.layout-auto .days { }
  @container card (min-width: 640px) {
    ha-card.layout-auto .days { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px 20px; }
    ha-card.layout-auto .day-head { padding-top: 6px; }
  }
  ha-card.layout-columns .days { grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px 20px; }

  /* Narrow phones: tighten time column */
  @container card (max-width: 360px) {
    ha-card { --tt-time-w: 70px; --tt-pad: 12px; }
    .time { font-size: .85em; }
  }
`;

/* ---------- helpers ---------- */

function pad2(n) { return String(n).padStart(2, "0"); }

function toLocalDate(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function dayKey(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function parseHaDate(obj) {
  // HA REST returns {date: "YYYY-MM-DD"} or {dateTime: ISO}
  if (!obj) return null;
  if (obj.dateTime) return { dt: new Date(obj.dateTime), allDay: false };
  if (obj.date) {
    const [y, m, d] = obj.date.split("-").map(Number);
    return { dt: new Date(y, m - 1, d), allDay: true };
  }
  return null;
}

function isoLocal(d) {
  // ISO with local offset, as the HA calendar API expects
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const a = Math.abs(off);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:00${sign}${pad2(Math.floor(a / 60))}:${pad2(a % 60)}`;
}

function lang(hass) {
  const l = (hass && hass.language) || (hass && hass.locale && hass.locale.language) || "en";
  return l.startsWith("de") ? "de" : "en";
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* ---------- card ---------- */

class TimeTreeCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig(hass) {
    const first = Object.keys(hass.states).find((id) => id.startsWith("calendar."));
    return { entities: first ? [first] : [], days: 7 };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._events = [];
    this._status = "idle"; // idle | loading | ready | error
    this._timer = null;
    this._lastFetch = 0;
    this._sig = "";
  }

  setConfig(config) {
    if (!config) throw new Error("timetree-card: missing config");
    const c = { ...DEFAULTS, ...config };
    if (config.entity && !config.entities) c.entities = [config.entity];
    if (typeof c.entities === "string") c.entities = [c.entities];
    c.days = Math.min(60, Math.max(1, Number(c.days) || 7));
    c.max_events = Math.max(1, Number(c.max_events) || 30);
    this._config = c;
    this._render();
    this._maybeFetch(true);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Refetch when a configured calendar entity changed (new next event etc.)
    const sig = (this._config?.entities || [])
      .map((e) => { const s = hass.states[e]; return s ? `${s.state}|${s.last_updated}` : "missing"; })
      .join(",");
    const changed = sig !== this._sig;
    this._sig = sig;
    if (first || changed) this._maybeFetch(first);
    else this._render(); // cheap re-render for "running" highlight
  }

  connectedCallback() {
    this._timer = setInterval(() => this._maybeFetch(true), REFRESH_MS);
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
  }

  getCardSize() {
    return this._config?.compact ? 3 : 5;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  /* ---------- data ---------- */

  async _maybeFetch(force) {
    if (!this._hass || !this._config) return;
    if (!force && Date.now() - this._lastFetch < 5000) return;
    const entities = this._config.entities || [];
    if (!entities.length) { this._status = "missing"; this._render(); return; }

    this._status = this._events.length ? "ready" : "loading";
    this._render();

    const start = toLocalDate(new Date());
    const end = new Date(start.getTime() + this._config.days * 86400000);
    const q = `?start=${encodeURIComponent(isoLocal(start))}&end=${encodeURIComponent(isoLocal(end))}`;

    try {
      const results = await Promise.all(
        entities.map(async (entity, idx) => {
          const raw = await this._hass.callApi("GET", `calendars/${entity}${q}`);
          return (raw || []).map((ev) => this._normalize(ev, entity, idx));
        })
      );
      this._events = results.flat().filter(Boolean).sort((a, b) => a.start - b.start || a.end - b.end);
      this._status = "ready";
      this._lastFetch = Date.now();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("timetree-card: fetch failed", err);
      this._status = "error";
    }
    this._render();
  }

  _normalize(ev, entity, idx) {
    const s = parseHaDate(ev.start);
    const e = parseHaDate(ev.end);
    if (!s || !e) return null;
    const color = (this._config.colors && this._config.colors[idx]) || PALETTE[idx % PALETTE.length];
    return {
      entity,
      color,
      allDay: s.allDay,
      start: s.dt,
      end: e.dt,
      summary: ev.summary || "",
      location: ev.location || "",
      description: ev.description || "",
      uid: ev.uid || "",
    };
  }

  /* ---------- rendering ---------- */

  _t(key, ...args) {
    const table = STRINGS[lang(this._hass)] || STRINGS.en;
    const v = table[key];
    return typeof v === "function" ? v(...args) : v;
  }

  _fmtTime(d) {
    const locale = (this._hass && this._hass.locale && this._hass.locale.language) || (this._hass && this._hass.language) || undefined;
    return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(d);
  }

  _fmtDay(d) {
    const locale = (this._hass && this._hass.locale && this._hass.locale.language) || (this._hass && this._hass.language) || undefined;
    return new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short" }).format(d);
  }

  _relDay(d, today) {
    if (!this._config.relative_days) return "";
    const diff = Math.round((toLocalDate(d) - today) / 86400000);
    if (diff === 0) return this._t("today");
    if (diff === 1) return this._t("tomorrow");
    if (diff === -1) return this._t("yesterday");
    return "";
  }

  _render() {
    if (!this._config) return;
    const c = this._config;
    const now = new Date();
    const today = toLocalDate(now);
    const t = (k, ...a) => this._t(k, ...a);

    let events = this._events;
    if (!c.show_all_day) events = events.filter((e) => !e.allDay);
    // hide events that already ended (keep running ones)
    events = events.filter((e) => e.end > now);
    const total = events.length;
    events = events.slice(0, c.max_events);

    // group by day (an event spanning days appears on its start day)
    const groups = new Map();
    for (const e of events) {
      const k = dayKey(e.allDay ? e.start : toLocalDate(e.start));
      if (!groups.has(k)) groups.set(k, { date: e.allDay ? e.start : toLocalDate(e.start), items: [] });
      groups.get(k).items.push(e);
    }
    for (const g of groups.values()) {
      // all-day first, then by time
      g.items.sort((a, b) => (a.allDay === b.allDay ? a.start - b.start : a.allDay ? -1 : 1));
    }

    const title = c.title || t("title");
    const accent = c.accent_color ? `--timetree-accent:${esc(c.accent_color)};` : "";
    const layoutClass = `layout-${c.layout === "columns" ? "columns" : c.layout === "list" ? "list" : "auto"}`;
    const iconHtml = c.show_icon
      ? `<div class="icon">${c.icon
          ? `<ha-icon icon="${esc(c.icon)}"></ha-icon>`
          : `<img src="/timetree_static/icon.png" alt="" onerror="this.replaceWith(Object.assign(document.createElement('ha-icon'),{icon:'mdi:calendar-heart'}))">`}</div>`
      : "";

    let body = "";
    if (this._status === "missing") {
      body = `<div class="state error"><ha-icon icon="mdi:calendar-alert"></ha-icon>${t("missing")}</div>`;
    } else if (this._status === "error") {
      body = `<div class="state error"><ha-icon icon="mdi:cloud-off-outline"></ha-icon>${t("error")}</div>`;
    } else if (this._status === "loading") {
      body = `<div class="state"><ha-circular-progress indeterminate size="small"></ha-circular-progress>${t("loading")}</div>`;
    } else if (!events.length) {
      body = `<div class="state"><ha-icon icon="mdi:calendar-check"></ha-icon>${esc(c.empty_text) || t("noEvents")}</div>`;
    } else {
      const dayHtml = [];
      for (const [, g] of groups) {
        const isToday = dayKey(g.date) === dayKey(today);
        const rel = this._relDay(g.date, today);
        const rows = g.items.map((e) => {
          const running = !e.allDay && e.start <= now && e.end > now;
          const runningAll = e.allDay && e.start <= now && e.end > now;
          const timeHtml = e.allDay
            ? `<div class="time">${t("allDay")}</div>`
            : `<div class="time">${running ? `<strong>${t("now")}</strong>` : this._fmtTime(e.start)}<span class="end">${t("until")} ${this._fmtTime(e.end)}</span></div>`;
          const loc = c.show_location && e.location
            ? `<div class="meta"><ha-icon icon="mdi:map-marker-outline"></ha-icon><span>${esc(e.location)}</span></div>` : "";
          const desc = c.show_description && e.description ? `<div class="desc">${esc(e.description)}</div>` : "";
          return `<div class="event${running || runningAll ? " running" : ""}" data-entity="${esc(e.entity)}" role="button" tabindex="0">
              ${timeHtml}<div class="dot" style="--dot:${esc(e.color)}"></div>
              <div class="main"><div class="summary">${esc(e.summary)}</div>${loc}${desc}</div>
            </div>`;
        }).join("");
        dayHtml.push(`<section class="day${isToday ? " today" : ""}">
            <div class="day-head">${rel ? `<span class="rel">${rel}</span>` : ""}<span>${this._fmtDay(g.date)}</span></div>
            ${rows}
          </section>`);
      }
      body = `<div class="days">${dayHtml.join("")}</div>${total > events.length ? `<div class="more">${t("more", total - events.length)}</div>` : ""}`;
    }

    const header = c.show_header
      ? `<div class="header">${iconHtml}<div style="min-width:0"><div class="title">${esc(title)}</div>${c.subtitle ? `<div class="sub">${esc(c.subtitle)}</div>` : ""}</div><div class="spacer"></div>${events.length ? `<div class="count">${events.length}</div>` : ""}</div>`
      : "";

    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card class="${layoutClass}${c.compact ? " compact" : ""}" style="${accent}">
        ${header}
        <div class="body">${body}</div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll(".event").forEach((el) => {
      const open = () => this._moreInfo(el.dataset.entity);
      el.addEventListener("click", open);
      el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } });
    });
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
  }
}

/* ---------- visual editor ---------- */

class TimeTreeCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { ...DEFAULTS };
  }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...config };
    if (config.entity && !config.entities) this._config.entities = [config.entity];
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  get _schema() {
    const de = lang(this._hass) === "de";
    const L = (d, e) => (de ? d : e);
    return [
      { name: "entities", selector: { entity: { multiple: true, filter: { domain: "calendar" } } } },
      { name: "title", selector: { text: {} } },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "days", selector: { number: { min: 1, max: 60, mode: "slider", unit_of_measurement: L("Tage", "days") } } },
          { name: "max_events", selector: { number: { min: 1, max: 100, mode: "box" } } },
          { name: "layout", selector: { select: { mode: "dropdown", options: [
            { value: "auto", label: L("Automatisch", "Auto") },
            { value: "list", label: L("Liste", "List") },
            { value: "columns", label: L("Tages-Spalten", "Day columns") },
          ] } } },
          { name: "accent_color", selector: { text: {} } },
        ],
      },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "show_header", selector: { boolean: {} } },
          { name: "show_icon", selector: { boolean: {} } },
          { name: "show_all_day", selector: { boolean: {} } },
          { name: "show_location", selector: { boolean: {} } },
          { name: "show_description", selector: { boolean: {} } },
          { name: "relative_days", selector: { boolean: {} } },
          { name: "compact", selector: { boolean: {} } },
        ],
      },
      { name: "empty_text", selector: { text: {} } },
    ];
  }

  _label(schema) {
    const de = lang(this._hass) === "de";
    const map = de ? {
      entities: "Kalender", title: "Titel", days: "Zeitraum", max_events: "Max. Termine",
      layout: "Darstellung", accent_color: "Akzentfarbe (z. B. #2ecc84)", show_header: "Kopfzeile",
      show_icon: "Icon", show_all_day: "Ganztägige anzeigen", show_location: "Ort anzeigen",
      show_description: "Beschreibung anzeigen", relative_days: "Heute / Morgen", compact: "Kompakt",
      empty_text: "Text wenn keine Termine",
    } : {
      entities: "Calendars", title: "Title", days: "Range", max_events: "Max. events",
      layout: "Layout", accent_color: "Accent colour (e.g. #2ecc84)", show_header: "Header",
      show_icon: "Icon", show_all_day: "Show all-day events", show_location: "Show location",
      show_description: "Show description", relative_days: "Today / Tomorrow", compact: "Compact",
      empty_text: "Text when empty",
    };
    return map[schema.name] || schema.name;
  }

  async _render() {
    if (!this.shadowRoot) return;
    if (!customElements.get("ha-form")) {
      // Force HA to load ha-form (it is lazy-loaded with the entities card editor).
      try {
        const helpers = await window.loadCardHelpers();
        const el = helpers.createCardElement({ type: "entities", entities: [] });
        if (el && el.constructor && el.constructor.getConfigElement) await el.constructor.getConfigElement();
      } catch (_) { /* ignore */ }
      await customElements.whenDefined("ha-form").catch(() => {});
    }
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const value = { ...ev.detail.value };
        // drop defaults to keep YAML tidy
        for (const k of Object.keys(value)) {
          if (JSON.stringify(value[k]) === JSON.stringify(DEFAULTS[k])) delete value[k];
        }
        value.type = `custom:${CARD_TAG}`;
        this._config = { ...DEFAULTS, ...value };
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: value }, bubbles: true, composed: true }));
      });
      this.shadowRoot.innerHTML = "";
      this.shadowRoot.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema;
    this._form.data = this._config;
    this._form.computeLabel = (s) => this._label(s);
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, TimeTreeCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, TimeTreeCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "TimeTree Agenda",
    description: "Responsive, theme-aware agenda for any calendar entity. Configurable without YAML.",
    preview: true,
    documentationURL: "https://github.com/tmsbyr87/TimeTree-HA#dashboard-card",
  });
}

// eslint-disable-next-line no-console
console.info(`%c TIMETREE-CARD %c ${CARD_VERSION} `, "color:#fff;background:#2ecc84;font-weight:700", "color:#2ecc84;background:#fff;font-weight:700");
