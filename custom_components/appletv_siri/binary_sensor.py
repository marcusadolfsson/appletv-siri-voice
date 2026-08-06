"""Is voice actually usable right now?

Worth an entity of its own: the failure mode this catches is silent. Buttons
keep working while Siri stops, because the Apple TV has dropped the data stream
that carries audio — so without something to watch, you find out by talking to a
remote that does nothing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BridgeCoordinator


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    if discovery_info is None or DOMAIN not in hass.data:
        return
    async_add_entities([SiriAvailableBinarySensor(hass.data[DOMAIN]["coordinator"])])


class SiriAvailableBinarySensor(CoordinatorEntity[BridgeCoordinator], BinarySensorEntity):
    """On when the selected Apple TV has a live voice data stream."""

    _attr_name = "Siri voice available"
    _attr_unique_id = f"{DOMAIN}_siri_available"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: BridgeCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.get("siriAvailable"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "active_identifier": self.coordinator.active_identifier,
            "recovering": data.get("recovering"),
        }
