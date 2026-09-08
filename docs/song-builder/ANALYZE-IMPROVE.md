# Analyze & Improve — private inbox and assigned destinations

Source base: V2 `8d0ca48defa0816a61572fe0cd79f07f328c1cca`.
Scope: `song_builder/`, its tests and this document. No Noise Lab or V1 changes.

## Musician flow

The editor opens **Analyze & Improve** in a separate tab so unsaved editing state
is not abandoned. The page uses a single scrolling layout on phone and desktop.

1. Confirm permission and upload 1–12 analysis copies to a private inbox.
2. Choose Sound DNA or Improve My Track. Set weights, exclude references, and
   supply Keep/Avoid traits. Improve accepts one active upload and an optional
   section map in file-relative seconds.
3. Assign an available destination. External destinations require disclosure
   acceptance tied to the exact destination configuration. Upload never starts
   analysis, chooses a default external provider, or transfers to Suno.
4. Run explicitly. Muted/zero-weight references are excluded from computation and
   outside transfer. Each active reference is processed once. A duplicate request
   ID returns the same run; changed settings with the same ID conflict.
5. Review preservation notes, conservative changes, confidence and tradeoffs.
   Accept/reject affects producer notes, never waveform data or project settings.
6. Edit the under-1000-character blueprint; save/export the report. Producer notes
   and the timecoded edit list contain accepted changes only. Full Audit,
   Markdown, text and JSON retain all decisions. Reports use schemaVersion 1.

## Capability boundaries

| Capability | Implementation / limitation |
|---|---|
| Local measurement | Duration, channel/sample rate, sample peak, RMS, crest factor, near-full-scale sample count and one-second RMS windows. Not LUFS/true peak/EBU LRA. |
| Local BPM | Bounded 90-second RMS-onset periodicity estimate. Low/medium heuristic confidence, half/double alternatives; no tempo fabricated for silence or weak evidence. Not a calibrated beat tracker. |
| Key/mode, genres, mood, instruments, vocals, texture, rhythm, production, energy | Optional musical interpretation adapter. Unknown locally; model labels/confidence are explicitly inferences. No external provider was called during verification. |
| Blending | Normalized active weights, exact-match shared/outlier trait labels, global Avoid exclusion. Keep traits are user directions. This is not an embedding similarity model. |
| Blueprint | Deterministic editable synthesis of supported/user traits, tempo if available, weighted length, proposed or user structure, exclusions, three general alternate directions. No Suno API integration. |
| Improve | Up to five provider recommendations, each validated against duration with benefit/tradeoff/confidence/identity risk/source requirements. Local destination gives only evidence-supported level/leading-silence tests, possibly none. |
| Tempo/key tests | Suggestions to audition in another version, with quality/performance risks. No new time-stretch/pitch engine or automatic edits. |
| Audio formats | 16-bit mono/stereo PCM WAV, <=14 MiB, <=10 minutes. Full tracks exceeding that need an authorized excerpt/smaller analysis copy. MP3/FLAC decoding is not implemented in this analysis inbox. |
| Project portability | Existing project schema is untouched. Analysis reports export independent JSON; they are not silently inserted into legacy project backups. |
| Spotify | Validated link-out for playback/reference only; no URL fetch, download, embedding or Spotify audio analysis. |

## Replaceable destinations

`analysis_provider.destinations()` always exposes `local`. It lists Gemini as
unavailable until all three operator settings exist:

- `ROOM_ANALYSIS_GEMINI_KEY`: server-side dedicated API key.
- `ROOM_ANALYSIS_GEMINI_MODEL`: exact supported audio-input model identifier.
- `ROOM_ANALYSIS_GEMINI_PAID_CONFIRMED=true`: operator confirmation that the key's
  Google Cloud project has active billing and the paid-service data policy applies.

Configuration is not live verification. Before enabling it for musicians, test
an authorized fixture against the account/model and assess musical accuracy,
latency, current pricing and provider retention. No credentials are stored in
reports, UI, request payloads or project exports. No SDK/global host changes.

The Gemini adapter uses the documented stateless `generateContent` endpoint with
inline WAV and JSON output. It does not use Google's Files API or cached-content
objects. Request/response sizes are bounded; redirects are refused; timeout is
60 seconds per reference; no retries or automatic destination failover.

Additional **server-registered** adapters can be added in
`app.config['ROOM_ANALYSIS_ADAPTERS']` as an ID mapped to:
`label`, `model`, `detail`, `available` (bool), `external` (bool, defaults true),
and `analyze(audio_bytes, measured, context) -> validated interpretation dict`.
Use `analysis_provider.validate_result` as the contract. Operators are responsible
for adapters' deadlines and disclosed policies; do not register unbounded code.
Browsers cannot supply endpoint URLs, credentials or executable adapter code.

## Privacy, quotas and cleanup

All routes inherit the existing Room account guard, account-bound CSRF/origin
checks, private/no-store responses and same-origin CSP. Ownership is checked on
uploads, runs, decisions, deletes and exports. Analysis storage is a separate
`analysis.sqlite3` next to the Room database; no writes touch saved song assets.
SQLite secure_delete is enabled. Audio appears only in private upload BLOBs and
worker memory; filenames are sanitized. Request parser temporary files follow
Flask/Werkzeug request cleanup. No audio or provider exceptions are logged.

Active analysis copies are deleted on success/failure; muted copies remain in
the inbox. Unassigned uploads expire after 24 hours, reports after 30 days.
Expired copies are purged on analysis API access and through:

```
flask --app app room-analysis-purge
```

For cleanup while the site is idle, schedule that command on the same mounted
storage at least hourly. This build does not configure a live scheduler. Until
then physical removal of expired idle copies occurs on the next analysis access.
Runs abandoned for 30 minutes become interrupted and release copies on cleanup;
never retried. Do not include this temporary analysis DB in long-lived song
backups if enforcing the stated expiry. Storage snapshots/provider monitoring
retention need separate operator review; do not promise global zero retention.

Limits: 12 retained uploads/account; 512 MiB retained audio across service;
2 queued/running jobs across service; 48 active-file analyses/account/day and
200/service/day. These are request-count limits, not a monetary cap. Gemini can
bill each active file. A failed multi-file run may incur charges for files already
sent; the UI says so and requires a fresh explicit upload/run to retry.

Street Banker's implementation does not train on uploads. Google's paid policy
states no use of inputs/outputs for product improvement, but abuse-monitoring
retention may apply; no blanket provider zero-retention promise is made.

Primary documentation reviewed September 8, 2026:
- https://ai.google.dev/gemini-api/docs/audio
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/terms#paid-services

## Verification

Synthetic PCM only; no artist uploads or paid calls. Python boundary tests cover
idle uploads, account isolation, CSRF, consent, unavailable destination, routing,
muted exclusion, invalid output, no retry, retention, numeric measurements,
blending, decisions/revisions and exports. Native JS audio/console regression
suite includes a real Flask+DOM analysis workflow test.

Run:
```
python -m pytest -q tests/test_room_analysis.py tests/test_song_builder_backend.py tests/test_song_builder_demo.py tests/test_song_builder_provider.py tests/test_song_builder_host.py
RACK_TEST_MODULES=/path/to/node_modules node --test tests/song_builder/*.test.mjs tests/song_builder/*.integration.mjs
```

Verification dependencies: Flask/pytest; jsdom and node-web-audio-api. The full
V2 host test requires the full repository (`app.py` and host dependencies), not
just the Room source snapshot. That host check could not execute in this scoped
checkout (missing `app`); it is not a passing result. No live deployment, physical
iPhone validation or paid-provider musical-quality validation is claimed.

The attempted Playwright visual review was blocked by repeated browser-download
timeouts. DOM behavior was exercised against a real local Flask server; rendered
browser layout and physical iPhone behavior remain unverified.
