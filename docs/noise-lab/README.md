# Street Banker Noise Lab — V2 Phase 1

Status: a default-off, account-gated validation prototype. This is the local audio
phase, not completion of the proposed AI-to-private-patch product. Real browser
playback, listening, mobile and sustained-device checks remain release gates.
See [VERIFICATION.md](VERIFICATION.md) for evidence and limitations.

## Repository and isolation

Built against `teamsummitarts-sys/v2-street-banker` main commit
`3c878d7723bb80a34a11c2c6b53faffd6e24a540`: Flask, Jinja, browser JavaScript and
SQLite. No framework or runtime dependency was added. Existing V2 DSP was
inspected; its DOM and rack-storage coupling led to a separate small engine.

The module owns `noise_lab/`, `tests/noise_lab/`, the two
`tests/test_noise_lab_*.py` files and `docs/noise-lab/`. Its only host change is
registration beside `audio_studio.init` in `app.py`. It does not alter shared
templates, navigation, styles, databases, V1 repositories or hosting settings.
No deployment is included. A source branch can be reviewed and pulled later.

After separate deployment approval, enable only the intended V2 environment
with `NOISE_LAB_ENABLED=1`, then visit `/noise-lab/` using an existing V2 account.
The default is off. Only boolean `True` in Flask config or the exact string `1`
enables the route. V2's existing session gate may redirect anonymous users to
login before the module gate runs. The page, assets and capabilities endpoint
require an authenticated identity; the module creates no identity bypass.

## Implemented journey

1. Press Play to create the browser audio context and audition an original,
   procedurally synthesized eight-second loop. Two synthetic sources are labeled
   as such; neither is represented as a guitar recording or licensed sample.
2. Choose one of four explicitly authored presets. The sound-description panel
   states that AI generation belongs to the next phase; it sends no request.
3. Hear the fixed audio graph and adjust Texture, Motion, Space, Mix and Level
   through native sliders or numeric inputs.
4. A auditions the previous committed settings; B retains the current settings.
   Clean comparison is independent. Undo/redo stores up to 50 changes in memory.
5. Download/import a versioned recipe JSON, or render one source pass to WAV
   locally. Downloads always use B. There is no cloud Save/version history yet.
6. Clear the session to release audio, settings history and download references.

The source can also be a local mono/stereo RIFF WAV: PCM16/24/32 or IEEE float32,
8–192 kHz, at most 30 seconds and 20 MiB, with a 64 MiB decoded PCM ceiling.
Compressed WAV, WAV extensible, RF64 and MP3 are rejected. Every stored float
sample is checked for finite values. Import uses basic linear resampling and
five-ms loop-edge fades; it is not an archival converter. Failed replacement
retains the previous source. Processing is local; no microphone is requested.

## Audio contract

`noise_lab/static/engine/index.mjs` exports `NoiseEngine`, `PRESETS`, `LOOPS`,
`DEFAULT_RECIPE`, `validateRecipe` and `supportsAudio`. Only the browser adapter
depends on Web Audio. `NoiseDSP` is shared by the shipped AudioWorklet processor
and local offline WAV rendering. The UI imports the module by a relative URL.

Fixed graph: DC removal → saturation → amplitude tremolo → filtered feedback
echo → dry/wet mix → output level → soft clipping and finite sample guard.
Space is filtered echo, not convolution reverb. All profiles use authored
parameters; recipe data cannot choose code, URLs, graph topology or formulas.
No AI-generated code is accepted or executed.

Texture/Motion/Space/Mix accept finite numbers from 0 to 100. Level accepts
−60 to 0 dB and starts at −12 dB. Preset/profile definitions are in
`recipes.mjs`. Parameter and clean-comparison changes ramp over 40 ms. Play/Stop
ramps and imported-loop edge fades reduce abrupt transitions. Source replacement
stops transport; explicit Play starts the replacement. This behavior and the
numerical tests do not prove inaudible switching on physical devices.

Output is guarded to a sample magnitude at or below `10 ** (-1 / 20)` (−1 dBFS),
including clean comparison and exports. A lower representable Float32 bound
preserves the ceiling after buffer conversion. Nonfinite signals latch silence.
This is a sample-peak bound, not true-peak certification, loudness normalization
or a guarantee about the user's listening volume.

WAV export is PCM16 at the actual context sample rate, one source pass, mono or
stereo matching the source, with an optional fixed two-second tail and boundary
ramps. A long echo may be truncated. Rendering starts from reset DSP state;
it does not capture the accumulated state of an already looping audition.
Source/settings changes or Cancel invalidate a render before download.

## Versioning and later import

The first recipe schema is exactly:

```json
{
  "schemaVersion": 1,
  "engineVersion": "noise-lab-1.0.0",
  "profile": "clean",
  "macros": {"texture": 10, "motion": 0, "space": 0, "mix": 25, "level": -12}
}
```

Unknown/missing fields, arrays, executable accessors, unrecognized profiles,
nonfinite/out-of-range numbers and unsupported versions fail before replacement.
Import never silently clamps or loads remote executable content. JSON contains
settings only, with no audio, owner ID or automatic source reference. Keep the
source file separately. Phase 1 does not promise full session reconstruction.

Before changing algorithms, profile mappings, macro behavior, protective stages,
resampling or export behavior, issue a new engine version. Before changing the
recipe envelope, issue a new schema version. Preserve the v1 reader and engine,
or add an explicit migration that retains the original recipe, validates the
converted settings and records source/target versions. Do not silently interpret
old settings through new formulas. Unknown future versions must remain readable
as an untouched downloadable file even when they cannot be applied; importing
one must retain the current sound. Add cross-version fixtures at the first
version change. There is only one implemented version today.

For a later Flask host, copy the owned module and call
`noise_lab.init(app, current_user=host_current_user)` once during application
creation. The injected resolver returns the authenticated account dictionary
with a stable `id`, or no account. Adapt the return URL in the blueprint to that
host. Keep the module's assets together; serve `.mjs` with a JavaScript MIME type
over HTTPS or localhost. Audio assets and worklets are same-origin. A different
frontend may reuse the engine separately; it needs its own UI/auth integration.
This is a bounded integration seam, not a universal one-click compatibility claim.

Future server adapters must receive the real identity namespace and stable
account ID, never trust an owner ID in a request, and avoid module-global identity
state. Private patch import must verify explicit ownership mapping; matching
emails or numeric IDs alone is insufficient.

## Privacy, deletion and backups

| Data | Actual Phase 1 behavior |
| --- | --- |
| Imported/synthesized audio and rendered PCM | Browser page memory only; no upload route, telemetry or provider request. |
| Settings and undo history | Page memory only. No localStorage, IndexedDB or server persistence. |
| Downloaded WAV/JSON | Saved wherever the browser/user chooses; the app cannot verify download completion or delete those files. Device backup services may copy them. |
| Clear, reload, close | Dispose the engine and release application references. No forensic memory-erasure claim. Back/forward restoration starts a cleared session. |
| Automatic recovery/backups | None for this module. Download recipes and source audio to keep work. |
| V2 account/infrastructure | Existing host behavior; no changes. Deployed disk durability, infrastructure logs and backup configuration have not been verified in this work. |

Responses use `Cache-Control: no-store`, account-sensitive caching headers, a
same-origin content policy and microphone/camera/geolocation denial. No third-party
fonts or analytics are loaded. Archivo is vendored with its OFL license and source
record. The supplied reference images are not shipped with the module.

Cloud patch retention and ownership checks are not implemented because there
are no patch records or server patch routes yet. Before a private pilot, require
documented durability, deletion and restore evidence. The proposed later policy
is 30-day minimal operational metadata, encrypted daily patch snapshots with
seven-day expiry, and a deletion ledger reapplied before restored data can be
served. These are proposed requirements, not configured services or guarantees.

## Remaining phases and gates

| Phase | Required next work and evidence |
| --- | --- |
| 1: audio/safety | Current source implementation and automated checks; physical-device/browser/listening matrix still required. |
| 2: prompt → settings | Server-side authenticated endpoint, CSRF, strict server/client validation against the tested effect allowlist, stale-request protection, manual fallback and last-good state. Use the OpenAI Developers credential workflow before API implementation; no key or provider calls were used here. |
| 3: UI/private storage | Owner-scoped immutable patch versions, save/reload/export/delete, accessible real-device flow, conflict handling, explicit migrations and verified retention/backup/restore. |
| 4: musician pilot | Consenting musicians, actual task observations, comparison with familiar tools, return-use and payment interviews. No invitations or claims of results in this change. |

Proposed Phase 2 limits: one active request/account, three starts/minute,
20 provider attempts/day/account, 1,000 prompt characters and 2 KiB request body,
bounded response size/tokens/time, no automatic paid retries. Count failed billed
attempts. Enforce atomic quotas across workers and a configured global spend
ceiling before enabling requests. Reserve maximum request cost, reconcile usage,
and conservatively retain reservations for unknown timeout billing. These limits
are not active features; generation is unavailable in Phase 1.

Test malformed, extra-field, truncated, refused, timeout and out-of-range model
responses; code/URL injection; stale response after edit/Undo/Cancel; forged owner
IDs; anonymous/expired/other-account reads and writes; CSRF; quota races; deletion
during generation; failed persistence and restored deletion. Invalid generation
must retain the last working patch and offer explicitly labeled manual presets.

Pilot measures: time from first eligible session entry to confirmed first private
patch save; preference against each musician's named existing tool on the same
task; return use on separate days; concrete willingness-to-pay responses;
generation failures/attempts by cause; actual token usage and provider cost per
attempt and successful saved sound. Local recipe download is not the private-save
metric. Report denominators, dropouts, uncertainty and observed device versions.
No analytics, participants, metrics or willingness-to-pay results exist yet.

Proposed pilot targets from the approval brief: 12 musicians/14 days; median
first private save ≤3 minutes; 8/12 prefer this task flow, 6/12 return on two more
days and 6/12 name a concrete price. Lock targets/budget before the pilot; do not
represent them as forecasts or measured results. Hardware, public marketplace,
live instrument input and universal pedal export remain excluded.

## Disable, remove and review

To disable after an approved deployment, unset `NOISE_LAB_ENABLED` or set it to
`0`, then restart only the approved V2 service. To remove source, delete the
Noise Lab registration block from `app.py`, then remove only the module, its
named tests and its docs. No database rollback or shared dependency removal is
needed. Test host routes afterward. Downloaded user files remain user-owned.
This procedure has been checked at the isolated blueprint seam; a deployed
service removal rehearsal has not been performed.

Code is prepared for an isolated V2 branch and draft PR. Both its commit message
and PR title carry `[skip render]` to request suppression of Render auto-deploys
and previews, as described in [Render deploys](https://render.com/docs/deploys)
and [service previews](https://render.com/docs/service-previews). No Render
configuration was modified. Other deployment automation must be reviewed before
enabling/merging; live service mapping remains unverified. No merge or deployment
is authorized by this source change.
