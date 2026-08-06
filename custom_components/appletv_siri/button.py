"""Buttons for the things you would otherwise call a service for."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .bridge import Bridge
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# The handful worth a one-tap button; everything else is appletv_siri.press.
BUTTONS = [
    ("TV_HOME", "Home", "mdi:home"),
    ("MENU", "Menu", "mdi:menu"),
    ("SELECT", "Select", "mdi:gesture-tap-button"),
    ("PLAY_PAUSE", "Play/Pause", "mdi:play-pause"),
]


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    if discovery_info is None or DOMAIN not in hass.data:
        return
    bridge: Bridge = hass.data[DOMAIN]["bridge"]
    entities: list[ButtonEntity] = [
        RemoteButton(bridge, code, label, icon) for code, label, icon in BUTTONS
    ]
    entities.append(RecoverButton(bridge))
    async_add_entities(entities)


class RemoteButton(ButtonEntity):
    """One remote key."""

    def __init__(self, bridge: Bridge, code: str, label: str, icon: str) -> None:
        self._bridge = bridge
        self._code = code
        self._attr_name = f"Apple TV {label}"
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}_btn_{code.lower()}"

    async def async_press(self) -> None:
        await self._bridge.press(self._code)


class RecoverButton(ButtonEntity):
    """Rebuild the Apple TV's voice data stream."""

    _attr_name = "Recover Siri voice"
    _attr_icon = "mdi:restart-alert"
    _attr_unique_id = f"{DOMAIN}_recover"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge

    async def async_press(self) -> None:
        # Takes about a minute, and buttons drop out twice while it republishes.
        await self._bridge.recover()
