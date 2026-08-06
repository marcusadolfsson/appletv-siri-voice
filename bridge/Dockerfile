# Build context is the REPOSITORY ROOT, not bridge/, so the licence files can be
# copied in:  docker build -f bridge/Dockerfile .
FROM node:22-bookworm-slim

WORKDIR /app
COPY bridge/package.json ./
RUN npm install --omit=dev && npm cache clean --force

# Apache-2.0 §4 and the MIT/BSD notice clauses apply to the IMAGE, which bundles
# node_modules — not to the repository, which only declares dependencies. Collect
# every dependency's licence so the notices travel with what is distributed.
# See THIRD_PARTY.md.
RUN mkdir -p /app/licenses && \
    for d in node_modules/*/ node_modules/@*/*/; do \
      [ -d "$d" ] || continue; \
      name=$(echo "$d" | sed 's|node_modules/||; s|/$||; s|/|__|g'); \
      for f in "$d"LICENSE "$d"LICENSE.md "$d"LICENSE.txt "$d"LICENCE "$d"COPYING; do \
        if [ -f "$f" ]; then cp "$f" "/app/licenses/$name.LICENSE"; break; fi; \
      done; \
    done; \
    echo "collected $(ls /app/licenses | wc -l) dependency licences"

COPY LICENSE NOTICE THIRD_PARTY.md ./
COPY bridge/index.js ./

# Pairing state. Mount a volume here — losing it drops the Home app pairing and
# every Apple TV target.
ENV HAP_STORAGE=/data/persist

# The control API is for the Home Assistant integration only. With host
# networking, loopback is reachable from HA while staying off the LAN. Do NOT
# bind 0.0.0.0 unless HA runs elsewhere: /press and /siri/stream would become an
# unauthenticated "control the TV and talk to Siri" endpoint for the whole LAN.
ENV CTRL_BIND=127.0.0.1

# HomeKit needs mDNS on the LAN, so the container must run with
# network_mode: host. Bridge networking will not work.
CMD ["node", "index.js"]
