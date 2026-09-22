"""Constants for the appletv_siri integration."""

DOMAIN = "appletv_siri"

CONF_BRIDGE_URL = "bridge_url"
CONF_TARGET = "target"
CONF_SIRI_WHEN = "siri_when"
CONF_ENTITY = "entity"
CONF_STATES = "states"
CONF_ASSIST_PIPELINE = "assist_pipeline"
CONF_TTS_ENGINE = "tts_engine"

# The routing rule as the UI stores it: a flat pair rather than YAML's nested
# `siri_when:` block, because a form has no nesting. routing.py folds either
# into the one rule everything reads.
CONF_SIRI_WHEN_ENTITY = "siri_when_entity"
CONF_SIRI_WHEN_STATES = "siri_when_states"
# Where an Assist satellite's utterance goes when the rule says "not Siri":
# a real speech-to-text engine, and a real agent to answer what it heard.
CONF_FALLBACK_STT = "fallback_stt"
CONF_FALLBACK_AGENT = "fallback_agent"

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8477"

# `idle` is the Apple TV awake on its home screen, which is where it is when
# someone asks it to open something -- leaving it out is the classic way to
# have "open YouTube" answered by the house instead of the television.
DEFAULT_SIRI_WHEN_STATES = "on, idle, playing, paused"

# What the Siri speech-to-text entity reports as its transcript. It never
# recognises anything; this only has to be something the silent agent can spot.
SENTINEL_TRANSCRIPT = "(sent to Siri)"

# What the bridge and tvOS both expect; nothing in the chain resamples.
SAMPLE_RATE = 16000
BYTES_PER_MS = 32

SERVICE_PRESS = "press"
SERVICE_RECOVER = "recover"
SERVICE_SAY = "say"

ATTR_BUTTON = "button"
ATTR_TARGET = "target"
ATTR_TEXT = "text"

BUTTONS = [
    "MENU", "PLAY_PAUSE", "TV_HOME", "SELECT",
    "ARROW_UP", "ARROW_RIGHT", "ARROW_DOWN", "ARROW_LEFT",
    "VOLUME_UP", "VOLUME_DOWN", "SIRI", "POWER", "GENERIC",
]

