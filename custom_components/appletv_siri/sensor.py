"""Diagnostics for the bridge, so its state is visible without curl.

The Apple TV identifiers live here. They are assigned by tvOS and are what goes
in `target:` and in `sources:`, so having to shell out to read them was the
worst part of setting this up.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BRIDGE_URL, DEFAULT_BRIDGE_URL, DOMAIN
from .coordinator import BridgeCoordinator


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    if discovery_info is None or DOMAIN not in hass.data:
        return
    data = hass.data[DOMAIN]
    async_add_entities([BridgeSensor(data["coordinator"], data["conf"])])


class BridgeSensor(CoordinatorEntity[BridgeCoordinator], SensorEntity):
    """How many Apple TVs the bridge can see, plus everything about them."""

    _attr_name = "Apple TV bridge"
    _attr_icon = "mdi:bridge"
    _attr_unique_id = f"{DOMAIN}_bridge"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "Apple TVs"

    def __init__(self, coordinator: BridgeCoordinator, conf: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._conf = conf

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.targets)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        data = c.data or {}
        streams = data.get("dataStreams") or []
        return {
            # The identifiers you need for `target:` / `sources:`, laid out so
            # they can be read straight off the entity's attributes panel.
            "apple_tvs": {
                ident: {
                    "name": info.get("name"),
                    "identifier": int(ident),
                    "configured": info.get("configured"),
                    "voice_ready": int(ident) in [int(s) for s in streams],
                }
                for ident, info in c.targets.items()
            },
            "active_identifier": c.active_identifier,
            "active_apple_tv": c.label_for(c.active_identifier) if c.active_identifier else None,
            "siri_available": data.get("siriAvailable"),
            "data_streams": streams,
            "recovering": data.get("recovering"),
            "bridge_url": self._conf.get(CONF_BRIDGE_URL, DEFAULT_BRIDGE_URL),
        }
