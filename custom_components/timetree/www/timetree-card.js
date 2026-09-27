/*
 * TimeTree Agenda Card — a responsive, theme-aware agenda for Home Assistant.
 *
 * Shipped by the TimeTree integration, but works with ANY calendar.* entity:
 * it reads events through Home Assistant's own REST calendar API. TimeTree
 * calendars additionally expose colour labels, which the card can show,
 * filter by (config) and toggle (chip bar on the card).
 *
 * No build step, no framework: a single vanilla Web Component plus a visual
 * editor based on <ha-form>, so the card can be configured without YAML.
 */

const CARD_VERSION = "1.2.1";
const CARD_TAG = "timetree-card";
const EDITOR_TAG = "timetree-card-editor";
const REFRESH_MS = 15 * 60 * 1000;

const PALETTE = ["#2ecc84", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6"];

const STRINGS = {
  de: {
    today: "Heute", tomorrow: "Morgen", yesterday: "Gestern", allDay: "Ganztägig",
    noEvents: "Keine Termine", loading: "Lade Termine …", error: "Kalender nicht erreichbar",
    missing: "Keine Kalender-Entität konfiguriert", now: "Jetzt", until: "bis",
    more: (n) => `+ ${n} weitere`, title: "Familienkalender", close: "Schließen",
    when: "Wann", where: "Wo", label: "Label", calendar: "Kalender", notes: "Notizen",
    allLabels: "Alle", noLabel: "Ohne Label", days: (n) => `${n} Tage`, day: "1 Tag",
    hours: (h) => `${h} Std.`, minutes: (m) => `${m} Min.`, running: "läuft gerade",
  },
  en: {
    today: "Today", tomorrow: "Tomorrow", yesterday: "Yesterday", allDay: "All day",
    noEvents: "No upcoming events", loading: "Loading events …", error: "Calendar unavailable",
    missing: "No calendar entity configured", now: "Now", until: "until",
    more: (n) => `+ ${n} more`, title: "Family calendar", close: "Close",
    when: "When", where: "Where", label: "Label", calendar: "Calendar", notes: "Notes",
    allLabels: "All", noLabel: "No label", days: (n) => `${n} days`, day: "1 day",
    hours: (h) => `${h} h`, minutes: (m) => `${m} min`, running: "in progress",
  },
};

const DEFAULTS = {
  title: "",
  icon: "",
  entities: [],
  days: 7,
  max_events: 30,
  show_all_day: true,
  show_location: true,
  show_description: false,
  show_label: true,
  show_header: true,
  show_icon: true,
  compact: false,
  relative_days: true,
  layout: "auto",        // auto | list | columns
  accent_color: "",
  empty_text: "",
  colors: [],
  labels: [],            // config filter: only these label ids (strings/numbers); empty = all
  label_filter: false,   // interactive chip bar on the card
  tap_action: "dialog",  // dialog | more-info | none
};

const STYLE = `
  :host { display: block; }
  ha-card {
    display: block; /* required: only block-level boxes can be size containers */
    position: relative;
    container-type: inline-size;
    container-name: card;
    overflow: hidden;
    border-radius: var(--ha-card-border-radius, 12px);
    background: var(--ha-card-background, var(--card-background-color, #fff));
    color: var(--primary-text-color);
    --tt-accent: var(--timetree-accent, var(--primary-color, #2ecc84));
    --tt-muted: var(--secondary-text-color);
    --tt-divider: var(--divider-color, rgba(127,127,127,.25));
    --tt-pad: 16px; --tt-row-pad: 10px; --tt-time-w: 92px;
    --tt-font: var(--ha-card-font-size, 15px);
  }
  ha-card.compact { --tt-pad: 12px; --tt-row-pad: 6px; --tt-time-w: 76px; --tt-font: 14px; }

  .header { display: flex; align-items: center; gap: 12px; padding: var(--tt-pad) var(--tt-pad) 6px; }
  .header .icon { width: 36px; height: 36px; border-radius: 50%; flex: none; display: grid; place-items: center;
    background: color-mix(in srgb, var(--tt-accent) 18%, transparent); color: var(--tt-accent); }
  .header .icon img { width: 22px; height: 22px; display: block; }
  .header .icon ha-icon { --mdc-icon-size: 22px; }
  .header .title { font-size: 1.05em; font-weight: 600; line-height: 1.2; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .header .spacer { flex: 1; }
  .header .count { font-size: .8em; color: var(--tt-muted); flex: none; }

  .chips { display: flex; gap: 6px; flex-wrap: wrap; padding: 4px var(--tt-pad) 6px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; font-size: .8em;
    border: 1px solid var(--tt-divider); background: transparent; color: var(--primary-text-color); cursor: pointer; user-select: none;
    transition: opacity 120ms ease, background 120ms ease; }
  .chip .sw { width: 9px; height: 9px; border-radius: 50%; background: var(--c); flex: none; }
  .chip.on { background: color-mix(in srgb, var(--c) 16%, transparent); border-color: color-mix(in srgb, var(--c) 55%, transparent); }
  .chip.off { opacity: .45; text-decoration: line-through; }
  .chip.all { --c: var(--tt-accent); }

  .body { padding: 0 var(--tt-pad) var(--tt-pad); }
  .state { padding: 14px 0 6px; color: var(--tt-muted); font-size: .95em; display: flex; align-items: center; gap: 10px; }
  .state.error { color: var(--error-color, #db4437); }

  .days { display: grid; grid-template-columns: 1fr; gap: 8px; }
  .day { min-width: 0; }
  .day-head { display: flex; align-items: baseline; gap: 8px; padding: 10px 0 4px; border-bottom: 1px solid var(--tt-divider);
    font-size: .82em; text-transform: uppercase; letter-spacing: .04em; color: var(--tt-muted); }
  .day-head .rel { font-weight: 700; color: var(--primary-text-color); text-transform: none; letter-spacing: 0; font-size: 1.05em; }
  .day.today .day-head { border-bottom-color: var(--tt-accent); }
  .day.today .day-head .rel { color: var(--tt-accent); }

  .event { display: grid; grid-template-columns: var(--tt-time-w) 10px 1fr; column-gap: 10px; align-items: start;
    padding: var(--tt-row-pad) 0; border-bottom: 1px solid var(--tt-divider); border-radius: 8px;
    transition: background 120ms ease; font-size: var(--tt-font); }
  .event.tappable { cursor: pointer; }
  .event:last-child { border-bottom: none; }
  .event.tappable:hover { background: color-mix(in srgb, var(--tt-accent) 6%, transparent); }
  .event.running { background: color-mix(in srgb, var(--tt-accent) 10%, transparent); }
  .event.running .time { color: var(--tt-accent); font-weight: 700; }
  .time { font-variant-numeric: tabular-nums; color: var(--tt-muted); font-size: .92em; line-height: 1.35; white-space: nowrap; }
  .time .end { display: block; font-size: .85em; opacity: .8; }
  .dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; background: var(--dot, var(--tt-accent)); }
  .main { min-width: 0; }
  .summary { font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
  .meta { color: var(--tt-muted); font-size: .88em; margin-top: 2px; display: flex; gap: 6px; align-items: center; min-width: 0; }
  .meta ha-icon { --mdc-icon-size: 14px; flex: none; }
  .meta span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tag { display: inline-flex; align-items: center; gap: 5px; font-size: .78em; padding: 1px 8px; border-radius: 999px; margin-top: 3px;
    background: color-mix(in srgb, var(--c) 16%, transparent); color: var(--primary-text-color); }
  .tag .sw { width: 7px; height: 7px; border-radius: 50%; background: var(--c); }
  .desc { color: var(--tt-muted); font-size: .86em; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
  .more { color: var(--tt-muted); font-size: .85em; padding-top: 8px; }

  @container card (min-width: 640px) {
    ha-card.layout-auto .days { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px 20px; }
    ha-card.layout-auto .day-head { padding-top: 6px; }
  }
  ha-card.layout-columns .days { grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px 20px; }
  @container card (max-width: 360px) { ha-card { --tt-time-w: 70px; --tt-pad: 12px; } .time { font-size: .85em; } }

  /* ---- detail dialog ---- */
  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 9; display: flex; align-items: flex-end; justify-content: center;
    animation: fade 120ms ease; }
  @keyframes fade { from { opacity: 0 } to { opacity: 1 } }
  .sheet { width: 100%; max-width: 560px; max-height: 88vh; overflow: auto; background: var(--ha-card-background, var(--card-background-color, #fff));
    color: var(--primary-text-color); border-radius: 20px 20px 0 0; box-shadow: 0 -8px 32px rgba(0,0,0,.25); animation: up 160ms ease; }
  @keyframes up { from { transform: translateY(24px); opacity: .6 } to { transform: none; opacity: 1 } }
  @media (min-width: 640px) { .backdrop { align-items: center; padding: 24px; } .sheet { border-radius: 20px; } }
  .sheet .bar { height: 6px; background: var(--c, var(--tt-accent)); }
  .sheet .inner { padding: 18px 20px 22px; }
  .sheet .top { display: flex; align-items: flex-start; gap: 12px; }
  .sheet h2 { margin: 0; font-size: 1.25em; line-height: 1.25; font-weight: 700; flex: 1; overflow-wrap: anywhere; }
  .sheet .x { flex: none; width: 36px; height: 36px; border-radius: 50%; border: none; background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
    color: var(--primary-text-color); cursor: pointer; display: grid; place-items: center; font-size: 20px; line-height: 1; }
  .sheet .rows { display: grid; grid-template-columns: 24px 1fr; gap: 12px 12px; margin-top: 16px; align-items: start; }
  .sheet .rows ha-icon { --mdc-icon-size: 20px; color: var(--tt-muted); margin-top: 1px; }
  .sheet .k { font-size: .78em; text-transform: uppercase; letter-spacing: .04em; color: var(--tt-muted); }
  .sheet .v { font-size: 1em; line-height: 1.4; overflow-wrap: anywhere; }
  .sheet .v .pre, .sheet .v.pre { white-space: pre-line; }
  .sheet .v a { color: var(--tt-accent); }
  .sheet .live { display: inline-block; margin-left: 8px; font-size: .78em; padding: 1px 8px; border-radius: 999px;
    background: color-mix(in srgb, var(--tt-accent) 18%, transparent); color: var(--tt-accent); font-weight: 600; }
`;

/* ---------- helpers ---------- */

const pad2 = (n) => String(n).padStart(2, "0");
const toLocalDate = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const dayKey = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

function parseHaDate(obj) {
  if (!obj) return null;
  if (obj.dateTime) return { dt: new Date(obj.dateTime), allDay: false };
  if (obj.date) { const [y, m, d] = obj.date.split("-").map(Number); return { dt: new Date(y, m - 1, d), allDay: true }; }
  return null;
}

function isoLocal(d) {
  const off = -d.getTimezoneOffset(); const sign = off >= 0 ? "+" : "-"; const a = Math.abs(off);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:00${sign}${pad2(Math.floor(a / 60))}:${pad2(a % 60)}`;
}

function lang(hass) {
  const l = (hass && hass.language) || (hass && hass.locale && hass.locale.language) || "en";
  return l.startsWith("de") ? "de" : "en";
}

const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// Colours are interpolated into style attributes. Escaping alone would still
// allow extra declarations ("red; background:url(...)"), so only accept plain
// hex colours for data coming from calendars, and a single validated CSS
// colour for the user's own accent setting.
const HEX_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const safeHex = (v, fallback = "#9e9e9e") => (typeof v === "string" && HEX_RE.test(v.trim()) ? v.trim() : fallback);
const safeCssColor = (v) => {
  if (typeof v !== "string" || !v.trim() || /[;{}()<>"'\\]/.test(v.replace(/^(rgb|rgba|hsl|hsla)\([^()]*\)$/i, ""))) return "";
  try { return window.CSS && CSS.supports("color", v.trim()) ? v.trim() : ""; } catch (_) { return ""; }
};

function linkify(text) {
  // escape first, then turn URLs into links
  return esc(text).replace(/(https?:\/\/[^\s<]+)/g, (m) => `<a href="${m}" target="_blank" rel="noopener">${m}</a>`);
}

const labelKey = (id) => String(id);

function isTimeTree(hass, entity) {
  const st = hass && hass.states && hass.states[entity];
  return !!(st && st.attributes && st.attributes.calendar_id !== undefined);
}

function labelsOf(hass, entities) {
  const out = new Map();
  for (const e of entities || []) {
    const st = hass && hass.states && hass.states[e];
    for (const l of (st && st.attributes && st.attributes.labels) || []) {
      if (l && l.id !== undefined && !out.has(labelKey(l.id))) out.set(labelKey(l.id), { id: l.id, name: l.name, color: safeHex(l.color) });
    }
  }
  return [...out.values()];
}

/* ---------- card ---------- */

class TimeTreeCard extends HTMLElement {
  static getConfigElement() { return document.createElement(EDITOR_TAG); }

  static getStubConfig(hass) {
    const first = Object.keys(hass.states).find((id) => id.startsWith("calendar."));
    return { entities: first ? [first] : [], days: 7, label_filter: true };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._events = [];
    this._status = "idle";
    this._timer = null;
    this._lastFetch = 0;
    this._sig = "";
    this._hidden = new Set();   // label keys hidden via chips ("__none" = events without label)
    this._open = null;          // event shown in the dialog
  }

  setConfig(config) {
    if (!config) throw new Error("timetree-card: missing config");
    const c = { ...DEFAULTS, ...config };
    if (config.entity && !config.entities) c.entities = [config.entity];
    if (typeof c.entities === "string") c.entities = [c.entities];
    c.days = Math.min(60, Math.max(1, Number(c.days) || 7));
    c.max_events = Math.max(1, Number(c.max_events) || 30);
    c.labels = (c.labels || []).map(labelKey);
    this._config = c;
    this._storageKey = `timetree-card:${(c.entities || []).join("|")}:${c.title || ""}`;
    this._loadHidden();
    this._render();
    this._maybeFetch(true);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const sig = (this._config?.entities || [])
      .map((e) => { const s = hass.states[e]; return s ? `${s.state}|${s.last_updated}` : "missing"; }).join(",");
    const changed = sig !== this._sig;
    this._sig = sig;
    if (first || changed) this._maybeFetch(first); else this._render();
  }

  connectedCallback() { this._timer = setInterval(() => this._maybeFetch(true), REFRESH_MS); }
  disconnectedCallback() { if (this._timer) clearInterval(this._timer); this._timer = null; }
  getCardSize() { return this._config?.compact ? 3 : 5; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

  _loadHidden() {
    try { const raw = localStorage.getItem(this._storageKey); this._hidden = new Set(raw ? JSON.parse(raw) : []); }
    catch (_) { this._hidden = new Set(); }
  }
  _saveHidden() { try { localStorage.setItem(this._storageKey, JSON.stringify([...this._hidden])); } catch (_) { /* ignore */ } }

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
      const results = await Promise.all(entities.map(async (entity, idx) => {
        // TimeTree calendars: label-aware feed from the integration; others: core REST API.
        const path = isTimeTree(this._hass, entity) ? `timetree/events/${entity}${q}` : `calendars/${entity}${q}`;
        let raw;
        try { raw = await this._hass.callApi("GET", path); }
        catch (err) {
          if (!path.startsWith("timetree/")) throw err;
          raw = await this._hass.callApi("GET", `calendars/${entity}${q}`); // graceful fallback
        }
        return (raw || []).map((ev) => this._normalize(ev, entity, idx));
      }));
      this._events = results.flat().filter(Boolean).sort((a, b) => a.start - b.start || a.end - b.end);
      this._status = "ready";
      this._lastFetch = Date.now();
    } catch (err) {
      console.warn("timetree-card: fetch failed", err); // eslint-disable-line no-console
      this._status = "error";
    }
    this._render();
  }

  _normalize(ev, entity, idx) {
    const s = parseHaDate(ev.start); const e = parseHaDate(ev.end);
    if (!s || !e) return null;
    const entityColor = safeHex(this._config.colors && this._config.colors[idx], PALETTE[idx % PALETTE.length]);
    const label = ev.label && ev.label.id !== undefined ? { id: ev.label.id, name: ev.label.name, color: safeHex(ev.label.color) } : null;
    const st = this._hass.states[entity];
    return {
      entity, entityName: (st && st.attributes && st.attributes.friendly_name) || entity,
      color: (label && label.color) || entityColor, label,
      allDay: s.allDay, start: s.dt, end: e.dt,
      summary: ev.summary || "", location: ev.location || "", description: ev.description || "", uid: ev.uid || "",
    };
  }

  /* ---------- formatting ---------- */

  _t(key, ...args) { const v = (STRINGS[lang(this._hass)] || STRINGS.en)[key]; return typeof v === "function" ? v(...args) : v; }
  _locale() { return (this._hass && this._hass.locale && this._hass.locale.language) || (this._hass && this._hass.language) || undefined; }
  _fmtTime(d) { return new Intl.DateTimeFormat(this._locale(), { hour: "2-digit", minute: "2-digit" }).format(d); }
  _fmtDay(d) { return new Intl.DateTimeFormat(this._locale(), { weekday: "short", day: "numeric", month: "short" }).format(d); }
  _fmtLong(d) { return new Intl.DateTimeFormat(this._locale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(d); }

  _relDay(d, today) {
    if (!this._config.relative_days) return "";
    const diff = Math.round((toLocalDate(d) - today) / 86400000);
    if (diff === 0) return this._t("today"); if (diff === 1) return this._t("tomorrow"); if (diff === -1) return this._t("yesterday");
    return "";
  }

  _duration(e) {
    if (e.allDay) { const n = Math.round((e.end - e.start) / 86400000); return n <= 1 ? this._t("day") : this._t("days", n); }
    const m = Math.round((e.end - e.start) / 60000);
    if (m < 60) return this._t("minutes", m);
    const h = Math.floor(m / 60), r = m % 60;
    return r ? `${this._t("hours", h)} ${this._t("minutes", r)}` : this._t("hours", h);
  }

  /* ---------- filtering ---------- */

  _visible(events) {
    const c = this._config;
    let out = events;
    if (c.labels && c.labels.length) out = out.filter((e) => e.label && c.labels.includes(labelKey(e.label.id)));
    if (c.label_filter && this._hidden.size) out = out.filter((e) => !this._hidden.has(e.label ? labelKey(e.label.id) : "__none"));
    return out;
  }

  /* ---------- rendering ---------- */

  _render() {
    if (!this._config) return;
    const c = this._config; const now = new Date(); const today = toLocalDate(now); const t = (k, ...a) => this._t(k, ...a);

    let events = this._events;
    if (!c.show_all_day) events = events.filter((e) => !e.allDay);
    events = events.filter((e) => e.end > now);
    events = this._visible(events);
    const total = events.length;
    events = events.slice(0, c.max_events);

    const groups = new Map();
    for (const e of events) {
      const d = e.allDay ? e.start : toLocalDate(e.start); const k = dayKey(d);
      if (!groups.has(k)) groups.set(k, { date: d, items: [] });
      groups.get(k).items.push(e);
    }
    for (const g of groups.values()) g.items.sort((a, b) => (a.allDay === b.allDay ? a.start - b.start : a.allDay ? -1 : 1));

    const title = c.title || t("title");
    const accentColor = safeCssColor(c.accent_color);
    const accent = accentColor ? `--timetree-accent:${esc(accentColor)};` : "";
    const layoutClass = `layout-${c.layout === "columns" ? "columns" : c.layout === "list" ? "list" : "auto"}`;
    const iconHtml = c.show_icon
      ? `<div class="icon">${c.icon ? `<ha-icon icon="${esc(c.icon)}"></ha-icon>`
        : `<img src="/timetree_static/icon.png" alt="" onerror="this.replaceWith(Object.assign(document.createElement('ha-icon'),{icon:'mdi:calendar-heart'}))">`}</div>` : "";

    // chip bar
    let chips = "";
    if (c.label_filter) {
      let labels = labelsOf(this._hass, c.entities);
      if (c.labels && c.labels.length) labels = labels.filter((l) => c.labels.includes(labelKey(l.id)));
      const hasUnlabeled = this._events.some((e) => !e.label);
      if (labels.length) {
        const allOn = this._hidden.size === 0;
        chips = `<div class="chips">
          <button class="chip all ${allOn ? "on" : ""}" data-key="__all"><span class="sw"></span>${t("allLabels")}</button>
          ${labels.map((l) => `<button class="chip ${this._hidden.has(labelKey(l.id)) ? "off" : "on"}" style="--c:${esc(l.color)}" data-key="${esc(labelKey(l.id))}"><span class="sw"></span>${esc(l.name)}</button>`).join("")}
          ${hasUnlabeled && !(c.labels && c.labels.length) ? `<button class="chip ${this._hidden.has("__none") ? "off" : "on"}" style="--c:#9e9e9e" data-key="__none"><span class="sw"></span>${t("noLabel")}</button>` : ""}
        </div>`;
      }
    }

    let body = "";
    if (this._status === "missing") body = `<div class="state error"><ha-icon icon="mdi:calendar-alert"></ha-icon>${t("missing")}</div>`;
    else if (this._status === "error") body = `<div class="state error"><ha-icon icon="mdi:cloud-off-outline"></ha-icon>${t("error")}</div>`;
    else if (this._status === "loading") body = `<div class="state"><ha-circular-progress indeterminate size="small"></ha-circular-progress>${t("loading")}</div>`;
    else if (!events.length) body = `<div class="state"><ha-icon icon="mdi:calendar-check"></ha-icon>${esc(c.empty_text) || t("noEvents")}</div>`;
    else {
      const tappable = c.tap_action !== "none";
      const dayHtml = [];
      let idx = 0;
      for (const [, g] of groups) {
        const isToday = dayKey(g.date) === dayKey(today); const rel = this._relDay(g.date, today);
        const rows = g.items.map((e) => {
          const running = e.start <= now && e.end > now;
          const timeHtml = e.allDay ? `<div class="time">${t("allDay")}</div>`
            : `<div class="time">${running ? `<strong>${t("now")}</strong>` : this._fmtTime(e.start)}<span class="end">${t("until")} ${this._fmtTime(e.end)}</span></div>`;
          const loc = c.show_location && e.location ? `<div class="meta"><ha-icon icon="mdi:map-marker-outline"></ha-icon><span>${esc(e.location)}</span></div>` : "";
          const tag = c.show_label && e.label ? `<div class="tag" style="--c:${esc(e.label.color)}"><span class="sw"></span>${esc(e.label.name)}</div>` : "";
          const desc = c.show_description && e.description ? `<div class="desc">${esc(e.description)}</div>` : "";
          const i = idx++; e._i = i;
          return `<div class="event${running ? " running" : ""}${tappable ? " tappable" : ""}" data-i="${i}" ${tappable ? 'role="button" tabindex="0"' : ""}>
              ${timeHtml}<div class="dot" style="--dot:${esc(e.color)}"></div>
              <div class="main"><div class="summary">${esc(e.summary)}</div>${loc}${tag}${desc}</div></div>`;
        }).join("");
        dayHtml.push(`<section class="day${isToday ? " today" : ""}"><div class="day-head">${rel ? `<span class="rel">${rel}</span>` : ""}<span>${this._fmtDay(g.date)}</span></div>${rows}</section>`);
      }
      body = `<div class="days">${dayHtml.join("")}</div>${total > events.length ? `<div class="more">${t("more", total - events.length)}</div>` : ""}`;
    }
    this._shown = events;

    const header = c.show_header
      ? `<div class="header">${iconHtml}<div style="min-width:0"><div class="title">${esc(title)}</div></div><div class="spacer"></div>${events.length ? `<div class="count">${events.length}</div>` : ""}</div>` : "";

    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card class="${layoutClass}${c.compact ? " compact" : ""}" style="${accent}">${header}${chips}<div class="body">${body}</div>${this._dialogHtml(now)}</ha-card>`;

    // wire up
    this.shadowRoot.querySelectorAll(".event.tappable").forEach((el) => {
      const open = () => this._tap(this._shown[Number(el.dataset.i)]);
      el.addEventListener("click", open);
      el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } });
    });
    this.shadowRoot.querySelectorAll(".chip").forEach((el) => el.addEventListener("click", () => this._toggleChip(el.dataset.key)));
    const bd = this.shadowRoot.querySelector(".backdrop");
    if (bd) {
      bd.addEventListener("click", (ev) => { if (ev.target === bd) this._closeDialog(); });
      const x = bd.querySelector(".x"); if (x) x.addEventListener("click", () => this._closeDialog());
      this._escHandler = (ev) => { if (ev.key === "Escape") this._closeDialog(); };
      window.addEventListener("keydown", this._escHandler, { once: true });
    }
  }

  _toggleChip(key) {
    if (key === "__all") this._hidden.clear();
    else if (this._hidden.has(key)) this._hidden.delete(key); else this._hidden.add(key);
    this._saveHidden(); this._render();
  }

  _tap(e) {
    if (!e) return;
    if (this._config.tap_action === "more-info") {
      this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: e.entity } }));
      return;
    }
    if (this._config.tap_action === "dialog") { this._open = e; this._render(); }
  }

  _closeDialog() { this._open = null; this._render(); }

  _dialogHtml(now) {
    const e = this._open; if (!e) return "";
    const t = (k, ...a) => this._t(k, ...a);
    const sameDay = dayKey(e.start) === dayKey(e.allDay ? new Date(e.end.getTime() - 1) : e.end);
    let when;
    if (e.allDay) {
      const endIncl = new Date(e.end.getTime() - 86400000);
      when = sameDay || endIncl <= e.start ? `${this._fmtLong(e.start)} · ${t("allDay")}` : `${this._fmtLong(e.start)} – ${this._fmtLong(endIncl)}`;
    } else {
      when = sameDay ? `${this._fmtLong(e.start)}<br>${this._fmtTime(e.start)} – ${this._fmtTime(e.end)} · ${this._duration(e)}`
        : `${this._fmtLong(e.start)}, ${this._fmtTime(e.start)}<br>${t("until")} ${this._fmtLong(e.end)}, ${this._fmtTime(e.end)}`;
    }
    const running = e.start <= now && e.end > now;
    const rows = [
      ["mdi:clock-outline", t("when"), `${when}${running ? `<span class="live">${t("running")}</span>` : ""}`],
      e.location ? ["mdi:map-marker-outline", t("where"), `<a href="https://maps.google.com/?q=${encodeURIComponent(e.location)}" target="_blank" rel="noopener">${esc(e.location)}</a>`] : null,
      e.label ? ["mdi:tag-outline", t("label"), `<span class="tag" style="--c:${esc(e.label.color)}"><span class="sw"></span>${esc(e.label.name)}</span>`] : null,
      e.description ? ["mdi:text", t("notes"), `<div class="pre">${linkify(e.description)}</div>`] : null,
      ["mdi:calendar", t("calendar"), esc(e.entityName)],
    ].filter(Boolean);
    return `<div class="backdrop" role="dialog" aria-modal="true">
      <div class="sheet" style="--c:${esc(e.color)}"><div class="bar"></div><div class="inner">
        <div class="top"><h2>${esc(e.summary)}</h2><button class="x" aria-label="${t("close")}">×</button></div>
        <div class="rows">${rows.map(([ic, k, v]) => `<ha-icon icon="${ic}"></ha-icon><div><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
      </div></div></div>`;
  }
}

/* ---------- visual editor ---------- */

class TimeTreeCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); this._config = { ...DEFAULTS }; }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...config };
    if (config.entity && !config.entities) this._config.entities = [config.entity];
    this._config.labels = (this._config.labels || []).map(labelKey);
    this._render();
  }
  set hass(hass) { this._hass = hass; this._render(); }

  get _schema() {
    const de = lang(this._hass) === "de"; const L = (d, e) => (de ? d : e);
    const labels = labelsOf(this._hass, this._config.entities);
    const schema = [
      { name: "entities", selector: { entity: { multiple: true, filter: { domain: "calendar" } } } },
      { type: "grid", name: "", schema: [
        { name: "title", selector: { text: {} } },
        { name: "icon", selector: { icon: {} } },
      ] },
      { type: "grid", name: "", schema: [
        { name: "days", selector: { number: { min: 1, max: 60, mode: "slider", unit_of_measurement: L("Tage", "days") } } },
        { name: "max_events", selector: { number: { min: 1, max: 100, mode: "box" } } },
        { name: "layout", selector: { select: { mode: "dropdown", options: [
          { value: "auto", label: L("Automatisch", "Auto") }, { value: "list", label: L("Liste", "List") }, { value: "columns", label: L("Tages-Spalten", "Day columns") } ] } } },
        { name: "tap_action", selector: { select: { mode: "dropdown", options: [
          { value: "dialog", label: L("Termin-Details", "Event details") }, { value: "more-info", label: L("Entitäten-Dialog", "Entity more-info") }, { value: "none", label: L("Nichts", "Nothing") } ] } } },
        { name: "accent_color", selector: { text: {} } },
      ] },
    ];
    if (labels.length) {
      schema.push({ name: "labels", selector: { select: { multiple: true, mode: "list", options: labels.map((l) => ({ value: labelKey(l.id), label: l.name })) } } });
    }
    schema.push({ type: "grid", name: "", schema: [
      { name: "label_filter", selector: { boolean: {} } },
      { name: "show_label", selector: { boolean: {} } },
      { name: "show_header", selector: { boolean: {} } },
      { name: "show_icon", selector: { boolean: {} } },
      { name: "show_all_day", selector: { boolean: {} } },
      { name: "show_location", selector: { boolean: {} } },
      { name: "show_description", selector: { boolean: {} } },
      { name: "relative_days", selector: { boolean: {} } },
      { name: "compact", selector: { boolean: {} } },
    ] });
    schema.push({ name: "empty_text", selector: { text: {} } });
    return schema;
  }

  _label(schema) {
    const de = lang(this._hass) === "de";
    const map = de ? {
      entities: "Kalender", title: "Titel", icon: "Icon", days: "Zeitraum", max_events: "Max. Termine", layout: "Darstellung",
      tap_action: "Beim Antippen", accent_color: "Akzentfarbe (z. B. #2ecc84)", labels: "Nur diese Labels anzeigen",
      label_filter: "Label-Filter auf der Karte", show_label: "Label am Termin", show_header: "Kopfzeile", show_icon: "Icon anzeigen",
      show_all_day: "Ganztägige anzeigen", show_location: "Ort anzeigen", show_description: "Beschreibung anzeigen",
      relative_days: "Heute / Morgen", compact: "Kompakt", empty_text: "Text wenn keine Termine",
    } : {
      entities: "Calendars", title: "Title", icon: "Icon", days: "Range", max_events: "Max. events", layout: "Layout",
      tap_action: "On tap", accent_color: "Accent colour (e.g. #2ecc84)", labels: "Only show these labels",
      label_filter: "Label filter on the card", show_label: "Label on event", show_header: "Header", show_icon: "Show icon",
      show_all_day: "Show all-day events", show_location: "Show location", show_description: "Show description",
      relative_days: "Today / Tomorrow", compact: "Compact", empty_text: "Text when empty",
    };
    return map[schema.name] || schema.name;
  }

  async _render() {
    if (!this.shadowRoot) return;
    if (!customElements.get("ha-form")) {
      try { const helpers = await window.loadCardHelpers(); const el = helpers.createCardElement({ type: "entities", entities: [] });
        if (el && el.constructor && el.constructor.getConfigElement) await el.constructor.getConfigElement(); } catch (_) { /* ignore */ }
      await customElements.whenDefined("ha-form").catch(() => {});
    }
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const value = { ...ev.detail.value };
        for (const k of Object.keys(value)) if (JSON.stringify(value[k]) === JSON.stringify(DEFAULTS[k])) delete value[k];
        value.type = `custom:${CARD_TAG}`;
        this._config = { ...DEFAULTS, ...value };
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: value }, bubbles: true, composed: true }));
        this._render(); // labels list depends on the chosen entities
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
  window.customCards.push({ type: CARD_TAG, name: "TimeTree Agenda",
    description: "Responsive, theme-aware agenda for any calendar entity with label filters and an event detail dialog.",
    preview: true, documentationURL: "https://github.com/tmsbyr87/TimeTree-HA#dashboard-card" });
}
console.info(`%c TIMETREE-CARD %c ${CARD_VERSION} `, "color:#fff;background:#2ecc84;font-weight:700", "color:#2ecc84;background:#fff;font-weight:700"); // eslint-disable-line no-console
