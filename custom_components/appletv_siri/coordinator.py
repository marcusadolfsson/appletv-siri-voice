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

    def label_for(self, identifier: Any) -> str:
        """Human label for a target, with the identifier kept visible.

        tvOS names can repeat across homes, and the identifier is what actually
        addresses the device — and what goes in `target:` — so it stays on show.
        """
        info = self.targets.get(str(identifier)) or {}
        return f"{info.get('name') or 'Apple TV'} ({identifier})"
