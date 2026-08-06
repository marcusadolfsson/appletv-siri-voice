"""UI setup.

Exists for more than the notice on the integrations page: an integration with no
config entry cannot create **devices**, so without this every Apple TV's buttons
would be named "Home" with no way to tell them apart.

Connection settings live here. The routing keys — `sources`, `siri_when`,
`assist_pipeline` — stay in YAML, because they are nested and awkward in a form,
and they are merged over whatever is configured here.

There is no "default Apple TV" to configure: every command names its own.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectOptionDict, TextSelector

from .bridge import Bridge, BridgeError
from .const import CONF_BRIDGE_URL, CONF_TTS_ENGINE, DEFAULT_BRIDGE_URL, DOMAIN

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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Only the bridge and the speech engine.

        Deliberately no "default Apple TV": every command names its own, so
        there is no hidden state deciding where an utterance ends up.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_BRIDGE_URL].rstrip("/")
            try:
                choices, _ = await _apple_tv_choices(self.hass, url)
            except BridgeError:
                errors["base"] = "cannot_connect"
            else:
                if not choices:
                    # Reachable but no Apple TVs: almost always means the
                    # accessory has not been paired in the Home app yet.
                    errors["base"] = "no_targets"
                else:
                    await self.async_set_unique_id(url)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Apple TV Siri Voice",
                        data={
                            CONF_BRIDGE_URL: url,
                            CONF_TTS_ENGINE: user_input.get(CONF_TTS_ENGINE) or None,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_BRIDGE_URL, default=DEFAULT_BRIDGE_URL): TextSelector(),
                vol.Optional(CONF_TTS_ENGINE): TextSelector(),
            }),
            errors=errors,
        )

    async def async_step_import(self, data: dict[str, Any]) -> FlowResult:
        """Adopt an existing YAML setup so nothing breaks on upgrade."""
        url = (data.get(CONF_BRIDGE_URL) or DEFAULT_BRIDGE_URL).rstrip("/")
        await self.async_set_unique_id(url)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Apple TV Siri Voice (YAML)",
            data={CONF_BRIDGE_URL: url, CONF_TTS_ENGINE: data.get(CONF_TTS_ENGINE)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return AppleTvSiriOptionsFlow()


class AppleTvSiriOptionsFlow(OptionsFlow):
    """Change the speech engine later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_TTS_ENGINE: user_input.get(CONF_TTS_ENGINE) or None}
            )
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_TTS_ENGINE,
                    description={"suggested_value": current.get(CONF_TTS_ENGINE)},
                ): TextSelector(),
            }),
        )
