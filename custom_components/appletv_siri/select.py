"""A select entity for choosing which Apple TV gets voice and buttons.

The bridge identifies Apple TVs by numeric identifiers that tvOS assigns, which
are no use in a dashboard. This exposes them as a normal select so a target can
be picked from the UI or set by an automation — "when the living room activity
starts, point the remote at the living room Apple TV".

Names come from the Apple TV itself. hap-nodejs currently returns them
concatenated (a TLV parsing quirk upstream), so a name that looks doubled-up is
expected; the identifier behind it is correct, and is shown alongside to keep
the options unambiguous.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .bridge import Bridge, BridgeError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the target selector."""
    if discovery_info is None:
        return
    data = hass.data.get(DOMAIN)
    if not data:
        return
    async_add_entities([AppleTvTargetSelect(data["bridge"])], update_before_add=True)


class AppleTvTargetSelect(SelectEntity):
    """Which Apple TV the bridge is currently pointed at."""

    _attr_has_entity_name = False
    _attr_name = "Apple TV target"
    _attr_icon = "mdi:apple"
    _attr_unique_id = f"{DOMAIN}_target"

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge
        self._targets: dict[str, int] = {}   # label -> identifier
        self._attr_options = []
        self._attr_current_option = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        try:
            state = await self._bridge.state()
        except BridgeError as err:
            _LOGGER.debug("Bridge unreachable: %s", err)
            self._attr_available = False
            return

        self._attr_available = True
        # Label with the identifier too: tvOS names can repeat across homes, and
        # the identifier is what actually addresses the device.
        self._targets = {
            f"{info.get('name') or 'Apple TV'} ({ident})": int(ident)
            for ident, info in (state.get("targets") or {}).items()
        }
        self._attr_options = sorted(self._targets)

        active = state.get("activeIdentifier")
        self._attr_current_option = next(
            (label for label, ident in self._targets.items() if ident == active), None
        )
        # Surfaced so an automation can react to voice being unavailable rather
        # than discovering it when an utterance silently goes nowhere.
        self._attr_extra_state_attributes = {
            "active_identifier": active,
            "siri_available": state.get("siriAvailable"),
            "data_streams": state.get("dataStreams"),
            "recovering": state.get("recovering"),
        }

    async def async_select_option(self, option: str) -> None:
        target = self._targets.get(option)
        if target is None:
            _LOGGER.warning("Unknown Apple TV target: %s", option)
            return
        await self._bridge.set_target(target)
        self._attr_current_option = option
        self.async_write_ha_state()
