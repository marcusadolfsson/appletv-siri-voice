"""A "say this to Siri" box per Apple TV.

Per Apple TV so that talking to the bedroom does not require first pointing a
shared selector at it.
"""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .const import ATTR_TARGET, ATTR_TEXT, DOMAIN, SERVICE_SAY
from .coordinator import BridgeCoordinator
from .entity_setup import add_per_target_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BridgeCoordinator = hass.data[DOMAIN]["coordinator"]
    add_per_target_entities(
        coordinator, async_add_entities,
        lambda t: [SiriCommandText(hass, coordinator, t)],
    )


class SiriCommandText(TextEntity):
    """Type a command; Siri on this Apple TV hears it."""

    _attr_has_entity_name = True
    _attr_name = "Say to Siri"
    _attr_icon = "mdi:microphone-message"
    _attr_native_max = 255
    _attr_mode = "text"

    def __init__(self, hass: HomeAssistant, coordinator: BridgeCoordinator, target: int) -> None:
        self._hass = hass
        self._target = target
        self._attr_native_value = ""
        self._attr_unique_id = f"{DOMAIN}_{target}_say"
        self._attr_device_info = coordinator.device_info(target)

    async def async_set_value(self, value: str) -> None:
        """Speak it, then clear — it is an action, not a setting."""
        text = value.strip()
        if not text:
            return
        self._attr_native_value = value
        self.async_write_ha_state()
        try:
            await self._hass.services.async_call(
                DOMAIN, SERVICE_SAY,
                {ATTR_TEXT: text, ATTR_TARGET: self._target},
                blocking=True,
            )
        finally:
            self._attr_native_value = ""
            self.async_write_ha_state()
