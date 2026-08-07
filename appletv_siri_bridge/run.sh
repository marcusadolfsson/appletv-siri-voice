#!/usr/bin/with-contenv bashio
# Translate add-on options into the environment the bridge already reads, so the
# bridge itself stays identical to the docker-compose build. Only options that a
# user has a basis to set are surfaced; the HDS_* and SIRI_LOCK_WAIT_MS timing
# knobs exist because the Apple TV data stream misbehaves and stay compiled in.
set -e

export HAP_NAME="$(bashio::config 'name')"
export HAP_UUID_SEED="$(bashio::config 'uuid_seed')"
export HAP_PINCODE="$(bashio::config 'pincode')"

# Empty means "bind every interface", which is HAP-NodeJS's own default and the
# right answer on a single-homed host. The interface name is not predictable
# inside an add-on, so there is deliberately no default here.
if bashio::config.has_value 'bind_interface'; then
    export HAP_BIND="$(bashio::config 'bind_interface')"
    bashio::log.info "Binding HAP to interface: ${HAP_BIND}"
fi

# Loopback unless explicitly opened. See the warning in config.yaml -- this
# endpoint has no authentication.
if bashio::config.true 'expose_control_api'; then
    export CTRL_BIND="0.0.0.0"
    bashio::log.warning "Control API bound to 0.0.0.0 — /press and /siri/stream are UNAUTHENTICATED on your LAN."
else
    export CTRL_BIND="127.0.0.1"
fi

bashio::log.info "Starting Apple TV Siri Voice bridge as '${HAP_NAME}'"
exec node /app/index.js
