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
    TimeTreeCalendarInfo,
    TimeTreeClient,
    TimeTreeConnectionError,
    TimeTreeInvalidCredentials,
    TimeTreeRateLimited,
    TimeTreeAuthError,
    TimeTreeSessionExpired,
)
from .const import (
    CONF_CALENDAR_ID,
    CONF_CALENDAR_NAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .coordinator import async_get_timetree_session

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


def _map_error(err: Exception) -> str:
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
    """Handle the TimeTree configuration flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._session_id: str | None = None
        self._calendars: list[TimeTreeCalendarInfo] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._session_id, self._calendars = await _async_login_and_list(
                    self, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except Exception as err:  # noqa: BLE001 – map every failure to a UI error
                errors["base"] = _map_error(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Unexpected error during TimeTree login")
            else:
                self._email = user_input[CONF_EMAIL]
                self._password = user_input[CONF_PASSWORD]
                if not self._calendars:
                    errors["base"] = "no_calendars"
                else:
                    return await self.async_step_calendar()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: pick one of the account's calendars."""
        if user_input is not None:
            calendar_id = int(user_input[CONF_CALENDAR_ID])
            chosen = next(
                (c for c in self._calendars if c.calendar_id == calendar_id), None
            )
            if chosen is None:
                return self.async_abort(reason="unknown")

            await self.async_set_unique_id(str(calendar_id))
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=chosen.name,
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_SESSION_ID: self._session_id,
                    CONF_CALENDAR_ID: calendar_id,
                    CONF_CALENDAR_NAME: chosen.name,
                },
            )

        options = [
            SelectOptionDict(value=str(c.calendar_id), label=c.name)
            for c in self._calendars
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_CALENDAR_ID): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="calendar", data_schema=schema)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Entry point when the coordinator raised ConfigEntryAuthFailed."""
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh password and store a new session."""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}
        email = self._reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            try:
                session_id, _ = await _async_login_and_list(
                    self, email, user_input[CONF_PASSWORD]
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _map_error(err)
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SESSION_ID: session_id,
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
    """Let the user tune the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Single options step."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=5,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="min",
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
