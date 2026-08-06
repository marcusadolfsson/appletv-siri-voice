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
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bridge import Bridge
from .const import DOMAIN
from .coordinator import BridgeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the target selector."""
    data = hass.data[DOMAIN]
    async_add_entities([AppleTvTargetSelect(data["coordinator"], data["bridge"])])


class AppleTvTargetSelect(CoordinatorEntity[BridgeCoordinator], SelectEntity):
    """Which Apple TV the bridge is currently pointed at."""

    _attr_has_entity_name = False
    _attr_name = "Apple TV target"
    _attr_icon = "mdi:apple"
    _attr_unique_id = f"{DOMAIN}_target"

    def __init__(self, coordinator: BridgeCoordinator, bridge: Bridge) -> None:
        super().__init__(coordinator)
        self._bridge = bridge
        self._attr_device_info = coordinator.bridge_device_info()

    @property
    def _labels(self) -> dict[str, int]:
        """label -> identifier."""
        return {
            self.coordinator.label_for(ident): int(ident)
            for ident in self.coordinator.targets
        }

    @property
    def options(self) -> list[str]:
        return sorted(self._labels)

    @property
    def current_option(self) -> str | None:
        active = self.coordinator.active_identifier
        return next((l for l, i in self._labels.items() if i == active), None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "active_identifier": self.coordinator.active_identifier,
            "siri_available": data.get("siriAvailable"),
            "data_streams": data.get("dataStreams"),
            "recovering": data.get("recovering"),
        }

    async def async_select_option(self, option: str) -> None:
        target = self._labels.get(option)
        if target is None:
            _LOGGER.warning("Unknown Apple TV target: %s", option)
            return
        await self._bridge.set_target(target)
        await self.coordinator.async_request_refresh()
