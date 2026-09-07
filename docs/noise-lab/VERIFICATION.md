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

## iPhone save/navigation regression — 2026-09-05

The user reported saving then being taken out of the app and confirmed an iPhone.
Source inspection found synthetic same-context blob navigation and destructive
pagehide/pageshow handling. These explain a possible preview-and-return loss;
the exact browser behavior has not been reproduced on the user's device.

Three regression tests failed against the original controller, then passed after
the correction. The expanded suite passes 10 controller + 15 DSP + 15 Python
tests (40 total), exit 0. Coverage includes no automatic export navigation, a
separate fallback context, gesture-triggered file sharing, cancelled/unsupported/
failed sharing, async WAV preparation, cached-return source/history retention,
and full-unload disposal. These use the real controller with DOM/engine fakes;
physical Safari/in-app browser behavior remains unverified.

Browser rationale: [download behavior can vary](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/a),
[file sharing needs a user gesture](https://developer.mozilla.org/en-US/docs/Web/API/Web_Share_API),
and [pagehide distinguishes cached navigation](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event).
No DSP algorithm, recipe schema, ownership gate or persistent storage changed.
# Phase 2 generation verification — 2026-09-05

Fresh combined checks on this source: **43 Python tests + 29 JavaScript tests =
72 passing**, exit status 0. `git diff --check` also passes. Commands:

```
python -m pytest -q tests/test_noise_lab_generation.py tests/test_noise_lab_routes.py tests/test_noise_lab_v2.py
node --test tests/noise_lab/controller.test.mjs tests/noise_lab/engine.test.mjs
```

The new server vertical-slice test initially failed because the session CSRF
boundary was absent; the new UI test initially failed because no generation
request was sent. Both now pass against the real route/controller, using a
synthetic provider boundary. No synthetic output is shipped as a fallback AI.

| Acceptance | Evidence | Status |
| --- | --- | --- |
| Auth/ownership/CSRF | Standalone route tests and actual V2 factory in an isolated subprocess; anonymous and switched-account rejection, forged identity/Origin, no host table migration | Confirmed in automated tests |
| Bounded data, no generated execution | Real JSON parser rejects duplicate/extra fields, refusal, incomplete output, tool calls, nonfinite/out-of-range values; real adapter body has no audio/tools and redirect/response caps tested | Confirmed in automated tests |
| Working patch retained | Actual controller event tests cover invalid response, expired login, cancellation, clear and late response after edits; manual presets and Undo remain usable | Confirmed with fake DOM/audio boundary |
| Generation limits | Locked reservations under concurrent threads, account isolation, 20/account and 100/process ceilings, two concurrent requests globally, cooldown, failed usage not refunded | Confirmed within one process |
| Recipe compatibility/output bounds | Cross-language fixtures pass the unchanged v1 reader; existing engine extrema, switching, WAV and sixty-second DSP tests pass | Confirmed numerically; physical listening unverified |
| iPhone export regression | Existing 2-step share/cancel/cache-return tests pass; owner confirmed prior release on iPhone | New generation flow not device verified |
| Provider and cost | Outbound request shape, error redaction, no retries and model snapshot verified with fakes; actual usage is counted only if reported | Live key/model access, invoice cost and sound preference unverified |
| Deployment | Exact V2 service preflight matches repo/main, auto-deploy off, one worker/instance | Final deploy evidence recorded in Phase 2 PR |

The user reports setting the API key in Render; its value was not read by this
work. The real provider integration still needs an authenticated Create sound
request. A public login-page check does not prove the private generation flow.
No fabricated audio result, participant measurement or completion claim is made.
See PHASE2.md for the supported single-process scope, retention and disable path.

## Provider limit diagnostics regression — 2026-09-05

The user's iPhone screenshot reports an upstream usage/rate limit with 19 local
attempts remaining. The original code discarded the 429 body; its exact reason
is unknown. The new insufficient-quota regression failed against that code
(`provider_limit` instead of `provider_quota`) before the correction.

Fresh combined checks using the commands above pass **58 Python + 35 JavaScript
tests = 93 total**, exit 0. Added cases cover seven recognized upstream codes,
unknown codes, legacy type-only errors, malformed/oversized/duplicate-key bodies,
bounded reads, no retry or raw-body exposure, actionable UI messages, retained
patch settings and usable manual presets. These use synthetic provider responses
and the real parser/controller with fake network/DOM boundaries. The existing
host-auth, CSRF, recipe, DSP and iPhone-save regressions also pass.

No successful live generation or new physical iPhone audio result is claimed.
This fix does not increase provider credits or limits. Deployment evidence and
the exact V2 commit are recorded in the associated pull request.

## Phase 3 private patch library — 2026-09-05

The owner subsequently reported that generation, A/B, Undo and audio export all
worked on their iPhone after adding API credit. This supersedes the earlier
absence of user-reported success for those features; it does not establish
measured API cost, sustained device playback, or results for this new library.

Fresh combined checks on the Phase 3 source pass **133 Python + 41 JavaScript
tests = 174 total**, exit 0. Commands:

```
python -m pytest -q tests/test_noise_lab_patches.py tests/test_noise_lab_storage_admin.py tests/test_noise_lab_generation.py tests/test_noise_lab_routes.py tests/test_noise_lab_v2.py
node --test tests/noise_lab/controller.test.mjs tests/noise_lab/engine.test.mjs
```

| Acceptance | Evidence | Status |
| --- | --- | --- |
| Private ownership and mutation protection | Real SQLite, two-account list/read/version/export/delete isolation, anonymous access, CSRF/Origin checks, bounded strict request parsing | Automated checks pass |
| Immutable versions and limits | Concurrent creates/appends, stale base versions, idempotent retries, deleted-request tombstones, per-account and per-patch ceilings | Automated checks pass |
| Compatibility and failure retention | Unknown/partial store schemas fail closed; unsupported/corrupt recipes remain exportable; controller preserves working audio after errors and newer edits after late acknowledgements | Automated checks pass; controller uses fake DOM/audio/network boundaries |
| Host integration and persistence | Actual V2 factory with synthetic identity; save, reopen the same SQLite file through a new factory/client, read and export owned versions | Local database reopening passes; Render restart test pending |
| Durable-storage gate | Flag off by default; production requires a real persistent mount with the resolved database below it; path/symlink escape rejection | Automated checks pass; paid mount not provisioned |
| Native database recovery helper | Live WAL content and user IDs preserved, SQLite integrity and foreign keys checked, private destination permissions, no overwrite, invalid source/path/mount rejection, safe failure cleanup | 18 helper tests pass; actual V2 backup/restore not performed |
| Library controls and iPhone export regression | Save/version, older-version load with Undo, duplicate-save prevention, lost-response retry, conflict/session errors, two-step archive export, explicit deletion confirmation, clear and account-change invalidation | 26 controller tests pass; physical device and visual review pending |
| Existing AI and audio behavior | Provider diagnostics/auth/limits and unchanged DSP extrema, finite output, switching ramps, WAV export, worklet equivalence and simulated sustained processing | Existing regressions pass; no new live generation or listening claim |

The isolated local preview at `http://127.0.0.1:5061/noise-lab/` was blocked by the
available browser with `net::ERR_BLOCKED_BY_CLIENT`. It used a synthetic local
identity and did not call the provider. No rendered library screenshot,
screen-reader/keyboard/touch result, real browser playback, or new iPhone result
was obtained. Automated DOM tests are not a visual or accessibility certification.

Phase 3 is prepared for review, not activated. No paid Render upgrade, persistent
disk, environment change, production data copy, backup schedule or Phase 3
deployment is included in this evidence. V1 was not modified. The existing Free
V2 filesystem is unsuitable for durable account saves. The concrete paid-storage
approval, pre-upgrade whole-database backup, activation, restart verification and
rollback steps are documented in PHASE3.md. The project-wide CI workflow does not
currently select these Noise Lab paths; these are local test results, not a claim
that GitHub CI ran. Musician preference, repeat use, willingness to pay,
time-to-first-saved-sound, generation failure rate and actual cost remain
unmeasured.
