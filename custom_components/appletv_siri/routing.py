"""The one routing rule: does this utterance belong to Siri?

Two things receive audio — the HTTP view, and the speech-to-text provider that
Assist satellites use — and both ask this module the same question, so there
is exactly one rule and one place it is read. It is a state-machine lookup
taken *before* the first audio chunk is consumed: Home Assistant already holds
the state in memory, so the decision costs nothing and never delays the Siri
path. That is why the rule is about device state rather than what was said —
deciding from the words means holding the audio until the person stops
talking, which is the latency this integration exists to avoid.

The rule is set from the integration's **Configure** dialog. A `siri_when:`
block in YAML is still honoured for anyone who has one, and is folded into the
same shape here so nothing downstream has to know where it came from.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENTITY,
    CONF_SIRI_WHEN,
    CONF_SIRI_WHEN_ENTITY,
    CONF_SIRI_WHEN_STATES,
    CONF_STATES,
    DEFAULT_SIRI_WHEN_STATES,
)


def parse_states(raw: str | list[str] | None) -> list[str]:
    """Accept ``"on, playing"`` from the form or ``["on", "playing"]`` from YAML."""
    if raw is None or raw == "":
        raw = DEFAULT_SIRI_WHEN_STATES
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(s).strip().lower() for s in raw if str(s).strip()]


def rule_from(conf: dict[str, Any]) -> dict[str, Any] | None:
    """The routing rule as ``{entity, states}``, or None for "always Siri".

    The UI keys win over a YAML block, because the UI is where the rule is
    edited now; YAML is kept working so an upgrade changes nothing.
    """
    entity = conf.get(CONF_SIRI_WHEN_ENTITY)
    if entity:
        return {
            CONF_ENTITY: entity,
            CONF_STATES: parse_states(conf.get(CONF_SIRI_WHEN_STATES)),
        }

    yaml_rule = conf.get(CONF_SIRI_WHEN)
    if yaml_rule and yaml_rule.get(CONF_ENTITY):
        return {
            CONF_ENTITY: yaml_rule[CONF_ENTITY],
            CONF_STATES: parse_states(yaml_rule.get(CONF_STATES)),
        }
    return None


def route_is_siri(hass: HomeAssistant, conf: dict[str, Any]) -> bool:
    """True if the next utterance should go to Siri.

    With no rule everything goes to Siri — that is the whole point of the
    integration, and routing elsewhere is the opt-in extra. A rule naming an
    entity that does not exist routes *away* from Siri rather than silently
    sending everything to the television.
    """
    rule = rule_from(conf)
    if rule is None:
        return True
    state = hass.states.get(rule[CONF_ENTITY])
    if state is None:
        return False
    return state.state.lower() in rule[CONF_STATES]
