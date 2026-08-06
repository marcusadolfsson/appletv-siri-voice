"""Shared polling of the bridge.

One poll feeds every entity. Without this the select, the sensor and the binary
sensor would each hit the bridge on their own schedule for the same JSON.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bridge import Bridge, BridgeError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class BridgeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the bridge's /state."""

    def __init__(self, hass: HomeAssistant, bridge: Bridge) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Fast enough that the setup page feels live while you are reading
            # identifiers off it, slow enough to be invisible.
            update_interval=timedelta(seconds=30),
        )
        self.bridge = bridge

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.bridge.state()
        except BridgeError as err:
            raise UpdateFailed(str(err)) from err

    # --- helpers the entities share -------------------------------------

    @property
    def targets(self) -> dict[str, dict[str, Any]]:
        return (self.data or {}).get("targets") or {}

    @property
    def active_identifier(self) -> int | None:
        return (self.data or {}).get("activeIdentifier")

    def clean_name(self, identifier: Any) -> str:
        """The Apple TV's real name, recovered where possible.

        hap-nodejs returns target names concatenated (a TLV parsing quirk
        upstream): with two Apple TVs called "Living Room" and "Bedroom", one
        arrives as "Living RoomBedroom" and the other as "BedroomLiving Room".

        Those two strings are rotations of each other, so with exactly two
        targets the split point can be found and the real names recovered. With
        any other number the encoding is ambiguous, so fall back to the
        identifier — which is at least unambiguous, and the device can be
        renamed in Home Assistant like any other.
        """
        raw = (self.targets.get(str(identifier)) or {}).get("name") or ""
        names = [(i, (info.get("name") or "")) for i, info in self.targets.items()]

        if len(names) == 2 and all(n for _, n in names):
            (i_a, a), (i_b, b) = names
            if len(a) == len(b):
                for k in range(1, len(a)):
                    if a[k:] + a[:k] == b:
                        first, second = a[:k], a[k:]
                        # `first` belongs to whichever target `a` came from.
                        return (first if str(identifier) == str(i_a) else second).strip()

        return raw.strip() or f"Apple TV {identifier}"

    def device_info(self, identifier: Any) -> dict[str, Any]:
        """Group this Apple TV's entities under one device."""
        return {
            "identifiers": {(DOMAIN, str(identifier))},
            "name": self.clean_name(identifier),
            "manufacturer": "Apple",
            "model": "Apple TV (HomeKit Target Control)",
        }

    def slug(self, identifier: Any) -> str:
        """URL-safe form of the Apple TV's name."""
        return self.clean_name(identifier).lower().replace(" ", "_").replace("-", "_")

    def voice_url(self, identifier: Any) -> str:
        """Where a microphone in that room should POST its audio."""
        return f"/api/{DOMAIN}/audio/{self.slug(identifier)}"

    def bridge_device_info(self) -> dict[str, Any]:
        """The bridge itself, so its entities are not left ungrouped."""
        return {
            "identifiers": {(DOMAIN, "bridge")},
            "name": "Apple TV Siri bridge",
            "manufacturer": "appletv-siri-voice",
            "model": "HomeKit Target Control bridge",
        }

    def label_for(self, identifier: Any) -> str:
        """Human label for a target, with the identifier kept visible.

        tvOS names can repeat across homes, and the identifier is what actually
        addresses the device — and what goes in `target:` — so it stays on show.
        """
        info = self.targets.get(str(identifier)) or {}
        return f"{info.get('name') or 'Apple TV'} ({identifier})"
