# Noise Lab Phase 1 verification

Evidence date: 2026-09-05. Source base: V2 main
`3c878d7723bb80a34a11c2c6b53faffd6e24a540`.

## Automated evidence

From the repository root, using Python with Flask/pytest and Node:

```sh
python -m pytest -q tests/test_noise_lab_routes.py tests/test_noise_lab_v2.py
node --test tests/noise_lab/engine.test.mjs
node --test tests/noise_lab/controller.test.mjs
node --check noise_lab/static/ui/controller.mjs
```

The Python run passed 15 tests, exit 0. It covers the default-off switch,
authenticated module/static access, unsupported flag values, per-app identity
isolation, absent generation/upload writes, host route preservation and removal
at the blueprint seam. The actual V2 application test runs in a separate process
with a temporary SQLite database and a narrow environment that excludes provider
credentials and deployed storage. It demonstrates V2's existing anonymous login
redirect, synthetic authenticated account access, missing-account rejection,
rendered page/assets, disabled access and no new Noise Lab database tables.

The Node run passed 15 tests, exit 0. It covers strict recipe rejection including
accessors and extra fields; original synthetic loop bounds; supported/malformed
WAVs and oversized decode demands; all 32 macro-extreme combinations across four
profiles at 8, 44.1 and 48 kHz, with one second per case to exercise echo feedback;
finite output and the −1 dBFS sample ceiling; fault-to-silence; parameter
and bypass ramps; rapid changes and 60 seconds of simulated DSP playback at 8 kHz; the
actual processor module against the shared DSP; local WAV encoding; cancelled
and stale exports/imports; retention of a previous valid source; transport races,
disposal and capability failure. Worklet execution is a Node harness with a fake
browser processor base, not a browser audio-device test. JavaScript syntax passed.

Five controller regressions also passed, exit 0, after independent review found
three defects. A now labels the preset actually auditioned; older asynchronous
recipe reads cannot replace a later import/edit/Undo; and Stop cancels pending
Play even before engine creation completes. Coverage includes malformed recipe
retention, clear-session invalidation and successful Play after cancellation.
The real controller runs with a small fake DOM and fake engine: this verifies
event/state behavior, not rendered accessibility or audible playback.
The independent reviewer scored all three listed fixes resolved after a fresh
five-test controller run. Its `ship` verdict covers those source-review findings
only; it is not browser, audio-device or deployment approval.

The actual Flask template renders and serves its local assets under the content
policy. The Impeccable source detector returned no findings but ran in degraded
regex mode: its HTML/CSS parser modules were unavailable. Computed contrast,
selector matching and custom-property checks did not run. This is not an
accessibility or visual approval.

## Browser and listening evidence not obtained

The available cloud browser blocked the local test URL
`http://127.0.0.1:5103/noise-lab/` with `net::ERR_BLOCKED_BY_CLIENT`. No alternate
deployment or hosting configuration was created to work around that block.
No valid desktop/mobile screenshot, real AudioWorklet playback, listening result,
download verification, keyboard/touch exercise or network-privacy capture was
obtained. The local test harness used a synthetic identity and is not shipped.

Do not claim tested browser/device support or that switching is inaudible based
on this report. Numerical bounds do not certify true-peak safety, acoustic volume,
browser scheduling, output-device latency, thermal behavior or glitch-free audio.

## Required device matrix before pilot

The following are proposed test targets, all currently **unverified**. Record
exact OS/browser versions, hardware, audio output, sample rate, result and evidence
when each is actually tested; do not label a browser family as universally supported.

| Target | Required exercise |
| --- | --- |
| Desktop Chromium on macOS/Windows | Full loop/preset/macros/A-B/undo/import/export journey, tab-only use, repeated switches and 30 minutes foreground playback. |
| Desktop Safari on macOS | Same journey, gesture-start/resume, worklet MIME/CSP and offline render/download. |
| iPhone Safari | Touch targets, narrow layout, loop preview, interruption/resume, file import/download and 30 minutes foreground playback. |
| Android Chrome | Same mobile journey, background/foreground and output-device changes. |
| Keyboard/screen reader and 200% zoom | Names/roles/values, focus order, numeric limits, error announcements, no trapped focus and no clipped controls. |
| Unsupported/insecure environment | Honest support message, audio disabled, recipe controls/export still available. |

Listen to and capture clean/preset/A-B/Undo/Stop/Play switches, imported loop
seams, extremes, long echoes and rapid gestures using declared outputs. Inspect
sample bounds and finite values on real captured renders. Document intentional
tail truncation. Compare current B export with a reset-state audition of that
recipe, not the accumulated tail of indefinite looping. Exercise pending import,
export Cancel, clear/reload, malformed file recovery and interrupted resume.
Check browser network traffic for source PCM/recording leakage and only owned
same-origin assets. Inspect actual memory pressure during sustained use.

## Scope of completion

Implemented source and automated evidence cover the isolated audio slice.
AI generation, server ownership of patch versions, durable storage, quotas,
provider costs, retention jobs, restore/deletion and musician metrics have no
implementation or completion claim here. No main-branch merge, live-site change,
service configuration change or deployment is part of these checks.
