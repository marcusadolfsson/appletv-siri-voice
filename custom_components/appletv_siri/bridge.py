"""Client for the appletv-siri-voice bridge (the Node HomeKit accessory).

Kept behind this thin class so the transport is swappable. HAP-python
implements neither Target Control nor HomeKit Data Stream, and the Home
Assistant container has no Node runtime, so the HAP side runs as a small
sidecar container. If HDS is ever ported to Python, only this file changes.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class BridgeError(Exception):
    """Bridge unreachable, or it refused the request."""


class BridgeUnavailable(BridgeError):
    """The Apple TV has no HomeKit data stream; the bridge is recovering."""


class Bridge:
    """Talks to the bridge over its control API."""

    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self._url = url.rstrip("/")

    async def state(self) -> dict[str, Any]:
        """Pairing state: known Apple TVs, which is active, data-stream health."""
        return await self._request("get", "/state")

    async def set_target(self, target: int) -> dict[str, Any]:
        return await self._request("post", f"/active/{int(target)}")

    async def press(self, button: str) -> dict[str, Any]:
        return await self._request("post", f"/press/{button.upper()}")

    async def recover(self) -> dict[str, Any]:
        """Kick the capability-toggle that makes tvOS reopen its data stream."""
        return await self._request("post", "/recover")

    async def speak(
        self, audio: AsyncIterable[bytes] | bytes, target: int | None = None
    ) -> dict[str, Any]:
        """Send an utterance to Siri on the Apple TV.

        The body IS the utterance: the bridge holds the SIRI button down for the
        whole request and releases it when the body ends, which is what makes
        tvOS process it. Passing a stream through un-buffered means audio
        reaches Siri while the user is still speaking.
        """
        path = "/siri/stream" + (f"?target={int(target)}" if target else "")
        return await self._request("post", path, data=audio)

    async def _request(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        try:
            async with self._session.request(method, f"{self._url}{path}", **kw) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 503:
                    raise BridgeUnavailable(str(body.get("error", body)))
                if resp.status >= 400:
                    raise BridgeError(f"{path} -> {resp.status}: {body}")
                return body
        except aiohttp.ClientError as err:
            raise BridgeError(f"bridge unreachable at {self._url}: {err}") from err
