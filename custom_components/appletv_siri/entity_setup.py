"""Add per-Apple-TV entities once the bridge has told us which exist.

Platforms set up when Home Assistant starts, which may be before the bridge is
answering — restart both together and the coordinator's first poll returns
nothing, so a one-shot snapshot creates zero entities and they stay missing
until the next Home Assistant restart. This adds whatever is known now, then
keeps watching and adds any Apple TV that turns up later.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BridgeCoordinator

_LOGGER = logging.getLogger(__name__)


def add_per_target_entities(
    coordinator: BridgeCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[int], Iterable[Entity]],
) -> None:
    """Create `factory(identifier)` entities for every Apple TV, now and later."""
    seen: set[int] = set()

    def _sync() -> None:
        new: list[Entity] = []
        for ident in coordinator.targets:
            identifier = int(ident)
            if identifier in seen:
                continue
            seen.add(identifier)
            new.extend(factory(identifier))
        if new:
            _LOGGER.debug("Adding %d entities for Apple TVs %s", len(new), sorted(seen))
            async_add_entities(new)

    _sync()
    coordinator.async_add_listener(_sync)
