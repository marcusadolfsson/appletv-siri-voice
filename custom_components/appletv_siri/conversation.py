"""A conversation agent that stays quiet while Siri answers.

This entity exists for one reason. An Assist pipeline always runs all three
stages — speech-to-text, then a conversation agent, then text-to-speech — and
when the speech-to-text stage was ``stt.py`` streaming the audio to Siri, the
"transcript" it hands on is a sentinel that means nothing. Give that to the
normal Home Assistant agent and it says "Sorry, I didn't understand" out loud,
on the satellite, at the same moment Siri is answering on the television.

So a pipeline that uses the Siri speech-to-text entity must use this agent as
well, and it answers the sentinel with silence. That is the whole job.

When the routing rule sent the utterance to a real recogniser instead, the
transcript is a genuine sentence that deserves a genuine answer, so it is
passed on to whichever agent is configured as the fallback. With no fallback
configured, silence is still the right answer — better than a second agent
guessing.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FALLBACK_AGENT, DOMAIN, SENTINEL_TRANSCRIPT
from .coordinator import BridgeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN]
    async_add_entities([SiriSilentAgent(hass, data["coordinator"], data["conf"])])


class SiriSilentAgent(conversation.ConversationEntity):
    """Silence for Siri's utterances; the fallback agent for anything else.

    Bridge-wide rather than per Apple TV: it never needs to know which
    television answered, only whether the transcript is the sentinel.
    """

    _attr_name = "Siri (silent)"
    _attr_icon = "mdi:volume-off"
    _attr_unique_id = f"{DOMAIN}_silent_agent"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, hass: HomeAssistant, coordinator: BridgeCoordinator, conf: dict[str, Any]
    ) -> None:
        self.hass = hass
        self._conf = conf
        self._attr_device_info = coordinator.bridge_device_info()

    @property
    def supported_languages(self) -> list[str] | str:
        return MATCH_ALL

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        text = (user_input.text or "").strip()
        agent_id = self._conf.get(CONF_FALLBACK_AGENT)

        if agent_id and agent_id == self.entity_id:
            # Delegating to ourselves would recurse forever.
            _LOGGER.error(
                "The fallback conversation agent is this entity (%s); choose a "
                "real agent", agent_id
            )
            agent_id = None

        if text and text != SENTINEL_TRANSCRIPT and agent_id:
            _LOGGER.debug("Not Siri's; passing %r to %s", text, agent_id)
            return await conversation.async_converse(
                self.hass,
                text=user_input.text,
                conversation_id=user_input.conversation_id,
                context=user_input.context,
                language=user_input.language,
                agent_id=agent_id,
                device_id=getattr(user_input, "device_id", None),
            )

        # Siri has it. Say nothing.
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech("")
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id
        )
