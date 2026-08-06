# Apple TV Siri Voice for Home Assistant

**Send voice to Siri on your Apple TV — and remote buttons — from Home Assistant.**

Home Assistant can already run a local assistant. What it can't do is talk to
*Siri*, and Siri is the only thing that knows how to skip to the next episode,
launch an app, or answer "who's in this?" about the show currently on screen.

This project makes Home Assistant appear to your Apple TV as a **HomeKit remote**
— the same accessory profile Crestron's TSR-310 uses — so it can deliver button
presses and stream voice into Siri.

No MFi licence, no special hardware, no jailbreak. It pairs from the Home app
with an ordinary 8-digit setup code.

<!-- Drop a screenshot/photo at docs/hero.png and uncomment:
![Apple TV Siri Voice](docs/hero.png)
-->

```
  microphone           Home Assistant            bridge              Apple TV
  (anything) ──POST──▶ /api/appletv_siri/audio ─▶ HomeKit ──────────▶ Siri
                                                  Target Control
  or just text ──────▶ appletv_siri.say ─────────▶ (spoken for you)
```

## Why this exists

Siri knows things a house assistant cannot: what is playing, who is in it, where
you are in it. Until now there was no way to reach it from Home Assistant at
all — you could automate the whole house and still not ask the TV to skip the
intro.

By default **every utterance goes to Siri**. If you already run Assist or a
local LLM, you can route some utterances there instead — see
[Sharing a microphone with Assist](#sharing-a-microphone-with-assist), which is
a secondary use case rather than the point.

I couldn't find another project doing this. The HomeKit "Target Control" profile
is documented in Apple's public non-commercial HAP specification (chapter 12),
but the reference implementations are all MFi hardware, and the assumption that
it requires MFi turns out to be **wrong** — §12.3 gates only Siri on the
accessory declaring itself a *hardware entity*, which is a flag it sets about
itself, not something Apple verifies.

## What you get

- **Voice to Siri on a chosen Apple TV.** Opus, 16 kHz — exactly what tvOS
  negotiates. Streamed as it arrives, so Siri hears the utterance while the
  person is still speaking.
- **Remote buttons over HomeKit** (`appletv_siri.press`) — menu, arrows, play/pause,
  volume, power. Independent of pyatv, so it keeps working when the Apple TV
  integration's connection is asleep or wedged.
- **Written commands** (`appletv_siri.say`) — Home Assistant speaks the text for
  you, so an automation can tell Siri something without a microphone.
- **Multiple Apple TVs on one bridge**, individually addressable, with a
  `select` entity for choosing the target from the UI.
- **Optional routing** to Assist if you already run a local assistant.

## Requirements

- An Apple TV on tvOS 12 or later, on the same LAN
- Home Assistant with `configuration.yaml` access
- Docker for the bridge (**Core, Container, or Supervised** — the bridge is a
  container, so HA OS users run it on any Docker host on the same network)
- **Host networking.** HomeKit needs mDNS; bridge networking will not work.

## Install

### 1. Run the bridge

```yaml
# docker-compose.yml
services:
  appletv-siri-voice:
    container_name: appletv-siri-voice
    image: ghcr.io/marcusadolfsson/appletv-siri-voice:latest
    network_mode: host          # REQUIRED — HomeKit needs mDNS
    restart: unless-stopped
    environment:
      # Only needed if the host has more than one interface and the wrong one
      # gets advertised (a Tailscale/CGNAT address is the usual culprit).
      # Use the interface NAME, not an address.
      - HAP_BIND=eth0
      # If Home Assistant is NOT on this host, expose the control API to it —
      # and put it behind a firewall, see "Security" below.
      # - CTRL_BIND=0.0.0.0
    volumes:
      - ./appletv-siri-voice-data:/data/persist    # pairing state — must persist
```

```
docker compose up -d appletv-siri-voice
docker logs appletv-siri-voice      # prints the Home app setup code
```

### 2. Pair it

Open the **Home** app → **Add Accessory** → **More options…** → pick
*Voice Remote* → enter the setup code (default `031-45-154`; change it with
`HAP_PINCODE`).

Within a few seconds the log shows your Apple TVs registering as targets:

```
[remote] target-add 207551296
[hap] data stream present at boot: 207551296
```

Note the identifiers — you'll want one for `target:`.

```
curl http://127.0.0.1:8477/state     # lists targets and their names
```

### 3. Install the integration

Copy `custom_components/appletv_siri/` into your Home Assistant `config/`
directory (or add this repo to HACS as a custom repository), then:

```yaml
# configuration.yaml
appletv_siri:
  bridge_url: http://127.0.0.1:8477
  target: 207551296                        # which Apple TV (from /state)
  tts_engine: tts.google_translate_en_com  # only needed for `say`
```

That's it — every utterance goes to Siri. Routing some of them to Assist
instead is optional and covered
[further down](#sharing-a-microphone-with-assist).

Restart Home Assistant.

### 4. Send it audio

POST raw **PCM16, 16 kHz, mono** to `/api/appletv_siri/audio` with a normal
long-lived token. The end of the request body is the end of the utterance, so
stream it — don't buffer and send.

```
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/octet-stream" \
     --data-binary @utterance.pcm \
     http://homeassistant.local:8123/api/appletv_siri/audio
```

```json
{"route": "siri", "ok": true, "ms": 1873, "target": 207551296}
```

Add `?route=siri` or `?route=assist` to override the routing rule.

Any microphone works: an ESP32, a phone shortcut, a wall tablet, or a hardware
remote. The reference client is an Android remote whose voice key streams its
microphone straight into this endpoint.

## What to say to it

Siri on an Apple TV is good at things a house assistant has no idea about,
because it can see what's playing:

**Playback**
- "Skip the intro"
- "Skip back thirty seconds"
- "Pause" / "Play the next episode"
- "Turn on subtitles" / "Turn on closed captions"
- "Jump to the last scene"

**About what's on screen**
- "What did she say?" — jumps back and turns captions on briefly
- "Who stars in this?"
- "What is this rated?"

**Finding something**
- "Play Ted Lasso"
- "Open Netflix"
- "Show me comedies from the nineties"
- "Watch the news"
- "Play the last thing I was watching"

**General**
- "What's the weather tomorrow?"
- "Set a timer for ten minutes"
- "How long is this movie?"

Meanwhile the Assist route handles the house: *"turn off the kitchen lights"*,
*"set the thermostat to 70"*, *"is the garage door closed?"*

> **Worth knowing:** if you already expose entities to HomeKit, Siri can control
> them too — so "turn off the lights" works on *both* routes and will be handled
> by whichever one the utterance reaches. Decide which you want owning that and
> set `siri_when` accordingly. Sending house commands through Assist keeps them
> local and avoids the Apple round-trip.

## Sharing a microphone with Assist

**Skip this unless you already run Assist or a local LLM.** Out of the box there
is no `siri_when` rule and everything goes to Siri, which is what most people
want.

If you do run one, the useful split is **by what the person is looking at**, not
by what they said:

- **TV is on and in front of them → Siri.** It has the media context. "Skip
  the intro", "who plays her", "put on the next episode" are things only the
  device playing the video can answer.
- **Otherwise → Assist.** Your local LLM or intent matcher runs the house, with
  no cloud round-trip and no Apple account involved.

That's what `siri_when` expresses, and it's one state lookup — no latency, no
guessing at meaning.

### Optional: chain them

```yaml
appletv_siri:
  fallback_to_siri: true
```

Assist gets first refusal; anything it can't match is forwarded to Siri. Good
when you want "turn off the kitchen lights" handled locally but "what's the
weather in Tokyo" to still get an answer.

**The trade-off is real and you should know it before enabling this.** Falling
back means the same audio has to reach two consumers, so the utterance is
**buffered instead of streamed** — Siri only starts hearing it after the speaker
has finished and Assist has declined. That adds roughly the length of the
utterance to the response time. With activity-based routing, audio reaches Siri
while the person is still talking.

A note on LLM agents: an LLM will usually answer *something* rather than
report no match, so `fallback_to_siri` is most useful with Home Assistant's
built-in intent matcher, or with an agent configured to defer when unsure. If
your pipeline is a chatty LLM, prefer `siri_when`.

## Services

| Service | What it does |
|---|---|
| `appletv_siri.say` | Speak text to Siri — no microphone needed |
| `appletv_siri.press` | Send a button (`TV_HOME`, `ARROW_UP`, `PLAY_PAUSE`, …) |
| `appletv_siri.set_target` | Choose which Apple TV gets buttons and voice |
| `appletv_siri.recover` | Force the Apple TV to reopen its voice data stream |

### Written commands

```yaml
action: appletv_siri.say
data:
  text: "Play the next episode"
```

Home Assistant synthesises the speech and streams it in as if it had been
spoken. Siri cannot tell the difference — it is just audio — so anything you
could say, an automation can say:

```yaml
# Wind the house down and put something on
- action: appletv_siri.say
  data:
    text: "Play Slow Horses on Apple TV"
```

Needs a working `tts_engine`. Home Assistant's *default* engine is the Cloud
one, which fails opaquely when the account is signed out, so pin one:

```yaml
appletv_siri:
  tts_engine: tts.google_translate_en_com
```

### Multiple Apple TVs

**One bridge covers them all.** tvOS pushes every Apple TV in the home to the
accessory as a separate target, so you do not run a bridge per device. Point
voice and buttons at one with `appletv_siri.set_target`, or from the
**`select.apple_tv_target`** entity the integration creates:

```yaml
- action: select.select_option
  target:
    entity_id: select.apple_tv_target
  data:
    option: "Bedroom (35040583)"
```

That entity also carries `siri_available`, `data_streams` and `recovering` as
attributes, so an automation can notice voice being unavailable rather than
discovering it when an utterance goes nowhere.

## The one quirk worth understanding

Siri audio doesn't ride the HomeKit connection. It rides a **HomeKit Data
Stream**, a separate TCP connection that the **Apple TV opens to the
accessory** — and tvOS only opens one when the remote's *capabilities* change.
Not when the accessory restarts. Not when it re-registers its targets.

So after the bridge restarts, an Apple TV can sit there holding a dead socket.
Buttons keep working perfectly while every utterance fails with *"target is not
connected via HDS"*, which is a confusing way to fail.

**The bridge handles this for you.** It publishes once as a buttons-only remote
and then again with Siri, which tvOS reads as a capability change and answers
with a fresh stream. It runs this automatically at startup if no stream appears
within ~25 s, and again if it later notices the stream has gone. Recovery takes
about a minute, during which buttons briefly drop out twice.

`appletv_siri.recover` triggers it manually. If recovery fails repeatedly,
restart the Apple TV — that always clears it.

(Clearing the stored target configurations does *not* help; the Apple TV
re-adds its targets and still opens nothing. Only the capability change works.)

## Security

The bridge's control API has **no authentication**. Anything that can reach it
can press buttons and talk to Siri. It binds to `127.0.0.1` by default for that
reason.

If Home Assistant runs on a different host and you set `CTRL_BIND=0.0.0.0`,
restrict it to HA's address with a firewall rule. Don't expose it to the
internet — and note that the `/api/appletv_siri/audio` endpoint *does* require a
Home Assistant token, so prefer sending audio through HA rather than reaching
the bridge directly.

## Configuration reference

### Bridge (environment)

| Variable | Default | Notes |
|---|---|---|
| `HAP_NAME` | `Voice Remote` | Name shown in the Home app |
| `HAP_PINCODE` | `031-45-154` | Setup code — change it |
| `HAP_USERNAME` | `1A:2B:3C:4D:5E:6F` | HAP identity; changing it needs re-pairing |
| `HAP_UUID_SEED` | `appletv-siri-voice.accessory` | **Do not change after pairing** (see below) |
| `HAP_PORT` | `47129` | HAP TCP port |
| `HAP_BIND` | *(auto)* | Interface **name** if the wrong one is advertised |
| `CTRL_PORT` / `CTRL_BIND` | `8477` / `127.0.0.1` | Control API |
| `HAP_STORAGE` | `/data/persist` | Pairing state — mount a volume |
| `HDS_BOOT_GRACE_MS` | `25000` | Wait before auto-recovering at boot |
| `HDS_PHASE1_MS` | `45000` | How long to sit as a buttons-only remote |
| `HDS_WATCHDOG_MS` | `300000` | Re-check interval |

> **`HAP_UUID_SEED` is load-bearing.** The accessory UUID determines every
> service's and characteristic's instance id. Change it after pairing and they
> all renumber while paired Apple TVs keep using their cached ids — buttons
> still work and Siri silently never opens a session. If you must change it,
> remove and re-add the accessory in the Home app.

### Integration

| Key | Default | Notes |
|---|---|---|
| `bridge_url` | `http://127.0.0.1:8477` | |
| `target` | *(bridge's active target)* | Apple TV identifier from `/state` |
| `siri_when.entity` / `.states` | *(absent)* | Route to Siri while entity is in one of these states. **Absent means everything goes to Siri** |
| `tts_engine` | *(HA default)* | Engine for `say`. Pin it — HA's default is the Cloud engine, which fails when signed out |
| `assist_pipeline` | *(HA default)* | **Pin this.** HA's default pipeline has no STT engine, and an unpinned pipeline silently returns nothing |
| `fallback_to_siri` | `false` | Assist first, Siri if it can't handle it (buffers) |
| `max_buffer_seconds` | `15` | Ceiling on a buffered utterance |

## Limitations

- **Siri, not Home Assistant, decides what an utterance means** on the Siri
  route. There's no transcript back — HomeKit doesn't return one.
- **The Apple TV must be awake** to respond to voice.
- Target *names* come back garbled (a TLV parsing quirk in hap-nodejs); the
  identifiers are correct, which is what matters.
- One utterance at a time per Apple TV.
- Not affiliated with or endorsed by Apple. "Siri", "Apple TV" and "HomeKit" are
  trademarks of Apple Inc.

## How it works

| Piece | Role |
|---|---|
| `bridge/index.js` | HomeKit accessory (category 32, "Remotes"), Opus encoding, data-stream recovery, control API |
| `custom_components/appletv_siri/__init__.py` | Audio endpoint, routing, Assist pipeline, services |
| `custom_components/appletv_siri/bridge.py` | Control-API client — the only file that knows the transport is Node |

The bridge is Node because [HAP-NodeJS](https://github.com/homebridge/HAP-NodeJS)
is the only open implementation of HomeKit Data Stream; HAP-python has neither
that nor Target Control. `bridge.py` is deliberately thin so a future Python
port would not disturb the integration.

## Licence

**Apache-2.0** — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Chosen to match
Home Assistant core and HAP-NodeJS, and for its explicit patent grant.

Dependencies are all permissive (no GPL/LGPL/AGPL anywhere in the tree); the
container image carries their licence texts in `/app/licenses`. See
[THIRD_PARTY.md](THIRD_PARTY.md).

Not affiliated with, endorsed by, or sponsored by Apple Inc. "Siri", "Apple TV",
"HomeKit" and "tvOS" are trademarks of Apple Inc., used only to describe
interoperability.
