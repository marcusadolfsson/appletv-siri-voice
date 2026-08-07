ARG BUILD_FROM
FROM ${BUILD_FROM}

# hap-nodejs and opusscript are pure JS -- opusscript is a WASM/JS Opus
# implementation rather than a native binding -- so there is nothing to compile
# and every architecture uses the same install. That is the only reason
# multi-arch here is a base-image swap instead of a cross-build.
RUN apk add --no-cache nodejs npm

WORKDIR /app
COPY bridge/package.json ./
RUN npm install --omit=dev && npm cache clean --force

# The image bundles node_modules, so Apache-2.0 §4 and the MIT/BSD notice
# clauses apply to what is DISTRIBUTED, not merely to this repo's own source.
# Collect every dependency's licence so the notices travel with the image.
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
COPY addon/run.sh /run.sh
RUN chmod a+x /run.sh

# Pairing state on the add-on's persistent volume. Losing it drops the Home app
# pairing and every paired Apple TV.
ENV HAP_STORAGE=/data/persist

CMD ["/run.sh"]
