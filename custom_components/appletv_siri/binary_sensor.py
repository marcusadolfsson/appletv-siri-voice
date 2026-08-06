"""Whether voice actually works, per Apple TV.

Worth an entity because the failure is silent: buttons keep working while Siri
stops, since the Apple TV has dropped the data stream that carries audio. With
nothing watching, you find out by talking to a remote that does nothing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BridgeCoordinator
from .entity_setup import add_per_target_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BridgeCoordinator = hass.data[DOMAIN]["coordinator"]
    add_per_target_entities(
        coordinator, async_add_entities, lambda t: [SiriAvailable(coordinator, t)],
    )


class SiriAvailable(CoordinatorEntity[BridgeCoordinator], BinarySensorEntity):
    """On when this Apple TV has a live voice data stream."""

    _attr_has_entity_name = True
    _attr_name = "Siri voice available"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: BridgeCoordinator, target: int) -> None:
        super().__init__(coordinator)
        self._target = target
        self._attr_unique_id = f"{DOMAIN}_{target}_siri_available"
        self._attr_device_info = coordinator.device_info(target)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        # Per Apple TV: the streams die independently, so a healthy one
        # elsewhere must not report this device as ready.
        streams = [int(s) for s in (self.coordinator.data.get("dataStreams") or [])]
        return self._target in streams

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "identifier": self._target,
            "is_active_target": self.coordinator.active_identifier == self._target,
            "recovering": (self.coordinator.data or {}).get("recovering"),
        }
