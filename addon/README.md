# Apple TV Siri Voice Bridge

Makes Home Assistant appear to your Apple TV as a **HomeKit remote**, so it can
send button presses and stream voice into Siri. No MFi licence and no special
hardware — it pairs from the Home app with an ordinary 8-digit code.

This add-on is the **bridge** half. You also need the
[Apple TV Siri Voice integration](https://github.com/marcusadolfsson/appletv-siri-voice)
in HACS, which is what your automations and dashboards actually talk to.

## Install

1. Install and start this add-on.
2. Open the **Home app** on an iPhone or iPad → **Add Accessory** → the
   accessory appears under the `name` you configured. Pair it with the
   `pincode`.
3. Install the integration from HACS and point it at `http://127.0.0.1:8477`.
4. In the Home app, assign the remote to the Apple TV you want it to drive.

## Options

| Option | Notes |
|---|---|
| `name` | What appears in the Home app when pairing. |
| `uuid_seed` | **Write-once in practice.** The accessory UUID derives from this, and every characteristic id derives from that — changing it after pairing invalidates your Apple TVs' cached view and breaks Siri until you re-pair. |
| `pincode` | The pairing code. The default is published in this repo, so change it before pairing if that matters to you. |
| `bind_interface` | **Leave empty** unless you know you need it. Empty binds every interface, which is what HAP-NodeJS does by default and is correct on a normal single-network host. |
| `expose_control_api` | Leave **off**. On binds the control API to all interfaces, making `/press` and `/siri/stream` an unauthenticated "control the TV and talk to Siri" endpoint for your whole LAN. Only turn it on if Home Assistant runs on a *different* machine, and firewall it if you do. |

## Things worth knowing

**Host networking is required, not a preference.** HomeKit discovers and pairs
accessories over mDNS on the LAN, which bridge networking does not carry — the
accessory is simply never found without it.

**Your pairing lives in `/data/persist`.** Uninstalling the add-on (rather than
just stopping it) discards that, which drops the Home app pairing and every
Apple TV assignment. Re-pairing is the fix, but it is not automatic.

**Pairing failing is almost always mDNS.** If the accessory never appears in the
Home app, the phone and the Home Assistant host are usually on different VLANs
or separated by AP isolation.
