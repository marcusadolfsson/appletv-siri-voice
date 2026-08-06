# Apple TV Siri Voice for Home Assistant

**Send voice to Siri on your Apple TV — and remote buttons — from Home Assistant.**

Speak into any microphone on your network and the words land on your Apple TV
as if you had held the button on the Siri Remote:

> *"Skip the intro"* · *"What did she say?"* · *"Play the next episode"* ·
> *"Open Netflix"* · *"Turn on subtitles"*

Or send text instead, and Home Assistant speaks it for you — so an automation
can talk to the TV with no microphone in the loop at all:

```yaml
- action: appletv_siri.say
  data:
    text: "Play Slow Horses"

# Any Apple TV in the house, by name in the UI or by id in an automation
- action: appletv_siri.say
  data:
    target: 35040583          # the bedroom Apple TV
    text: "Pause"
```

Both paths reach the same place. This project makes Home Assistant appear to
your Apple TV as a **HomeKit remote** — the same accessory profile Crestron's
TSR-310 uses — so it can stream voice into Siri and deliver button presses.

No MFi licence, no special hardware, no jailbreak. It pairs from the Home app
with an ordinary 8-digit setup code.

<!-- Drop a screenshot/photo at docs/hero.png and uncomment:
![Apple TV Siri Voice](docs/hero.png)
-->

```
  living room mic ──▶ POST /api/appletv_siri/audio/living_room ─┐
  bedroom mic ──────▶ POST .../audio/bedroom ───────────────────┤
  automation ───────▶ appletv_siri.say  (spoken for you) ───────┤
                                                                │
                                              Home Assistant ───┘
                                                    │
                                                    ▼
                                            bridge (HomeKit
                                            Target Control)
                                                    │
                                    ┌───────────────┴───────────────┐
                                    ▼                               ▼
                            Living Room Apple TV            Bedroom Apple TV
                                  → Siri                        → Siri
```

One bridge, one pairing in the Home app. Each Apple TV gets its own URL, so a
microphone only has to know which room it is in.

## Why this exists

Siri knows things a house assistant cannot: what is playing, who is in it, and
where you are in it. Until now there was no way to reach it from Home Assistant
at all — you could automate an entire house and still not ask the TV to skip the
intro.

By default **every utterance goes to Siri**. If you already run Assist or a
local LLM, some utterances can go there instead — see
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
- **Multiple Apple TVs on one bridge** — each becomes a device with its own
  buttons and its own say-to-Siri box, so nothing has to be "selected" first.
- **Optional routing** to Assist if you already run a local assistant.

## Requirements

- An Apple TV on tvOS 12 or later, on the same LAN
- Home Assistant (setup is a UI dialog; YAML only if you want per-microphone routing)
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

Within a few seconds the log shows your Apple TVs registering themselves:

```
[remote] target-add 207551296
[hap] data stream present at boot: 207551296
```

You do not need to note anything down — the integration surfaces all of it in
the next step.

### 3. Install the integration

Copy `custom_components/appletv_siri/` into your Home Assistant `config/`
directory (or add this repo to HACS as a custom repository) and restart, then
**Settings → Devices & Services → Add Integration → Apple TV Siri Voice**.

It asks for the bridge URL, then offers your Apple TVs by name — read from the
bridge, so there are no identifiers to look up — and optionally a speech engine
for written commands. Each Apple TV becomes a **device** with its own buttons
and its own say-to-Siri box.

Everything is editable afterwards from the integration's **Configure** button.

#### Or configure it in YAML

Routing (`sources`, `siri_when`, `assist_pipeline`) is YAML-only, because it is
nested and awkward in a form. A YAML block is adopted into a config entry
automatically the first time, so both can be used together — YAML routing on top
of the connection settings from the UI:

```yaml
appletv_siri:
  tts_engine: tts.google_translate_en_com
  sources:
    living_room: { target: 207551296 }
    bedroom:     { target: 35040583 }
```

> `google_translate` is one of four integrations Home Assistant sets up
> automatically during onboarding, so this entity usually exists already — but
> the id varies by language and domain (`tts.google_translate_de_de` and so on).
> Check Settings → Devices & Services → Entities and filter for `tts.`. Any
> engine works; pin one explicitly, because Home Assistant's *default* is the
> Cloud engine and it fails opaquely when the account is signed out. That is genuinely all of it: with one Apple TV, voice
goes to it and there is nothing else to configure.

**With more than one Apple TV**, open **`sensor.apple_tv_bridge`** in
Developer Tools → States. Its attributes list every Apple TV the bridge can see:

```yaml
apple_tvs:
  "207551296":
    name: Living Room
    identifier: 207551296
    voice_ready: true
  "35040583":
    name: Bedroom
    identifier: 35040583
    voice_ready: true
```

Use those identifiers to pin a default, and to name each microphone:

```yaml
appletv_siri:
  tts_engine: tts.google_translate_en_com
  target: 207551296          # default Apple TV
  sources:
    living_room: { target: 207551296 }
    bedroom:     { target: 35040583 }
```

You can also switch target at any time from `select.apple_tv_target` rather than
editing YAML.

### 4. Send it audio

**Every Apple TV has its own URL.** Point a microphone at the one in its room
and it needs to know nothing else:

```
/api/appletv_siri/audio/living_room     ← by name
/api/appletv_siri/audio/207551296       ← or by identifier
/api/appletv_siri/audio                 ← or the default Apple TV
```

The exact URLs are listed on `sensor.apple_tv_bridge`, so there is nothing to
construct.

POST raw **PCM16, 16 kHz, mono** with a normal long-lived token. The end of the
request body is the end of the utterance, so stream it — don't buffer and send.

```
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/octet-stream" \
     --data-binary @utterance.pcm \
     http://homeassistant.local:8123/api/appletv_siri/audio/living_room
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

### Entities

You get one set per Apple TV, named after it, so nothing has to be "selected"
before it can be used:

| Entity | What it does |
|---|---|
| `text.say_to_siri_<apple tv>` | Type a command, press enter, Siri on **that** Apple TV hears it. The box clears afterwards, because it is an action rather than a setting |
| `button.<apple tv>_home` / `_menu` / `_select` / `_play_pause` | The keys worth one tap; everything else is `appletv_siri.press` |
| `binary_sensor.<apple tv>_siri_voice_available` | Whether voice works for that Apple TV right now |
| `select.apple_tv_target` | The **default** Apple TV — used only by `/audio` with no Apple TV in the URL, and by services called without a `target` |
| `sensor.apple_tv_bridge` | How many Apple TVs the bridge can see, and everything about them |
| `button.recover_siri_voice` | Rebuild the voice data stream by hand (bridge-wide) |

Each Apple TV is a **device**, so its entities are grouped under it and the
names stay short. The three bridge-wide entities sit under an "Apple TV Siri
bridge" device.

`sensor.apple_tv_bridge` carries the details, including the identifiers that
`sources:` needs:

```yaml
apple_tvs:
  "207551296":
    name: Living Room
    identifier: 207551296
    configured: true
    voice_ready: true      # has a live data stream
  "35040583":
    name: Bedroom
    identifier: 35040583
    configured: true
    voice_ready: true
active_identifier: 207551296
siri_available: true
recovering: false
```

`binary_sensor.<apple tv>_siri_voice_available` is worth an automation. The
failure it catches is silent — buttons keep working while Siri stops, because
the Apple TV dropped the stream that carries audio — so without something
watching, you find out by talking to a remote that does nothing.

The text box is the fastest end-to-end check after installing: type "what's the
weather" and watch the TV.

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
accessory as a separate target, so you do not run a bridge per device. (For
pointing *microphones* at them, see
[Multiple microphones](#multiple-microphones) — each Apple TV has its own URL.)

Each one becomes a **device** with its own entities, so you address it directly
rather than selecting it first:

```yaml
- action: button.press
  target:
    entity_id: button.bedroom_home

- action: text.set_value
  target:
    entity_id: text.say_to_siri_bedroom
  data:
    value: "Play the next episode"
```

Services take a target too, which is what automations usually want:

```yaml
- action: appletv_siri.say
  data:
    target: 35040583
    text: "Pause"
```

`select.apple_tv_target` sets the **default** — used only by `/audio` with no
Apple TV named in the URL, and by services called without a `target`. It is a
fallback, not a mode: you never have to select an Apple TV before acting on it.

(The bridge does have a single "active target" underneath, because HomeKit's
Active Identifier characteristic is single-valued. Every call sets it as part of
the same request, so it is an implementation detail rather than something to
manage.)

### Multiple microphones

Give each one the URL of the Apple TV in its room:

```
kitchen tablet   → /api/appletv_siri/audio/kitchen
bedroom remote   → /api/appletv_siri/audio/bedroom
```

That is the whole configuration. The URL is the address, so a microphone holds
no state and makes no decision — replacing an Apple TV changes nothing on the
device, because the name stays the same even though the identifier tvOS assigns
does not.

`sensor.apple_tv_bridge` lists the URL for each Apple TV.

#### Advanced: named sources

Only needed if a microphone wants **different routing** rather than a different
Apple TV — sending one room's utterances to Assist while another goes to Siri:

```yaml
appletv_siri:
  sources:
    bedroom:
      target: 35040583
      siri_when:
        entity: input_select.bedroom_activity
        states: ["Watch Apple TV"]
```

```
POST /api/appletv_siri/audio?source=bedroom
```

An unrecognised source falls back to the default and logs a warning naming the
ones it knows, so a typo does not quietly talk to the wrong room.

### Simultaneous conversations — the one real limitation

**Only one utterance can be in flight at a time, across all Apple TVs.** A
second request waits up to 4 seconds for the first to finish and then gets a
clean `409`, rather than interleaving its audio into the first one's stream.

For a household this is usually invisible: it only bites if two people speak to
two *different* Apple TVs within the same couple of seconds, and the 4-second
wait absorbs merely near-simultaneous use. Measure before working around it.

**This is a limitation of the library, not of HomeKit.** The spec explicitly
provides for concurrency (§8.39):

> *"If an accessory can support control of multiple concurrent Apple TVs at the
> same time without requiring the user to select an Apple TV on the remote
> accessory UI, it must expose multiple instances of this service."*

HAP-NodeJS creates exactly one Target Control service and holds a single audio
session. Its own source leaves the question open:

```js
// you can also expose multiple TargetControl services to control multiple apple tvs simultaneously.
// should we extend this class to support multiple TargetControl services or should users just create a second accessory?
```

Note that the **data streams are already per-Apple-TV** — a bridge serving two
holds two open concurrently. Only the controller layer above them serializes.

#### Workaround: one bridge per Apple TV

Run a second container with its own HomeKit identity and pair it separately. You
get one accessory, and one setup code, per Apple TV:

```yaml
  appletv-siri-voice-bedroom:
    image: ghcr.io/marcusadolfsson/appletv-siri-voice:latest
    network_mode: host
    environment:
      - HAP_NAME=Voice Remote (Bedroom)
      - HAP_USERNAME=1A:2B:3C:4D:5E:70   # MUST differ from the first bridge
      - HAP_PORT=47130                   # ditto
      - HAP_UUID_SEED=bedroom            # ditto
      - CTRL_PORT=8478
    volumes:
      - ./bedroom-data:/data/persist     # its own pairing state
```

The cost is a second pairing to manage and a second setup code, which is why it
is not the default.

#### The better fix, if it ever proves necessary

Multiple Target Control service instances **inside one bridge** — one per Apple
TV, each with its own `Active Identifier` and `Button Event` — plus keying the
audio session by target rather than holding one. The Home Assistant side would
not change at all, since `sources` already resolves a target per microphone.

Two things keep this speculative rather than planned. Services are static in the
accessory database, so the number of instances is fixed at publish time while
targets only arrive *after* pairing; and adding services renumbers instance ids,
which is precisely the failure mode where buttons keep working and Siri silently
stops. Most importantly, §8.39 is an *accessory-side* requirement — it does not
promise that tvOS will actually drive two instances at once, and that is
unverified.

Anyone wanting this should spike it first: publish two Target Control services
and see whether tvOS assigns a different target to each.

## How this differs from the Apple TV integration (pyatv)

Home Assistant's built-in `apple_tv` integration uses **pyatv**, which speaks
Apple's own MRP/Companion/AirPlay protocols. This uses **HomeKit Target
Control**. They are different stacks with different strengths, and they are
complementary rather than competing — most people should run both.

| | `apple_tv` (pyatv) | this |
|---|---|---|
| **Metadata** | Now playing, app, artwork, position, volume | **None** — see below |
| **Siri voice** | No | **Yes** |
| **Buttons** | Rich: transport, app launch, keyboard, power | The 13 HAP button types |
| **Pairing** | Per Apple TV, PIN codes in Home Assistant | One Home app pairing covers every Apple TV in the home |
| **Failure mode** | The Companion connection can go stale, reporting old state for minutes | Independent path; unaffected |

**Use pyatv for state, this for voice.** The two useful things here that pyatv
cannot do:

1. **Siri.** pyatv has no audio path at all — its `Siri` HID command is only a
   button press, and there is no microphone channel behind it.
2. **A button path that does not depend on pyatv's connection health.** When the
   Companion connection goes stale, `media_player` state freezes while buttons
   sent this way keep working. That is not theoretical: it happened during
   development, and reading pyatv's `media_player` state to check whether
   HomeKit buttons had landed produced hours of false negatives — HA reported a
   paused movie a full second after the TV had already gone to its home screen.

If you already run `apple_tv`, keep it. Nothing here conflicts with it; the two
reach the Apple TV over entirely separate transports.

### Can this read metadata back?

**No.** Target Control is a remote-control profile, not a media one. Button
events go accessory → controller, and the only thing that comes back is
configuration: which Apple TVs exist, their names and identifiers, and which one
has claimed the remote. There is no now-playing, no app, no position, no volume
— the protocol has no channel for it.

What you *can* learn from this integration is surfaced on
`sensor.apple_tv_bridge`: the Apple TVs the controller has told us about, which
one is active, and whether each has a live voice stream.

For anything about what is *playing*, use the `apple_tv` integration alongside
it. That is what it is good at.

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

### Integration — set in the UI

Asked during setup, and editable afterwards from **Configure**.

| Key | Default | Notes |
|---|---|---|
| `bridge_url` | `http://127.0.0.1:8477` | Where the bridge's control API is |
| `target` | *(bridge's active target)* | Default Apple TV, chosen from a list of names |
| `tts_engine` | *(HA default)* | Engine for `say`. Pin it — HA's default is the Cloud engine, which fails when signed out |

### Integration — YAML only

Routing is nested, so it stays in `configuration.yaml`. A YAML block is adopted
into a config entry automatically, and these keys are merged over whatever the
UI holds — so the two can be used together.

| Key | Default | Notes |
|---|---|---|
| `sources` | `{}` | Named microphones; each may set `target`, `siri_when`, `assist_pipeline`. Selected with `?source=<name>` |
| `siri_when.entity` / `.states` | *(absent)* | Route to Siri while entity is in one of these states. **Absent means everything goes to Siri** |
| `assist_pipeline` | *(HA default)* | **Pin this** if you use the Assist route. HA's default pipeline has no STT engine, and an unpinned one silently returns nothing |
| `fallback_to_siri` | `false` | Assist first, Siri if it can't handle it (buffers — see [Sharing a microphone with Assist](#sharing-a-microphone-with-assist)) |
| `max_buffer_seconds` | `15` | Ceiling on a buffered utterance |

A `target` set in YAML wins over the one chosen in the UI.

## Limitations

- **Siri, not Home Assistant, decides what an utterance means** on the Siri
  route. There's no transcript back — HomeKit doesn't return one.
- **The Apple TV must be awake** to respond to voice.
- Target *names* come back garbled (a TLV parsing quirk in hap-nodejs); the
  identifiers are correct, which is what matters.
- One utterance at a time, across all Apple TVs — a HAP-NodeJS limitation rather
  than a HomeKit one. Workarounds and the proper fix are documented under
  [Simultaneous conversations](#simultaneous-conversations--the-one-real-limitation).
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
