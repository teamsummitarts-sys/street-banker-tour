# Street Banker Noise Lab — V2 Phase 2

Status: an account-gated local audio and prompt-to-settings validation prototype.
Phase 2 adds a server-side OpenAI adapter; live provider calls and the new mobile
generation flow remain unverified until activation and an authenticated retest.
The owner confirmed the preceding iPhone export fix works. Sustained playback,
listening quality and broader device checks remain pilot gates.
See [VERIFICATION.md](VERIFICATION.md) for evidence and limitations.

## Repository and isolation

Built against `teamsummitarts-sys/v2-street-banker` main commit
`3c878d7723bb80a34a11c2c6b53faffd6e24a540`: Flask, Jinja, browser JavaScript and
SQLite. Phase 2 builds on `0ac3b12dcaacbeb022b85086dbed3a3bcac74f87` and leaves
the engine and recipe schema unchanged. No runtime dependency was added. Existing V2 DSP was
inspected; its DOM and rack-storage coupling led to a separate small engine.

The module owns `noise_lab/`, `tests/noise_lab/`, the
`tests/test_noise_lab_*.py` files and `docs/noise-lab/`. Its only host change is
registration beside `audio_studio.init` in `app.py`. It does not alter shared
templates, navigation, styles, databases, V1 repositories or hosting settings.
The prior audio and iPhone-save releases are deployed to the separately approved
V2 service. Phase 2 deployment evidence is recorded in its PR. This source can
still be copied to another compatible Flask host through the existing seam.

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
2. Choose one of four manual presets, or enter a description and press Create
   sound after loading a loop. When configured, only the description goes to
   OpenAI. The server and browser validate the result before replacing B. The
   prior patch remains available on A/Undo. Unavailable or failed generation
   keeps the working patch and manual presets. New edits invalidate late results.
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

| Data | Actual prototype behavior |
| --- | --- |
| Imported/synthesized audio and rendered PCM | Browser page memory only; no upload route, telemetry or provider request. |
| Settings and undo history | Page memory only. No localStorage, IndexedDB or server persistence. |
| Sound descriptions | Sent only on Create sound to the authenticated V2 route and OpenAI. No prompt/response-body persistence or logging by this module. Responses API uses `store:false`; this does not disable provider abuse-monitoring retention. |
| Generation usage | Account-linked attempt/success/failure counters, reported token totals and total request duration in server-process memory until restart. No backup. Clear session does not reset limits. |
| Downloaded WAV/JSON | Saved wherever the browser/user chooses; the app cannot verify download completion or delete those files. Device backup services may copy them. |
| Clear, reload, close | Dispose the engine and release application references. No forensic memory-erasure claim. Back/forward restoration preserves the session only when the browser retained the page in memory. |
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
| 2: prompt → settings | Implemented and tested with synthetic provider responses; real provider and physical-device flow still require verification. See PHASE2.md for the contract, credential authorization, limits and activation. |
| 3: UI/private storage | Owner-scoped immutable patch versions, save/reload/export/delete, accessible real-device flow, conflict handling, explicit migrations and verified retention/backup/restore. |
| 4: musician pilot | Consenting musicians, actual task observations, comparison with familiar tools, return-use and payment interviews. No invitations or claims of results in this change. |

Current closed-pilot limits supersede the earlier proposal: one active request
per account, two across the process, ten seconds between starts, 20 attempts per
account and 100 across the process lifetime, 500 prompt characters, 4 KiB request,
32 KiB provider response, 256 output tokens and 12-second network timeout. No
automatic paid retries. Failures and cancelled requests consume attempts. Limits
are atomic within V2's verified single-worker, single-instance configuration and
reset on restart; they are not daily quotas or a durable billing cap. Before
scaling or recruiting a wider pilot, replace the in-memory allowance with shared
durable quotas and a reconciled monetary budget. Do not scale this implementation
while generation is enabled.

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
Generation counters exist only for requests actually attempted; test figures are
synthetic and not pilot results. No participant, preference or willingness-to-pay
results exist yet.

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

The exact approved Render service is `srv-dad6q3gae00c7393s02g`,
`street-banker-v2-workflows`, in the previously confirmed Lucas workspace. It
deploys this repository's `main`, has auto deploy off, one Gunicorn worker and
one free instance. V2 deployment and a dedicated OpenAI credential were approved
in the conversation; this is the specific exception to the foundation runbook's
earlier prohibition on provider credentials. Do not replace other environment
variables, change accounts or copy any V1 credential. Use one manual deployment
after merge; the user reports adding the new key in Render. No key value is read
into this source, tests, docs or PR.

## iPhone export correction — 2026-09-05

Exports now use two deliberate steps: Prepare WAV/recipe, then Save / share file
when file sharing is supported, or Download file. Preparation never navigates
the lab. The native save sheet is invoked directly from the second tap, after
rendering has finished. The fallback is a real download link with a separate
browsing target and no opener; a browser file preview should leave the lab tab
intact. In-app browsers may still open an external viewer.

One prepared file is retained in page memory until replaced, Clear session or
page teardown. New edits do not alter it; prepare again to export new settings.
Cancelling/failing the save sheet preserves the prepared file and working patch.
The app does not claim the user actually saved a file. Choosing a share target
can transfer the file through the device; the app does not upload recordings.

A cached history return retains audio/settings/undo and resumes only after Play.
A real reload, page eviction or closed tab can still lose unsaved work. This adds
no persistent browser storage or cloud backup. Physical iPhone confirmation is
pending; the user's report establishes the symptom, not a completed diagnosis
of the specific browser or iOS version.
