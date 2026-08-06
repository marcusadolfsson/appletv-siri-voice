# Third-party software

The **repository** only declares dependencies. The **container image** bundles
them, so the notices below travel with the image; `bridge/Dockerfile` copies
every dependency's licence file into `/app/licenses` inside it.

```
docker run --rm --entrypoint sh ghcr.io/marcusadolfsson/appletv-siri-voice:latest \
  -c 'ls /app/licenses'
```

Nothing here is copyleft — no GPL, LGPL or AGPL anywhere in the tree.

## Direct dependencies

| Component | Licence | Role |
|---|---|---|
| [HAP-NodeJS](https://github.com/homebridge/HAP-NodeJS) | Apache-2.0 | HomeKit Accessory Protocol, including the Data Stream transport that carries Siri audio |
| [opusscript](https://github.com/abalabahaha/opusscript) | MIT | Opus encoder (an Emscripten build of libopus, BSD-3-Clause) |

## Transitive dependencies

At the time of writing, 35 packages: 27 MIT, 3 Apache-2.0, and one each of
BSD-3-Clause, 0BSD, BlueOak-1.0.0 and Unlicense. Regenerate the current list
with:

```
cd bridge && npm ls --all --json | npx license-checker --summary
```

## Protocol

The HomeKit Accessory Protocol is specified by Apple. This project implements
against the publicly published **non-commercial** specification, which is *not*
redistributed here — obtain it from Apple directly. Nothing in this repository
is Apple-certified, and it is not an MFi product.

## Trademarks

Neither the Apache License nor any dependency licence grants trademark rights.
"Apple TV", "Siri", "HomeKit" and "tvOS" are trademarks of Apple Inc., used here
solely to describe what this software interoperates with.
