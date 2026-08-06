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
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_BRIDGE_URL, DEFAULT_BRIDGE_URL, DOMAIN
from .coordinator import BridgeCoordinator
from .entity_setup import add_per_target_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN]
    coordinator: BridgeCoordinator = data["coordinator"]
    async_add_entities([BridgeSensor(coordinator, data["conf"])])
    # One per Apple TV, so the URL a microphone needs is on that Apple TV's own
    # device page rather than buried in another entity's attributes.
    add_per_target_entities(
        coordinator, async_add_entities, lambda t: [VoiceUrlSensor(hass, coordinator, t)]
    )


class BridgeSensor(CoordinatorEntity[BridgeCoordinator], SensorEntity):
    """How many Apple TVs the bridge can see, plus everything about them."""

    _attr_has_entity_name = True
    _attr_name = "Apple TVs found"
    _attr_icon = "mdi:bridge"
    _attr_unique_id = f"{DOMAIN}_bridge"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "Apple TVs"

    def __init__(self, coordinator: BridgeCoordinator, conf: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._conf = conf
        self._attr_device_info = coordinator.bridge_device_info()

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
                    "name": c.clean_name(ident),
                    # What the bridge reported, which hap-nodejs mangles.
                    "name_reported": info.get("name"),
                    "identifier": int(ident),
                    "configured": info.get("configured"),
                    "voice_ready": int(ident) in [int(s) for s in streams],
                    # POST audio here to talk to this Apple TV specifically.
                    "voice_url": c.voice_url(ident),
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


class VoiceUrlSensor(CoordinatorEntity[BridgeCoordinator], SensorEntity):
    """Where to POST audio for this Apple TV.

    A sensor rather than an attribute somewhere: this is the one thing you have
    to copy into a microphone's config, and it should be visible on the device
    page for the Apple TV it belongs to.
    """

    _attr_has_entity_name = True
    _attr_name = "Voice Url"
    _attr_icon = "mdi:link-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, coordinator: BridgeCoordinator, target: int) -> None:
        super().__init__(coordinator)
        self._hass = hass
        self._target = target
        self._attr_unique_id = f"{DOMAIN}_{target}_voice_url"
        self._attr_device_info = coordinator.device_info(target)

    @property
    def native_value(self) -> str | None:
        path = self.coordinator.voice_url(self._target)
        # Absolute where possible, so it can be pasted straight into a device.
        try:
            return f"{get_url(self._hass)}{path}"
        except NoURLAvailableError:
            return path

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "path": self.coordinator.voice_url(self._target),
            "identifier": self._target,
            "audio_format": "PCM16, 16 kHz, mono — POST the raw stream",
        }
