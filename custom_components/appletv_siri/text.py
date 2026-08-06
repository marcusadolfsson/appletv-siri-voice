"""A text box for talking to Siri from the Home Assistant UI.

Type a command, press enter, and Home Assistant speaks it to the Apple TV. It is
the `say` service with somewhere to put it — useful on a dashboard, and the
quickest way to check the whole chain is alive without a microphone.
"""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import ATTR_TEXT, DOMAIN, SERVICE_SAY

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    if discovery_info is None or DOMAIN not in hass.data:
        return
    async_add_entities([SiriCommandText(hass)])


class SiriCommandText(TextEntity):
    """Say something to Siri."""

    _attr_name = "Say to Siri"
    _attr_icon = "mdi:microphone-message"
    _attr_unique_id = f"{DOMAIN}_say"
    _attr_native_max = 255
    _attr_mode = "text"

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._attr_native_value = ""

    async def async_set_value(self, value: str) -> None:
        """Speak it. The box then clears, so it reads as an action, not a setting."""
        text = value.strip()
        if not text:
            return
        self._attr_native_value = value
        self.async_write_ha_state()
        try:
            await self._hass.services.async_call(
                DOMAIN, SERVICE_SAY, {ATTR_TEXT: text}, blocking=True
            )
        finally:
            self._attr_native_value = ""
            self.async_write_ha_state()
