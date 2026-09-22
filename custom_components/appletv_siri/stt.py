"""A speech-to-text provider that does not transcribe — it streams to Siri.

This is how an **Assist satellite** reaches Siri. A Voice PE, an ESPHome or
Wyoming satellite, or a hardware remote with a mic button cannot POST to a
URL; the only thing it speaks is an Assist pipeline. So the pipeline's
speech-to-text stage is where this integration has to sit.

Home Assistant hands an STT provider a live ``AsyncIterable[bytes]`` while the
person is still talking — a stream, not a finished recording. That is the
whole trick: rather than recognising the audio, this hands those chunks to the
bridge as they arrive. The bridge holds the SIRI button down for as long as the
request body keeps coming and releases it when the body ends, so the utterance
reaches Siri live instead of being reconstructed and replayed afterwards.

Nothing is recognised here, so the "transcript" is a fixed sentinel. See
``conversation.py`` for why that does not produce "sorry, I didn't understand"
spoken over Siri's reply every time.

One provider **per Apple TV**, for the same reason the buttons are: choosing
the Apple TV is choosing which "Siri" entity the pipeline uses, so there is no
hidden "current target" deciding where an utterance ends up.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any

from homeassistant.components import stt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import Bridge, BridgeError, BridgeUnavailable
from .const import CONF_FALLBACK_STT, DOMAIN, SENTINEL_TRANSCRIPT
from .coordinator import BridgeCoordinator
from .entity_setup import add_per_target_entities
from .routing import route_is_siri

_LOGGER = logging.getLogger(__name__)

# Long enough for any plausible utterance, short enough that a wedged bridge
# does not pin the pipeline open until aiohttp's five-minute default.
_UTTERANCE_TIMEOUT = 60

# Siri's language is whatever the Apple TV is set to. This list only has to
# satisfy the pipeline's own language matching, which happens before any audio
# is sent and never reaches Siri.
_LANGUAGES = [
    "en-US", "en-GB", "en-AU", "en-CA", "en-IE", "en-IN", "en-NZ", "en-ZA",
    "de-DE", "es-ES", "es-MX", "fr-FR", "fr-CA", "it-IT", "ja-JP", "ko-KR",
    "nl-NL", "nb-NO", "pt-BR", "sv-SE", "zh-CN", "zh-TW",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN]
    coordinator: BridgeCoordinator = data["coordinator"]
    bridge: Bridge = data["bridge"]
    conf: dict[str, Any] = data["conf"]
    add_per_target_entities(
        coordinator, async_add_entities,
        lambda t: [SiriSpeechToText(hass, coordinator, bridge, conf, t)],
    )


class SiriSpeechToText(stt.SpeechToTextEntity):
    """Pipeline audio goes to Siri on this Apple TV instead of being recognised."""

    _attr_has_entity_name = True
    _attr_name = "Siri"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: BridgeCoordinator,
        bridge: Bridge,
        conf: dict[str, Any],
        target: int,
    ) -> None:
        self.hass = hass
        self._bridge = bridge
        self._conf = conf
        self._target = target
        self._attr_unique_id = f"{DOMAIN}_{target}_stt"
        self._attr_device_info = coordinator.device_info(target)

    @property
    def supported_languages(self) -> list[str]:
        return _LANGUAGES

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        return [stt.AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Send this utterance to Siri, or hand it to a real recogniser."""
        # Decided before a single chunk is read, so the Siri path is not
        # slowed by the existence of routing. Same rule as the HTTP view.
        if not route_is_siri(self.hass, self._conf):
            return await self._delegate(metadata, stream)
        return await self._to_siri(stream)

    async def _delegate(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Not for Siri: let a real speech-to-text engine have the stream."""
        engine_id = self._conf.get(CONF_FALLBACK_STT)
        if not engine_id:
            _LOGGER.warning(
                "The routing rule sent this utterance away from Siri, but no "
                "fallback speech-to-text engine is configured; discarding it"
            )
            return stt.SpeechResult("", stt.SpeechResultState.ERROR)

        engine = stt.async_get_speech_to_text_entity(self.hass, engine_id)
        if engine is None or engine is self or engine.entity_id == self.entity_id:
            # Missing, or pointed back at one of our own entities — which would
            # recurse until the stream or the stack gave out.
            _LOGGER.error(
                "Fallback speech-to-text engine %s is missing or is this "
                "integration's own; choose a real recogniser", engine_id
            )
            return stt.SpeechResult("", stt.SpeechResultState.ERROR)

        _LOGGER.debug("Not for Siri; handing the stream to %s", engine_id)
        return await engine.async_process_audio_stream(metadata, stream)

    async def _to_siri(self, stream: AsyncIterable[bytes]) -> stt.SpeechResult:
        """Forward the live audio and return a sentinel transcript."""
        sent = 0

        async def _counted() -> AsyncIterable[bytes]:
            # Counting here rather than pre-reading keeps the stream un-buffered:
            # nothing waits for the end of the utterance before Siri hears the
            # start of it.
            nonlocal sent
            async for chunk in stream:
                if chunk:
                    sent += len(chunk)
                    yield chunk

        try:
            async with asyncio.timeout(_UTTERANCE_TIMEOUT):
                await self._bridge.speak(_counted(), self._target)
        except BridgeUnavailable as err:
            # The bridge is re-establishing the Apple TV's data stream, which is
            # expected for about a minute after it restarts.
            _LOGGER.warning("Siri unavailable on %s: %s", self._target, err)
            return stt.SpeechResult("", stt.SpeechResultState.ERROR)
        except BridgeError as err:
            _LOGGER.error("Bridge rejected the utterance: %s", err)
            return stt.SpeechResult("", stt.SpeechResultState.ERROR)
        except TimeoutError:
            _LOGGER.error("Timed out streaming to the bridge after %ss", _UTTERANCE_TIMEOUT)
            return stt.SpeechResult("", stt.SpeechResultState.ERROR)

        if not sent:
            # The button was tapped rather than held. Not an error worth
            # surfacing, but Siri got nothing.
            _LOGGER.debug("No audio arrived from the pipeline; nothing sent")
        else:
            _LOGGER.debug("Streamed %d bytes to Siri on %s", sent, self._target)

        return stt.SpeechResult(SENTINEL_TRANSCRIPT, stt.SpeechResultState.SUCCESS)
