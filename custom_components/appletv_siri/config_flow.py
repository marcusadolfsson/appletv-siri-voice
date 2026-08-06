"""UI setup.

Exists for more than the notice on the integrations page: an integration with no
config entry cannot create **devices**, so without this every Apple TV's buttons
would be named "Home" with no way to tell them apart.

Connection settings live here. The routing keys — `sources`, `siri_when`,
`assist_pipeline` — stay in YAML, because they are nested and awkward in a form,
and they are merged over whatever is configured here.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .bridge import Bridge, BridgeError
from .const import (
    CONF_BRIDGE_URL,
    CONF_TARGET,
    CONF_TTS_ENGINE,
    DEFAULT_BRIDGE_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _apple_tv_choices(hass, url: str) -> tuple[list[SelectOptionDict], str | None]:
    """Ask the bridge which Apple TVs it can see, for the dropdown."""
    bridge = Bridge(async_get_clientsession(hass), url)
    state = await bridge.state()          # raises BridgeError if unreachable
    choices = [
        SelectOptionDict(value=str(ident), label=f"{(info.get('name') or 'Apple TV')} ({ident})")
        for ident, info in (state.get("targets") or {}).items()
    ]
    return choices, (str(state["activeIdentifier"]) if state.get("activeIdentifier") else None)


class AppleTvSiriConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set the integration up from the UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._url: str = DEFAULT_BRIDGE_URL

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask for the bridge, then offer the Apple TVs it reports."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._url = user_input[CONF_BRIDGE_URL].rstrip("/")
            try:
                choices, active = await _apple_tv_choices(self.hass, self._url)
            except BridgeError:
                errors["base"] = "cannot_connect"
            else:
                if not choices:
                    # Reachable but no Apple TVs yet — almost always means the
                    # accessory has not been paired in the Home app.
                    errors["base"] = "no_targets"
                else:
                    await self.async_set_unique_id(self._url)
                    self._abort_if_unique_id_configured()
                    self._choices, self._active = choices, active
                    return await self.async_step_target()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_BRIDGE_URL, default=self._url): TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_target(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Pick the default Apple TV, and the engine used to speak text."""
        if user_input is not None:
            return self.async_create_entry(
                title="Apple TV Siri Voice",
                data={
                    CONF_BRIDGE_URL: self._url,
                    CONF_TARGET: int(user_input[CONF_TARGET]),
                    CONF_TTS_ENGINE: user_input.get(CONF_TTS_ENGINE) or None,
                },
            )

        return self.async_show_form(
            step_id="target",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET, default=self._active or self._choices[0]["value"]):
                        SelectSelector(SelectSelectorConfig(options=self._choices)),
                    vol.Optional(CONF_TTS_ENGINE): TextSelector(),
                }
            ),
        )

    async def async_step_import(self, data: dict[str, Any]) -> FlowResult:
        """Adopt an existing YAML setup so nothing breaks on upgrade."""
        url = (data.get(CONF_BRIDGE_URL) or DEFAULT_BRIDGE_URL).rstrip("/")
        await self.async_set_unique_id(url)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Apple TV Siri Voice (YAML)",
            data={
                CONF_BRIDGE_URL: url,
                CONF_TARGET: data.get(CONF_TARGET),
                CONF_TTS_ENGINE: data.get(CONF_TTS_ENGINE),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return AppleTvSiriOptionsFlow()


class AppleTvSiriOptionsFlow(OptionsFlow):
    """Change the default Apple TV or the speech engine later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self.config_entry
        if user_input is not None:
            return self.async_create_entry(data={
                CONF_TARGET: int(user_input[CONF_TARGET]),
                CONF_TTS_ENGINE: user_input.get(CONF_TTS_ENGINE) or None,
            })

        current = {**entry.data, **entry.options}
        try:
            choices, _ = await _apple_tv_choices(self.hass, current[CONF_BRIDGE_URL])
        except BridgeError:
            choices = []

        target_default = str(current.get(CONF_TARGET) or (choices[0]["value"] if choices else ""))
        schema: dict[Any, Any] = {}
        if choices:
            schema[vol.Required(CONF_TARGET, default=target_default)] = SelectSelector(
                SelectSelectorConfig(options=choices)
            )
        schema[vol.Optional(CONF_TTS_ENGINE, description={"suggested_value": current.get(CONF_TTS_ENGINE)})] = TextSelector()
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
