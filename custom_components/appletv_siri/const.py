"""Constants for the appletv_siri integration."""

DOMAIN = "appletv_siri"

CONF_BRIDGE_URL = "bridge_url"
CONF_TARGET = "target"
CONF_SIRI_WHEN = "siri_when"
CONF_ENTITY = "entity"
CONF_STATES = "states"
CONF_ASSIST_PIPELINE = "assist_pipeline"
CONF_TTS_ENGINE = "tts_engine"
CONF_SOURCES = "sources"

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8477"

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

