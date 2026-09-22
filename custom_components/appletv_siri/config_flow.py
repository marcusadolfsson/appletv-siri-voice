"""UI setup.

Exists for more than the notice on the integrations page: an integration with no
config entry cannot create **devices**, so without this every Apple TV's buttons
would be named "Home" with no way to tell them apart.

Connection settings are asked at setup. The routing rule and what happens to
an utterance that is not for Siri are in **Configure**, so both the HTTP view
and the Assist speech-to-text entity read one rule that can be changed without
touching YAML. A YAML `siri_when:` block is still honoured, and is adopted into
the entry's options when the YAML is first imported.

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
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    TextSelector,
)

from .bridge import Bridge, BridgeError
from .const import (
    CONF_BRIDGE_URL,
    CONF_ENTITY,
    CONF_FALLBACK_AGENT,
    CONF_FALLBACK_STT,
    CONF_SIRI_WHEN,
    CONF_SIRI_WHEN_ENTITY,
    CONF_SIRI_WHEN_STATES,
    CONF_STATES,
    CONF_TTS_ENGINE,
    DEFAULT_BRIDGE_URL,
    DEFAULT_SIRI_WHEN_STATES,
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
        # A YAML routing rule becomes the entry's rule, so it shows up in
        # Configure and there is one place to edit it from then on.
        options: dict[str, Any] = {}
        rule = data.get(CONF_SIRI_WHEN) or {}
        if rule.get(CONF_ENTITY):
            options[CONF_SIRI_WHEN_ENTITY] = rule[CONF_ENTITY]
            options[CONF_SIRI_WHEN_STATES] = ", ".join(rule.get(CONF_STATES) or [])
        return self.async_create_entry(
            title="Apple TV Siri Voice (YAML)",
            data={CONF_BRIDGE_URL: url, CONF_TTS_ENGINE: data.get(CONF_TTS_ENGINE)},
            options=options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return AppleTvSiriOptionsFlow()


class AppleTvSiriOptionsFlow(OptionsFlow):
    """The routing rule, the fallbacks, and the speech engine.

    The rule is the same one the HTTP view and the Siri speech-to-text entity
    both read. Leaving the entity blank means everything goes to Siri.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            # Blank means "not set", so a cleared field really clears it.
            return self.async_create_entry(
                data={k: v for k, v in user_input.items() if v not in (None, "")}
            )
        current = {**self.config_entry.data, **self.config_entry.options}

        def _suggest(key: str, default: Any = None) -> dict[str, Any]:
            value = current.get(key, default)
            return {"suggested_value": value} if value not in (None, "") else {}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SIRI_WHEN_ENTITY, description=_suggest(CONF_SIRI_WHEN_ENTITY)
                ): EntitySelector(),
                vol.Optional(
                    CONF_SIRI_WHEN_STATES,
                    description=_suggest(CONF_SIRI_WHEN_STATES, DEFAULT_SIRI_WHEN_STATES),
                ): TextSelector(),
                vol.Optional(
                    CONF_FALLBACK_STT, description=_suggest(CONF_FALLBACK_STT)
                ): EntitySelector(EntitySelectorConfig(domain="stt")),
                vol.Optional(
                    CONF_FALLBACK_AGENT, description=_suggest(CONF_FALLBACK_AGENT)
                ): EntitySelector(EntitySelectorConfig(domain="conversation")),
                vol.Optional(
                    CONF_TTS_ENGINE, description=_suggest(CONF_TTS_ENGINE)
                ): TextSelector(),
            }),
        )
