/*
 * appletv-siri-voice bridge — a software HomeKit "Target Control" accessory.
 *
 * Pairs from the Home app with an ordinary setup code (no MFi, no hardware) and
 * then delivers remote-button events and Siri voice input to a chosen Apple TV.
 *
 * This process is the HAP transport ONLY. Nothing here talks to Home Assistant;
 * all policy — which Apple TV, and whether an utterance goes to Siri or to a
 * local assistant — lives in the Home Assistant integration that drives the
 * control API below.
 *
 * Protocol: HomeKit Accessory Protocol R2, chapter 12 "Remotes for Apple TV".
 */
'use strict';

const {
  Accessory, Categories, Characteristic, RemoteController, ButtonType,
  uuid, Service, HAPStorage,
} = require('hap-nodejs');
const http = require('http');
const fs = require('fs');
const OpusScript = require('opusscript');

// --- configuration ---------------------------------------------------------

const NAME = process.env.HAP_NAME || 'Voice Remote';
// Stable across restarts so a restart doesn't orphan the pairing.
const USERNAME = process.env.HAP_USERNAME || '1A:2B:3C:4D:5E:6F';
const PINCODE = process.env.HAP_PINCODE || '031-45-154';
const HAP_PORT = Number(process.env.HAP_PORT || 47129);
const CTRL_PORT = Number(process.env.CTRL_PORT || 8477);
const CTRL_BIND = process.env.CTRL_BIND || '127.0.0.1';
// Interface NAME, not an address. On a host running Tailscale (or any CGNAT
// interface) mDNS otherwise advertises 100.x, which no LAN client can reach —
// and binding a literal IP is worse still, because then no A record is
// published at all. Leave unset to let hap-nodejs choose.
const BIND = process.env.HAP_BIND || undefined;

// Pairing state (AccessoryInfo + ControllerStorage). MUST persist: losing it
// drops the Home app pairing and every Apple TV target.
if (process.env.HAP_STORAGE) HAPStorage.setCustomStoragePath(process.env.HAP_STORAGE);

// KEEP THIS SEED STRING STABLE. The accessory UUID determines every service's
// and characteristic's instance id; changing it renumbers them all while a
// paired Apple TV goes on using its cached ids. The failure is silent and
// confusing: buttons keep working, and Siri simply never opens a session.
const ACCESSORY_UUID = uuid.generate(process.env.HAP_UUID_SEED || 'appletv-siri-voice.accessory');

// 20 ms @ 16 kHz mono PCM16 = 320 samples = 640 bytes. tvOS negotiates exactly
// this (Opus, 1 channel, VBR, 16 kHz, 20 ms), which is also what a phone or a
// remote records natively — so nothing in the chain has to resample.
const FRAME_SAMPLES = 320;
const FRAME_BYTES = FRAME_SAMPLES * 2;
const FRAME_MS = 20;

// Recovery timings — see recoverHds().
const BOOT_HDS_GRACE_MS = Number(process.env.HDS_BOOT_GRACE_MS || 25_000);
const RECOVERY_PHASE1_MS = Number(process.env.HDS_PHASE1_MS || 45_000);
const RECOVERY_WAIT_MS = Number(process.env.HDS_WAIT_MS || 60_000);
const WATCHDOG_INTERVAL_MS = Number(process.env.HDS_WATCHDOG_MS || 300_000);
/** How long a new utterance waits for the previous one to finish. */
const LOCK_WAIT_MS = Number(process.env.SIRI_LOCK_WAIT_MS || 4_000);

const log = (...a) => console.log(new Date().toISOString(), ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- audio -----------------------------------------------------------------

/**
 * The utterance currently in flight, or null.
 *
 * Exactly one at a time, deliberately. hap-nodejs supports a single Siri audio
 * session, and the SIRI button and active target are both single-valued — so
 * two overlapping utterances cannot be delivered no matter how this is written.
 * Holding them in one object scoped to the request means a second caller gets a
 * clean 409 instead of interleaving its audio into the first one's buffer and
 * flipping the target out from under it, which is what a shared global did.
 */
let session = null;

const newSession = (target) => ({
  target, pending: Buffer.alloc(0), handler: null, encoder: null, frames: 0,
});

function rmsNorm(buf) {
  let sum = 0;
  for (let i = 0; i + 1 < buf.length; i += 2) {
    const s = buf.readInt16LE(i);
    sum += s * s;
  }
  const n = buf.length / 2;
  return n ? Math.sqrt(sum / n) / 32768 : 0;
}

/** Append PCM to the in-flight utterance and emit every whole 20 ms frame. */
function pushPcm(chunk) {
  if (!session) return;
  if (chunk.length) {
    session.pending = session.pending.length ? Buffer.concat([session.pending, chunk]) : chunk;
  }
  if (!session.handler) return; // audio session not open yet — keep buffering
  while (session.pending.length >= FRAME_BYTES) {
    const slice = session.pending.subarray(0, FRAME_BYTES);
    session.pending = session.pending.subarray(FRAME_BYTES);
    try {
      session.handler({ data: session.encoder.encode(slice, FRAME_SAMPLES), rms: rmsNorm(slice) });
      session.frames++;
    } catch (e) {
      log('[siri] encode error:', e.message);
      return;
    }
  }
}

class PcmSiriAudioProducer {
  constructor(frameHandler) {
    this.frameHandler = frameHandler;
  }

  startAudioProduction(selected) {
    if (!session) { log('[siri] audio session opened with no utterance in flight'); return; }
    log(`[siri] session opened for ${session.target}; tvOS asked for`, JSON.stringify(selected));
    session.encoder = new OpusScript(16000, 1, OpusScript.Application.VOIP);
    session.frames = 0;
    session.handler = this.frameHandler;
    pushPcm(Buffer.alloc(0)); // flush whatever arrived before the session opened
  }

  stopAudioProduction() {
    if (session) {
      log(`[siri] session closed after ${session.frames} frames (${session.frames * FRAME_MS} ms)`);
      session.handler = null;
      session.encoder = null;
      session.pending = Buffer.alloc(0);
    }
  }
}

// --- accessory lifecycle ---------------------------------------------------

/** The currently published accessory + its controller. */
let live = null;
let recovering = false;
let lastRecovery = 0;

function buildAccessory(withSiri) {
  const acc = new Accessory(NAME, ACCESSORY_UUID);
  acc.getService(Service.AccessoryInformation)
    .setCharacteristic(Characteristic.Manufacturer, 'appletv-siri-voice')
    .setCharacteristic(Characteristic.Model, 'HomeKit Target Control')
    .setCharacteristic(Characteristic.SerialNumber, USERNAME.replace(/:/g, ''));

  // Supplying an audio producer sets `hardwareImplemented` in the supported
  // configuration and adds the SIRI button. HAP §12.3 allows Siri only for a
  // remote declaring itself a hardware entity — buttons are NOT gated on it.
  const rc = new RemoteController(withSiri ? PcmSiriAudioProducer : undefined);
  acc.configureController(rc);

  rc.on('target-add', (t) => log(`[remote] target-add ${t.targetIdentifier}`));
  rc.on('target-remove', (id) => log(`[remote] target-remove ${id}`));
  rc.on('active-identifier-change', (id) => log(`[remote] active target -> ${id}`));

  return { acc, rc, withSiri };
}

async function publishAccessory(withSiri) {
  if (live) {
    try {
      await live.acc.unpublish();
    } catch (e) {
      log('[hap] unpublish failed (continuing):', e.message);
    }
    await sleep(1500); // let the HAP port and mDNS registration clear
  }
  live = buildAccessory(withSiri);
  live.acc.publish({
    username: USERNAME,
    pincode: PINCODE,
    port: HAP_PORT,
    category: Categories.TARGET_CONTROLLER,
    ...(BIND ? { bind: BIND } : {}),
  });
  log(`[hap] published ${withSiri ? 'with Siri' : 'buttons-only'} on ${HAP_PORT}`);
}

/** Apple TVs that have an open HomeKit Data Stream to us. */
function hdsTargets() {
  const m = live && live.rc && live.rc.dataStreamConnections;
  return m ? Array.from(m.keys()) : [];
}

/**
 * Whether a SPECIFIC Apple TV has a data stream.
 *
 * Per-target, not "any target", because the streams die independently: one
 * Apple TV can be perfectly healthy while the one being targeted has nothing.
 * An any-target check reports Siri as available, lets the request through, and
 * the utterance vanishes silently.
 */
function hasHdsFor(target) {
  const m = live && live.rc && live.rc.dataStreamConnections;
  return !!(m && target != null && m.has(Number(target)));
}

/** The target we would actually send to right now. */
const activeTarget = () => (live && live.rc && live.rc.activeIdentifier) || null;

/** Is voice usable for the currently selected Apple TV? */
const siriReady = () => !!(live && live.withSiri) && hasHdsFor(activeTarget());

async function waitFor(pred, timeoutMs, stepMs = 1000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (pred()) return true;
    await sleep(stepMs);
  }
  return pred();
}

/**
 * Recover a dead HomeKit Data Stream.
 *
 * Siri audio rides an HDS connection that the *Apple TV* opens to us, and it
 * only opens one when the remote's CAPABILITIES change — not when the accessory
 * restarts, and not when it re-registers its targets. So after any restart of
 * this process the Apple TV is left holding a dead socket, and every utterance
 * fails with "target is not connected via HDS" while buttons keep working
 * perfectly. Nothing on our side can request the connection; the accessory can
 * only wait for a `targetControl`/`whoami` on a stream the controller opens.
 *
 * The lever that does work is a capability change: publish once as a
 * buttons-only remote, then again with Siri. tvOS re-reads and opens a fresh
 * stream. (Clearing the stored target configurations does NOT work — the Apple
 * TV re-adds its targets and still opens nothing.)
 *
 * Buttons keep working throughout except for a ~2 s gap at each re-publish.
 */
async function recoverHds(reason) {
  if (recovering) return false;
  recovering = true;
  const started = Date.now();
  try {
    log(`[recover] starting — ${reason}`);
    await publishAccessory(false);                       // capability removed
    await sleep(RECOVERY_PHASE1_MS);                     // let tvOS notice
    await publishAccessory(true);                        // capability restored
    const ok = await waitFor(hasHds, RECOVERY_WAIT_MS);
    log(ok
      ? `[recover] data stream restored after ${Math.round((Date.now() - started) / 1000)}s: ${hdsTargets()}`
      : '[recover] FAILED — no data stream. If this persists, restart the Apple TV.');
    lastRecovery = Date.now();
    return ok;
  } finally {
    recovering = false;
  }
}

/**
 * Boot + periodic supervision.
 *
 * A fresh process never inherits a live stream, so the first recovery on boot
 * is expected rather than exceptional — voice is unavailable for roughly a
 * minute after startup, buttons immediately.
 */
async function superviseHds() {
  // At boot any stream will do — the active target may not be chosen yet.
  if (!(await waitFor(() => hdsTargets().length > 0, BOOT_HDS_GRACE_MS))) {
    await recoverHds('no data stream after boot');
  } else {
    log(`[hap] data stream present at boot: ${hdsTargets()}`);
  }
  setInterval(async () => {
    if (recovering) return;
    // Watch the ACTIVE target specifically. Streams die independently, so a
    // healthy stream to some other Apple TV must not mask a dead one here.
    if (siriReady()) return;
    if (Date.now() - lastRecovery < WATCHDOG_INTERVAL_MS) return;
    await recoverHds(`watchdog: no data stream for active target ${activeTarget()}`);
  }, WATCHDOG_INTERVAL_MS);
}

// --- control API -----------------------------------------------------------

function json(res, obj, code = 200) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

/** Wait for an Apple TV to claim the remote — it writes `Active` on its own schedule. */
function whenActive(timeoutMs = 5000) {
  return waitFor(() => live && live.rc.isActive(), timeoutMs, 200);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const [, action, arg] = url.pathname.split('/');
  const rc = live && live.rc;

  try {
    if (action === 'state') {
      const targets = {};
      if (rc) {
        rc.targetConfigurations.forEach((t, id) => {
          // isConfigured() needs the identifier; bare it returns has(undefined).
          targets[id] = { name: t.targetName, configured: rc.isConfigured(id) };
        });
      }
      return json(res, {
        active: !!(rc && rc.isActive()),
        activeIdentifier: (rc && rc.activeIdentifier) || null,
        targets,
        siriAvailable: siriReady(),
        dataStreams: hdsTargets(),
        recovering,
      });
    }

    if (action === 'active' && arg) {
      rc.setActiveIdentifier(parseInt(arg, 10));
      return json(res, { ok: true, activeIdentifier: rc.activeIdentifier });
    }

    if (action === 'press' && arg) {
      const btn = ButtonType[arg.toUpperCase()];
      if (btn === undefined) return json(res, { error: `unknown button ${arg}` }, 400);
      // ?target= selects and presses in one call. Doing it as two round trips
      // is a race when several Apple TVs are driven from separate entities.
      const t = url.searchParams.get('target');
      if (t) rc.setActiveIdentifier(parseInt(t, 10));
      if (!(await whenActive())) return json(res, { error: 'no Apple TV has claimed the remote' }, 409);
      rc.pushAndReleaseButton(btn);
      return json(res, { ok: true, button: arg.toUpperCase(), target: rc.activeIdentifier });
    }

    // Recover on demand (the HA integration exposes this as a button).
    if (action === 'recover') {
      recoverHds('requested via API');   // deliberately not awaited: it takes ~1 min
      return json(res, { ok: true, note: 'recovery started; expect ~60s' }, 202);
    }

    // Stream an utterance. The request BODY is raw PCM16 @ 16 kHz mono and the
    // end of the body is the end of the utterance. SIRI is held down for the
    // whole body and released after: pushAndReleaseButton() releases at 200 ms,
    // which tears the audio session down before a syllable lands.
    if (action === 'siri' && arg === 'stream') {
      // Wait for the previous utterance rather than refusing outright: the
      // release tail keeps the lock ~250 ms after a reply is sent, so two
      // sequential requests would otherwise collide even though they never
      // actually overlap. A genuine overlap still gets a clean 409.
      if (session && !(await waitFor(() => !session, LOCK_WAIT_MS, 100))) {
        return json(res, {
          error: `busy: an utterance to Apple TV ${session.target} is already in flight`,
        }, 409);
      }
      const target = url.searchParams.get('target');
      if (target) rc.setActiveIdentifier(parseInt(target, 10));
      if (!(await whenActive())) return json(res, { error: 'no Apple TV has claimed the remote' }, 409);
      if (!hasHdsFor(rc.activeIdentifier)) {
        recoverHds(`siri requested but target ${rc.activeIdentifier} has no data stream`);
        return json(res, {
          error: `no HomeKit data stream to Apple TV ${rc.activeIdentifier}; recovery started`,
          retryAfterSeconds: 60,
        }, 503);
      }

      session = newSession(rc.activeIdentifier);
      rc.pushButton(ButtonType.SIRI);
      log(`[siri] utterance -> target ${session.target}`);

      let bytes = 0;
      const finish = () => {
        // Small tail so the last frames flush before tvOS gets endOfStream.
        setTimeout(() => {
          try { rc.releaseButton(ButtonType.SIRI); } catch (e) { /* already released */ }
          log(`[siri] released after ${bytes} bytes (~${Math.round(bytes / 32)} ms)`);
          session = null;   // lock freed only here, so the next caller cannot overlap
        }, 250);
      };
      req.on('data', (c) => { bytes += c.length; pushPcm(c); });
      req.on('end', () => {
        finish();
        json(res, { ok: true, bytes, ms: Math.round(bytes / 32), target: rc.activeIdentifier });
      });
      req.on('error', finish);
      return;
    }

    // Replay a 16 kHz mono PCM16 WAV, paced in real time. Useful for testing
    // without a microphone; Siri endpoints on the far side, so an un-paced
    // burst reads as noise rather than speech.
    if (action === 'siri' && arg === 'file') {
      const file = url.searchParams.get('file');
      if (!file || !fs.existsSync(file)) return json(res, { error: 'missing/unknown file' }, 400);
      if (!(await whenActive())) return json(res, { error: 'no Apple TV has claimed the remote' }, 409);
      if (!hasHdsFor(rc.activeIdentifier)) return json(res, { error: 'no HomeKit data stream for the active target' }, 503);
      if (session && !(await waitFor(() => !session, LOCK_WAIT_MS, 100))) {
        return json(res, { error: 'busy: an utterance is already in flight' }, 409);
      }
      const pcm = fs.readFileSync(file).subarray(44);
      session = newSession(rc.activeIdentifier);
      rc.pushButton(ButtonType.SIRI);
      let off = 0;
      const iv = setInterval(() => {
        if (off + FRAME_BYTES > pcm.length) {
          clearInterval(iv);
          setTimeout(() => {
            try { rc.releaseButton(ButtonType.SIRI); } catch (e) { /* already released */ }
            session = null;
          }, 250);
          return;
        }
        pushPcm(pcm.subarray(off, off + FRAME_BYTES));
        off += FRAME_BYTES;
      }, FRAME_MS);
      return json(res, { ok: true, ms: Math.round(pcm.length / 32) });
    }

    return json(res, {
      error: 'use /state, /active/<id>, /press/<BUTTON>, /siri/stream, /siri/file, /recover',
    }, 404);
  } catch (e) {
    return json(res, { error: e.message }, 500);
  }
});

// --- start -----------------------------------------------------------------

(async () => {
  await publishAccessory(true);
  console.log(`\n  ${NAME}: add it in the Home app with setup code ${PINCODE}\n`);
  server.listen(CTRL_PORT, CTRL_BIND, () => log(`[api] control API on ${CTRL_BIND}:${CTRL_PORT}`));
  superviseHds();
})();

const bye = () => process.exit(0);
process.on('SIGINT', bye);
process.on('SIGTERM', bye);
