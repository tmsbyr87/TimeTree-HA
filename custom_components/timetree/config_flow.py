"""Config flow for TimeTree."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    TimeTreeApiChanged,
    TimeTreeCalendarInfo,
    TimeTreeClient,
    TimeTreeConnectionError,
    TimeTreeInvalidCredentials,
    TimeTreeRateLimited,
    TimeTreeAuthError,
    TimeTreeSessionExpired,
)
from .const import (
    CONF_CALENDAR_NAMES,
    CONF_CALENDARS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .coordinator import TimeTreeAccount, async_get_timetree_session
from .entry_data import account_unique_id, merge_calendar_names, selected_calendars

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


async def _async_login_and_list(
    flow: ConfigFlow, email: str, password: str
) -> tuple[str, list[TimeTreeCalendarInfo]]:
    """Log in and fetch calendars. Returns (session_id, calendars)."""
    client = TimeTreeClient(async_get_timetree_session(flow.hass))
    session_id = await client.async_login(email, password)
    calendars = await client.async_list_calendars()
    return session_id, calendars


def _calendar_selector(names: dict[str, str]) -> SelectSelector:
    """Checkbox list of calendars (``{id: name}``)."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=cal_id, label=name) for cal_id, name in names.items()],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def _scan_interval_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL_MINUTES,
            max=MAX_SCAN_INTERVAL_MINUTES,
            step=5,
            mode=NumberSelectorMode.SLIDER,
            unit_of_measurement="min",
        )
    )


def _names_of(calendars: list[TimeTreeCalendarInfo]) -> dict[str, str]:
    return {str(c.calendar_id): c.name for c in calendars}


def _map_error(err: Exception) -> str:
    if isinstance(err, TimeTreeApiChanged):
        return "api_changed"
    if isinstance(err, TimeTreeInvalidCredentials):
        return "invalid_auth"
    if isinstance(err, TimeTreeRateLimited):
        return "rate_limited"
    if isinstance(err, (TimeTreeAuthError, TimeTreeSessionExpired)):
        return "invalid_auth"
    if isinstance(err, TimeTreeConnectionError):
        return "cannot_connect"
    return "unknown"


class TimeTreeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the TimeTree configuration flow (one entry per account)."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._session_id: str | None = None
        self._calendars: list[TimeTreeCalendarInfo] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            await self.async_set_unique_id(account_unique_id(email))
            self._abort_if_unique_id_configured()
            try:
                self._session_id, self._calendars = await _async_login_and_list(
                    self, email, user_input[CONF_PASSWORD]
                )
            except Exception as err:  # noqa: BLE001 – map every failure to a UI error
                errors["base"] = _map_error(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Unexpected error during TimeTree login")
            else:
                self._email = email
                self._password = user_input[CONF_PASSWORD]
                if not self._calendars:
                    errors["base"] = "no_calendars"
                else:
                    return await self.async_step_calendars()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_calendars(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: pick any number of the account's calendars."""
        names = _names_of(self._calendars)
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [cal_id for cal_id in user_input.get(CONF_CALENDARS, []) if cal_id in names]
            if not chosen:
                errors["base"] = "no_calendar_selected"
            else:
                return self.async_create_entry(
                    title=self._email or "TimeTree",
                    data={
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_SESSION_ID: self._session_id,
                        CONF_CALENDAR_NAMES: names,
                    },
                    options={CONF_CALENDARS: chosen},
                )

        schema = vol.Schema(
            {vol.Required(CONF_CALENDARS, default=list(names)): _calendar_selector(names)}
        )
        return self.async_show_form(step_id="calendars", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Entry point when the coordinator raised ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh password and store a new session."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        email = entry.data[CONF_EMAIL]

        if user_input is not None:
            try:
                session_id, calendars = await _async_login_and_list(
                    self, email, user_input[CONF_PASSWORD]
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _map_error(err)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SESSION_ID: session_id,
                        CONF_CALENDAR_NAMES: merge_calendar_names(
                            entry.data.get(CONF_CALENDAR_NAMES) or {},
                            {c.calendar_id: c.name for c in calendars},
                        ),
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"email": email},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TimeTreeOptionsFlow:
        """Expose the options flow."""
        return TimeTreeOptionsFlow()


class TimeTreeOptionsFlow(OptionsFlow):
    """Choose calendars and the polling interval."""

    async def _async_known_calendars(self) -> dict[str, str]:
        """Stored names, refreshed from TimeTree when the session allows it."""
        entry = self.config_entry
        names = dict(entry.data.get(CONF_CALENDAR_NAMES) or {})
        account: TimeTreeAccount | None = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        client = (
            account.client
            if account is not None
            else TimeTreeClient(
                async_get_timetree_session(self.hass),
                session_id=entry.data.get(CONF_SESSION_ID),
            )
        )
        try:
            fresh = await client.async_list_calendars()
        except Exception as err:  # noqa: BLE001 – offline: offer what we know
            _LOGGER.debug("Could not refresh the TimeTree calendar list: %s", err)
            return names
        merged = merge_calendar_names(names, {c.calendar_id: c.name for c in fresh})
        if merged != names:
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_CALENDAR_NAMES: merged}
            )
        return merged

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Single options step."""
        entry = self.config_entry
        names = await self._async_known_calendars()
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [cal_id for cal_id in user_input.get(CONF_CALENDARS, []) if cal_id in names]
            if not chosen:
                errors["base"] = "no_calendar_selected"
            else:
                return self.async_create_entry(
                    data={**user_input, CONF_CALENDARS: chosen}
                )

        current_calendars = [
            str(cal_id) for cal_id in selected_calendars(dict(entry.data), dict(entry.options))
        ]
        current_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        schema = vol.Schema(
            {
                vol.Required(CONF_CALENDARS, default=current_calendars): _calendar_selector(names),
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): _scan_interval_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
