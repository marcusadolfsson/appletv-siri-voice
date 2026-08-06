"""One set of remote keys per Apple TV.

Per Apple TV rather than one shared set, because a single set would act on
whichever target happened to be selected — so driving a second Apple TV would
mean flipping a selector first and then pressing, with the state shared between
them. Each button here names its own target, and the press is a single call.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .bridge import Bridge
from .const import DOMAIN
from .coordinator import BridgeCoordinator
from .entity_setup import add_per_target_entities

_LOGGER = logging.getLogger(__name__)

# The handful worth a one-tap button; everything else is appletv_siri.press.
KEYS = [
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
    data = hass.data[DOMAIN]
    coordinator: BridgeCoordinator = data["coordinator"]
    bridge: Bridge = data["bridge"]

    async_add_entities([RecoverButton(bridge)])
    add_per_target_entities(
        coordinator, async_add_entities,
        lambda t: [RemoteButton(coordinator, bridge, t, c, l, i) for c, l, i in KEYS],
    )


class RemoteButton(ButtonEntity):
    """One key on one Apple TV.

    Named with the Apple TV in the entity name rather than relying on
    has_entity_name + device_info: a YAML-configured integration has no config
    entry, so Home Assistant cannot create devices for it, device_info is
    ignored, and every Apple TV would end up with a button called just "Home".
    """

    def __init__(
        self, coordinator: BridgeCoordinator, bridge: Bridge,
        target: int, code: str, label: str, icon: str,
    ) -> None:
        self._bridge = bridge
        self._target = target
        self._code = code
        self._attr_name = f"{coordinator.clean_name(target)} {label}"
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}_{target}_btn_{code.lower()}"

    async def async_press(self) -> None:
        await self._bridge.press(self._code, self._target)


class RecoverButton(ButtonEntity):
    """Rebuild the voice data stream. Bridge-wide, so it is not per Apple TV."""

    _attr_name = "Recover Siri voice"
    _attr_icon = "mdi:restart-alert"
    _attr_unique_id = f"{DOMAIN}_recover"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge

    async def async_press(self) -> None:
        # Takes about a minute, and buttons drop out twice while it republishes.
        await self._bridge.recover()
