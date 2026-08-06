"""Apple TV Siri Voice — send voice and remote buttons to an Apple TV.

A microphone anywhere on your network POSTs raw audio to
``/api/appletv_siri/audio``. This integration decides what the audio *means*:

* **Siri on the Apple TV** — when the TV is what the person is looking at.
  Siri already knows how to scrub, skip, launch apps and answer general
  questions, and it acts on the thing on screen.
* **Assist** — otherwise. Your local pipeline (LLM or the built-in intent
  matcher) controls the house.

Optionally the two chain: let Assist try first, and forward anything it can't
handle to Siri. See ``fallback_to_siri`` in the README for the trade-off, which
is real — the fallback has to buffer the utterance instead of streaming it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import stt, tts
from homeassistant.components.assist_pipeline import async_pipeline_from_audio_stream
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .bridge import Bridge, BridgeError, BridgeUnavailable
from .const import (
    ATTR_BUTTON,
    ATTR_TARGET,
    ATTR_TEXT,
    BUTTONS,
    BYTES_PER_MS,
    CONF_ASSIST_PIPELINE,
    CONF_BRIDGE_URL,
    CONF_ENTITY,
    CONF_FALLBACK_TO_SIRI,
    CONF_MAX_BUFFER_SECONDS,
    CONF_SIRI_WHEN,
    CONF_SOURCES,
    CONF_STATES,
    CONF_TARGET,
    DEFAULT_BRIDGE_URL,
    DOMAIN,
    NO_MATCH_CODES,
    CONF_TTS_ENGINE,
    SERVICE_PRESS,
    SERVICE_RECOVER,
    SERVICE_SAY,
    SERVICE_SET_TARGET,
)

_LOGGER = logging.getLogger(__name__)

SIRI_WHEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY): cv.entity_id,
        vol.Required(CONF_STATES): vol.All(cv.ensure_list, [cv.string]),
    }
)

# A named microphone. `source` in the URL is an IDENTITY claim ("I am the
# bedroom remote"), not a routing decision — where "bedroom" points stays here,
# so replacing an Apple TV means editing this block rather than reconfiguring
# every remote in the house.
SOURCE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TARGET): vol.Coerce(int),
        vol.Optional(CONF_SIRI_WHEN): SIRI_WHEN_SCHEMA,
        vol.Optional(CONF_ASSIST_PIPELINE): cv.string,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_SOURCES, default={}): {cv.string: SOURCE_SCHEMA},
                vol.Optional(CONF_BRIDGE_URL, default=DEFAULT_BRIDGE_URL): cv.string,
                vol.Optional(CONF_TARGET): vol.Coerce(int),
                vol.Optional(CONF_SIRI_WHEN): SIRI_WHEN_SCHEMA,
                vol.Optional(CONF_ASSIST_PIPELINE): cv.string,
                vol.Optional(CONF_FALLBACK_TO_SIRI, default=False): cv.boolean,
                vol.Optional(CONF_MAX_BUFFER_SECONDS, default=15): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=60)
                ),
                vol.Optional(CONF_TTS_ENGINE): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from configuration.yaml."""
    conf = config.get(DOMAIN) or {}
    bridge = Bridge(
        async_get_clientsession(hass), conf.get(CONF_BRIDGE_URL, DEFAULT_BRIDGE_URL)
    )
    hass.data[DOMAIN] = {"bridge": bridge, "conf": conf}

    hass.http.register_view(SiriRemoteAudioView(hass, bridge, conf))

    async def _press(call: ServiceCall) -> None:
        if target := call.data.get(ATTR_TARGET):
            await bridge.set_target(target)
        await bridge.press(call.data[ATTR_BUTTON])

    async def _set_target(call: ServiceCall) -> None:
        await bridge.set_target(call.data[ATTR_TARGET])

    async def _recover(call: ServiceCall) -> None:
        await bridge.recover()

    async def _say(call: ServiceCall) -> None:
        if target := call.data.get(ATTR_TARGET):
            await bridge.set_target(target)
        pcm = await _text_to_pcm(hass, call.data[ATTR_TEXT], conf.get(CONF_TTS_ENGINE))
        await bridge.speak(pcm, call.data.get(ATTR_TARGET) or conf.get(CONF_TARGET))

    hass.services.async_register(
        DOMAIN, SERVICE_PRESS, _press,
        schema=vol.Schema({
            vol.Required(ATTR_BUTTON): vol.In(BUTTONS),
            vol.Optional(ATTR_TARGET): vol.Coerce(int),
        }),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_TARGET, _set_target,
        schema=vol.Schema({vol.Required(ATTR_TARGET): vol.Coerce(int)}),
    )
    hass.services.async_register(DOMAIN, SERVICE_RECOVER, _recover, schema=vol.Schema({}))
    hass.services.async_register(
        DOMAIN, SERVICE_SAY, _say,
        schema=vol.Schema({
            vol.Required(ATTR_TEXT): cv.string,
            vol.Optional(ATTR_TARGET): vol.Coerce(int),
        }),
    )

    # Entities, so the integration is usable from the UI rather than being
    # service-calls-only: a target selector, a box to talk to Siri, and the
    # handful of remote keys worth one tap.
    for platform in ("select", "text", "button"):
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))
    return True


async def _text_to_pcm(hass: HomeAssistant, text: str, engine: str | None) -> bytes:
    """Speak `text` with Home Assistant's TTS, as PCM16 16 kHz mono for Siri.

    Siri accepts synthesised speech perfectly well — it is just audio to it —
    which is what makes a written command possible at all.

    Whatever the engine produces (usually MP3, sometimes WAV at another rate) is
    transcoded with ffmpeg, which ships in the Home Assistant container.
    """
    media_id = tts.generate_media_source_id(
        hass, message=text, engine=engine, language=None, options=None, cache=False
    )
    try:
        _ext, data = await tts.async_get_media_source_audio(hass, media_id)
    except Exception as err:  # noqa: BLE001 — the cause is worth naming
        # Home Assistant's default engine is the cloud one, which fails opaquely
        # (a JWT decode error) when the account is signed out. Say so, rather
        # than surfacing a stack trace about token segments.
        raise HomeAssistantError(
            f"Text-to-speech failed using engine {engine or '<default>'}: {err}. "
            "Set tts_engine: to a working engine — the Home Assistant Cloud "
            "engine fails this way when the account is signed out."
        ) from err

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0", "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    pcm, err = await proc.communicate(data)
    if proc.returncode != 0 or not pcm:
        raise HomeAssistantError(
            f"Could not convert the speech to PCM: {err.decode(errors='replace')[:200]}"
        )
    _LOGGER.debug("say: %d bytes of TTS -> %d bytes PCM (%d ms)", len(data), len(pcm), len(pcm) // 32)
    return pcm


class SiriRemoteAudioView(HomeAssistantView):
    """Receives an utterance and routes it.

    ``POST /api/appletv_siri/audio`` with a raw PCM16 body (16 kHz, mono). The
    end of the request body is the end of the utterance.

    ``?route=siri|assist`` overrides the routing rule, which is useful for
    testing and for a client that already knows where it wants to go.
    """

    url = f"/api/{DOMAIN}/audio"
    name = f"api:{DOMAIN}:audio"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, bridge: Bridge, conf: dict[str, Any]) -> None:
        self._hass = hass
        self._bridge = bridge
        self._conf = conf

    def _settings_for(self, source: str | None) -> dict[str, Any]:
        """Config for this microphone: its own keys, falling back to the global ones."""
        if not source:
            return self._conf
        src = (self._conf.get(CONF_SOURCES) or {}).get(source)
        if src is None:
            _LOGGER.warning(
                "Unknown source %r; using the default target. Known sources: %s",
                source, sorted(self._conf.get(CONF_SOURCES) or {}) or "none configured",
            )
            return self._conf
        return {**self._conf, **{k: v for k, v in src.items() if v is not None}}

    def _route_is_siri(self, conf: dict[str, Any] | None = None) -> bool:
        """Where this utterance should go.

        With no `siri_when` rule everything goes to Siri — that is the whole
        point of the integration, and routing to Assist is the opt-in extra.
        """
        conf = conf or self._conf
        rule = conf.get(CONF_SIRI_WHEN)
        if not rule:
            return True
        state = self._hass.states.get(rule[CONF_ENTITY])
        return bool(state and state.state in rule[CONF_STATES])

    async def post(self, request: web.Request) -> web.Response:
        conf = self._settings_for(request.query.get("source"))
        route = request.query.get("route")
        to_siri = route == "siri" or (route is None and self._route_is_siri(conf))

        if to_siri:
            return await self._to_siri(request.content, conf)

        # Assist. With fallback enabled the audio must be buffered, because a
        # stream can only be consumed once and Siri may need the same bytes.
        if conf.get(CONF_FALLBACK_TO_SIRI):
            cap = conf.get(CONF_MAX_BUFFER_SECONDS, 15) * 1000 * BYTES_PER_MS
            audio = await self._read_capped(request, cap)
            result = await self._run_assist(_chunks(audio), conf)
            if result.get("handled"):
                return self.json({"route": "assist", **result["payload"]})
            _LOGGER.debug("Assist did not handle the utterance; forwarding to Siri")
            resp = await self._to_siri(audio, conf)
            # Report both so a client can show what actually happened.
            return resp

        return self.json({"route": "assist", **(await self._run_assist(
            _stream(request), conf
        ))["payload"]})

    async def _to_siri(self, audio: Any, conf: dict[str, Any]) -> web.Response:
        try:
            result = await self._bridge.speak(audio, conf.get(CONF_TARGET))
        except BridgeUnavailable as err:
            # The bridge is re-establishing the Apple TV's data stream. This is
            # expected for about a minute after the bridge restarts.
            _LOGGER.warning("Siri unavailable: %s", err)
            return self.json(
                {"route": "siri", "error": str(err), "retry_after": 60}, status_code=503
            )
        except BridgeError as err:
            _LOGGER.error("Siri route failed: %s", err)
            return self.json({"route": "siri", "error": str(err)}, status_code=502)
        return self.json({"route": "siri", **result})

    async def _read_capped(self, request: web.Request, cap: int) -> bytes:
        """Read the body with a hard ceiling, so a stuck client can't grow forever."""
        buf = bytearray()
        async for chunk in request.content.iter_chunked(4096):
            buf.extend(chunk)
            if len(buf) >= cap:
                _LOGGER.warning("Utterance hit the %d-byte buffer cap; truncating", cap)
                break
        return bytes(buf)

    async def _run_assist(
        self, audio: AsyncIterable[bytes], conf: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run the Assist pipeline; report whether it actually handled anything."""
        conf = conf or self._conf
        events: dict[str, Any] = {}

        def _on_event(event: Any) -> None:
            if event.data:
                events[str(event.type)] = event.data

        try:
            await async_pipeline_from_audio_stream(
                self._hass,
                context=Context(),
                event_callback=_on_event,
                stt_metadata=stt.SpeechMetadata(
                    language=self._hass.config.language,
                    format=stt.AudioFormats.WAV,
                    codec=stt.AudioCodecs.PCM,
                    bit_rate=stt.AudioBitRates.BITRATE_16,
                    sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                    channel=stt.AudioChannels.CHANNEL_MONO,
                ),
                stt_stream=audio,
                pipeline_id=conf.get(CONF_ASSIST_PIPELINE),
            )
        except Exception as err:  # noqa: BLE001 — surface anything to the client
            _LOGGER.exception("Assist route failed")
            return {"handled": False, "payload": {"error": str(err)}}

        stt_end = events.get("stt-end", {})
        intent_end = events.get("intent-end", {})
        tts_end = events.get("tts-end", {})
        response = intent_end.get("intent_output", {}).get("response", {})

        if not stt_end:
            # The pipeline never reached speech-to-text. Overwhelmingly this
            # means the selected pipeline has no STT engine — Home Assistant's
            # default pipeline ships with stt=None, and without this warning the
            # route just returns nulls and looks like a dead microphone.
            _LOGGER.warning(
                "Assist produced no transcript (pipeline=%s). If that pipeline has no "
                "speech-to-text engine, set assist_pipeline: to one that does.",
                conf.get(CONF_ASSIST_PIPELINE) or "<default>",
            )

        code = response.get("data", {}).get("code")
        handled = bool(stt_end) and response.get("response_type") != "error" and code not in NO_MATCH_CODES

        return {
            "handled": handled,
            "payload": {
                "transcript": stt_end.get("stt_output", {}).get("text"),
                "response": response.get("speech", {}).get("plain", {}).get("speech"),
                "tts_url": tts_end.get("tts_output", {}).get("url"),
            },
        }


async def _stream(request: web.Request) -> AsyncIterable[bytes]:
    async for chunk in request.content.iter_chunked(1024):
        yield chunk


async def _chunks(data: bytes, size: int = 1024) -> AsyncIterable[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]
